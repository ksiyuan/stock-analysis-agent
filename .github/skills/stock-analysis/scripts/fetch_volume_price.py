# -*- coding: utf-8 -*-
"""
量价分析（用户策略补充）：基于成交量判断量价配合度
从 output/market_data.pkl 读取历史行情（含 volume），计算：
  - 量比5/20：近5日均量 / 前20日均量（>1.2 放量，<0.8 缩量）
  - 放量天数：近5日成交量 > 前20日均量×1.5 的天数
  - 量价信号：放量上涨/放量下跌/缩量上涨/缩量回调/量能平稳
输出: output/量价分析.json
  {code: {"量比5_20":1.3,"放量天数":2,"ret5":4.2,"信号":"放量上涨(健康)","近5日均量":..}}
用法: python fetch_volume_price.py [工作区路径] [输出目录]
"""
import os
import sys
import json
import pickle

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


def load_market():
    pkl = os.path.join(OUT, "market_data.pkl")
    if not os.path.exists(pkl):
        return {}
    with open(pkl, "rb") as f:
        return pickle.load(f)


def judge(ret5, vol_ratio, vol_days):
    """量价信号判定"""
    if ret5 > 1 and vol_ratio > 1.2:
        return "放量上涨(健康)"
    if ret5 < -1 and vol_ratio > 1.2:
        return "放量下跌(警惕)"
    if ret5 > 1 and vol_ratio < 0.8:
        return "缩量上涨(动能弱)"
    if ret5 < -1 and vol_ratio < 0.8:
        return "缩量回调(健康)"
    if vol_ratio > 1.5:
        return "显著放量(关注)"
    return "量能平稳"


def main():
    market = load_market()
    result = {}
    for code, meta in market.items():
        df = meta.get("df")
        if df is None or df.empty or "volume" not in df.columns:
            continue
        df = df.sort_values("date").reset_index(drop=True)
        vol = pd.to_numeric(df["volume"], errors="coerce").dropna()
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(vol) < 25 or len(close) < 25:
            continue
        avg5 = vol.iloc[-5:].mean()
        avg20_prev = vol.iloc[-25:-5].mean()
        vol_ratio = round(float(avg5 / avg20_prev), 2) if avg20_prev > 0 else None
        vol_days = int((vol.iloc[-5:] > avg20_prev * 1.5).sum())
        ret5 = round(float(close.iloc[-1] / close.iloc[-6] - 1) * 100, 1) if len(close) >= 6 else None
        result[code] = {
            "量比5_20": vol_ratio,
            "放量天数": vol_days,
            "近5日均量(万手)": round(float(avg5) / 1e4, 1) if avg5 else None,
            "ret5": ret5,
            "信号": judge(ret5 or 0, vol_ratio or 1, vol_days),
        }
    with open(os.path.join(OUT, "量价分析.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"[OK] 量价分析.json 已写入（{len(result)} 只）")
    for c, v in list(result.items())[:14]:
        print(f"  {c}: 量比{v['量比5_20']} 放量{v['放量天数']}天 5日{v['ret5']}% [{v['信号']}]")


if __name__ == "__main__":
    main()
