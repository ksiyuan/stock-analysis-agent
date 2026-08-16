# -*- coding: utf-8 -*-
"""
行情数据获取：个股 + ETF
用法: python fetch_market.py [工作区路径] [输出目录]
说明: 东方财富优先、新浪回退；ETF 用新浪 fund_etf_hist_sina
"""
import os
import time

import common

BASE, OUT = common.parse_cli()
common.setup_paths(BASE, OUT)

# (代码, 名称, 类型)  type: stock / etf
DEFAULT_TARGETS = [
    # 持仓
    ("588170", "科创半导体ETF华夏", "etf"),
    ("600030", "中信证券", "stock"),
    ("600036", "招商银行", "stock"),
    ("600941", "中国移动", "stock"),
    ("601872", "招商轮船", "stock"),
]

START = "20260401"
END = time.strftime("%Y%m%d")


def parse_targets(arg):
    """支持 --targets 600519,600036:stock,588170:etf 逗号分隔"""
    if not arg:
        return DEFAULT_TARGETS
    out = []
    for item in arg.split(","):
        item = item.strip()
        if ":" in item:
            code, typ = item.split(":")
        else:
            code, typ = item, ("etf" if item.startswith(("1", "5")) else "stock")
        out.append((code, "", typ))
    return out


if __name__ == "__main__":
    import sys
    targets = DEFAULT_TARGETS
    extra = [a for a in sys.argv if a.startswith("--targets=")]
    if extra:
        targets = parse_targets(extra[0].split("=", 1)[1])

    data = common.fetch_market(targets, START, END, out_pkl=os.path.join(OUT, "market_data.pkl"))
    print(f"[OK] 共获取 {len(data)} 只标的行情")
