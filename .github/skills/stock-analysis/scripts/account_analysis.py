# -*- coding: utf-8 -*-
"""
账户分析主脚本（股票分析技能配套）
流程：解析同花顺导出 -> 完整性检查 -> 含费已实现盈亏 + 资金流口径 -> 报告
用法：
  python account_analysis.py [工作区路径] [输出目录]          # 自动找 持仓.xls/交易记录.xls
  python account_analysis.py <持仓.xls> <交易记录.xls> [输出目录]  # 直接指定文件
"""
import os
import sys
import pandas as pd

import common

# ---------- 参数解析：兼容两种调用方式 ----------
if len(sys.argv) > 2 and (sys.argv[1].lower().endswith(".xls") or sys.argv[1].lower().endswith(".csv")):
    # 方式2：直接传文件路径
    POS_FILE, TR_FILE = sys.argv[1], sys.argv[2]
    OUT = sys.argv[3] if len(sys.argv) > 3 else common.OUT
    BASE = common.BASE
else:
    # 方式1：传工作区路径/输出目录（与一键流水线一致）
    BASE, OUT = common.parse_cli()
    POS_FILE = os.path.join(BASE, "持仓.xls")
    TR_FILE = os.path.join(BASE, "交易记录.xls")
os.makedirs(OUT, exist_ok=True)

# ---------- 1. 解析同花顺导出（GBK + Tab） ----------
def load(path):
    for enc in ["gbk", "gb18030", "utf-8"]:
        try:
            df = pd.read_csv(path, sep="\t", encoding=enc, dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception:
            continue
    raise ValueError(f"无法解析 {path}")

pos = load(POS_FILE).dropna(subset=["证券代码"])
tr = load(TR_FILE).dropna(subset=["证券代码"])

num_cols = ["股票余额", "可用余额", "成本价", "市价", "盈亏", "盈亏比(%)",
            "当日盈亏", "市值", "仓位占比(%)", "持股天数"]
for c in num_cols:
    if c in pos.columns:
        pos[c] = pd.to_numeric(pos[c], errors="coerce")
pos["证券代码"] = pos["证券代码"].astype(str).str.zfill(6)

for c in ["成交数量", "成交均价", "成交金额", "发生金额", "印花税",
          "其他杂费", "过户费", "经手费", "证管费", "净佣金"]:
    if c in tr.columns:
        tr[c] = pd.to_numeric(tr[c], errors="coerce")
tr["成交日期"] = pd.to_datetime(tr["成交日期"].astype(str).str.strip(),
                                format="%Y%m%d", errors="coerce")
tr["证券代码"] = tr["证券代码"].astype(str).str.zfill(6)
tr["量"] = tr["成交数量"].abs()
tr["方向"] = tr["操作"].map(lambda x: "买" if x == "证券买入"
                            else ("卖" if x == "证券卖出" else "其他"))

# ---------- 2. 数据完整性检查 ----------
print("=" * 66)
print("完整性检查（期初持仓推导）")
print("=" * 66)
incomplete = []
for code in sorted(set(tr["证券代码"])):
    sub = tr[tr["证券代码"] == code]
    b = sub[sub["操作"] == "证券买入"]["量"].sum()
    bonus = sub[sub["操作"] == "红股入账"]["量"].sum()
    s = sub[sub["操作"] == "证券卖出"]["量"].sum()
    p = pos[pos["证券代码"] == code]
    end = float(p["股票余额"].iloc[0]) if not p.empty else 0.0
    init = end + s - b - bonus
    if abs(init) > 100:
        incomplete.append((code, sub["证券名称"].iloc[0], init))
        print(f"  [WARN] {code} {str(sub['证券名称'].iloc[0])[:12]:<12} 期初约{init:,.0f}股")
if not incomplete:
    print("  [OK] 记录完整（期初持仓为0）")
else:
    print("  [!!] 存在期初持仓，需让用户导出到账户起点（开户日）")

# ---------- 3. 含费已实现盈亏（同花顺口径） ----------
print("=" * 66)
print("含费已实现盈亏（移动加权平均，红股0成本，发生金额口径）")
print("=" * 66)
realized = {}
lots = {}
for _, r in tr.sort_values(["成交日期", "成交时间"]).iterrows():
    code = r["证券代码"]
    lots.setdefault(code, {"qty": 0.0, "cost": 0.0})
    op, qty, c = r["操作"], r["量"], lots[code]
    if op == "证券买入":
        amt = abs(r["发生金额"])  # 含买入费用
        new_qty = c["qty"] + qty
        c["cost"] = (c["cost"] * c["qty"] + amt) / new_qty if new_qty else 0
        c["qty"] = new_qty
    elif op == "红股入账":  # 免费份额：只摊薄成本，不计成本总额
        if c["qty"] + qty > 0:
            c["cost"] = c["cost"] * c["qty"] / (c["qty"] + qty)
        c["qty"] += qty
    elif op == "证券卖出":
        sell_qty = min(qty, c["qty"])
        sell_amt = abs(r["发生金额"]) * (sell_qty / qty) if qty else 0  # 含卖费
        pnl = sell_amt - sell_qty * c["cost"]
        realized.setdefault(code, {"pnl": 0.0, "shares": 0.0, "name": r["证券名称"]})
        realized[code]["pnl"] += pnl
        realized[code]["shares"] += sell_qty
        c["qty"] -= sell_qty
        if c["qty"] <= 0:
            c["qty"], c["cost"] = 0.0, 0.0

total_realized = sum(v["pnl"] for v in realized.values())
flt = pos["盈亏"].sum()
print(f"含费已实现盈亏合计: {total_realized:,.2f} 元")
print(f"当前持仓浮动盈亏: {flt:,.2f} 元")
print(f"合计(已实现+浮动): {total_realized + flt:,.2f} 元  [与同花顺核对]")
print(f"{'代码':<8}{'名称':<14}{'卖出股数':>10}{'已实现盈亏':>14}")
for code, v in sorted(realized.items(), key=lambda x: x[1]["pnl"]):
    if abs(v["pnl"]) > 100:
        print(f"{code:<8}{str(v['name'])[:12]:<14}{v['shares']:>10,.0f}{v['pnl']:>14,.2f}")

# ---------- 4. 资金流口径 ----------
print("=" * 66)
print("资金流口径（总盈亏 = 当前市值 - 累计净投入）")
print("=" * 66)
buy = tr[tr["操作"] == "证券买入"]["发生金额"].sum()
sell = tr[tr["操作"] == "证券卖出"]["发生金额"].sum()
other = tr[tr["操作"].isin(["股息入账", "股息红利税补", "红股入账"])]["发生金额"].sum()
net_invest = -(buy + sell + other)
mv = pos["市值"].sum()
print(f"累计净投入: {net_invest:,.2f} | 当前市值: {mv:,.2f}")
print(f"总盈亏 = {mv - net_invest:,.2f}")
if incomplete:
    print("[!!] 记录不完整，资金流口径失真，仅供参考")

# ---------- 5. 保存 CSV ----------
os.makedirs(OUT, exist_ok=True)
pos.to_csv(os.path.join(OUT, "持仓明细.csv"), index=False, encoding="utf-8-sig")
tr.to_csv(os.path.join(OUT, "交易明细_clean.csv"), index=False, encoding="utf-8-sig")
rl_df = pd.DataFrame([{"证券代码": k, "证券名称": v["name"],
                       "已实现盈亏": v["pnl"], "卖出股数": v["shares"]}
                      for k, v in realized.items()])
rl_df.to_csv(os.path.join(OUT, "已实现盈亏_修正.csv"), index=False, encoding="utf-8-sig")
print(f"\n[OK] 输出已保存到 {OUT}")
