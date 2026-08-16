# -*- coding: utf-8 -*-
"""
获取美股/港股行情，并做「中美联动补涨」对比（用户策略第6条）
用法:
  python fetch_global_market.py [工作区路径] [输出目录]
  python fetch_global_market.py --pairs "AMAT:002371:应用材料:北方华创"  # 指定对比对
输出:
  market_global.pkl  (原始行情)
  中美联动对比.csv    (美/中各自区间涨幅对比)
"""
import os
import sys
import time
import pickle
import numpy as np
import pandas as pd

import common

BASE, OUT = common.parse_cli()

# 默认中美联动对比对: (美股代码, A股代码, 美股名, A股名)
# 【重要 - 用户实盘观察】美股与A股并非普遍强关联，过分强调会顾此失彼。
# 经观察真正强关联的只有以下两对：
#   应用材料(AMAT) -> 北方华创 / 科创半导体(半导体设备/材料映射)
#   Frontline(FRO) -> 招商轮船(油运映射)
# 其余（如 NVDA->浪潮信息、TSM->兆易创新）相关性弱，不作为默认对比。
DEFAULT_PAIRS = [
    ("AMAT", "002371", "应用材料", "北方华创"),
    ("AMAT", "588170", "应用材料", "科创半导体ETF"),
    ("FRO", "601872", "Frontline", "招商轮船"),
]

START = "20260401"
END = time.strftime("%Y%m%d")


def load_global_market():
    pkl = os.path.join(OUT, "market_global.pkl")
    if os.path.exists(pkl):
        with open(pkl, "rb") as f:
            return pickle.load(f)
    return {}


def get_us(sym, tries=3):
    for _ in range(tries):
        df, _ = common.get_us_stock(sym, START, END)
        if df is not None and len(df) > 0:
            return df
        time.sleep(2)
    return None


def get_a(sym, tries=3):
    for _ in range(tries):
        fn = common.get_etf if sym[0] in ("1", "5") else common.get_stock
        df, _ = fn(sym, START, END)
        if df is not None and len(df) > 0:
            return df
        time.sleep(2)
    return None


def calc_ret(df, window=20):
    if df is None or len(df) < 2:
        return np.nan, np.nan
    close = df["close"]
    ret5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) > 5 else np.nan
    ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 20 else np.nan
    return ret5, ret20


def calc_positions(df, window=60):
    """区间位置（最高/最低点相对位置）
    返回: (pos60 区间位置%, from_high 距60日高点%, from_low 距60日低点%)
    - pos60 = (现价-60日低)/(60日高-60日低)*100；0%=区间最低，100%=区间最高
    - from_high = (现价/60日高-1)*100（负=已回落，越接近0越贴近高点）
    - from_low = (现价/60日低-1)*100（正=相对低点涨幅）
    """
    if df is None or len(df) < 2:
        return np.nan, np.nan, np.nan
    close = df["close"]
    win = min(window, len(close))
    hi = close.iloc[-win:].max()
    lo = close.iloc[-win:].min()
    c = close.iloc[-1]
    pos = (c - lo) / (hi - lo) * 100 if hi > lo else 50.0
    from_high = (c / hi - 1) * 100
    from_low = (c / lo - 1) * 100
    return pos, from_high, from_low


def load_financials():
    """读取财报分析.csv（若已生成），返回 {代码: 净利同比%}
    注意: 美股代码(NVDA等)不补零，A股代码(002371)需 zfill(6)"""
    path = os.path.join(OUT, "财报分析.csv")
    if not os.path.exists(path):
        return {}, {}
    df = pd.read_csv(path)
    a_map = {}
    us_map = {}
    for _, r in df.iterrows():
        raw = str(r.get("代码", "")).strip()
        code = raw.zfill(6) if raw.isdigit() else raw  # 仅数字代码补零
        np_yoy = r.get("净利同比%")
        try:
            np_yoy = float(np_yoy) if pd.notna(np_yoy) else None
        except (TypeError, ValueError):
            np_yoy = None
        if r.get("市场") == "美股":
            us_map[code] = np_yoy
        else:
            a_map[code] = np_yoy
    return a_map, us_map


def signal(row):
    """综合行情+区间位置+财报给出信号（用户策略第6条）。
    逻辑:
      - 美股净利高增(>20) + A股净利落后 → 补涨预期
      - 美股行情强 + A股60日位置低(<40) → 补涨空间大
      - 美股行情强 + A股60日位置高(>70) → A股已高位，追涨谨慎
      - 美股财报大幅下滑(<0) → A股映射风险
      - A股60日位置极端(>90) → 高位追涨风险提示
    """
    us20 = row.get("美20日%")
    a20 = row.get("A20日%")
    gap = row.get("补涨缺口(美-A)")
    us_ny = row.get("美股净利同比%")
    a_ny = row.get("A股净利同比%")
    a_pos = row.get("A60日位%")
    us_pos = row.get("美60日位%")
    msgs = []

    def num(x):
        try:
            return float(x) if pd.notna(x) else None
        except (TypeError, ValueError):
            return None

    us20, a20, gap, us_ny, a_ny = (num(x) for x in (us20, a20, gap, us_ny, a_ny))
    a_pos, us_pos = num(a_pos), num(us_pos)

    # 财报维度
    if us_ny is not None and us_ny > 20:
        msgs.append(f"美股财报净利+{us_ny:.0f}%")
    elif us_ny is not None and us_ny < 0:
        msgs.append(f"美股财报净利{us_ny:.0f}%下滑→风险")

    # 行情+位置维度（核心补涨逻辑）
    if us20 is not None and us20 > 0 and gap is not None and gap > 5:
        if a_pos is not None and a_pos < 40:
            msgs.append(f"A股60日位置{a_pos:.0f}%低位+美股领先→补涨空间大")
        elif a_pos is not None and a_pos > 70:
            msgs.append(f"A股60日位置{a_pos:.0f}%已高位→追涨谨慎")
        else:
            msgs.append("美股走势领先A股")

    # A股区间位置极端提示（用户策略1：最高/最低点位置）
    if a_pos is not None and a_pos > 90:
        msgs.append(f"A股60日位置{a_pos:.0f}%接近高点→追高风险")
    elif a_pos is not None and a_pos < 15:
        msgs.append(f"A股60日位置{a_pos:.0f}%接近低点→关注企稳")

    # 综合：美股财报好 + A股业绩落后 → 补涨预期
    if us_ny is not None and us_ny > 20:
        if a_ny is not None and a_ny < us_ny - 10:
            msgs.append("A股业绩落后→补涨预期")
        if gap is not None and gap > 5 and a_pos is not None and a_pos < 40:
            msgs.append("行情+业绩+位置三重落后→补涨信号强")

    if not msgs:
        return ""
    return "；".join(msgs)


if __name__ == "__main__":
    pairs = DEFAULT_PAIRS
    extra = [a for a in sys.argv if a.startswith("--pairs=")]
    if extra:
        raw = extra[0].split("=", 1)[1]
        parts = raw.split(":")
        # 格式: us_code:a_code:us_name:a_name
        if len(parts) == 4:
            pairs = [(parts[0], parts[1], parts[2], parts[3])]

    global_data = load_global_market()
    a_fin, us_fin = load_financials()
    rows = []

    for us_code, a_code, us_name, a_name in pairs:
        print(f"--- {us_name}({us_code}) vs {a_name}({a_code}) ---")
        if us_code not in global_data:
            us_df = get_us(us_code)
            if us_df is not None and len(us_df) > 0:
                global_data[us_code] = {"name": us_name, "type": "us", "df": us_df}
                print(f"  [OK] 美股 {us_code} {us_name}")
            else:
                print(f"  [FAIL] 美股 {us_code}")
        a_df = get_a(a_code)
        us_df = global_data[us_code]["df"] if us_code in global_data else None

        us5, us20 = calc_ret(us_df)
        a5, a20 = calc_ret(a_df)
        # 区间位置（最高/最低点相对位置，窗口60日）
        us_pos, us_from_high, us_from_low = calc_positions(us_df)
        a_pos, a_from_high, a_from_low = calc_positions(a_df)
        # 补涨缺口 = 美股20日涨幅 - A股20日涨幅（>0 表示美股强A股弱，存在补涨预期）
        gap = (us20 - a20) if (us20 is not None and a20 is not None) else np.nan

        def _r(v, nd=2):
            return round(float(v), nd) if v == v else ""

        row = {
            "美股": us_name, "美股代码": us_code, "美5日%": _r(us5),
            "美20日%": _r(us20), "美60日位%": _r(us_pos, 0),
            "美距60日高%": _r(us_from_high, 1), "美距60日低%": _r(us_from_low, 1),
            "A股": a_name, "A股代码": a_code, "A5日%": _r(a5),
            "A20日%": _r(a20), "A60日位%": _r(a_pos, 0),
            "A距60日高%": _r(a_from_high, 1), "A距60日低%": _r(a_from_low, 1),
            "补涨缺口(美-A)": _r(gap),
            "美股净利同比%": us_fin.get(us_code, ""),
            "A股净利同比%": a_fin.get(a_code, ""),
        }
        row["信号"] = signal(row)
        rows.append(row)
        time.sleep(0.3)

    # 保存全球行情
    with open(os.path.join(OUT, "market_global.pkl"), "wb") as f:
        pickle.dump(global_data, f)

    df_out = pd.DataFrame(rows)
    if len(df_out):
        df_out.to_csv(os.path.join(OUT, "中美联动对比.csv"), index=False, encoding="utf-8-sig")
        print()
        print("=== 中美联动对比（行情+财报综合信号）===")
        with pd.option_context("display.max_columns", None, "display.width", 300):
            print(df_out.to_string(index=False))
        print()
        # 提示补涨机会
        for _, r in df_out.iterrows():
            sig = str(r.get("信号", ""))
            if sig and "补涨" in sig:
                print(f"[提示] {r['A股']} 补涨信号: {sig}")
            elif sig and "风险" in sig:
                print(f"[风险] {r['A股']} 映射美股财报下滑: {sig}")
    print(f"\n[OK] 中美联动对比.csv 已保存到 {OUT}")
