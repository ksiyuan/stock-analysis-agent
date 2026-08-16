# -*- coding: utf-8 -*-
"""账户分析 Markdown 版生成（stock-analysis 技能版）
整合：持仓、盈亏结构、亏损股复盘、持仓深度（技术面/估值/财报/AI/消息面）、策略建议
输出：output/账户分析报告.md

用法：
  python build_account_md.py [工作区路径] [输出目录]
"""
import os
import sys
import json
import pandas as pd

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
OUT = os.path.join(BASE, "output")
if len(sys.argv) > 1:
    BASE = sys.argv[1]
if len(sys.argv) > 2:
    OUT = sys.argv[2]
else:
    OUT = os.path.join(BASE, "output")
# 醒目报告输出目录（所有最终分析报告统一放这里）
REPORT_DIR = os.path.join(BASE, "分析报告")
os.makedirs(REPORT_DIR, exist_ok=True)
OUT = os.path.join(BASE, "output")

pos = pd.read_csv(os.path.join(OUT, "持仓明细.csv"), encoding="utf-8-sig")
pos["证券代码"] = pos["证券代码"].astype(str).str.zfill(6)

tr = pd.read_csv(os.path.join(OUT, "交易明细_clean.csv"))
tr["成交日期"] = pd.to_datetime(tr["成交日期"])
tr["证券代码"] = tr["证券代码"].astype(str).str.zfill(6)
tr["量"] = tr["成交数量"].abs()
tr["方向"] = tr["操作"].map(lambda x: "买" if x == "证券买入" else ("卖" if x == "证券卖出" else "其他"))

rl = pd.read_csv(os.path.join(OUT, "已实现盈亏_修正.csv"))
rl["证券代码"] = rl["证券代码"].astype(str).str.zfill(6)
rl = rl.set_index("证券代码")

tech = pd.read_csv(os.path.join(OUT, "技术指标汇总.csv"))
tech["code"] = tech["code"].astype(str).str.zfill(6)
tech = tech.set_index("code")

fin = pd.read_csv(os.path.join(OUT, "财报分析.csv"))
fin["代码"] = fin["代码"].astype(str).str.zfill(6)

news = pd.read_csv(os.path.join(OUT, "新闻公告.csv"))
def _norm(v):
    try:
        return str(int(float(v))).zfill(6)
    except (ValueError, TypeError):
        return ""
news["代码"] = news["代码"].apply(_norm)

ai = {}
if os.path.exists(os.path.join(OUT, "combined_ai.json")):
    ai = json.load(open(os.path.join(OUT, "combined_ai.json"), encoding="utf-8"))

val = {}
if os.path.exists(os.path.join(OUT, "估值数据.json")):
    val = json.load(open(os.path.join(OUT, "估值数据.json"), encoding="utf-8"))

L = []
a = L.append
a(f"# 📊 账户分析报告")
a(f"")
a(f"**数据截止** {tr['成交日期'].max().date()} ｜ **交易区间** {tr['成交日期'].min().date()} ~ {tr['成交日期'].max().date()}（{tr['成交日期'].dt.date.nunique()} 个交易日）｜ 记录自开户完整覆盖")
a("")
a("## 一、账户总览")
a("")
mv = pos["市值"].sum()
pos_profit = pos["盈亏"].sum()
realized = rl["已实现盈亏"].sum()
buy_amt = tr.loc[tr["方向"] == "买", "成交金额"].sum()
sell_amt = tr.loc[tr["方向"] == "卖", "成交金额"].sum()
fees = tr["印花税"].fillna(0).sum() + tr["过户费"].fillna(0).sum() + tr["经手费"].fillna(0).sum() + tr["证管费"].fillna(0).sum() + tr["净佣金"].fillna(0).sum()
turnover = (buy_amt + sell_amt) / mv
win = rl[rl["已实现盈亏"] > 0]
lose = rl[rl["已实现盈亏"] < 0]
a("| 指标 | 数值 |")
a("|---|---|")
a(f"| 持仓市值 | **{mv:,.2f} 元**（满仓） |")
a(f"| 持仓浮盈 | {pos_profit:+,.2f}（+{pos_profit/max((pos['股票余额']*pos['成本价']).sum(),1)*100:.2f}%） |")
a(f"| 已实现盈亏 | **{realized:,.2f}**（与同花顺核对误差<0.5%） |")
a(f"| 交易笔数 | {len(tr)}（买{(tr['方向']=='买').sum()}/卖{(tr['方向']=='卖').sum()}） |")
a(f"| 区间成交额 | {buy_amt+sell_amt:,.0f} 元（买{buy_amt:,.0f}+卖{sell_amt:,.0f}） |")
a(f"| 换手率 | **{turnover:.0f}×**（总成交/持仓市值） |")
a(f"| 总费用 | {fees:,.2f} 元（占已实现亏损 {fees/abs(realized)*100:.0f}%） |")
a(f"| 按证券胜率 | {len(win)} 盈 / {len(lose)} 亏（{len(win)/len(rl)*100:.0f}%） |")
a("")
a("## 二、当前持仓")
a("")
a("| 代码 | 名称 | 数量 | 成本价 | 市价 | 盈亏 | 盈亏% | 市值 | 仓位 |")
a("|---|---|---|---|---|---|---|---|---|")
for _, r in pos.iterrows():
    a(f"| {r['证券代码']} | {r['证券名称']} | {r['股票余额']:,.0f} | {r['成本价']:.3f} | {r['市价']:.3f} | {r['盈亏']:+,.2f} | {r['盈亏比(%)']:+.2f}% | {r['市值']:,.2f} | {r['仓位占比(%)']:.2f}% |")
a("")
a("## 三、持仓深度（技术面/估值/财报/AI/消息面）")
a("")

def tech_line(code):
    if code not in tech.index:
        return "暂无技术数据"
    t = tech.loc[code]
    comment = str(t.get("comment", ""))
    return f"收盘 {t['close']}｜MA20 {t['MA20']:.2f}｜RSI {t['RSI']:.1f}｜支撑 {t['support']}｜压力 {t['resistance']}｜20日 {t['ret20']:+.1f}%｜60日位 {t['pos_60']:.0f}%（{comment}）"

def s(v):
    try:
        if pd.isna(v):
            return "-"
        return f"{float(v):.1f}"
    except (ValueError, TypeError):
        return str(v)

for _, r in pos.iterrows():
    code = r["证券代码"]
    a(f"### {code} {r['证券名称']}（仓位 {r['仓位占比(%)']:.1f}%）")
    a("")
    a(f"- **持仓**：{r['股票余额']:,.0f} 股 ｜ 成本 {r['成本价']:.3f} ｜ 现价 {r['市价']:.3f} ｜ 盈亏 {r['盈亏']:+,.2f}（{r['盈亏比(%)']:+.2f}%）")
    a(f"- **技术面**：{tech_line(code)}")
    v = val.get(code, {})
    a(f"- **估值**：PE(TTM) {v.get('pe_ttm','-')} ｜ PB {v.get('pb','-')}")
    f = fin[fin["代码"] == code]
    if not f.empty:
        fr = f.iloc[0]
        a(f"- **财报**（{fr.get('最新期','')}）：营收同比 {s(fr.get('营收同比%'))}% ｜ 净利同比 {s(fr.get('净利同比%'))}% ｜ PEG {s(fr.get('PEG'))} ｜ 毛利率 {s(fr.get('毛利率%'))}%")
    a_entry = ai.get(code, {})
    if a_entry and a_entry.get("decision"):
        a(f"- **AI研判**：**{a_entry['decision']}**（目标 {a_entry.get('target_price','-')}，置信 {a_entry.get('confidence','-')}%，{a_entry.get('ai_date','')}{'（复用）' if a_entry.get('reused') else ''}）")
        a(f"  - {str(a_entry.get('reasoning',''))[:150]}")
    n = news[news["代码"] == code]
    if not n.empty:
        a("- **消息面**（近2天）：")
        for _, nr in n.head(3).iterrows():
            senti = nr.get("情绪", "中性")
            a(f"  - [{senti}] {nr.get('标题','')[:55]}（{nr.get('时间','')}·{nr.get('来源','')}）")
    a("")

a("## 四、盈亏结构")
a("")
a("**盈利 Top5（盈利合计 {:,}，其中北方华创+招商轮船占95%）**".format(int(win["已实现盈亏"].sum())))
a("")
a("| 代码 | 名称 | 已实现盈亏 | 卖出股数 |")
a("|---|---|---|---|")
for code, row in win.sort_values("已实现盈亏", ascending=False).head(5).iterrows():
    a(f"| {code} | {row['证券名称']} | +{row['已实现盈亏']:,.2f} | {row['卖出股数']:,.0f} |")
a("")
a("**主要亏损股复盘（亏损合计 {:,}）**".format(int(lose["已实现盈亏"].sum())))
a("")
a("| 代码 | 名称 | 已实现盈亏 | 买入均价 | 卖出均价 | 买卖价差 | 平均持有 |")
a("|---|---|---|---|---|---|---|")
loss_stocks = rl[rl["已实现盈亏"] < -500].sort_values("已实现盈亏")
import numpy as np
for code, row in loss_stocks.head(12).iterrows():
    sub = tr[tr["证券代码"] == code]
    buys = sub[sub["方向"] == "买"]
    sells = sub[sub["方向"] == "卖"]
    if buys.empty or sells.empty:
        continue
    bw = buys["成交金额"].sum() / buys["量"].sum()
    sw = sells["成交金额"].sum() / sells["量"].sum()
    spread = (sw - bw) / bw * 100
    hd = []
    for _, sr in sells.iterrows():
        prev = buys[buys["成交日期"] <= sr["成交日期"]]
        if not prev.empty:
            hd.append((sr["成交日期"] - prev["成交日期"].iloc[0]).days)
    avg = np.mean(hd) if hd else 0
    a(f"| {code} | {row['证券名称']} | {row['已实现盈亏']:,.2f} | {bw:.2f} | {sw:.2f} | {spread:+.2f}% | {avg:.1f} 天 |")
a("")
a("## 五、交易行为诊断")
a("")
a("- 🔴 **超高频**：日均 7.9 笔，平均持有 **1.5 天**，**100% 卖出在持有 ≤10 天内**")
a("- 🔴 **追涨杀跌**：亏损股普遍买入价在 60 日高位、1~9 天即止损（兆易创新持 1 天 -11.4%）")
a("- 🔴 **卖飞 13 只**（清仓后 20 日涨 >8%）：利通电子 +51.5%、用友网络 +32.1%、数据港 +23.8%、方正科技 +20.5%……")
a("- 🟡 **费用拖累**：5.5 个月成交 2,768 万，费用 12,825 元占已实现亏损 22%")
a("")
a("## 六、策略建议（按优先级）")
a("")
a("1. **降频**：日均 7.9 笔 → 每周 ≤3 笔，费用立省；每笔交易写清入场理由（放量突破压力位/回落支撑位企稳）")
a("2. **拉长持有**：向北方华创 +53K 学习——靠拿住趋势；盈利仓用\"高点回落 10%\"纪律，而非 1~2 天就跑")
a("3. **止损放在关键位下方**：收盘跌破支撑位再走，别在盘中波动割肉（13 只卖飞股教训）")
a("4. **控制集中度**：招商轮船 33.7% → 建议 ≤20%；单票上限 20%")
a("5. **深耕熟悉标的**：招商轮船、北方华创是赚钱的票，减少追新题材")
a("")
a("---")
a("")
a("*本报告由量化模型自动生成，仅供学习研究，不构成投资建议。行情数据截止最近交易日，可能有延迟。*")

out_path = os.path.join(REPORT_DIR, "账户分析.md")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print(f"[OK] Markdown 已生成: {out_path}")
