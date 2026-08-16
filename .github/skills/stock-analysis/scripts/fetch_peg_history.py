# -*- coding: utf-8 -*-
"""
三年 PEG（平滑增速估值）计算
背景：当期 PEG 用最新一期净利同比，若处于周期高点/低基数反弹（如工业富联 +96%、
      长电科技 +42.7%），PEG 会严重失真——看起来便宜其实是"补泡沫/低基数反弹"。
      三年 PEG 用最近3个完整年度的净利 CAGR（复合增速）替代当期增速，平滑周期波动。
公式：三年净利CAGR = (最近第3年净利 / 最早年净利)^(1/年数差) - 1；三年PEG = PE(TTM) / CAGR%
用法: python fetch_peg_history.py [工作区路径] [输出目录] [--codes=601138,002916]
输出: output/三年PEG.json
  {code: {"name":.., "np_2023":210.4(亿), "cagr3":29.5, "peg3":0.95, "note":..}}
⚠️ 近年有亏损（净利<=0）时 CAGR 不可算，peg3=None，note 标注
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

# 自适应工作区路径：技能 scripts/（上4级）或 output/（上1级）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_SCRIPT_DIR) == "scripts" and "skills" in _SCRIPT_DIR:
    BASE = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
else:
    BASE = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
OUT = os.path.join(BASE, "output")
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
if _pos:
    BASE = _pos[0]
    OUT = os.path.join(BASE, "output")

# 目标：持仓 + 自选个股（ETF 无财报会失败自动跳过）
DEFAULT_TARGETS = {
    "600030": "中信证券", "600036": "招商银行", "600941": "中国移动",
    "601872": "招商轮船",
    "002371": "北方华创", "600584": "长电科技", "000977": "浪潮信息",
    "601138": "工业富联", "002916": "深南电路", "002028": "思源电气",
}


def to_float(v):
    """兼容 akshare 返回的数值/字符串（可能带 亿/万 单位）"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if s.endswith("亿"):
        return float(s[:-1]) * 1e8
    if s.endswith("万"):
        return float(s[:-1]) * 1e4
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def get_annual_np(code):
    """同花顺按报告期：取完整年度净利润（正数才保留）"""
    df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    df["报告期"] = pd.to_datetime(df["报告期"])
    annual = df[df["报告期"].dt.month == 12].sort_values("报告期")
    out = {}
    for _, r in annual.iterrows():
        npv = to_float(r.get("净利润"))
        if npv is not None and npv > 0:
            out[r["报告期"].year] = npv
    return out


def load_valuation():
    try:
        with open(os.path.join(OUT, "估值数据.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    targets = DEFAULT_TARGETS
    extra = [a for a in sys.argv[1:] if a.startswith("--codes=")]
    if extra:
        codes = [c.strip() for c in extra[0].split("=", 1)[1].split(",") if c.strip()]
        targets = {c: targets.get(c, c) for c in codes}
    val = load_valuation()
    result = {}
    for code, name in targets.items():
        try:
            years = get_annual_np(code)
            if len(years) < 2:
                print(f"[WARN] {code} {name} 完整年度不足2年，跳过")
                continue
            yrs = sorted(years)
            last3 = yrs[-3:]
            first, last = last3[0], last3[-1]
            npf, npl = years[first], years[last]
            rec = {"name": name, "years": last3}
            for y in last3:
                rec[f"np_{y}"] = round(years[y] / 1e8, 2)  # 亿
            if npf <= 0 or npl <= 0:
                rec["cagr3"] = None
                rec["peg3"] = None
                rec["note"] = "近年有亏损，CAGR不可算"
            else:
                n = last - first
                cagr = (npl / npf) ** (1 / n) - 1
                cagr_pct = round(cagr * 100, 1)
                rec["cagr3"] = cagr_pct
                # 两年CAGR（2024→2025，加速度参考；仅当有第3个年度时）
                if len(years) >= 3:
                    np_p2 = years[last3[-2]]
                    if np_p2 and np_p2 > 0:
                        rec["cagr2"] = round((npl / np_p2 - 1) * 100, 1)
                pe = val.get(code, {}).get("pe_ttm")
                try:
                    pe = float(pe) if pe not in (None, "-") else None
                except (ValueError, TypeError):
                    pe = None
                rec["peg3"] = round(pe / cagr_pct, 2) if (pe and cagr_pct > 0) else None
                if rec["peg3"] is not None:
                    rec["note"] = ("三年PEG<1真便宜" if rec["peg3"] < 1
                                   else "三年PEG合理" if rec["peg3"] < 2 else "三年PEG偏高")
                else:
                    rec["note"] = "CAGR非正或PE缺失"
                # 加速度判断（两年 vs 三年，辅助识别周期高点/增速放缓）
                c2, c3 = rec.get("cagr2"), rec.get("cagr3")
                if c2 is not None and c3 is not None:
                    diff = c2 - c3
                    if diff > 20:
                        rec["note"] += f"；近两年加速({c2:.0f}%>{c3:.0f}%，警惕周期高点)"
                    elif diff < -10:
                        rec["note"] += f"；近两年减速({c2:.0f}%<{c3:.0f}%，增长放缓)"
            result[code] = rec
            print(f"[OK] {code} {name}: 三年CAGR {rec.get('cagr3','-')}% 两年CAGR {rec.get('cagr2','-')}% 三年PEG {rec.get('peg3','-')} {rec.get('note','')}")
            time.sleep(0.3)
        except Exception as e:
            print(f"[WARN] {code} {name} 失败: {str(e)[:90]}")
            time.sleep(0.5)
    with open(os.path.join(OUT, "三年PEG.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"[OK] 已写入 output/三年PEG.json（共 {len(result)} 只）")


if __name__ == "__main__":
    main()
