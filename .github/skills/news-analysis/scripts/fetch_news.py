# -*- coding: utf-8 -*-
"""
新闻与公告抓取（辅助决策）
功能:
  1. 个股新闻: 持仓/自选股最近的 stock_news_em（标题+内容+来源+链接）
  2. 最近交易日公告: stock_notice_report(date=最近交易日)，筛选持仓/自选股的公告
  3. 财经要闻: stock_info_global_em 全球财经要闻 + stock_info_global_cls 财联社电报
  4. 高影响度筛选: 按关键词标记（业绩/增持/回购/减持/重组/中标/立案/处罚等）
  5. 情绪打分: 正向/负向/中性（利好/利空/中性）
  6. 消息面×技术面联动: 每条新闻/公告自动关联该股技术位（现价/支撑/压力/MA20/60日位）
用法:
  python fetch_news.py [工作区路径] [输出目录] [--codes 600030,600036] [--days 2]
输出: output/新闻公告.md / 新闻公告.csv
"""
import os
import sys
import time
import akshare as ak
import pandas as pd

# ---------- 控制台 UTF-8 ----------
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------- 路径 ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
# 位置参数：[工作区路径] [输出目录]；--codes=xxx 是可选开关，勿当路径
pos_args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(pos_args) > 0:
    BASE = pos_args[0]
if len(pos_args) > 1:
    OUT = pos_args[1]
else:
    OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

# ---------- 标的 ----------
# 持仓（从持仓明细读取，ETF 跳过） + 可选自选
WATCHLIST = [
    ("002371", "北方华创"), ("600584", "长电科技"),
    ("000977", "浪潮信息"),
    ("601138", "工业富联"), ("002916", "深南电路"), ("002028", "思源电气"),
]


def load_holdings():
    """读取持仓个股（ETF 跳过：代码 1/5 开头）"""
    path = os.path.join(OUT, "持仓明细.csv")
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            df["证券代码"] = df["证券代码"].astype(str).str.zfill(6)
            return [(r["证券代码"], r["证券名称"]) for _, r in df.iterrows()
                    if r["证券代码"][0] not in ("1", "5")]
        except Exception:
            pass
    return []


# 高影响度关键词（辅助决策）
IMPORTANT_KW = ["业绩", "预增", "预减", "亏损", "回购", "增持", "减持", "重组",
                "中标", "订单", "合同", "立案", "处罚", "退市", "ST", "分红",
                "送转", "解禁", "质押", "担保", "收购", "出售", "定增", "获批"]

# 情绪词表（利好/利空）
POSITIVE_KW = ["预增", "增长", "回购", "增持", "中标", "获批", "分红", "送转",
               "涨停", "扭亏", "新高", "签约", "控制权", "创新高", "上调", "盈利",
               "超预期"]
NEGATIVE_KW = ["预减", "亏损", "减持", "立案", "处罚", "退市", "解禁", "质押",
               "担保", "跌停", "爆雷", "违规", "调查", "跌破", "下滑", "下降",
               "终止", "延期", "诉讼", "减值", "风险提示", "商誉减值"]


def flag_importance(text):
    if not text:
        return ""
    hits = [k for k in IMPORTANT_KW if k in text]
    return ",".join(hits)


# 防串新闻排除词（2026-08-16 用户指出：招商银行误配了招商局集运新闻）
EXCLUDE_HINTS = {
    "600036": ["集运", "油运", "船舶", "滚装", "航运"],  # 招商银行（银行）不应出现航运/集运业务新闻
}


def is_relevant(title, code, name, all_targets):
    """新闻-股票相关性过滤（防串新闻）：
    1. 标题含当前股票代码 → 相关
    2. 标题含当前股票全称 → 相关
    3. 标题含其他目标股全称 → 不相关（属于别的股票）
    4. 标题含该股排除词 → 不相关
    5. 否则 → 相关（行业/泛新闻保留）
    """
    t = str(title)
    if code in t:
        return True
    if name and len(name) >= 3 and name in t:
        return True
    for oc, on in all_targets:
        if oc == code:
            continue
        if on and len(on) >= 4 and on in t:
            return False
    hints = EXCLUDE_HINTS.get(code, [])
    if any(k in t for k in hints):
        return False
    return True


def flag_sentiment(text):
    """情绪打分：正向词 +1 / 负向词 -1，>0 利好，<0 利空，=0 中性"""
    if not text:
        return "中性"
    score = sum(1 for k in POSITIVE_KW if k in text)
    score -= sum(1 for k in NEGATIVE_KW if k in text)
    return "利好" if score > 0 else ("利空" if score < 0 else "中性")


def _retry(fn, tries=3, delay=2):
    for _ in range(tries):
        try:
            df = fn()
            if df is not None and len(df) > 0:
                return df
        except Exception:
            time.sleep(delay)
    return None


def fetch_stock_news(code):
    return _retry(lambda: ak.stock_news_em(symbol=code))


def fetch_notices(date):
    return _retry(lambda: ak.stock_notice_report(symbol="全部", date=date))


def latest_trade_date():
    """最近交易日（今天若非交易日则回退到上一个交易日）"""
    try:
        cal = ak.tool_trade_date_hist_sina()
        cal["trade_date"] = pd.to_datetime(cal["trade_date"]).dt.date
        today = pd.Timestamp(time.strftime("%Y-%m-%d")).date()
        valid = cal[cal["trade_date"] <= today]
        if not valid.empty:
            return valid["trade_date"].iloc[-1].strftime("%Y%m%d")
    except Exception:
        pass
    return time.strftime("%Y%m%d")  # 拿不到日历就退回今天


def fetch_global_news():
    out = {}
    out["em"] = _retry(lambda: ak.stock_info_global_em())
    out["cls"] = _retry(lambda: ak.stock_info_global_cls(symbol="全部"))
    return out


# ---------- 消息面 × 技术面联动 ----------
def load_technical_positions():
    """读取技术指标汇总.csv，返回 {code: {close, support, resistance, ma20, ret20, pos60}}"""
    path = os.path.join(OUT, "技术指标汇总.csv")
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
        df["code"] = df["code"].astype(str).str.zfill(6)
        out = {}
        for _, r in df.iterrows():
            out[r["code"]] = {
                "close": r.get("close"), "support": r.get("support"),
                "resistance": r.get("resistance"), "ma20": r.get("MA20"),
                "ret20": r.get("ret20"), "pos60": r.get("pos_60"),
                "name": r.get("name", ""),
            }
        return out
    except Exception:
        return {}


def tech_line(tech, code):
    """生成某股技术位一行文字；无技术位返回空串"""
    if not tech:
        return ""
    t = tech.get(code)
    if not t or t.get("close") is None:
        return ""
    parts = [f"现价 {t['close']}", f"支撑 {t['support']}", f"压力 {t['resistance']}",
             f"MA20 {t['ma20']}"]
    if t.get("ret20") is not None:
        parts.append(f"20日 {t['ret20']:+.1f}%")
    if t.get("pos60") is not None:
        parts.append(f"60日位 {t['pos60']:.0f}%")
    return " | ".join(parts)


if __name__ == "__main__":
    # 标的：--codes 覆盖，否则 持仓 + 自选（自选仅个股，ETF 无新闻可忽略）
    targets = []
    extra = [a for a in sys.argv if a.startswith("--codes=")]
    if extra:
        codes_raw = extra[0].split("=", 1)[1].split(",")
        targets = [(c, c) for c in codes_raw]
    else:
        targets = load_holdings()
        targets += [(c, n) for c, n in WATCHLIST if c not in [t[0] for t in targets]]

    # 新闻时间窗口：--days=N（默认最近 2 天），太远的新闻没意义
    days = 2
    for a in sys.argv:
        if a.startswith("--days="):
            try:
                days = max(1, int(a.split("=", 1)[1]))
            except ValueError:
                pass
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)

    tech_map = load_technical_positions()

    lines = []
    lines.append("# 新闻与公告（辅助决策）")
    lines.append(f"生成时间：{time.strftime('%Y-%m-%d %H:%M')} ｜ 技术位截止最近交易日 ｜ 新闻窗口：最近 {days} 天")
    lines.append("")

    rows = []

    # 1. 个股新闻（只保留最近 days 天）
    lines.append("## 一、个股新闻（持仓/自选，最近 %d 天）" % days)
    all_targets = list(targets)
    for code, name in targets:
        df = fetch_stock_news(code)
        if df is None:
            continue
        # 按发布时间过滤最近 days 天
        recent = []
        for _, r in df.iterrows():
            pub = str(r.get("发布时间", ""))
            try:
                pub_ts = pd.to_datetime(pub)
            except Exception:
                continue
            if pub_ts >= cutoff:
                recent.append((pub_ts, r))
        if not recent:
            continue
        tline = tech_line(tech_map, code)
        lines.append(f"\n### {code} {name}" + (f"\n   📍 {tline}" if tline else ""))
        for pub_ts, r in recent:
            title = str(r.get("新闻标题", ""))
            if not is_relevant(title, code, name, all_targets):
                print(f"[FILTER] {code} {name} 剔除不相关新闻: {title[:40]}")
                continue
            time_ = str(r.get("发布时间", ""))
            src = str(r.get("文章来源", ""))
            imp = flag_importance(title)
            senti = flag_sentiment(title)
            tag = f" [{senti}]" if senti != "中性" else ""
            mark = f"  ⚠️影响:{imp}" if imp else ""
            lines.append(f"- [{time_}] {title}（{src}）{tag}{mark}")
            rows.append({"类型": "个股新闻", "代码": code, "名称": name,
                         "标题": title, "时间": time_, "来源": src,
                         "影响标签": imp, "情绪": senti, "链接": r.get("新闻链接", ""),
                         "现价": tech_map.get(code, {}).get("close", ""),
                         "支撑": tech_map.get(code, {}).get("support", ""),
                         "压力": tech_map.get(code, {}).get("resistance", "")})
        time.sleep(0.3)

    # 2. 最近交易日公告（标的股）
    latest_date = latest_trade_date()
    lines.append(f"\n## 二、标的股最近交易日公告（{latest_date}）")
    notices = fetch_notices(latest_date)
    if notices is not None:
        notices["代码"] = notices["代码"].astype(str).str.zfill(6)
        hold_codes = [c for c, _ in targets]
        mine = notices[notices["代码"].isin(hold_codes)]
        if len(mine) > 0:
            for _, r in mine.iterrows():
                title = str(r.get("公告标题", ""))
                imp = flag_importance(title)
                senti = flag_sentiment(title)
                code = r["代码"]
                tline = tech_line(tech_map, code)
                tag = f" [{senti}]" if senti != "中性" else ""
                mark = f"  ⚠️影响:{imp}" if imp else ""
                lines.append(f"- {code} {r['名称']}: {title}{tag}{mark}")
                if tline:
                    lines.append(f"    📍 {tline}")
                rows.append({"类型": "公告", "代码": code, "名称": r["名称"],
                             "标题": title, "时间": str(r.get("公告日期", "")),
                             "来源": "东方财富公告", "影响标签": imp, "情绪": senti,
                             "链接": r.get("网址", ""),
                             "现价": tech_map.get(code, {}).get("close", ""),
                             "支撑": tech_map.get(code, {}).get("support", ""),
                             "压力": tech_map.get(code, {}).get("resistance", "")})
        else:
            lines.append("（无标的股公告）")
    else:
        lines.append("（获取失败）")

    # 3. 财经要闻（前10条）
    g = fetch_global_news()
    em = g.get("em")
    if em is not None:
        lines.append("\n## 三、财经要闻（东方财富）")
        for _, r in em.head(10).iterrows():
            title = str(r.get("标题", ""))
            lines.append(f"- {title}")
            rows.append({"类型": "要闻", "代码": "", "名称": "",
                         "标题": title, "时间": str(r.get("发布时间", "")),
                         "来源": "东方财富", "影响标签": "", "情绪": "中性",
                         "链接": r.get("链接", ""), "现价": "", "支撑": "", "压力": ""})
    cls = g.get("cls")
    if cls is not None:
        lines.append("\n## 四、财联社电报（前8条）")
        for _, r in cls.head(8).iterrows():
            title = str(r.get("标题", ""))
            lines.append(f"- {title}")
            rows.append({"类型": "电报", "代码": "", "名称": "",
                         "标题": title, "时间": str(r.get("发布时间", "")),
                         "来源": "财联社", "影响标签": "", "情绪": "中性",
                         "链接": "", "现价": "", "支撑": "", "压力": ""})

    report = "\n".join(lines)
    md_path = os.path.join(OUT, "新闻公告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)

    if rows:
        pd.DataFrame(rows).to_csv(os.path.join(OUT, "新闻公告.csv"),
                                  index=False, encoding="utf-8-sig")
    print(f"\n[OK] 新闻公告.md / 新闻公告.csv 已保存到 {OUT}")
