# -*- coding: utf-8 -*-
"""
估值数据获取（百度估值：市盈率TTM、市净率）
用法: python fetch_valuation.py [工作区路径] [输出目录] [--codes 600030,600036]
"""
import os
import sys
import time
import json

import akshare as ak

import common

# ⚠️ 过滤 --codes 等参数，避免被当工作区路径（2026-08-17 修复：原 common.parse_cli() 会误把 --codes 当 sys.argv[1]）
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
if _pos:
    BASE, OUT = common.parse_cli(_pos[0])
else:
    BASE, OUT = common.parse_cli()

DEFAULT_CODES = ["600030", "600036", "600941", "601872",
                 "002371", "600584", "000977", "601138", "002916", "002028"]


def get_valuation(symbol, indicator, tries=3):
    for _ in range(tries):
        try:
            df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator=indicator, period="全部")
            df = df.dropna()
            return df.iloc[-1]["value"]
        except Exception:
            time.sleep(1)
    return None


if __name__ == "__main__":
    codes = DEFAULT_CODES
    extra = [a for a in sys.argv if a.startswith("--codes=")]
    if extra:
        codes = extra[0].split("=", 1)[1].split(",")

    result = {}
    for code in codes:
        pe = get_valuation(code, "市盈率(TTM)")
        time.sleep(0.3)
        pb = get_valuation(code, "市净率")
        time.sleep(0.3)
        result[code] = {"name": code, "pe_ttm": pe, "pb": pb}
        print(f"[OK] {code} PE(TTM)={pe} PB={pb}")

    with open(os.path.join(OUT, "估值数据.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"[OK] 估值数据.json 已保存到 {OUT}")
