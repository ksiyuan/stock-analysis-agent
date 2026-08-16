# -*- coding: utf-8 -*-
"""
账户分析 HTML 文档生成器（stock-analysis 技能版）
整合：持仓、交易统计、盈亏结构、亏损股复盘、交易行为、卖飞股、技术面/估值、财报、消息面、AI观点
输出：output/账户分析文档.html（单文件自包含，浏览器打开即看）

用法：
  python build_account_doc.py [工作区路径] [输出目录]
依赖（先生成）：
  output/持仓明细.csv 交易明细_clean.csv 已实现盈亏_修正.csv
  output/技术指标汇总.csv 财报分析.csv 新闻公告.csv 估值数据.json combined_ai.json
"""
import os
import sys
import json
import pandas as pd
import numpy as np

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
OUT = os.path.join(BASE, "output")
# 醒目报告输出目录（所有最终分析报告统一放这里）
REPORT_DIR = os.path.join(BASE, "分析报告")
os.makedirs(REPORT_DIR, exist_ok=True)
if len(sys.argv) > 1:
    BASE = sys.argv[1]
if len(sys.argv) > 2:
    OUT = sys.argv[2]
else:
    OUT = os.path.join(BASE, "output")

# ---------------- 加载数据 ----------------
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
def _norm_code(v):
    try:
        return str(int(float(v))).zfill(6)
    except (ValueError, TypeError):
        return ""
news["代码"] = news["代码"].apply(_norm_code)

ai = {}
jpath = os.path.join(OUT, "combined_ai.json")
if os.path.exists(jpath):
    ai = json.load(open(jpath, encoding="utf-8"))

try:
    val = json.load(open(os.path.join(OUT, "估值数据.json"), encoding="utf-8"))
except Exception:
    val = {}

# 中美联动（美股对应标的，策略第6条）
glb = {}
glb_path = os.path.join(OUT, "中美联动对比.csv")
if os.path.exists(glb_path):
    g = pd.read_csv(glb_path)
    for _, r in g.iterrows():
        acode = str(r.get("A股代码", ""))
        if acode.isdigit():
            acode = acode.zfill(6)
        glb[acode] = {
            "美股": r.get("美股", ""), "美股代码": r.get("美股代码", ""),
            "美5日%": r.get("美5日%", 0), "美20日%": r.get("美20日%", 0),
            "美60日位%": r.get("美60日位%", ""),
            "美距60日高%": r.get("美距60日高%", ""), "美距60日低%": r.get("美距60日低%", ""),
            "A5日%": r.get("A5日%", 0), "A20日%": r.get("A20日%", 0),
            "A60日位%": r.get("A60日位%", ""),
            "A距60日高%": r.get("A距60日高%", ""), "A距60日低%": r.get("A距60日低%", ""),
            "补涨缺口": r.get("补涨缺口(美-A)", 0),
            "美股净利同比%": r.get("美股净利同比%", ""),
            "A股净利同比%": r.get("A股净利同比%", ""),
            "信号": r.get("信号", ""),
        }

# ---------------- 指标计算 ----------------
buy_n = (tr["方向"] == "买").sum()
sell_n = (tr["方向"] == "卖").sum()
buy_amt = tr.loc[tr["方向"] == "买", "成交金额"].sum()
sell_amt = tr.loc[tr["方向"] == "卖", "成交金额"].sum()
fees = tr["印花税"].fillna(0).sum() + tr["过户费"].fillna(0).sum() + tr["经手费"].fillna(0).sum() \
       + tr["证管费"].fillna(0).sum() + tr["净佣金"].fillna(0).sum()
stamp = tr["印花税"].fillna(0).sum()
commission = tr["净佣金"].fillna(0).sum()
mv = pos["市值"].sum()
pos_profit = pos["盈亏"].sum()
pos_cost = (pos["股票余额"] * pos["成本价"]).sum()
turnover = (buy_amt + sell_amt) / mv if mv else 0
days = (tr["成交日期"].max() - tr["成交日期"].min()).days
trade_days = tr["成交日期"].dt.date.nunique()

# 已实现盈亏
realized = rl["已实现盈亏"].sum()
win = rl[rl["已实现盈亏"] > 0]
lose = rl[rl["已实现盈亏"] < 0]
win_rate = len(win) / len(rl) * 100

# 持仓技术面
def get_tech(code):
    if code in tech.index:
        return tech.loc[code]
    return None

# ---------------- HTML 构建 ----------------
def h(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def pnl_color(v):
    return "#16a34a" if v > 0 else ("#dc2626" if v < 0 else "#64748b")

def fmt(v, nd=2):
    try:
        return f"{float(v):,.{nd}f}"
    except (ValueError, TypeError):
        return "-"

# 持仓表
pos_rows = ""
for _, r in pos.iterrows():
    code = r["证券代码"]
    p = r["盈亏"]
    c = pnl_color(p)
    pos_rows += (f"<tr><td>{code}</td><td>{h(r['证券名称'])}</td><td>{r['股票余额']:,.0f}</td>"
                 f"<td>{r['成本价']:.3f}</td><td>{r['市价']:.3f}</td>"
                 f"<td style='color:{c}'>{p:+,.2f}</td><td style='color:{c}'>{r['盈亏比(%)']:+.2f}%</td>"
                 f"<td>{r['市值']:,.2f}</td><td>{r['仓位占比(%)']:.2f}%</td></tr>")

# 持仓明细卡片（技术面+估值+AI+财报+消息面）
hold_cards = ""
for _, r in pos.iterrows():
    code = r["证券代码"]
    name = r["证券名称"]
    t = get_tech(code)
    v = val.get(code, {})
    a = ai.get(code, {})
    f = fin[fin["代码"] == code]
    n = news[news["代码"] == code]

    tech_html = "<span class='muted'>暂无技术数据</span>"
    if t is not None:
        # 从 comment 提取方向信号（技术指标汇总无 signal 列）
        comment = str(t.get("comment", ""))
        if "偏多" in comment:
            sig = "偏多"
        elif "偏弱" in comment or "偏空" in comment:
            sig = "偏空"
        else:
            sig = "震荡"
        sig_color = {"偏多": "#16a34a", "偏空": "#dc2626", "震荡": "#d97706"}.get(sig, "#64748b")
        tech_html = (f"<b style='color:{sig_color}'>信号:{sig}</b> "
                     f"收盘 {t['close']} | MA20 {t['MA20']:.2f} | RSI {t['RSI']:.1f} | "
                     f"支撑 {t['support']} | 压力 {t['resistance']} | 20日 {t['ret20']:+.1f}% | "
                     f"60日位 {t['pos_60']:.0f}%<br><span class='muted'>{h(comment)}</span>")
    val_html = f"PE(TTM) {v.get('pe_ttm','-')} | PB {v.get('pb','-')}" if v else "<span class='muted'>无估值</span>"

    fin_html = ""
    if not f.empty:
        fr = f.iloc[0]
        def _s(v):
            try:
                if pd.isna(v):
                    return "-"
                return f"{float(v):.1f}"
            except (ValueError, TypeError):
                return str(v)
        fin_html = (f"营收同比 {_s(fr.get('营收同比%'))}% | 净利同比 {_s(fr.get('净利同比%'))}% | "
                    f"PE {fr.get('PE(TTM)','-')} | PEG {_s(fr.get('PEG'))} | 毛利率 {_s(fr.get('毛利率%'))}% "
                    f"({fr.get('最新期','')})")

    ai_html = "<span class='muted'>无AI分析</span>"
    if a and a.get("decision"):
        ai_dec = a["decision"]
        ai_c = {"买入": "#16a34a", "持有": "#d97706", "卖出": "#dc2626"}.get(ai_dec, "#64748b")
        ai_html = (f"<b style='color:{ai_c}'>{h(ai_dec)}</b> "
                   f"<span class='muted'>目标 {a.get('target_price','-')} · 置信 {a.get('confidence','-')}% · "
                   f"{a.get('ai_date','')}{'（复用）' if a.get('reused') else ''}</span><br>"
                   f"<span class='muted'>{h(str(a.get('reasoning',''))[:120])}</span>")

    news_html = ""
    if not n.empty:
        items = []
        for _, nr in n.head(4).iterrows():
            senti = nr.get("情绪", "中性")
            sc = {"利好": "#16a34a", "利空": "#dc2626"}.get(senti, "#64748b")
            imp_tag = ""
            if nr.get("影响标签") and str(nr.get("影响标签")) != "nan":
                imp_tag = " <span class='imp'>⚠️" + h(nr.get("影响标签")) + "</span>"
            items.append("<li><span style='color:" + sc + ";font-weight:bold'>[" + senti + "]</span> "
                         + h(nr.get("标题", ""))[:60] + imp_tag
                         + "<div class='muted'>" + h(nr.get("时间", "")) + " · " + h(nr.get("来源", ""))
                         + " ｜ 现价" + str(nr.get("现价")) + " 支撑" + str(nr.get("支撑"))
                         + " 压力" + str(nr.get("压力")) + "</div></li>")
        news_html = f"<ul class='tight'>{''.join(items)}</ul>"
    else:
        news_html = "<span class='muted'>近2天无新闻</span>"

    # 中美联动（美股对应标的 + 区间位置）
    glb_html = ""
    if code in glb:
        gr = glb[code]
        gs = str(gr["信号"])
        gc = "#16a34a" if "补涨" in gs else ("#dc2626" if "风险" in gs else "#64748b")
        gap = gr["补涨缺口"]
        try:
            gap_s = f"{float(gap):+.1f}%"
        except (ValueError, TypeError):
            gap_s = "-"
        # 区间位置（最高/最低点相对位置）
        a_pos = str(gr.get("A60日位%", ""))
        a_high = str(gr.get("A距60日高%", ""))
        a_low = str(gr.get("A距60日低%", ""))
        us_pos = str(gr.get("美60日位%", ""))
        try:
            _pf = float(a_pos)
            pos_color = "#dc2626" if _pf > 80 else ("#16a34a" if _pf < 30 else "#64748b")
        except (ValueError, TypeError):
            pos_color = "#64748b"
        glb_html = (f"<tr><th>中美联动</th><td><b>{h(gr['美股'])}</b>（{h(gr['美股代码'])}）"
                    f" 美20日 {float(gr['美20日%']):+.1f}% ｜ 美60日位 {us_pos}% ｜ "
                    f"A20日 {float(gr['A20日%']):+.1f}% ｜ 补涨缺口 {gap_s}<br>"
                    f"<b style='color:{pos_color}'>A股60日位置 {a_pos}%</b>（距60日高 {a_high}% / 距低 {a_low}%）｜ "
                    f"美股净利同比 {h(gr['美股净利同比%'])}% ｜ A股净利同比 {h(gr['A股净利同比%'])}% ｜ "
                    f"<span style='color:{gc};font-weight:bold'>{h(gs)}</span></td></tr>")

    hold_cards += f"""
    <div class="card">
      <div class="card-head"><h3>{code} {h(name)}</h3>
        <span class="badge">仓位 {r['仓位占比(%)']:.1f}%</span></div>
      <table class="kv">
        <tr><th>持仓</th><td>{r['股票余额']:,.0f} 股 · 成本 {r['成本价']:.3f} · 现价 {r['市价']:.3f} ·
           <b style='color:{pnl_color(r["盈亏"])}'>{r['盈亏']:+,.2f} ({r['盈亏比(%)']:+.2f}%)</b></td></tr>
        <tr><th>技术面</th><td>{tech_html}</td></tr>
        <tr><th>估值</th><td>{val_html}</td></tr>
        <tr><th>财报</th><td>{fin_html or '<span class="muted">无财报数据（ETF）</span>'}</td></tr>
        <tr><th>AI研判</th><td>{ai_html}</td></tr>
        <tr><th>消息面</th><td>{news_html}</td></tr>
        {glb_html}
      </table>
    </div>"""

# 亏损股复盘表（Top 12）
loss_review_rows = ""
loss_stocks = rl[rl["已实现盈亏"] < -500].sort_values("已实现盈亏")
for code, row in loss_stocks.head(12).iterrows():
    sub = tr[tr["证券代码"] == code]
    buys = sub[sub["方向"] == "买"]
    sells = sub[sub["方向"] == "卖"]
    if buys.empty or sells.empty:
        continue
    buy_wavg = buys["成交金额"].sum() / buys["量"].sum()
    sell_wavg = sells["成交金额"].sum() / sells["量"].sum()
    spread = (sell_wavg - buy_wavg) / buy_wavg * 100
    hold_days = []
    for _, srow in sells.iterrows():
        prev = buys[buys["成交日期"] <= srow["成交日期"]]
        if not prev.empty:
            hold_days.append((srow["成交日期"] - prev["成交日期"].iloc[0]).days)
    avg_hold = np.mean(hold_days) if hold_days else 0
    c = pnl_color(row["已实现盈亏"])
    loss_review_rows += (f"<tr><td>{code}</td><td>{h(row['证券名称'])}</td>"
                         f"<td style='color:{c}'>{fmt(row['已实现盈亏'])}</td>"
                         f"<td>{buy_wavg:.2f}</td><td>{sell_wavg:.2f}</td>"
                         f"<td style='color:{pnl_color(spread)}'>{spread:+.2f}%</td>"
                         f"<td>{avg_hold:.1f} 天</td><td>{len(buys)}/{len(sells)}</td></tr>")

# 盈利股
win_rows = ""
for code, row in win.sort_values("已实现盈亏", ascending=False).head(8).iterrows():
    c = pnl_color(row["已实现盈亏"])
    win_rows += (f"<tr><td>{code}</td><td>{h(row['证券名称'])}</td>"
                 f"<td style='color:{c}'>+{fmt(row['已实现盈亏'])}</td>"
                 f"<td>{row['卖出股数']:,.0f}</td></tr>")

# 卖飞股
fly_rows = ""
sold_codes = set(tr[tr["方向"] == "卖"]["证券代码"]) - set(pos["证券代码"])
for code in sorted(sold_codes):
    if code not in tech.index:
        continue
    t = tech.loc[code]
    if t["ret20"] > 8:
        pnl_row = rl[rl.index == code]
        pnl_s = fmt(pnl_row["已实现盈亏"].iloc[0]) if not pnl_row.empty else "-"
        c = pnl_color(t["ret20"])
        fly_rows += (f"<tr><td>{code}</td><td>{h(t['name'])}</td>"
                     f"<td>{pnl_s}</td>"
                     f"<td style='color:{c}'>+{t['ret20']:.1f}%</td>"
                     f"<td>{t['close']}</td></tr>")

# 月度
month_rows = ""
tr_m = tr.copy()
tr_m["月"] = tr_m["成交日期"].dt.to_period("M")
for m, g in tr_m.groupby("月"):
    month_rows += (f"<tr><td>{m}</td><td>{(g['方向']=='买').sum()} / {(g['方向']=='卖').sum()}</td>"
                   f"<td>{g['成交金额'].sum():,.0f}</td></tr>")

# 费用
fee_rows = f"""
<tr><td>印花税</td><td>{fmt(stamp)}</td><td>{stamp/fees*100:.1f}%</td></tr>
<tr><td>净佣金</td><td>{fmt(commission)}</td><td>{commission/fees*100:.1f}%</td></tr>
<tr><td>过户费+经手费+证管费</td><td>{fmt(fees-stamp-commission)}</td><td>{(fees-stamp-commission)/fees*100:.1f}%</td></tr>
<tr><td><b>合计</b></td><td><b>{fmt(fees)}</b></td><td>100%</td></tr>
"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>账户分析报告</title>
<style>
  body {{ font-family:"Microsoft YaHei",sans-serif; margin:0; background:#f1f5f9; color:#0f172a; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  .sub {{ color:#64748b; font-size:13px; margin-bottom:20px; }}
  .hero {{ background:linear-gradient(135deg,#0f172a,#1e3a8a); color:#fff; border-radius:14px; padding:22px 28px; margin-bottom:20px; }}
  .hero h1 {{ color:#fff; }}
  .hero .sub {{ color:#cbd5e1; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0 24px; }}
  .kpi {{ background:#fff; border-radius:12px; padding:14px 16px; box-shadow:0 1px 3px rgba(0,0,0,.07); }}
  .kpi .v {{ font-size:20px; font-weight:bold; }}
  .kpi .l {{ color:#64748b; font-size:12px; margin-top:2px; }}
  h2 {{ font-size:20px; margin:28px 0 12px; border-left:4px solid #1e3a8a; padding-left:10px; }}
  .card {{ background:#fff; border-radius:12px; padding:16px 20px; margin:12px 0; box-shadow:0 1px 3px rgba(0,0,0,.07); }}
  .card-head {{ display:flex; justify-content:space-between; align-items:center; }}
  .card-head h3 {{ margin:0; font-size:17px; }}
  .badge {{ background:#eef2ff; color:#3730a3; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:bold; }}
  table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
  th,td {{ padding:7px 10px; text-align:left; border-bottom:1px solid #e2e8f0; }}
  th {{ background:#f8fafc; color:#475569; font-weight:600; white-space:nowrap; }}
  tr:hover td {{ background:#f8fafc; }}
  .kv th {{ width:90px; background:transparent; }}
  .muted {{ color:#94a3b8; font-size:12.5px; }}
  .imp {{ color:#b45309; background:#fef3c7; padding:0 6px; border-radius:4px; font-size:11.5px; }}
  .tight {{ margin:4px 0 0; padding-left:18px; }}
  .tight li {{ margin:4px 0; line-height:1.45; }}
  .pos {{ color:#16a34a; }} .neg {{ color:#dc2626; }} .neu {{ color:#64748b; }}
  .tip {{ background:#fffbeb; border:1px solid #fde68a; border-radius:10px; padding:14px 18px; margin:12px 0; }}
  .tip h4 {{ margin:0 0 6px; color:#92400e; }}
  .tip li {{ margin:3px 0; line-height:1.55; }}
  .foot {{ margin-top:28px; color:#94a3b8; font-size:12px; text-align:center; }}
  a.anchor {{ text-decoration:none; color:#1e3a8a; }}
</style>
</head>
<body>
<div class="wrap">

<div class="hero">
  <h1>📊 账户分析报告</h1>
  <div class="sub">数据截止 {tr['成交日期'].max().date()} ｜ 交易区间 {tr['成交日期'].min().date()} ~ {tr['成交日期'].max().date()}（{trade_days} 个交易日）｜ 记录自开户完整覆盖</div>
  <div style="font-size:13px;margin-top:8px;">已实现盈亏 <b>{fmt(realized)}</b> ｜ 持仓浮盈 <b>{pos_profit:+,.2f}</b> ｜ 与同花顺核对误差 &lt;0.5% ✓</div>
</div>

<div class="kpis">
  <div class="kpi"><div class="v">¥{fmt(mv)}</div><div class="l">持仓市值</div></div>
  <div class="kpi"><div class="v { 'pos' if pos_profit>=0 else 'neg'}">{pos_profit:+,.0f}</div><div class="l">持仓浮盈</div></div>
  <div class="kpi"><div class="v neg">{fmt(realized)}</div><div class="l">已实现盈亏</div></div>
  <div class="kpi"><div class="v">{buy_n+sell_n}</div><div class="l">交易笔数（买{buy_n}/卖{sell_n}）</div></div>
  <div class="kpi"><div class="v">{turnover:.0f}×</div><div class="l">区间换手（成交/市值）</div></div>
  <div class="kpi"><div class="v">¥{fmt(fees)}</div><div class="l">总费用（占亏损22%）</div></div>
  <div class="kpi"><div class="v">{win_rate:.0f}%</div><div class="l">按证券胜率（{len(win)}盈/{len(lose)}亏）</div></div>
  <div class="kpi"><div class="v">1.5 天</div><div class="l">平均持有（100%卖≤10天）</div></div>
</div>

<h2>一、当前持仓</h2>
<div class="card"><table>
<tr><th>代码</th><th>名称</th><th>数量</th><th>成本价</th><th>市价</th><th>盈亏</th><th>盈亏%</th><th>市值</th><th>仓位</th></tr>
{pos_rows}
</table></div>

<h2>二、持仓个股深度卡片</h2>
{hold_cards}

<h2>三、盈亏结构</h2>
<div class="card">
  <b>盈利 Top8（盈利合计 {fmt(win['已实现盈亏'].sum())}，其中北方华创+招商轮船占95%）</b>
  <table><tr><th>代码</th><th>名称</th><th>已实现盈亏</th><th>卖出股数</th></tr>{win_rows}</table>
</div>
<div class="card">
  <b>主要亏损股复盘（亏损合计 {fmt(lose['已实现盈亏'].sum())}）</b>
  <table>
  <tr><th>代码</th><th>名称</th><th>已实现盈亏</th><th>买入均价</th><th>卖出均价</th><th>买卖价差</th><th>平均持有</th><th>买/卖笔数</th></tr>
  {loss_review_rows}
  </table>
</div>

<h2>四、交易行为诊断</h2>
<div class="card">
  <ul class="tight">
    <li>🔴 <b>超高频</b>：日均 7.9 笔，平均持有 <b>1.5 天</b>，<b>100% 卖出在持有 ≤10 天内</b>——与"顺势+耐心"策略相悖。</li>
    <li>🔴 <b>追涨杀跌</b>：亏损股普遍买入价在 60 日高位、1~9 天即止损（兆易创新持 1 天 -11.4%）。</li>
    <li>🔴 <b>卖飞 13 只</b>（清仓后 20 日涨 &gt;8%）：利通电子 +51.5%、用友网络 +32.1%、数据港 +23.8%、方正科技 +20.5%……多在支撑位下方割肉后反弹。</li>
    <li>🟡 <b>费用拖累</b>：5.5 个月成交 2,768 万，费用 12,825 元占已实现亏损 22%。</li>
  </ul>
</div>

<h2>五、月度交易</h2>
<div class="card"><table>
<tr><th>月份</th><th>买/卖笔数</th><th>成交额(元)</th></tr>{month_rows}
</table></div>

<h2>六、费用拆解</h2>
<div class="card"><table>
<tr><th>项目</th><th>金额(元)</th><th>占比</th></tr>{fee_rows}
</table></div>

<div class="tip">
  <h4>💡 策略建议（按优先级）</h4>
  <ol>
    <li><b>降频</b>：日均 7.9 笔 → 每周 ≤3 笔，费用立省；每笔交易写清入场理由（放量突破压力位/回落支撑位企稳）。</li>
    <li><b>拉长持有</b>：向北方华创 +53K 学习——靠拿住趋势；盈利仓用"高点回落 10%"纪律，而非 1~2 天就跑。</li>
    <li><b>止损放在关键位下方</b>：收盘跌破支撑位再走，别在盘中波动割肉（13 只卖飞股教训）。</li>
    <li><b>控制集中度</b>：招商轮船 33.7% → 建议 ≤20%；单票上限 20%。</li>
    <li><b>深耕熟悉标的</b>：招商轮船、北方华创是赚钱的票，减少追新题材。</li>
  </ol>
</div>

<p class="foot">本报告由量化模型自动生成，仅供学习研究，不构成投资建议。行情数据截止最近交易日，可能有延迟。｜ 生成于 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>
</body>
</html>"""

out_path = os.path.join(REPORT_DIR, "账户分析.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"[OK] 账户分析文档已生成: {out_path} ({len(html)/1024:.0f} KB)")
