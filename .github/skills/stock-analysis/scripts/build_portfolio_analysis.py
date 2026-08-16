# -*- coding: utf-8 -*-
"""
持仓 + 自选股综合分析 HTML 文档生成器（stock-analysis 技能版）
整合：技术面/估值/财报(含业绩预告)/AI研判/消息面/中美联动/红利维度/涨幅透支/量价 → 综合评级
- 红利股（股息率≥3%）：股息率+分红持续性+财务健康+估值，技术面弱化
- 成长股：PEG(优先业绩预告中值)+技术面+涨幅透支+情绪炒作警示+AI+消息面+中美联动
- 强周期股/亏损股：不看PEG；含买卖建议(买入区间/止盈/止损/高点-10%线)+卖出条件实时标注
输出：分析报告/持仓自选综合分析.html（单文件自包含）
用法: python build_portfolio_analysis.py [工作区路径]
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
# 醒目报告输出目录（所有最终分析报告统一放这里）
REPORT_DIR = os.path.join(BASE, "分析报告")
os.makedirs(REPORT_DIR, exist_ok=True)
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
if _pos:
    BASE = _pos[0]
    OUT = os.path.join(BASE, "output")
    REPORT_DIR = os.path.join(BASE, "分析报告")
    os.makedirs(REPORT_DIR, exist_ok=True)

# ---------------- 目标标的 ----------------
HOLDINGS = [  # (代码, 名称, 类型)
    ("588170", "科创半导体ETF华夏", "持仓"),
    ("600030", "中信证券", "持仓"),
    ("600036", "招商银行", "持仓"),
    ("600941", "中国移动", "持仓"),
    ("601872", "招商轮船", "持仓"),
]
WATCHLIST = [
    ("601138", "工业富联", "自选"),
    ("002916", "深南电路", "自选"),
    ("002028", "思源电气", "自选"),
    ("002371", "北方华创", "自选"),
    ("600584", "长电科技", "自选"),
    ("000977", "浪潮信息", "自选"),
]
TARGETS = HOLDINGS + WATCHLIST

# 强周期股（PEG 对周期股无意义：盈利随周期大幅波动，用户策略）
CYCLE_STOCKS = {"601872": "招商轮船"}  # 油运强周期

# ---------------- 加载数据 ----------------
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

try:
    val = json.load(open(os.path.join(OUT, "估值数据.json"), encoding="utf-8"))
except Exception:
    val = {}

# 股息数据（红利股识别：股息率≥3%视为红利股）
div_data = {}
div_path = os.path.join(OUT, "股息数据.json")
if os.path.exists(div_path):
    div_data = json.load(open(div_path, encoding="utf-8"))

# 涨幅透支数据（成长股：前期涨幅是否透支业绩）
over_ext = {}
ov_path = os.path.join(OUT, "涨幅透支.json")
if os.path.exists(ov_path):
    over_ext = json.load(open(ov_path, encoding="utf-8"))

# 量价分析数据
vp_data = {}
vp_path = os.path.join(OUT, "量价分析.json")
if os.path.exists(vp_path):
    vp_data = json.load(open(vp_path, encoding="utf-8"))

# combined_analysis.json（含 quant+ai+news，持仓股）
comb = {}
if os.path.exists(os.path.join(OUT, "combined_analysis.json")):
    comb = json.load(open(os.path.join(OUT, "combined_analysis.json"), encoding="utf-8"))
    comb = comb.get("stocks", {})

# combined_ai.json（决策）
ai_extra = {}
if os.path.exists(os.path.join(OUT, "combined_ai.json")):
    ai_extra = json.load(open(os.path.join(OUT, "combined_ai.json"), encoding="utf-8"))

# 中美联动
glb = {}
if os.path.exists(os.path.join(OUT, "中美联动对比.csv")):
    g = pd.read_csv(os.path.join(OUT, "中美联动对比.csv"))
    for _, r in g.iterrows():
        acode = str(r["A股代码"])
        acode = acode.zfill(6) if acode.isdigit() else acode
        glb[acode] = {
            "美股": r["美股"], "美股代码": r.get("美股代码", ""),
            "美20日%": r["美20日%"], "美60日位%": r.get("美60日位%", ""),
            "A20日%": r["A20日%"], "A60日位%": r.get("A60日位%", ""),
            "A距60日高%": r.get("A距60日高%", ""), "A距60日低%": r.get("A距60日低%", ""),
            "信号": r["信号"],
        }

# 持仓信息（仓位）
pos = pd.read_csv(os.path.join(OUT, "持仓明细.csv"), encoding="utf-8-sig")
pos["证券代码"] = pos["证券代码"].astype(str).str.zfill(6)
pos_map = {r["证券代码"]: r for _, r in pos.iterrows()}

# ---------------- 工具函数 ----------------
def h(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def s(v, nd=1):
    try:
        if pd.isna(v):
            return "-"
        return f"{float(v):.{nd}f}"
    except (ValueError, TypeError):
        return str(v)

def sig_of(code):
    """从 comment 提取技术方向信号"""
    if code not in tech.index:
        return "震荡", ""
    t = tech.loc[code]
    comment = str(t.get("comment", ""))
    if "偏多" in comment:
        return "偏多", comment
    if "偏弱" in comment or "偏空" in comment:
        return "偏空", comment
    return "震荡", comment

def get_ai(code):
    """获取 AI 决策：优先 combined_analysis（含日期），其次 combined_ai"""
    if code in comb and comb[code].get("ai"):
        return comb[code]["ai"]
    if code in ai_extra:
        return ai_extra[code]
    return None

def get_fin(code):
    f = fin[fin["代码"] == code]
    if f.empty:
        return None
    return f.iloc[0]

def get_news(code):
    return news[news["代码"] == code]

def rating(code, sig, g=None, div=None):
    """综合评级（红利股 vs 成长股差异化，用户策略）：
    - 红利股（股息率≥3%）：看股息率吸引度 + 分红持续性 + 财务健康(ROE/现金流/净利) + 估值(PE/PB)，技术面弱化
    - 成长股：看 PEG + 技术面 + AI + 消息面情绪 + 中美联动（仅强关联标的）
    """
    a = get_ai(code)
    f = get_fin(code)
    n = get_news(code)
    # 消息面情绪倾向（⚠️ 业绩类消息已在财报/PEG 中体现，不重复计入——用户约定 2026-08-16）
    # 例：中国移动 3 条"中报净利下滑"利空若计入会把评级从推荐打成关注，而净利下滑财报已体现
    EARNINGS_KW = ["业绩", "预增", "预减", "亏损", "中报", "年报", "季报", "财报",
                   "半年报", "营收", "净利", "净利润", "利润"]
    good = bad = 0
    for _, r in n.iterrows():
        title = str(r.get("标题", ""))
        if any(k in title for k in EARNINGS_KW):
            continue  # 业绩类消息（与财报重复）不参与情绪打分
        if r.get("情绪") == "利好":
            good += 1
        elif r.get("情绪") == "利空":
            bad += 1
    news_tilt = "利好" if good > bad else ("利空" if bad > good else "中性")
    v = val.get(code, {})

    # ---------- 红利股逻辑（技术面弱化） ----------
    if div is not None and (div.get("股息率%") or 0) >= 3.0:
        score = 0.0
        reasons = []
        dy = float(div.get("股息率%") or 0)
        if dy >= 6:
            score += 3; reasons.append(f"股息率{dy:.1f}%高")
        elif dy >= 4:
            score += 2; reasons.append(f"股息率{dy:.1f}%")
        elif dy >= 2:
            score += 1; reasons.append(f"股息率{dy:.1f}%")
        years = int(div.get("连续分红年数") or 0)
        if years >= 20:
            score += 2; reasons.append(f"连续分红{years}年")
        elif years >= 10:
            score += 1.5; reasons.append(f"连续分红{years}年")
        elif years >= 5:
            score += 1; reasons.append(f"分红{years}年")
        # 财务健康（ROE/净利/现金流）
        if f is not None:
            np_yoy = f.get("净利同比%")
            try:
                np_yoy = float(np_yoy) if pd.notna(np_yoy) else None
            except (ValueError, TypeError):
                np_yoy = None
            if np_yoy is not None and np_yoy > 0:
                score += 1; reasons.append(f"净利+{np_yoy:.0f}%")
            roe = f.get("ROE%")
            try:
                roe = float(roe) if pd.notna(roe) else None
            except (ValueError, TypeError):
                roe = None
            if roe is not None and roe >= 10:
                score += 0.5; reasons.append(f"ROE{roe:.0f}%")
            ocf = f.get("经营现金流(亿)")
            try:
                if ocf is not None and pd.notna(ocf) and float(ocf) > 0:
                    score += 0.5; reasons.append("现金流正")
            except (ValueError, TypeError):
                pass
        # 估值（低 PE/PB）
        pe, pb = v.get("pe_ttm"), v.get("pb")
        try:
            if pe is not None and float(pe) <= 7:
                score += 1; reasons.append(f"PE{pe}低")
        except (ValueError, TypeError):
            pass
        try:
            if pb is not None and float(pb) <= 1:
                score += 0.5; reasons.append(f"PB{pb}")
        except (ValueError, TypeError):
            pass
        # 技术面弱化（只参考，不主导）
        if sig == "偏多":
            score += 0.5; reasons.append("技术偏多(参考)")
        elif sig == "偏空":
            score -= 0.5; reasons.append("技术偏空(弱化)")
        # AI / 消息面辅助
        if a:
            d = str(a.get("decision", ""))
            if "买入" in d or "加仓" in d:
                score += 1; reasons.append("AI买入")
            elif "卖出" in d or "减仓" in d:
                score -= 1; reasons.append("AI卖出")
            elif "持有" in d:
                score += 0.5; reasons.append("AI持有")
        if news_tilt == "利好":
            score += 0.5
        elif news_tilt == "利空":
            score -= 0.5
        if score >= 6.5:
            r, c = "重点推荐", "#16a34a"
        elif score >= 4.5:
            r, c = "推荐", "#65a30d"
        elif score >= 2.5:
            r, c = "关注", "#d97706"
        elif score >= 0.5:
            r, c = "观望", "#64748b"
        else:
            r, c = "回避", "#dc2626"
        return r, c, "、".join(reasons)

    # ---------- 成长股逻辑（技术面 + PEG + AI + 消息面 + 中美联动 + 涨幅透支） ----------
    peg = None
    if f is not None:
        try:
            peg = float(f["PEG"]) if pd.notna(f["PEG"]) else None
        except (ValueError, TypeError):
            peg = None

    score = 0
    reasons = []
    if sig == "偏多":
        score += 2
        reasons.append("技术多头")
    elif sig == "偏空":
        score -= 2
        reasons.append("技术空头")
    # 涨幅透支（用户洞察：PEG低可能只是补前期泡沫，须结合前期涨幅）
    ov = over_ext.get(code)
    ov_lvl = (ov or {}).get("透支", "低") if ov else "低"
    ov_r1 = ov.get("涨1年%") if ov else None
    ov_dd = ov.get("距1年高%") if ov else None
    if ov_lvl == "高":
        score -= 1.5
        reasons.append(f"涨幅透支(1年涨{float(ov_r1):.0f}%)")
    elif ov_lvl == "中":
        score -= 0.5
        if ov_r1 is not None and float(ov_r1) >= 80:
            reasons.append(f"涨幅偏大(1年涨{float(ov_r1):.0f}%)")
        else:
            reasons.append("估值偏高")
    # 距1年高点大幅回调：风险部分释放，PEG可信度回升
    if ov_dd is not None and float(ov_dd) <= -30:
        score += 0.5
        reasons.append(f"已回调{float(ov_dd):.0f}%")
    if a:
        d = str(a.get("decision", ""))
        if "买入" in d or "加仓" in d:
            score += 2
            reasons.append("AI买入")
        elif "卖出" in d or "减仓" in d:
            score -= 2
            reasons.append("AI卖出")
        elif "持有" in d:
            score += 1
            reasons.append("AI持有")
    if news_tilt == "利好":
        score += 1
        reasons.append("消息利好")
    elif news_tilt == "利空":
        score -= 1
        reasons.append("消息利空")

    # PEG（用户定义：估值 / 未来增速；仅非周期、非亏损的成长股适用）
    # 注意：PEG 低不代表便宜——若 PE>50 且 PB>5 属情绪炒作，PEG 失真
    np_yoy = None
    if f is not None:
        try:
            np_yoy = float(f["净利同比%"]) if pd.notna(f["净利同比%"]) else None
        except (ValueError, TypeError):
            np_yoy = None
    is_cycle = code in CYCLE_STOCKS
    is_loss = (np_yoy is not None and np_yoy <= 0) or (
        f is not None and f.get("净利(亿)") is not None and pd.notna(f.get("净利(亿)")) and float(f["净利(亿)"]) < 0)
    if is_cycle:
        reasons.append("强周期股(不看PEG)")
    if is_loss:
        reasons.append("净利下滑(不看PEG)")
    if not is_cycle and not is_loss and peg is not None:
        pe_v, pb_v = v.get("pe_ttm"), v.get("pb")
        pe_f = pb_f = None
        try:
            pe_f = float(pe_v) if pe_v not in (None, "-") else None
        except (ValueError, TypeError):
            pe_f = None
        try:
            pb_f = float(pb_v) if pb_v not in (None, "-") else None
        except (ValueError, TypeError):
            pb_f = None
        if peg < 1 and pe_f is not None and pe_f > 50 and pb_f is not None and pb_f > 5:
            # 情绪炒作：PEG低但PE极高+PB极高，增长已被价格充分/过度定价
            score -= 1.5
            reasons.append(f"情绪炒作(PE{pe_f:.0f}/PB{pb_f:.1f} PEG低失真)")
        elif peg < 1:
            score += 2
            reasons.append(f"PEG {peg}<1")
        elif peg < 2:
            score += 1
            reasons.append(f"PEG {peg}")
    # 中美联动（仅强关联标的：g 有数据才评估，含区间位置）
    if g:
        gs = str(g.get("信号", ""))
        a_pos = str(g.get("A60日位%", ""))
        if "补涨" in gs:
            score += 1
            reasons.append("美股联动补涨")
        if "风险" in gs:
            score -= 1
            reasons.append("美股映射风险")
        try:
            pf = float(a_pos)
            if pf > 80:
                score -= 1
                reasons.append(f"60日高位{pf:.0f}%")
            elif pf < 15:
                score += 1
                reasons.append(f"60日低位{pf:.0f}%")
        except (ValueError, TypeError):
            pass

    if score >= 4:
        r, c = "重点推荐", "#16a34a"
    elif score >= 2:
        r, c = "推荐", "#65a30d"
    elif score >= 0:
        r, c = "关注", "#d97706"
    elif score >= -2:
        r, c = "观望", "#64748b"
    else:
        r, c = "回避", "#dc2626"
    return r, c, "、".join(reasons)

# ---------------- 构建卡片 ----------------
def build_card(code, name, typ):
    sig, comment = sig_of(code)
    sig_c = {"偏多": "#16a34a", "偏空": "#dc2626", "震荡": "#d97706"}.get(sig, "#64748b")
    t = tech.loc[code] if code in tech.index else None
    v = val.get(code, {})
    f = get_fin(code)
    a = get_ai(code)
    n = get_news(code)
    g = glb.get(code)
    div = div_data.get(code)
    pr = pos_map.get(code)
    r, rc, reasons = rating(code, sig, g, div)

    tech_html = "-"
    if t is not None:
        tech_html = (f"收盘 {t['close']} ｜ MA20 {s(t['MA20'],2)} ｜ RSI {s(t['RSI'])} ｜ "
                     f"支撑 {s(t['support'],2)} ｜ 压力 {s(t['resistance'],2)} ｜ "
                     f"20日 {float(t['ret20']):+.1f}% ｜ 60日位 {float(t['pos_60']):.0f}%")
    val_html = f"PE(TTM) {v.get('pe_ttm','-')} ｜ PB {v.get('pb','-')}" if v else "无（ETF）"
    fin_html = "-"
    if f is not None:
        _fc = f.get("预告净利中值%")
        _fc_src = str(f.get("PEG增速源", ""))
        # 净利同比：业绩预告中值优先（用户约定：预告=未来增速），无预告用当期
        if pd.notna(_fc):
            _np_show, _np_note = _fc, "预告"
        else:
            _np_show, _np_note = f.get("净利同比%"), "当期"
        fin_html = (f"营收同比 {s(f.get('营收同比%'))}% ｜ 净利同比 {s(_np_show)}%({_np_note}) ｜ "
                    f"PEG {s(f.get('PEG'),2)}{'(' + _fc_src + ')' if _fc_src else ''} ｜ "
                    f"毛利率 {s(f.get('毛利率%'))}%（{f.get('最新期','')}）")
    ai_html = "-"
    if a:
        d = str(a.get("decision", "未知"))
        dc = {"买入": "#16a34a", "持有": "#d97706", "卖出": "#dc2626"}.get(d, "#64748b")
        ai_html = (f"<b style='color:{dc}'>{h(d)}</b> 目标 {a.get('target_price','-')} 置信 {a.get('confidence','-')}%"
                   f"{'（复用 '+str(a.get('ai_date',''))+'）' if a.get('reused') else ''}")
        if a.get("reasoning"):
            ai_html += f"<div class='muted'>{h(str(a['reasoning'])[:100])}</div>"
    news_html = "-"
    if not n.empty:
        items = []
        for _, nr in n.head(3).iterrows():
            senti = str(nr.get("情绪", "中性"))
            sc = {"利好": "#16a34a", "利空": "#dc2626"}.get(senti, "#64748b")
            imp = ""
            if nr.get("影响标签") and str(nr.get("影响标签")) != "nan":
                imp = " <span class='imp'>⚠️" + h(nr.get("影响标签")) + "</span>"
            items.append(f"<li><span style='color:{sc};font-weight:bold'>[{senti}]</span> "
                         f"{h(nr.get('标题',''))[:48]}{imp}"
                         f"<div class='muted'>{h(nr.get('时间',''))}·{h(nr.get('来源',''))}</div></li>")
        news_html = f"<ul class='tight'>{''.join(items)}</ul>"
    glb_html = ""
    if g:
        _gs = g.get("信号")
        gs = "" if pd.isna(_gs) else str(_gs)
        gc = "#16a34a" if "补涨" in gs else ("#dc2626" if "风险" in gs else "#64748b")
        a_pos = str(g.get("A60日位%", ""))
        try:
            _pf = float(a_pos)
            pos_color = "#dc2626" if _pf > 80 else ("#16a34a" if _pf < 30 else "#64748b")
        except (ValueError, TypeError):
            pos_color = "#64748b"
        glb_html = (f"<tr><th>中美联动<small style='color:#b45309'>(强关联)</small></th>"
                    f"<td>{h(g['美股'])}（{h(g.get('美股代码',''))}）"
                    f" 美20日 {float(g['美20日%']):+.1f}% ｜ 美60日位 {h(g.get('美60日位%',''))}% ｜ "
                    f"A20日 {float(g['A20日%']):+.1f}% ｜ "
                    f"<b style='color:{pos_color}'>A股60日位置 {a_pos}%</b>"
                    f"（距高 {h(g.get('A距60日高%',''))}% / 距低 {h(g.get('A距60日低%',''))}%）｜ "
                    f"<span style='color:{gc}'>{h(gs)}</span></td></tr>")
    pos_html = ""
    if pr is not None:
        pos_html = f"<span class='badge'>仓位 {s(pr['仓位占比(%)'],1)}%</span>"

    # 红利维度（红利股专用：股息率≥3%）
    div_html = ""
    if div is not None and (div.get("股息率%") or 0) >= 3.0:
        div_html = (f"<tr><th>红利维度<small style='color:#b45309'>(红利股)</small></th>"
                    f"<td>股息率 <b>{s(div.get('股息率%'),1)}%</b> ｜ TTM每股分红 {div.get('TTM每股分红','-')} ｜ "
                    f"连续分红 {div.get('连续分红年数','-')} 年 ｜ 最近分红 {h(str(div.get('最近分红日期','-')))})</td></tr>")

    # 涨幅透支（成长股风险提示：前期涨幅是否透支业绩，防"补泡沫"）
    ov_html = ""
    ov = over_ext.get(code)
    if ov:
        lvl = str(ov.get("透支", "低"))
        lc = {"高": "#dc2626", "中": "#d97706", "低": "#16a34a"}.get(lvl, "#64748b")
        r1 = ov.get("涨1年%", "-")
        r2 = ov.get("涨2年%", "-")
        dd = ov.get("距1年高%", "-")
        try:
            r1c = "#dc2626" if float(r1) >= 80 else "#64748b"
        except (ValueError, TypeError):
            r1c = "#64748b"
        ov_html = (f"<tr><th>涨幅透支<small style='color:#b45309'>(防补泡沫)</small></th>"
                   f"<td>近1年 <b style='color:{r1c}'>{r1}%</b> ｜ 近2年 {r2}% ｜ 距1年高 {dd}% ｜ "
                   f"<b style='color:{lc}'>[{lvl}]</b> <span class='muted'>{h(ov.get('透支说明',''))}</span></td></tr>")

    # 量价分析（用户策略补充）
    vp_html = ""
    vp = vp_data.get(code, {})
    if vp:
        _vs = str(vp.get("信号", ""))
        vc = "#dc2626" if ("警惕" in _vs or "动能弱" in _vs or "放量下跌" in _vs) else ("#16a34a" if "健康" in _vs else "#64748b")
        vp_html = (f"<tr><th>量价<small style='color:#b45309'>(量能)</small></th>"
                   f"<td>量比5/20 <b>{s(vp.get('量比5_20'),2)}</b> ｜ 放量 {vp.get('放量天数','-')}天/5日 ｜ "
                   f"5日涨幅 {s(vp.get('ret5'),1)}% ｜ <b style='color:{vc}'>{h(vp.get('信号',''))}</b></td></tr>")

    # 建议买卖价 + 卖出条件（用户策略：放量破支撑/次日未收复/高点回落10%/基本面恶化）
    trade_html = ""
    if t is not None:
        close = float(t["close"])
        support_f = resistance_f = cyc_f = None
        try:
            support_f = float(t["support"]) if str(t.get("support", "")) not in ("nan", "") else None
        except (ValueError, TypeError):
            support_f = None
        try:
            resistance_f = float(t["resistance"]) if str(t.get("resistance", "")) not in ("nan", "") else None
        except (ValueError, TypeError):
            resistance_f = None
        # 高点回落10%线基准 = 本轮上涨高点（用户策略⑩：非60日历史高点）
        # cycle_high 优先；老数据无该列时回退 hi60（尽量保证兼容）
        try:
            cyc_f = float(t["cycle_high"]) if str(t.get("cycle_high", "")) not in ("nan", "") else None
        except (ValueError, TypeError):
            cyc_f = None
        if cyc_f is None:
            try:
                hi60_f = float(t["hi60"]) if str(t.get("hi60", "")) not in ("nan", "") else None
                cyc_f = hi60_f
            except (ValueError, TypeError):
                cyc_f = None
        high10 = cyc_f * 0.9 if cyc_f else None  # 本轮上涨高点回落10%线（用户策略卖出条件）
        # 买入区间：回落支撑位附近尝试（用户策略③）
        if support_f:
            buy_txt = f"{s(support_f*0.97,2)}~{s(support_f*1.02,2)}"
        else:
            buy_txt = f"参考{s(close*0.95,2)}(现价-5%)"
        # 止盈：压力位（须高于现价）；否则高点-10%线（若高于现价）；否则现价×1.1
        sell_lo = None
        if resistance_f and resistance_f > close:
            sell_lo = resistance_f
        elif high10 and high10 > close:
            sell_lo = high10
        else:
            sell_lo = close * 1.1
        stop = round(support_f * 0.95, 2) if support_f else None
        # 卖出信号检查（用户4条规则）
        sells = []
        if support_f and close <= support_f * 1.01:
            sells.append("贴支撑")
        if high10 and close <= high10:
            sells.append(f"破高点-10%({s(high10,2)})")
        _vsig = str(vp.get("信号", ""))
        if "放量下跌" in _vsig:
            sells.append("放量下跌")
        if f is not None:
            _ny = None
            try:
                _ny = float(f["净利同比%"]) if pd.notna(f["净利同比%"]) else None
            except (ValueError, TypeError):
                _ny = None
            if _ny is not None and _ny < -20:
                sells.append(f"净利恶化({_ny:.0f}%)")
        sell_txt = "、".join(sells) if sells else "未触发"
        trade_html = (f"<tr><th>买卖建议</th><td>买入 <b>{buy_txt}</b> ｜ "
                      f"止盈 <b>{s(sell_lo,2) if sell_lo else '-'}</b> ｜ "
                      f"止损 <b>{s(stop,2) if stop else '-'}</b> ｜ 高点-10%线 {s(high10,2) if high10 else '-'} ｜ "
                      f"卖出信号 <b style='color:{'#dc2626' if sells else '#16a34a'}'>{sell_txt}</b></td></tr>")

    return f"""
    <div class="card">
      <div class="card-head">
        <h3>{code} {h(name)} <span class="tag {'tag-h' if typ=='持仓' else 'tag-w'}">{typ}</span></h3>
        <div><span class="badge">{r}</span> {pos_html}</div>
      </div>
      <table class="kv">
        <tr><th>技术面</th><td><b style='color:{sig_c}'>信号:{sig}</b> ｜ {tech_html}</td></tr>
        <tr><th>估值</th><td>{val_html}</td></tr>
        {vp_html}
        {div_html}
        {ov_html}
        <tr><th>财报</th><td>{fin_html}</td></tr>
        <tr><th>AI研判</th><td>{ai_html}</td></tr>
        <tr><th>消息面</th><td>{news_html}</td></tr>
        {glb_html}
        {trade_html}
        <tr><th>综合评级</th><td><b style='color:{rc}'>{r}</b> <span class='muted'>（{h(reasons)}）</span></td></tr>
      </table>
    </div>"""

hold_cards = "\n".join(build_card(c, n, t) for c, n, t in HOLDINGS)
watch_cards = "\n".join(build_card(c, n, t) for c, n, t in WATCHLIST)

# ---------------- 自选股推荐排序表 ----------------
rank_rows = ""
rank = []
for code, name, typ in WATCHLIST:
    sig, _ = sig_of(code)
    f = get_fin(code)
    peg = None
    np_yoy = None
    if f is not None:
        try:
            peg = float(f["PEG"]) if pd.notna(f["PEG"]) else None
        except (ValueError, TypeError):
            peg = None
        try:
            # 净利同比：业绩预告中值优先（用户约定），无预告用当期
            _fc = f.get("预告净利中值%")
            if pd.notna(_fc):
                np_yoy = float(_fc)
            elif pd.notna(f["净利同比%"]):
                np_yoy = float(f["净利同比%"])
        except (ValueError, TypeError):
            np_yoy = None
    v = val.get(code, {})
    t = tech.loc[code] if code in tech.index else None
    g = glb.get(code)
    div = div_data.get(code)
    r, rc, reasons = rating(code, sig, g, div)
    rank.append((code, name, sig, v.get("pe_ttm", "-"), np_yoy, peg, t, r, rc))
# 排序：评级高的优先，同评级 PEG 小优先（周期股/亏损股 PEG=None 排后）
order = {"重点推荐": 0, "推荐": 1, "关注": 2, "观望": 3, "回避": 4}
rank.sort(key=lambda x: (order.get(x[7], 5), (x[5] if x[5] is not None else 999)))
for code, name, sig, pe, np_yoy, peg, t, r, rc in rank:
    sig_c = {"偏多": "#16a34a", "偏空": "#dc2626", "震荡": "#d97706"}.get(sig, "#64748b")
    rank_rows += (f"<tr><td>{code}</td><td>{h(name)}</td>"
                  f"<td style='color:{sig_c}'>{sig}</td>"
                  f"<td>{pe}</td><td>{s(np_yoy)}%</td><td>{s(peg,2)}</td>"
                  f"<td>{s(t['close'],2) if t is not None else '-'}</td>"
                  f"<td style='color:{rc};font-weight:bold'>{r}</td></tr>")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>持仓 + 自选股综合分析</title>
<style>
  body {{ font-family:"Microsoft YaHei",sans-serif; margin:0; background:#f1f5f9; color:#0f172a; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
  .hero {{ background:linear-gradient(135deg,#0f172a,#14532d); color:#fff; border-radius:14px; padding:22px 28px; margin-bottom:20px; }}
  .hero h1 {{ margin:0 0 6px; font-size:26px; color:#fff; }}
  .hero .sub {{ color:#cbd5e1; font-size:13px; }}
  h2 {{ font-size:20px; margin:28px 0 12px; border-left:4px solid #14532d; padding-left:10px; }}
  .card {{ background:#fff; border-radius:12px; padding:16px 20px; margin:12px 0; box-shadow:0 1px 3px rgba(0,0,0,.07); }}
  .card-head {{ display:flex; justify-content:space-between; align-items:center; }}
  .card-head h3 {{ margin:0; font-size:16px; }}
  .tag {{ padding:2px 8px; border-radius:4px; font-size:11px; margin-left:6px; }}
  .tag-h {{ background:#dcfce7; color:#166534; }}
  .tag-w {{ background:#e0f2fe; color:#075985; }}
  .badge {{ background:#eef2ff; color:#3730a3; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:bold; }}
  table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
  th,td {{ padding:7px 10px; text-align:left; border-bottom:1px solid #e2e8f0; }}
  th {{ background:#f8fafc; color:#475569; font-weight:600; white-space:nowrap; }}
  .kv th {{ width:90px; background:transparent; }}
  .muted {{ color:#94a3b8; font-size:12.5px; }}
  .imp {{ color:#b45309; background:#fef3c7; padding:0 6px; border-radius:4px; font-size:11.5px; }}
  .tight {{ margin:4px 0 0; padding-left:18px; }}
  .tight li {{ margin:4px 0; line-height:1.4; }}
  .foot {{ margin-top:28px; color:#94a3b8; font-size:12px; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">

<div class="hero">
  <h1>📈 持仓 + 自选股综合分析</h1>
  <div class="sub">数据截止 {tech['date'].iloc[0] if 'date' in tech.columns else '最近交易日'}（技术面）｜ 持仓 {len(HOLDINGS)} 只 + 自选 {len(WATCHLIST)} 只 ｜ 综合评级 = 技术面 + 估值/PEG + AI + 消息面情绪 + 中美联动</div>
</div>

<div class="card" style="background:#fffbeb;border-left:4px solid #d97706;">
  <b>🛡️ 卖出条件（用户策略，满足任一即考虑卖出）</b>
  <div class="muted" style="margin-top:4px;font-size:13px;">
    ① <b>放量跌破关键支撑位</b>（量比&gt;1.2 且收盘跌破支撑）② <b>次日未收复</b> ③ <b>高点回落 10%</b>（现价跌破本轮上涨高点的 -10% 线）④ <b>基本面本质恶化</b>（净利大幅下滑/亏损/重大利空）。
    每张卡片「买卖建议」行会实时标注当前触发状态。
  </div>
</div>

<h2>一、自选股推荐排序（按综合评级）</h2>
<div class="card"><table>
<tr><th>代码</th><th>名称</th><th>技术面</th><th>PE</th><th>净利同比</th><th>PEG</th><th>现价</th><th>评级</th></tr>
{rank_rows}
</table></div>

<h2>二、持仓股分析</h2>
{hold_cards}

<h2>三、自选股分析</h2>
{watch_cards}

<p class="foot">本报告由量化模型自动生成，仅供学习研究，不构成投资建议。行情数据截止最近交易日，可能有延迟。｜ 生成于 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>
</body>
</html>"""

out_path = os.path.join(REPORT_DIR, "持仓自选综合分析.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"[OK] 已生成: {out_path} ({len(html)/1024:.0f} KB)")
