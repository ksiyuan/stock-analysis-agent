# -*- coding: utf-8 -*-
"""
生成综合 HTML 报告（内嵌图表）并打包 zip
用法: python build_report.py [工作区路径] [输出目录]
依赖: 账户分析/技术面/估值/复盘/成本 各步骤产物（CSV/JSON/png）
"""
import os
import sys
import json
import base64
import zipfile
import pandas as pd
from datetime import datetime

import common

BASE, OUT = common.parse_cli()


def img_to_b64(name):
    p = os.path.join(OUT, name)
    if os.path.exists(p):
        with open(p, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    return ""


def read_or(path, default=""):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return default


# ---------- 读取数据 ----------
pos = pd.read_csv(os.path.join(OUT, "持仓明细.csv"))
pos["证券代码"] = pos["证券代码"].astype(str).str.zfill(6)
tech_json = json.loads(read_or(os.path.join(OUT, "技术指标.json"), "{}"))
val = json.loads(read_or(os.path.join(OUT, "估值数据.json"), "{}"))
account_report = read_or(os.path.join(OUT, "账户分析报告.txt"))
loss_report = read_or(os.path.join(OUT, "亏损股复盘.txt"))
cost_report = read_or(os.path.join(OUT, "成本优化分析.txt"))

HOLD = [("588170", "科创半导体ETF华夏"), ("600030", "中信证券"),
        ("600036", "招商银行"), ("600941", "中国移动"), ("601872", "招商轮船")]


def fmt_tech(code):
    return tech_json.get(code, {}).get("comment", "")


def hold_section():
    rows = []
    for code, name in HOLD:
        t = tech_json.get(code, {})
        v = val.get(code, {})
        p = pos[pos["证券代码"] == code]
        if p.empty:
            continue
        p = p.iloc[0]
        rows.append(f"""
        <div class="card">
          <h3>{code} {name}</h3>
          <table class="mini">
            <tr><td>现价</td><td><b>{p['市价']}</b></td><td>成本</td><td>{p['成本价']}</td><td>市值</td><td>{p['市值']:,.0f}</td></tr>
            <tr><td>持仓盈亏</td><td class="{'red' if p['盈亏']<0 else 'green'}">{p['盈亏']:+,.0f} ({p['盈亏比(%)']:+.2f}%)</td><td>仓位</td><td>{p['仓位占比(%)']:.1f}%</td></tr>
            <tr><td>PE(TTM)</td><td>{v.get('pe_ttm','-')}</td><td>PB</td><td>{v.get('pb','-')}</td><td>RSI</td><td>{t.get('RSI','-')}</td></tr>
            <tr><td>5日</td><td class="{'red' if t.get('ret5',0)<0 else 'green'}">{t.get('ret5','-')}%</td><td>20日</td><td class="{'red' if t.get('ret20',0)<0 else 'green'}">{t.get('ret20','-')}%</td><td>60日</td><td class="{'red' if t.get('ret60',0)<0 else 'green'}">{t.get('ret60','-')}%</td></tr>
          </table>
          <p class="comment">{fmt_tech(code)}</p>
          <div class="imgs">
            <img src="{img_to_b64(f'analysis_{code}_kline.png')}" alt="K线">
            <img src="{img_to_b64(f'analysis_{code}_indicators.png')}" alt="指标">
          </div>
        </div>""")
    return "\n".join(rows)


def watchlist_section():
    watch = [("002371", "北方华创"), ("588910", "科创价值ETF建信"), ("588810", "科创芯片ETF富国"),
             ("600584", "长电科技"), ("159566", "储能电池ETF"), ("000977", "浪潮信息"),
             ("601138", "工业富联"), ("002916", "深南电路"), ("002028", "思源电气")]
    rows = ["<table><tr><th>代码</th><th>名称</th><th>现价</th><th>5日%</th><th>20日%</th><th>60日%</th><th>RSI</th><th>支撑</th><th>压力</th><th>结论</th></tr>"]
    for code, name in watch:
        t = tech_json.get(code, {})
        pos60 = t.get("pos_60", "-")
        cls = "red" if pos60 >= 80 else ("green" if pos60 <= 20 else "")
        brk = t.get("breakout", "")
        conclusion = fmt_tech(code)
        if brk:
            conclusion = f"<span style='color:#d62728;font-weight:bold'>突破</span> {conclusion}"
        rows.append(f"""<tr>
          <td>{code}</td><td>{name}</td><td>{t.get('close','-')}</td>
          <td class="{'red' if t.get('ret5',0)<0 else 'green'}">{t.get('ret5','-')}%</td>
          <td class="{'red' if t.get('ret20',0)<0 else 'green'}">{t.get('ret20','-')}%</td>
          <td class="{'red' if t.get('ret60',0)<0 else 'green'}">{t.get('ret60','-')}%</td>
          <td>{t.get('RSI','-')}</td>
          <td class="{cls}">{t.get('support','-')}</td><td>{t.get('resistance','-')}</td>
          <td class="small">{conclusion}</td></tr>""")
    rows.append("</table>")
    return "\n".join(rows)


def news_section():
    """新闻与公告（辅助决策）"""
    md_path = os.path.join(OUT, "新闻公告.md")
    if not os.path.exists(md_path):
        return '<div class="card">未生成新闻公告（运行 fetch_news.py）</div>'
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 简单转 HTML
    import html as _html
    lines = []
    in_pre = False
    for ln in content.splitlines():
        ln = _html.escape(ln)
        if ln.startswith("# "):
            lines.append(f"<h4>{ln[2:]}</h4>")
        elif ln.startswith("## "):
            lines.append(f"<h4 style='margin-top:14px;border-bottom:1px solid #eee;padding-bottom:4px'>{ln[3:]}</h4>")
        elif ln.startswith("### "):
            lines.append(f"<b>{ln[4:]}</b>")
        elif ln.startswith("- "):
            lines.append(f"<div style='margin:3px 0;font-size:13px'>{ln[2:]}</div>")
        elif ln.strip():
            lines.append(f"<div style='font-size:13px;color:#555'>{ln}</div>")
    return f'<div class="card">{"".join(lines)}</div>'


def global_section():
    """中美联动对比（策略第6条，行情+财报综合信号）"""
    path = os.path.join(OUT, "中美联动对比.csv")
    if not os.path.exists(path):
        return '<div class="card">未生成中美联动对比（运行 fetch_global_market.py）</div>'
    df = pd.read_csv(path)
    has_fin = "美股净利同比%" in df.columns
    head = "<th>美股</th><th>美5日%</th><th>美20日%</th><th>A股</th><th>A5日%</th><th>A20日%</th><th>补涨缺口</th>"
    if has_fin:
        head += "<th>美股净利%</th><th>A股净利%</th>"
    head += "<th>综合信号</th>"
    rows = [f"<table><tr>{head}</tr>"]
    for _, r in df.iterrows():
        gap = r.get("补涨缺口(美-A)", "")
        sig = str(r.get("信号", ""))
        cls = ""
        if "补涨" in sig:
            cls = "green"
        elif "风险" in sig or "下滑" in sig:
            cls = "red"
        fin_cells = ""
        if has_fin:
            un = r.get("美股净利同比%", "")
            an = r.get("A股净利同比%", "")
            fin_cells = (f"<td class=\"{'red' if isinstance(un,(int,float)) and un<0 else 'green'}\">{un}</td>"
                         f"<td>{an}</td>")
        rows.append(f"""<tr>
          <td>{r.get('美股','')}</td><td>{r.get('美5日%','')}</td><td>{r.get('美20日%','')}</td>
          <td>{r.get('A股','')}</td><td>{r.get('A5日%','')}</td><td>{r.get('A20日%','')}</td>
          <td>{gap}</td>
          {fin_cells}
          <td class="small {cls}">{sig}</td></tr>""")
    rows.append("</table>")
    return f'<div class="card">{"".join(rows)}<div class="small" style="margin-top:6px">补涨缺口 = 美股20日涨幅 − A股20日涨幅；综合信号结合美股/A股财报净利增速（用户策略第6条）：补涨=绿、风险=红</div></div>'


def financial_section():
    """财报分析（策略第4/9条）"""
    path = os.path.join(OUT, "财报分析.csv")
    if not os.path.exists(path):
        return '<div class="card">未生成财报分析（运行 fetch_financials.py）</div>'
    df = pd.read_csv(path)
    has_mkt = "市场" in df.columns
    rows = ["<table><tr>" + ("<th>市场</th>" if has_mkt else "") + "<th>代码</th><th>名称</th><th>PE(TTM)</th><th>PEG</th><th>最新期</th><th>营收(亿)</th><th>营收同比%</th><th>净利(亿)</th><th>净利同比%</th><th>毛利率%</th><th>ROE%</th><th>负债率%</th><th>现金流(亿)</th><th>提示</th></tr>"]
    for _, r in df.iterrows():
        np_yoy = r.get("净利同比%")
        rev_yoy = r.get("营收同比%")
        peg = r.get("PEG")
        debt = r.get("资产负债率%")
        note = ""
        cls = ""
        msgs = []
        try:
            if pd.notna(np_yoy) and np_yoy > 20:
                msgs.append("净利高增")
            elif pd.notna(np_yoy) and np_yoy < 0:
                msgs.append("净利下滑")
        except (TypeError, ValueError):
            pass
        try:
            if pd.notna(peg) and peg < 1:
                msgs.append("PEG<1低估成长")
                cls = "green"
        except (TypeError, ValueError):
            pass
        try:
            if pd.notna(debt) and debt > 70:
                msgs.append("负债率偏高")
            elif pd.notna(debt) and debt < 30:
                msgs.append("负债率低稳健")
        except (TypeError, ValueError):
            pass
        if msgs:
            note = "; ".join(msgs)
        market_cell = f"<td>{r.get('市场','')}</td>" if has_mkt else ""
        rows.append(f"""<tr>
          {market_cell}
          <td>{r.get('代码','')}</td><td>{r.get('名称','')}</td>
          <td>{r.get('PE(TTM)','')}</td><td class="{cls}">{peg if pd.notna(peg) else '-'}</td>
          <td>{r.get('最新期','')}</td><td>{r.get('营收(亿)','')}</td>
          <td class="{'red' if pd.notna(rev_yoy) and rev_yoy<0 else 'green'}">{rev_yoy if pd.notna(rev_yoy) else '-'}</td>
          <td>{r.get('净利(亿)','')}</td>
          <td class="{'red' if pd.notna(np_yoy) and np_yoy<0 else 'green'}">{np_yoy if pd.notna(np_yoy) else '-'}</td>
          <td>{r.get('毛利率%','')}</td><td>{r.get('ROE%','')}</td>
          <td class="{'red' if pd.notna(debt) and debt>70 else ''}">{debt if pd.notna(debt) else '-'}</td>
          <td>{r.get('经营现金流(亿)','')}</td>
          <td class="small">{note}</td></tr>""")
    rows.append("</table>")
    return f'<div class="card">{"".join(rows)}<div class="small" style="margin-top:6px">财报为最近1-2期（半年报/一季报）；PEG=PE(TTM)/净利同比增速，&lt;1 为低估成长（用户策略第4/9条）</div></div>'


def loss_section():
    rows = ["<table><tr><th>代码</th><th>名称</th><th>已实现盈亏</th><th>资金流口径</th><th>买入均价</th><th>卖出均价</th><th>价差%</th><th>平均持有</th><th>买/卖笔数</th></tr>"]
    tr = pd.read_csv(os.path.join(OUT, "交易明细_clean.csv"))
    tr["成交日期"] = pd.to_datetime(tr["成交日期"])
    tr["量"] = tr["成交数量"].abs()
    tr["方向"] = tr["操作"].map(lambda x: "买" if x == "证券买入" else ("卖" if x == "证券卖出" else "其他"))
    rl_path = os.path.join(OUT, "已实现盈亏_修正.csv")
    rl2 = pd.read_csv(rl_path) if os.path.exists(rl_path) else pd.read_csv(os.path.join(OUT, "已实现盈亏.csv"))
    rl2["证券代码"] = rl2["证券代码"].astype(str).str.zfill(6)
    pnl_map = {}
    pnl_path = os.path.join(OUT, "总盈亏_资金口径.csv")
    if os.path.exists(pnl_path):
        pdf = pd.read_csv(pnl_path)
        pdf["证券代码"] = pdf["证券代码"].astype(str).str.zfill(6)
        pnl_map = dict(zip(pdf["证券代码"], pdf["总盈亏"]))
    loss = rl2[rl2["已实现盈亏"] < -500].sort_values("已实现盈亏")
    for _, row in loss.iterrows():
        code = row["证券代码"]
        sub = tr[tr["证券代码"].astype(str).str.zfill(6) == code]
        buys, sells = sub[sub["方向"] == "买"], sub[sub["方向"] == "卖"]
        bavg = buys["成交金额"].sum() / buys["量"].sum() if len(buys) else 0
        savg = sells["成交金额"].sum() / sells["量"].sum() if len(sells) else 0
        spread = (savg - bavg) / bavg * 100 if bavg else 0
        hold = []
        for _, srow in sells.iterrows():
            pb = buys[buys["成交日期"] <= srow["成交日期"]]
            if not pb.empty:
                hold.append((srow["成交日期"] - pb["成交日期"].iloc[0]).days)
        avg_hold = sum(hold) / len(hold) if hold else 0
        fund = pnl_map.get(code, row["已实现盈亏"])
        rows.append(f"""<tr>
          <td>{code}</td><td>{row['证券名称']}</td>
          <td class="red">{row['已实现盈亏']:,.0f}</td>
          <td class="red">{fund:,.0f}</td>
          <td>{bavg:.2f}</td><td>{savg:.2f}</td>
          <td class="red">{spread:+.1f}%</td><td>{avg_hold:.0f}天</td><td>{len(buys)}/{len(sells)}</td></tr>""")
    rows.append("</table>")
    return "\n".join(rows)


def imgs_section():
    items = [("账户_持仓占比.png", "持仓市值分布"), ("账户_已实现盈亏.png", "已实现盈亏"),
             ("账户_月度成交额.png", "月度成交额")]
    htmls = []
    for name, label in items:
        htmls.append(f'<figure><img src="{img_to_b64(name)}" alt="{label}"><figcaption>{label}</figcaption></figure>')
    return "\n".join(htmls)


html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>股票账户综合分析报告</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f4f6f9; color: #222; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 16px 60px; }}
  h1 {{ font-size: 26px; }}
  h2 {{ border-left: 5px solid #d62728; padding-left: 10px; margin-top: 44px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 16px 20px; margin: 18px 0; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; }}
  th, td {{ border: 1px solid #e3e6ea; padding: 6px 8px; text-align: left; }}
  th {{ background: #f0f2f5; }}
  table.mini td {{ border: none; padding: 4px 8px; }}
  .red {{ color: #d62728; }} .green {{ color: #2ca02c; }}
  .comment {{ background: #fffbe6; border-left: 3px solid #faad14; padding: 8px 12px; border-radius: 4px; font-size: 13px; }}
  .imgs {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }}
  .imgs img {{ width: 100%; border-radius: 6px; border: 1px solid #eee; }}
  pre {{ background: #f8f9fb; padding: 14px; border-radius: 8px; overflow-x: auto; font-size: 12px; line-height: 1.5; }}
  figure {{ margin: 14px 0; text-align: center; }}
  figure img {{ max-width: 100%; border-radius: 8px; border: 1px solid #e3e6ea; }}
  figcaption {{ color: #666; font-size: 13px; margin-top: 6px; }}
  .small {{ font-size: 11px; color: #555; }}
  .summary {{ background: #e8f4ff; border-left: 5px solid #1f77b4; padding: 14px 18px; border-radius: 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>📈 股票账户综合分析报告</h1>
  <p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 数据来源：同花顺导出 + AkShare</p>
  <div class="summary">{account_report[:400] if account_report else '（账户分析报告未生成，请先运行 account_analysis.py）'}</div>

  <h2>一、当前持仓分析（技术面 + 估值）</h2>
  {hold_section()}

  <h2>二、自选股技术面快览</h2>
  <div class="card">{watchlist_section()}</div>

  <h2>三、财报分析（最近1-2期）</h2>
  {financial_section()}

  <h2>四、新闻与公告（辅助决策）</h2>
  {news_section()}

  <h2>五、中美联动对比（补涨机会）</h2>
  {global_section()}

  <h2>六、账户整体概况</h2>
  <div class="card"><pre>{account_report}</pre></div>
  <div class="card">{imgs_section()}</div>

  <h2>七、亏损股买卖点复盘</h2>
  <div class="card">{loss_section()}</div>
  <div class="card"><pre>{loss_report}</pre></div>

  <h2>八、成本与换手率优化分析</h2>
  <div class="card"><pre>{cost_report}</pre></div>
</div>
</body>
</html>"""

html_path = os.path.join(OUT, "账户综合分析报告.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"[OK] HTML 报告: {html_path}")

# 打包 zip
zip_path = os.path.join(BASE, "账户分析打包.zip")
files = []
for fn in os.listdir(OUT):
    if fn.startswith("analysis_") or fn.startswith("账户_") or fn in [
            "账户分析报告.txt", "亏损股复盘.txt", "成本优化分析.txt",
            "持仓明细.csv", "交易明细_clean.csv", "已实现盈亏_修正.csv",
            "技术指标汇总.csv", "估值数据.json", "技术指标.json",
            "账户综合分析报告.html", "market_data.pkl"]:
        files.append(fn)

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for fn in files:
        zf.write(os.path.join(OUT, fn), arcname=os.path.join("账户分析", fn))
print(f"[OK] 打包完成: {zip_path}（{len(files)} 个文件）")
