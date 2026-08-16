# -*- coding: utf-8 -*-
"""
亏损股买卖点复盘
用法: python loss_review.py [工作区路径] [输出目录]
依赖: 交易明细_clean.csv / 已实现盈亏_修正.csv（由 account_analysis.py 生成）
"""
import os
import numpy as np
import pandas as pd

import common

BASE, OUT = common.parse_cli()

tr = pd.read_csv(os.path.join(OUT, "交易明细_clean.csv"))
tr["成交日期"] = pd.to_datetime(tr["成交日期"])

# 已实现盈亏（修正版，红股0成本）
rl_path = os.path.join(OUT, "已实现盈亏_修正.csv")
if os.path.exists(rl_path):
    rl = pd.read_csv(rl_path)
else:
    rl = pd.read_csv(os.path.join(OUT, "已实现盈亏.csv"))
rl["证券代码"] = rl["证券代码"].astype(str).str.zfill(6)
rl = rl.set_index("证券代码")

# 资金流口径总盈亏
pnl_map = {}
pnl_path = os.path.join(OUT, "总盈亏_资金口径.csv")
if os.path.exists(pnl_path):
    pnl_df = pd.read_csv(pnl_path)
    pnl_df["证券代码"] = pnl_df["证券代码"].astype(str).str.zfill(6)
    pnl_map = dict(zip(pnl_df["证券代码"], pnl_df["总盈亏"]))

loss_stocks = rl[rl["已实现盈亏"] < -500].sort_values("已实现盈亏")

print("=" * 80)
print("亏损股买卖点复盘（按已实现亏损排序）")
print("=" * 80)

report_lines = []
for code, row in loss_stocks.iterrows():
    name = row["证券名称"]
    pnl = row["已实现盈亏"]
    sub = tr[tr["证券代码"] == code].sort_values(["成交日期", "成交时间"])
    if sub.empty:
        continue
    buys = sub[sub["方向"] == "买"]
    sells = sub[sub["方向"] == "卖"]
    buy_wavg = (buys["成交金额"].sum() / buys["量"].sum()) if len(buys) else 0
    sell_wavg = (sells["成交金额"].sum() / sells["量"].sum()) if len(sells) else 0
    n_buy, n_sell = len(buys), len(sells)
    buy_dates = buys["成交日期"].dt.strftime("%m-%d").tolist()
    sell_dates = sells["成交日期"].dt.strftime("%m-%d").tolist()

    hold_days = []
    for _, srow in sells.iterrows():
        prev_buys = buys[buys["成交日期"] <= srow["成交日期"]]
        if not prev_buys.empty:
            hold_days.append((srow["成交日期"] - prev_buys["成交日期"].iloc[0]).days)
    avg_hold = np.mean(hold_days) if hold_days else np.nan

    lines = []
    fund_pnl = pnl_map.get(code, None)
    pnl_str = f"{pnl:,.2f}"
    if fund_pnl is not None and abs(fund_pnl - pnl) > 100:
        pnl_str = f"{pnl:,.2f}（资金流口径 {fund_pnl:,.2f}）"
    lines.append(f"\n### {code} {name}  已实现盈亏: {pnl_str}")
    lines.append(f"- 买入 {n_buy} 笔, 加权均价 {buy_wavg:.3f}; 卖出 {n_sell} 笔, 加权均价 {sell_wavg:.3f}")
    lines.append(f"- 买卖价差: {(sell_wavg - buy_wavg) / buy_wavg * 100:+.2f}%" if buy_wavg else "- 价差数据不足")
    lines.append(f"- 平均持有约 {avg_hold:.1f} 天" if not np.isnan(avg_hold) else "- 持有期数据不足")
    lines.append(f"- 买入日期: {','.join(buy_dates[:10])}{'...' if len(buy_dates) > 10 else ''}")
    lines.append(f"- 卖出日期: {','.join(sell_dates[:10])}{'...' if len(sell_dates) > 10 else ''}")
    if buys["量"].sum() > 0:
        lines.append(f"- 累计买入 {buys['量'].sum():,.0f} 股 / 卖出 {sells['量'].sum():,.0f} 股")
    print("\n".join(lines))
    report_lines.extend(lines)

with open(os.path.join(OUT, "亏损股复盘.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))
print(f"\n[OK] 亏损股复盘.txt 已保存（共 {len(loss_stocks)} 只）")
