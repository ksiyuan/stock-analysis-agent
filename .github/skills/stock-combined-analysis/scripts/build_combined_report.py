# -*- coding: utf-8 -*-
"""
股票综合双引擎分析 - HTML 报告生成
==================================
读取 combined_analysis.json，生成综合报告 HTML（含量化信号、AI决策、共识/分歧、综合评级）。

用法:
    python build_combined_report.py                # 读 output/combined_analysis.json
    python build_combined_report.py path/to/x.json # 指定数据文件
"""
import os
import sys
import json
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
BASE = SCRIPTS_DIR.parents[3]
OUT = BASE / "output"

POS_FILE = BASE / "持仓.xls"


def load_data(path=None):
    path = path or (OUT / "combined_analysis.json")
    if not Path(path).exists():
        print(f"[ERR] 未找到综合数据: {path}，先运行 combined_analysis.py")
        sys.exit(1)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def consensus_analysis(quant, ai):
    """交叉验证量化与AI，得出共识/分歧"""
    if not ai or "decision" not in ai:
        return {"verdict": "仅量化", "rating": "参考", "quant_dir": "-",
                "ai_dir": "-", "detail": "AI分析未完成或失败，当前仅展示量化信号"}
    q_signal = (quant.get("technical") or {}).get("signal", "未知")
    ai_decision = ai.get("decision", "未知")

    # 量化方向：偏多/偏空/震荡
    q_dir = {"偏多": "多", "偏空": "空", "震荡": "中"}.get(q_signal, "中")
    # AI方向：buy/hold/sell/strong buy/strong sell
    d_lower = str(ai_decision).lower()
    if any(k in d_lower for k in ("strong buy", "买入", "强烈")):
        ai_dir = "多"
    elif any(k in d_lower for k in ("buy", "加仓", "建仓")):
        ai_dir = "多"
    elif any(k in d_lower for k in ("strong sell", "卖出", "清仓")):
        ai_dir = "空"
    elif any(k in d_lower for k in ("sell", "减仓")):
        ai_dir = "空"
    else:
        ai_dir = "中"

    if q_dir == ai_dir and q_dir != "中":
        verdict = "共识"
        rating = {"多": "强看多", "空": "强看空"}.get(q_dir, "关注")
    elif q_dir == "中" or ai_dir == "中":
        verdict = "中性"
        rating = "观望"
    else:
        verdict = "分歧"
        rating = "谨慎"

    return {
        "verdict": verdict,
        "rating": rating,
        "quant_dir": q_dir,
        "ai_dir": ai_dir,
        "detail": (f"量化信号「{q_signal}」与AI决策「{ai_decision}」"
                   f"{'方向一致，形成共识' if verdict == '共识' else '方向相反，需谨慎对待'}"),
    }


def position_view(position, ai):
    """结合持仓与AI建议的评估"""
    if not position:
        return "无持仓数据"
    if not ai or "decision" not in ai:
        return f"持仓 {position['qty']:.0f} 股，成本 {position['cost']}，盈亏 {position['pnl_pct']}%"
    d_lower = str(ai.get("decision", "")).lower()
    lines = [f"持仓 {position['qty']:.0f} 股 | 成本 {position['cost']} | "
             f"现价 {position['price']} | 盈亏 {position['pnl_pct']}% | 仓位 {position['position_pct']}%"]
    if "buy" in d_lower or "加仓" in ai.get("decision", ""):
        lines.append("AI建议买入/加仓 → 与当前持仓方向一致" if position["pnl"] <= 0
                     else "AI建议买入/加仓 → 当前已盈利，可考虑")
    elif "sell" in d_lower or "减仓" in ai.get("decision", ""):
        lines.append(f"AI建议卖出/减仓 → 当前持仓{'亏损' if position['pnl'] < 0 else '盈利'}，需权衡")
    return "；".join(lines)


def html_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def news_block(news):
    """渲染消息面（新闻/公告 + 情绪 + 关键位）"""
    if not news:
        return ""
    senti_color = {"利好": "#16a34a", "利空": "#dc2626", "中性": "#64748b"}
    items = []
    for it in news[:6]:  # 最多显示 6 条
        title = html_escape(it.get("标题", ""))
        time_ = html_escape(it.get("时间", ""))
        src = html_escape(it.get("来源", ""))
        senti = html_escape(it.get("情绪", "中性"))
        imp = html_escape(it.get("影响标签", ""))
        color = senti_color.get(senti, "#64748b")
        tline = ""
        if it.get("现价"):
            tline = (f'<span class="muted">📍 现价 {it["现价"]} | 支撑 {it["支撑"]} | '
                     f'压力 {it["压力"]}</span>')
        imp_tag = f'<span class="imp">⚠️{imp}</span>' if imp and imp != "nan" else ""
        items.append(
            f'<li><span class="senti" style="color:{color};font-weight:bold">[{senti}]</span> '
            f'{title} {imp_tag}<br>'
            f'<span class="muted">{time_} · {src}</span><br>{tline}</li>')
    return f'<div class="news"><h3>📰 消息面 <small>新闻/公告 · 情绪 · 关键位</small></h3><ul>{"".join(items)}</ul></div>'


def build_html(data):
    stocks = data.get("stocks", {})
    cards = []
    for sym, item in stocks.items():
        quant = item.get("quant", {})
        ai = item.get("ai", {})
        tech = quant.get("technical", {})
        val = quant.get("valuation", {})
        pos = quant.get("position")
        news = item.get("news", [])
        cons = consensus_analysis(quant, ai)
        pv = position_view(pos, ai)

        name = (pos or {}).get("name", sym)
        close = tech.get("last_close", "-")
        q_points = "；".join(tech.get("points", [])) or "无"
        verdict_color = {"共识": "#16a34a", "分歧": "#dc2626", "中性": "#d97706",
                         "仅量化": "#64748b"}.get(cons["verdict"], "#64748b")

        ai_block = ""
        if ai:
            if "error" in ai:
                ai_block = f'<p class="muted">AI分析失败：{html_escape(ai["error"][:200])}</p>'
            else:
                reason = html_escape(ai.get("reasoning", ai.get("raw", "")))
                ai_date = html_escape(str(ai.get("ai_date", "")))
                ai_tag = f'<small>分析日期 {ai_date}{"（复用）" if ai.get("reused") else ""}</small>' if ai_date else ""
                ai_block = (
                    f'<p><b>AI决策：</b><span class="ai-decision">{html_escape(ai.get("decision", "未知"))}</span>'
                    f' <span class="ai-meta">{ai_tag}</span></p>'
                    f'<p class="reason">{reason[:400]}</p>'
                )
        else:
            ai_block = '<p class="muted">无AI分析</p>'

        cards.append(f"""
        <div class="card">
          <div class="card-head">
            <h2>{sym} {html_escape(name)}</h2>
            <span class="verdict" style="background:{verdict_color}">{cons['verdict']} · {cons['rating']}</span>
          </div>
          <div class="grid2">
            <div class="quant">
              <h3>📊 量化信号 <small>信号:{tech.get('signal','-')} | 数据源:{tech.get('source','-')} | {tech.get('last_date','-')}</small></h3>
              <p>收盘: <b>{close}</b> | MA20: {tech.get('ma20','-')} | RSI: {tech.get('rsi','-')} | MACD: {tech.get('macd','-')}</p>
              <p class="muted">{html_escape(q_points)}</p>
              <p>估值: PE(TTM)={val.get('pe_ttm','-')} | PB={val.get('pb','-')}</p>
              <p class="muted">{html_escape(pv)}</p>
            </div>
            <div class="ai">
              <h3>🤖 AI 研判 (TradingAgents + DeepSeek)</h3>
              {ai_block}
            </div>
          </div>
          <p class="consensus">🔍 综合研判：{html_escape(cons['detail'])}</p>
          {news_block(news)}
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>股票综合分析报告</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px; background:#f5f6f8; color:#1e293b; }}
  h1 {{ color:#0f172a; }}
  .meta {{ color:#64748b; font-size:13px; }}
  .card {{ background:#fff; border-radius:10px; padding:18px 22px; margin:16px 0;
           box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .card-head {{ display:flex; justify-content:space-between; align-items:center; }}
  .card-head h2 {{ margin:0; font-size:20px; }}
  .verdict {{ color:#fff; padding:4px 12px; border-radius:20px; font-size:13px; font-weight:bold; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:12px; }}
  .quant,.ai {{ background:#f8fafc; border-radius:8px; padding:12px 16px; }}
  h3 {{ margin:0 0 8px; font-size:15px; }}
  h3 small {{ color:#94a3b8; font-weight:normal; }}
  .muted {{ color:#64748b; font-size:13px; }}
  .reason {{ font-size:13px; line-height:1.6; color:#334155; }}
  .ai-decision {{ font-weight:bold; color:#7c3aed; }}
  .ai-meta {{ color:#94a3b8; font-size:12px; }}
  .consensus {{ margin-top:12px; padding:10px 14px; background:#eff6ff; border-radius:8px; font-size:14px; }}
  .news {{ margin-top:12px; padding:10px 14px; background:#fefce8; border-radius:8px; }}
  .news h3 {{ margin:0 0 8px; font-size:14px; }}
  .news ul {{ margin:0; padding-left:18px; font-size:13px; }}
  .news li {{ margin:6px 0; line-height:1.5; }}
  .senti {{ margin-right:4px; }}
  .imp {{ color:#b45309; background:#fef3c7; padding:0 6px; border-radius:4px; font-size:12px; }}
  .foot {{ margin-top:20px; color:#94a3b8; font-size:12px; }}
</style>
</head>
<body>
<h1>📈 股票综合分析报告（量化 + AI 双引擎）</h1>
<p class="meta">生成时间：{html_escape(data.get('generated_at',''))} ｜ 量化数据来自 AkShare（新浪/东财），AI 研判来自 TradingAgents-CN（DeepSeek）</p>
{''.join(cards)}
<p class="foot">⚠️ 免责声明：本报告由量化模型与 AI 自动生成，仅用于学习与研究，不构成任何投资建议。投资有风险，决策需谨慎。数据可能有延迟，请以官方行情为准。</p>
</body>
</html>"""
    return html


def main():
    path = None
    if len(sys.argv) > 1:
        path = sys.argv[1]
    data = load_data(path)
    html = build_html(data)
    out_path = OUT / "股票综合分析报告.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"[OK] 综合报告已生成: {out_path}")


if __name__ == "__main__":
    main()
