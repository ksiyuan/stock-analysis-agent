# -*- coding: utf-8 -*-
"""
成本与换手率优化分析
用法: python cost_analysis.py [工作区路径] [输出目录]
依赖: 交易明细_clean.csv / 持仓明细.csv / 已实现盈亏_修正.csv
"""
import os
import numpy as np
import pandas as pd

import common

BASE, OUT = common.parse_cli()

tr = pd.read_csv(os.path.join(OUT, "交易明细_clean.csv"))
tr["成交日期"] = pd.to_datetime(tr["成交日期"])
tr["量"] = tr["成交数量"].abs()
tr["方向"] = tr["操作"].map(lambda x: "买" if x == "证券买入" else ("卖" if x == "证券卖出" else "其他"))

buy = tr[tr["方向"] == "买"]
sell = tr[tr["方向"] == "卖"]
trade = tr[tr["方向"].isin(["买", "卖"])]
n_days = tr["成交日期"].nunique()

lines = []
lines.append("=" * 66)
lines.append("成本与换手率优化分析")
lines.append(f"区间: {tr['成交日期'].min().date()} ~ {tr['成交日期'].max().date()}（{n_days} 个交易日）")
lines.append("=" * 66)

# 1. 费用拆解
fee_cols = ["印花税", "过户费", "经手费", "证管费", "净佣金", "其他杂费"]
fee_sum = trade[fee_cols].sum()
total_fee = fee_sum.sum()
lines.append("\n【1. 交易费用拆解】")
lines.append(f"总费用: {total_fee:,.2f} 元")
for c in fee_cols:
    if fee_sum[c] > 0:
        lines.append(f"  {c:<6}: {fee_sum[c]:>12,.2f} 元 ({fee_sum[c] / total_fee * 100:.1f}%)")

# 2. 佣金费率
buy_amt = buy["成交金额"].sum()
sell_amt = sell["成交金额"].sum()
total_amt = buy_amt + sell_amt
comm_rate = fee_sum["净佣金"] / total_amt * 10000 if total_amt else 0
lines.append(f"\n【2. 佣金费率估算】")
lines.append(f"买入总额: {buy_amt:,.2f} | 卖出总额: {sell_amt:,.2f} | 双边成交: {total_amt:,.2f}")
lines.append(f"净佣金费率估算: {comm_rate:.2f} 个基点（万{comm_rate:.2f}）")
lines.append(f"印花税: 卖出额 x 0.05% 应收 {sell_amt*0.0005:,.2f}（实收 {fee_sum['印花税']:,.2f}）")

# 3. 换手率与频次
lines.append(f"\n【3. 换手率与交易频次】")
lines.append(f"总成交笔数: {len(trade)}（买 {len(buy)} / 卖 {len(sell)}）")
lines.append(f"日均成交笔数: {len(trade)/n_days:.1f} 笔/日")
lines.append(f"单笔平均金额: {total_amt/len(trade):,.0f} 元")
lines.append(f"日均成交额: {total_amt/n_days:,.0f} 元")
pos = pd.read_csv(os.path.join(OUT, "持仓明细.csv"))
mv = pos["市值"].sum()
daily_avg = total_amt / n_days
lines.append(f"持仓市值: {mv:,.2f} 元")
lines.append(f"日均成交额/持仓市值 = {daily_avg/mv:.2f} 倍/日（每个交易日成交额约为持仓市值的 {daily_avg/mv*100:.0f}%）")
lines.append(f"区间总成交额/持仓市值 = {total_amt/mv:.1f} 倍")

# 4. 费用对收益拖累
rl_path = os.path.join(OUT, "已实现盈亏_修正.csv")
rl = pd.read_csv(rl_path) if os.path.exists(rl_path) else pd.read_csv(os.path.join(OUT, "已实现盈亏.csv"))
realized = rl["已实现盈亏"].sum()
lines.append(f"\n【4. 成本对收益的拖累】")
lines.append(f"已实现盈亏: {realized:,.2f} 元")
if realized:
    lines.append(f"总费用: {total_fee:,.2f} 元（占已实现盈亏的 {abs(total_fee/realized)*100:.1f}%）")
lines.append(f"费用相当于每笔交易约 {total_fee/len(trade):.2f} 元的摩擦成本")

# 5. 佣金最高交易
top_comm = trade.nlargest(10, "净佣金")
lines.append(f"\n【5. 佣金最高的 10 笔交易】")
lines.append(f"{'日期':<10}{'代码':<8}{'名称':<12}{'操作':<6}{'金额':>10}{'净佣金':>10}")
for _, r in top_comm.iterrows():
    lines.append(f"{str(r['成交日期'].date()):<10}{str(r['证券代码']):<8}{str(r['证券名称'])[:10]:<12}"
                 f"{'买' if r['方向']=='买' else '卖':<6}{r['成交金额']:>10,.0f}{r['净佣金']:>10,.2f}")

# 6. 亏损股佣金贡献
trade["证券代码"] = trade["证券代码"].astype(str).str.zfill(6)
rl["证券代码"] = rl["证券代码"].astype(str).str.zfill(6)
loss = rl[rl["已实现盈亏"] < -1000].sort_values("已实现盈亏")
lines.append(f"\n【6. 主要亏损股的佣金贡献】")
lines.append(f"{'代码':<8}{'名称':<14}{'已实现盈亏':>12}{'净佣金':>10}{'占比':>8}")
for _, row in loss.iterrows():
    code = row["证券代码"]
    comm = trade[trade["证券代码"] == code]["净佣金"].sum()
    pnl = row["已实现盈亏"]
    ratio = comm / abs(pnl) * 100 if pnl else 0
    lines.append(f"{str(code):<8}{str(row['证券名称'])[:12]:<14}{pnl:>12,.0f}{comm:>10,.0f}{ratio:>7.1f}%")

print("\n".join(lines))
with open(os.path.join(OUT, "成本优化分析.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\n[OK] 成本优化分析.txt 已保存到 {OUT}")
