# -*- coding: utf-8 -*-
"""
财报分析增强版（stock-analysis 技能配套，2026-08-15 由 financial-analysis 并入）
功能:
  1. A股: 业绩报表(最近1-2期) + 资产负债表(资产负债率) + 现金流量表(经营现金流)
  2. 美股: stock_financial_us_analysis_indicator_em 财务指标(营收/净利/毛利率/ROE/负债率)
  3. PEG = PE(TTM) / 净利同比
用法:
  python fetch_financials.py [工作区路径] [输出目录] [--codes 600036,600030]
  python fetch_financials.py --codes NVDA:us:英伟达   # 美股:代码:us:名称
输出: output/财报分析.csv / 美股财报.csv
"""
import os
import sys
import time
import json
import akshare as ak
import pandas as pd

# ---------- 控制台 UTF-8 ----------
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------- 路径 ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
OUT = os.path.join(BASE, "output")
# 仅接受不带 -- 的位置参数作为工作区路径（--codes 等不能误当路径）
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
if _pos:
    BASE = _pos[0]
    OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# 默认 A 股持仓个股（ETF 无财报）
DEFAULT_CODES = ["600030", "600036", "600941", "601872"]

# 最近两期报告期（用户要求最近一两次）
REPORT_DATES = ["20260630", "20260331"]
REPORT_LABELS = {"20260630": "2026半年报", "20260331": "2026一季报"}


def _retry(fn, tries=3, delay=2):
    for _ in range(tries):
        try:
            return fn()
        except Exception:
            time.sleep(delay)
    return None


def get_report(date):
    return _retry(lambda: ak.stock_yjbb_em(date=date))


def get_balance(date):
    return _retry(lambda: ak.stock_zcfz_em(date=date))


def get_cashflow(date):
    return _retry(lambda: ak.stock_xjll_em(date=date))


def get_us_financial(symbol):
    return _retry(lambda: ak.stock_financial_us_analysis_indicator_em(symbol=symbol))


def get_forecast(date):
    """业绩预告（东财 stock_yjyg_em）：含归母净利润预告"""
    return _retry(lambda: ak.stock_yjyg_em(date=date))


def parse_forecast(forecast, code):
    """解析业绩预告：取'归母净利润'预测指标的业绩变动幅度中值（未来增速）"""
    import re
    if forecast is None or forecast.empty:
        return None
    sub = forecast[forecast["股票代码"].astype(str).str.zfill(6) == code]
    if sub.empty:
        return None
    hit = sub[sub["预测指标"].astype(str).str.contains("归属于", na=False)]
    if hit.empty:
        hit = sub[sub["预测指标"].astype(str).str.contains("净利润", na=False)]
    if hit.empty:
        return None
    s = str(hit.iloc[0].get("业绩变动幅度", "")).replace(" ", "").replace("，", "")
    nums = re.findall(r"[-+]?\d+\.?\d*", s)
    if not nums:
        return None
    nums = [float(x) for x in nums]
    return round(sum(nums) / len(nums), 2) if nums else None


def load_valuation():
    val_path = os.path.join(OUT, "估值数据.json")
    if os.path.exists(val_path):
        with open(val_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def analyze_a_stock(code, reports, balances, cashflows, val, forecast=None):
    """A股财报：业绩 + 负债率 + 经营现金流 + PEG（优先业绩预告中值）"""
    rec = {"code": code, "market": "A股"}
    latest = None
    for d in REPORT_DATES:
        df = reports.get(d)
        if df is None:
            continue
        # ⚠️ 东财股票代码可能去前导零（002916->2916），必须 zfill 后匹配
        hit = df[df["股票代码"].astype(str).str.zfill(6) == code]
        if hit.empty:
            continue
        r = hit.iloc[0]
        rec["name"] = r["股票简称"]
        if latest is None:
            # 只保留最新匹配报告期（REPORT_DATES 从新到旧，半年报优先）
            # 修复 2026-08-17：原逻辑 period_latest/latest 被最后匹配期覆盖（601138 中报显示成一季报）
            rec["period_latest"] = d
            latest = d
        rec[f"rev_{d}"] = r.get("营业总收入-营业总收入")
        rec[f"rev_yoy_{d}"] = r.get("营业总收入-同比增长")
        rec[f"np_{d}"] = r.get("净利润-净利润")
        rec[f"np_yoy_{d}"] = r.get("净利润-同比增长")
        rec[f"roe_{d}"] = r.get("净资产收益率")
        rec[f"gross_{d}"] = r.get("销售毛利率")
        rec[f"eps_{d}"] = r.get("每股收益")
    if not rec.get("name"):
        return None

    # 资产负债率（最新报告期）
    for d in REPORT_DATES:
        bdf = balances.get(d)
        if bdf is None:
            continue
        bdf = bdf.copy()
        bdf["股票代码"] = bdf["股票代码"].astype(str).str.zfill(6)
        hit = bdf[bdf["股票代码"] == code]
        if hit.empty:
            continue
        r = hit.iloc[0]
        rec[f"debt_{d}"] = r.get("资产负债率")
        break

    # 经营现金流（最新报告期）
    for d in REPORT_DATES:
        cdf = cashflows.get(d)
        if cdf is None:
            continue
        cdf = cdf.copy()
        cdf["股票代码"] = cdf["股票代码"].astype(str).str.zfill(6)
        hit = cdf[cdf["股票代码"] == code]
        if hit.empty:
            continue
        r = hit.iloc[0]
        rec[f"ocf_{d}"] = r.get("经营性现金流-现金流量净额")
        break

    # PEG（用户定义：估值/未来增速；优先业绩预告中值=未来增速，其次当期净利同比）
    np_yoy = rec.get(f"np_yoy_{latest}")
    pe = val.get(code, {}).get("pe_ttm")
    rec["pe_ttm"] = pe
    fc = parse_forecast(forecast, code) if forecast is not None else None
    rec["forecast_np_mid%"] = fc
    growth = fc if fc is not None else np_yoy
    rec["peg"] = round(pe / growth, 2) if (pe and growth and growth > 0) else None
    rec["peg_src"] = "预告" if fc is not None else "当期"
    return rec


def analyze_us_stock(code, name):
    """美股财报：营收/净利/毛利率/ROE/负债率（最新年报）"""
    df = get_us_financial(code)
    if df is None or df.empty:
        return None
    r = df.iloc[0]  # 最新一期
    return {
        "code": code, "name": r.get("SECURITY_NAME_ABBR") or name, "market": "美股",
        "period_latest": f"{r.get('DATE_TYPE','')} {r.get('REPORT_DATA_TYPE','')}",
        "rev": r.get("OPERATE_INCOME"), "rev_yoy": r.get("OPERATE_INCOME_YOY"),
        "np": r.get("PARENT_HOLDER_NETPROFIT"), "np_yoy": r.get("PARENT_HOLDER_NETPROFIT_YOY"),
        "gross": r.get("GROSS_PROFIT_RATIO"), "roe": r.get("ROE_AVG"),
        "eps": r.get("BASIC_EPS"), "debt": r.get("DEBT_ASSET_RATIO"),
        "np_ratio": r.get("NET_PROFIT_RATIO"), "currency": r.get("CURRENCY_ABBR"),
    }


if __name__ == "__main__":
    codes = DEFAULT_CODES
    us_codes = []
    # 支持 --codes=xxx 和 --codes xxx 两种格式
    raw_codes = None
    for i, a in enumerate(sys.argv):
        if a.startswith("--codes="):
            raw_codes = a.split("=", 1)[1]
        elif a == "--codes" and i + 1 < len(sys.argv):
            raw_codes = sys.argv[i + 1]
    if raw_codes:
        codes = []
        for item in raw_codes.split(","):
            parts = item.strip().split(":")
            # 格式: 代码:us:名称（美股） 或 代码（A股）
            if len(parts) == 3 and parts[1] == "us":
                us_codes.append((parts[0], parts[2]))
            else:
                codes.append(parts[0])

    val = load_valuation()

    # A股报表 + 业绩预告（2026半年报，用户要求：预告中值作估值参考）
    reports, balances, cashflows = {}, {}, {}
    for d in REPORT_DATES:
        reports[d] = get_report(d)
        balances[d] = get_balance(d)
        cashflows[d] = get_cashflow(d)
        print(f"[OK] {REPORT_LABELS[d]} 业绩/负债/现金流已获取")
    forecast = get_forecast("20260630")
    print(f"[OK] 业绩预告已获取（{len(forecast) if forecast is not None else 0} 条）")

    a_rows = []
    for code in codes:
        rec = analyze_a_stock(code, reports, balances, cashflows, val, forecast)
        if rec:
            a_rows.append(rec)
            print(f"[OK] A股 {code} {rec['name']} PEG={rec['peg']}({rec.get('peg_src','当期')})")

    # 美股
    us_rows = []
    for code, name in us_codes:
        rec = analyze_us_stock(code, name)
        if rec:
            us_rows.append(rec)
            print(f"[OK] 美股 {code} {rec['name']}")

    # 汇总输出
    all_rows = []
    for r in a_rows:
        latest = r.get("period_latest", "")
        all_rows.append({
            "市场": "A股", "代码": r["code"], "名称": r.get("name", ""),
            "PE(TTM)": r.get("pe_ttm"), "PEG": r.get("peg"),
            "最新期": REPORT_LABELS.get(latest, latest),
            "营收(亿)": round(r.get(f"rev_{latest}", 0) / 1e8, 1) if r.get(f"rev_{latest}") else "",
            "营收同比%": round(r.get(f"rev_yoy_{latest}", 0), 2) if r.get(f"rev_yoy_{latest}") is not None else "",
            "净利(亿)": round(r.get(f"np_{latest}", 0) / 1e8, 2) if r.get(f"np_{latest}") else "",
            "净利同比%": round(r.get(f"np_yoy_{latest}", 0), 2) if r.get(f"np_yoy_{latest}") is not None else "",
            "预告净利中值%": r.get("forecast_np_mid%"),
            "PEG增速源": r.get("peg_src", ""),
            "毛利率%": round(r.get(f"gross_{latest}", 0), 2) if r.get(f"gross_{latest}") is not None else "",
            "ROE%": round(r.get(f"roe_{latest}", 0), 2) if r.get(f"roe_{latest}") is not None else "",
            "资产负债率%": round(r.get(f"debt_{latest}", 0), 2) if r.get(f"debt_{latest}") is not None else "",
            "经营现金流(亿)": round(r.get(f"ocf_{latest}", 0) / 1e8, 1) if r.get(f"ocf_{latest}") else "",
        })
    for r in us_rows:
        all_rows.append({
            "市场": "美股", "代码": r["code"], "名称": r.get("name", ""),
            "PE(TTM)": "", "PEG": "",
            "最新期": r.get("period_latest", ""),
            "营收(亿)": round(r.get("rev", 0) / 1e8, 1) if r.get("rev") else "",
            "营收同比%": round(r.get("rev_yoy", 0), 2) if r.get("rev_yoy") is not None else "",
            "净利(亿)": round(r.get("np", 0) / 1e8, 2) if r.get("np") else "",
            "净利同比%": round(r.get("np_yoy", 0), 2) if r.get("np_yoy") is not None else "",
            "毛利率%": round(r.get("gross", 0), 2) if r.get("gross") is not None else "",
            "ROE%": round(r.get("roe", 0), 2) if r.get("roe") is not None else "",
            "资产负债率%": round(r.get("debt", 0), 2) if r.get("debt") is not None else "",
            "经营现金流(亿)": "",
        })

    df_sum = pd.DataFrame(all_rows)
    if len(df_sum):
        # 合并已有 CSV（东财接口不稳定时多次运行累积；同代码本次结果覆盖旧的）
        csv_path = os.path.join(OUT, "财报分析.csv")
        if os.path.exists(csv_path):
            try:
                old = pd.read_csv(csv_path, encoding="utf-8-sig")
                old["代码"] = old["代码"].astype(str).str.zfill(6)
                new_codes = set(df_sum["代码"].astype(str).str.zfill(6))
                merged = old[~old["代码"].isin(new_codes)]
                df_sum = pd.concat([merged, df_sum], ignore_index=True)
            except Exception:
                pass
        df_sum.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print()
        print("=== 财报分析（最近1-2期，含财务健康）===")
        with pd.option_context("display.max_columns", None, "display.width", 300):
            print(df_sum.to_string(index=False))
        print()
        for _, s in df_sum.iterrows():
            np_yoy = s.get("净利同比%")
            peg = s.get("PEG")
            debt = s.get("资产负债率%")
            msgs = []
            try:
                if pd.notna(np_yoy) and np_yoy > 20:
                    msgs.append(f"净利高增 {np_yoy:.0f}%")
                elif pd.notna(np_yoy) and np_yoy < 0:
                    msgs.append(f"净利下滑 {np_yoy:.0f}%")
            except (TypeError, ValueError):
                pass
            try:
                if pd.notna(peg) and peg < 1:
                    msgs.append(f"PEG={peg} 低估成长")
            except (TypeError, ValueError):
                pass
            try:
                if pd.notna(debt) and debt > 70:
                    msgs.append(f"负债率偏高 {debt:.0f}%")
                elif pd.notna(debt) and debt < 30:
                    msgs.append(f"负债率低 {debt:.0f}% 稳健")
            except (TypeError, ValueError):
                pass
            if msgs:
                print(f"[提示] {s['市场']} {s['代码']} {s['名称']}: {'; '.join(msgs)}")
        print(f"\n[OK] 财报分析.csv 已保存到 {OUT}")
