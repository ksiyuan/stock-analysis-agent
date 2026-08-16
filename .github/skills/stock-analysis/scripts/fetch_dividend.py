# -*- coding: utf-8 -*-
"""
红利股股息数据获取
- 对持仓/自选/重点标的获取：股息率、TTM每股分红、连续分红年数、最近分红
- 计算股息率 = 最近365天已实施每股分红 / 现价
输出: output/股息数据.json
"""
import os
import sys
import time
import json
import akshare as ak
import pandas as pd

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = r"c:\Users\kongs\Documents\股票"
OUT = os.path.join(BASE, "output")

# 目标：持仓 + 自选 + 高股息候选
TARGETS = {
    "600030": "中信证券", "600036": "招商银行", "600941": "中国移动",
    "601872": "招商轮船", "588170": "科创半导体ETF华夏",
    "002371": "北方华创", "600584": "长电科技", "000977": "浪潮信息",
    "601138": "工业富联", "002916": "深南电路", "002028": "思源电气",
    "601166": "兴业银行", "600028": "中国石化", "601088": "中国神华",
    "600900": "长江电力", "601398": "工商银行", "600519": "贵州茅台",
    "000651": "格力电器", "601288": "农业银行",
}

# 现价（从技术指标汇总读取）
tech_path = os.path.join(OUT, "技术指标汇总.csv")
price_map = {}
if os.path.exists(tech_path):
    tech = pd.read_csv(tech_path)
    tech["code"] = tech["code"].astype(str).str.zfill(6)
    price_map = dict(zip(tech["code"], tech["close"]))
# 补充不在技术指标里的
for code in TARGETS:
    if code not in price_map:
        price_map[code] = None


def _retry(fn, tries=3, delay=2):
    for _ in range(tries):
        try:
            df = fn()
            if df is not None and len(df) > 0:
                return df
        except Exception:
            time.sleep(delay)
    return None


def get_dividends(code):
    return _retry(lambda: ak.stock_history_dividend_detail(symbol=code, indicator="分红"))


def calc_div(code):
    """计算股息数据：
    - TTM每股分红：最近365天内已实施(进度=实施)的分红合计（派息字段为每10股派X元 → /10）
    - 连续分红年数：从最近一次实施往前数，每年至少一次实施
    """
    df = get_dividends(code)
    if df is None:
        return None
    # 列名：公告日期/送股/转增/派息/进度/除权除息日
    cols = [c.strip() for c in df.columns]
    df.columns = cols
    div_col = "派息"
    prog_col = "进度"
    date_col = "公告日期"
    ex_col = "除权除息日" if "除权除息日" in cols else date_col

    df[div_col] = pd.to_numeric(df[div_col], errors="coerce")
    df[ex_col] = pd.to_datetime(df[ex_col], errors="coerce")
    # 已实施的分红
    impl = df[df[prog_col].astype(str).str.contains("实施", na=False)].dropna(subset=[ex_col])
    if impl.empty:
        return None
    impl = impl.sort_values(ex_col, ascending=False)

    now = pd.Timestamp.now()
    ttm_start = now - pd.Timedelta(days=365)
    # TTM 口径（对齐同花顺）：最近两笔已实施分红合计 = 最近一个完整财年的中期+末期
    # （避免滚动365天把跨财年的年度分红也算进去，如中信 0.98 含 2024 财年 0.28，应为 0.70）
    top2 = impl.head(2)
    div_ttm_per10 = top2[div_col].sum()
    if len(top2) >= 2:
        gap_days = (top2.iloc[0][ex_col] - top2.iloc[1][ex_col]).days
        if gap_days > 400:
            # 两笔相隔过久，说明中间缺分红，回退为最近12个月已实施合计
            ttm = impl[impl[ex_col] >= ttm_start]
            div_ttm_per10 = ttm[div_col].sum()
    div_ttm = div_ttm_per10 / 10.0  # 每股

    # 连续分红年数（从最近实施往前，每自然年至少一次实施）
    years = set()
    for _, r in impl.iterrows():
        years.add(r[ex_col].year)
    years = sorted(years, reverse=True)
    cont = 0
    last = years[0] if years else None
    for y in years:
        if last is not None and last - y <= 1:  # 连续或最多隔1年（允许披露错位）
            cont += 1
            last = y
        else:
            break

    price = price_map.get(code)
    div_yield = div_ttm / price * 100 if (div_ttm and price) else None

    return {
        "名称": TARGETS.get(code, code),
        "现价": round(price, 2) if price else None,
        "TTM每股分红": round(div_ttm, 4) if div_ttm else None,
        "股息率%": round(div_yield, 2) if div_yield is not None else None,
        "连续分红年数": cont,
        "最近分红日期": str(impl.iloc[0][ex_col].date()) if not impl.empty else None,
        "分红记录数": len(impl),
    }


result = {}
for code, name in TARGETS.items():
    try:
        r = calc_div(code)
        if r:
            result[code] = r
            print(f"[OK] {code} {name}: 股息率={r['股息率%']}% TTM分红={r['TTM每股分红']} 连续{cont_years}年" if (cont_years := r['连续分红年数']) else f"[OK] {code} {name}: 股息率={r['股息率%']}%")
        else:
            print(f"[--] {code} {name}: 无分红数据")
    except Exception as e:
        print(f"[ERR] {code} {name}: {str(e)[:80]}")
    time.sleep(0.5)

with open(os.path.join(OUT, "股息数据.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print(f"\n[OK] 股息数据.json 已保存（{len(result)} 只）")
