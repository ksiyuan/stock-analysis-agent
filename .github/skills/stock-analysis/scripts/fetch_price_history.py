# -*- coding: utf-8 -*-
"""
涨幅透支分析：计算成长股"前期股价涨幅是否透支业绩"风险指标
背景：PEG 用当期增速衡量性价比，但若前期股价大涨（涨幅 >> 业绩涨幅），
      PEG 低可能只是"补去年的泡沫"（估值扩张回落中），须警惕。
指标（近1年/近2年）：
  - 涨1年% / 涨2年%：累计涨幅
  - 距1年高% / 距2年高%：距区间高点的回撤（负=回撤）
  - 透支判定：高/中/低 + 说明（结合涨幅 + PE/PB 估值绝对水平）
用法: python fetch_price_history.py [工作区路径] [输出目录] [--codes=601138,002916]
输出: output/涨幅透支.json
  {code: {"涨1年%":..,"涨2年%":..,"距1年高%":..,"距2年高%":..,"透支":"高","透支说明":"..."}}
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

# 目标：持仓 + 自选（成长股重点，但全算）
DEFAULT_TARGETS = {
    "588170": "科创半导体ETF华夏", "600030": "中信证券", "600036": "招商银行",
    "600941": "中国移动", "601872": "招商轮船",
    "002371": "北方华创", "600584": "长电科技", "000977": "浪潮信息",
    "601138": "工业富联", "002916": "深南电路", "002028": "思源电气",
}

# 估值（PE/PB）辅助透支判定
def load_valuation(OUT):
    try:
        with open(os.path.join(OUT, "估值数据.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def sina_symbol(code):
    """新浪代码：sh/sz 前缀 + qfq"""
    if code.startswith(("6", "9", "5")):
        return "sh" + code
    return "sz" + code


def calc(code):
    """拉新浪 qfq 日线（近2年+，确保>=504交易日），计算涨幅与回撤"""
    sym = sina_symbol(code)
    end = time.strftime("%Y%m%d")
    df = ak.stock_zh_a_daily(symbol=sym, start_date="20240101", end_date=end, adjust="qfq")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    if len(df) < 60:
        return None
    c = df["close"]
    out = {}
    if len(df) >= 252:
        out["涨1年%"] = round((c.iloc[-1] / c.iloc[-252] - 1) * 100, 1)
        hi1 = c.iloc[-252:].max()
        out["距1年高%"] = round((c.iloc[-1] / hi1 - 1) * 100, 1)
    if len(df) >= 504:
        out["涨2年%"] = round((c.iloc[-1] / c.iloc[-504] - 1) * 100, 1)
        hi2 = c.iloc[-504:].max()
        out["距2年高%"] = round((c.iloc[-1] / hi2 - 1) * 100, 1)
    # 近1年最高点日期（辅助判断泡沫顶部时间）
    if len(df) >= 252:
        out["1年高日期"] = str(c.iloc[-252:].idxmax().date())
    return out


def judge(code, m, val):
    """透支判定：涨幅大 + 估值绝对水平高 → 透支风险高"""
    pe = pb = None
    v = val.get(code, {})
    try:
        pe = float(v.get("pe_ttm")) if v.get("pe_ttm") not in (None, "-") else None
    except (ValueError, TypeError):
        pe = None
    try:
        pb = float(v.get("pb")) if v.get("pb") not in (None, "-") else None
    except (ValueError, TypeError):
        pb = None
    r1 = m.get("涨1年%")
    r2 = m.get("涨2年%")
    dd = m.get("距1年高%")
    r1 = float(r1) if r1 is not None else 0.0
    r2 = float(r2) if r2 is not None else r1
    dd = float(dd) if dd is not None else 0.0

    lvl, note = "低", ""
    if r1 >= 80 and (pb is not None and pb >= 5 or pe is not None and pe >= 50):
        lvl = "高"
        note = (f"近1年涨{r1:.0f}%且PB{pb if pb else '-'}/PE{pe if pe else '-'}偏高："
                f"前期涨幅可能透支业绩，PEG低或为'补泡沫'")
    elif r1 >= 80:
        lvl = "中"
        note = f"近1年涨{r1:.0f}%涨幅大：若增速放缓PEG将失真"
    elif (pb is not None and pb >= 5) or (pe is not None and pe >= 50):
        lvl = "中"
        note = f"PB{pb if pb else '-'}/PE{pe if pe else '-'}偏高：估值含较多预期"
    elif r2 >= 100 and r1 < 30:
        lvl = "中"
        note = f"近2年涨{r2:.0f}%但近1年仅{r1:.0f}%：前期大涨后动能衰减"
    # 高位回撤提示（风险已部分释放）
    if dd <= -30:
        lvl = "低" if lvl == "高" else lvl
        note += ("" if not note else "；") + f"已从1年高点回调{dd:.0f}%，风险部分释放"
    if not note:
        note = "涨幅与估值匹配，未见明显透支"
    m["透支"] = lvl
    m["透支说明"] = note
    return m


def main():
    targets = DEFAULT_TARGETS
    extra = [a for a in sys.argv[1:] if a.startswith("--codes=")]
    if extra:
        codes = [c.strip() for c in extra[0].split("=", 1)[1].split(",") if c.strip()]
        targets = {c: targets.get(c, c) for c in codes}
    val = load_valuation(OUT)
    result = {}
    for code, name in targets.items():
        try:
            m = calc(code)
            if m is None:
                print(f"[WARN] {code} {name} 数据不足，跳过")
                continue
            m = judge(code, m, val)
            m["name"] = name
            result[code] = m
            print(f"[OK] {code} {name}: 涨1年{m.get('涨1年%','-')}% 距高{m.get('距1年高%','-')}% 透支[{m.get('透支')}]")
            time.sleep(0.3)
        except Exception as e:
            print(f"[WARN] {code} {name} 失败: {str(e)[:100]}")
            time.sleep(0.5)
    with open(os.path.join(OUT, "涨幅透支.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"[OK] 已写入 output/涨幅透支.json（共 {len(result)} 只）")


if __name__ == "__main__":
    main()
