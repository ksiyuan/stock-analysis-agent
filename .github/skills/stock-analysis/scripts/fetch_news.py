# -*- coding: utf-8 -*-
"""
新闻与公告抓取（辅助决策）
功能:
  1. 个股新闻: 持仓/自选股最近的 stock_news_em（标题+内容+来源+链接）
  2. 当日公告: stock_notice_report(date=最近交易日)，筛选持仓/自选股的公告
  3. 财经要闻: stock_info_global_em 全球财经要闻 + stock_info_global_cls 财联社电报
  4. 高影响度筛选: 按关键词标记（业绩/增持/回购/减持/重组/中标/立案/处罚等）
用法:
  python fetch_news.py [工作区路径] [输出目录] [--codes 600030,600036]
输出: output/新闻公告.md / 新闻公告.csv
"""
import os
import sys
import time
import json
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
OUT = os.path.join(BASE, "output")
# ⚠️ 过滤 --codes/--days 等参数，避免被当工作区路径（2026-08-17 修复）
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
try:
    import common
    if _pos:
        BASE, OUT = common.parse_cli(_pos[0])
    else:
        BASE, OUT = common.parse_cli()
except Exception:
    if _pos:
        BASE = _pos[0]
    if len(_pos) > 1:
        OUT = _pos[1]
    else:
        OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

# 持仓个股（从持仓明细读取，ETF 跳过新闻）
def load_holdings():
    path = os.path.join(OUT, "持仓明细.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)
        df["证券代码"] = df["证券代码"].astype(str).str.zfill(6)
        return [(r["证券代码"], r["证券名称"]) for _, r in df.iterrows()
                if r["证券代码"][0] not in ("1", "5")]
    return []


# 高影响度关键词（辅助决策）
IMPORTANT_KW = ["业绩", "预增", "预减", "亏损", "回购", "增持", "减持", "重组",
                "中标", "订单", "合同", "立案", "处罚", "退市", "ST", "分红",
                "送转", "解禁", "质押", "担保", "收购", "出售", "定增", "获批"]

# 防串新闻排除词（2026-08-16 用户指出：招商银行误配了招商局集运新闻）
# 若新闻标题含排除词，判定与该股票无关，剔除
EXCLUDE_HINTS = {
    "600036": ["集运", "油运", "船舶", "滚装", "航运"],  # 招商银行（银行）不应出现航运/集运业务新闻
}


def flag_importance(text):
    if not text:
        return ""
    hits = [k for k in IMPORTANT_KW if k in text]
    return ",".join(hits)


def is_relevant(title, code, name, all_holdings):
    """新闻-股票相关性过滤（防串新闻）：
    1. 标题含当前股票代码 → 相关
    2. 标题含当前股票全称 → 相关
    3. 标题含其他目标股全称 → 不相关（属于别的股票）
    4. 标题含该股排除词（EXCLUDE_HINTS）→ 不相关
    5. 否则 → 相关（行业/泛新闻保留，辅助决策）
    """
    t = str(title)
    if code in t:
        return True
    if name and len(name) >= 3 and name in t:
        return True
    for oc, on in all_holdings:
        if oc == code:
            continue
        if on and len(on) >= 4 and on in t:
            return False  # 属于别的目标股
    hints = EXCLUDE_HINTS.get(code, [])
    if any(k in t for k in hints):
        return False  # 业务无关新闻
    return True


def fetch_stock_news(code, name, tries=3):
    for _ in range(tries):
        try:
            df = ak.stock_news_em(symbol=code)
            if df is not None and len(df) > 0:
                return df
        except Exception:
            time.sleep(2)
    return None


def fetch_notices(date):
    for _ in range(3):
        try:
            return ak.stock_notice_report(symbol="全部", date=date)
        except Exception:
            time.sleep(2)
    return None


def fetch_global_news():
    out = {}
    for _ in range(3):
        try:
            out["em"] = ak.stock_info_global_em()
            break
        except Exception:
            time.sleep(2)
    for _ in range(3):
        try:
            out["cls"] = ak.stock_info_global_cls(symbol="全部")
            break
        except Exception:
            time.sleep(2)
    return out


if __name__ == "__main__":
    extra = [a for a in sys.argv if a.startswith("--codes=")]
    holdings = load_holdings()
    if extra:
        codes_raw = extra[0].split("=", 1)[1].split(",")
        holdings = [(c, c) for c in codes_raw]

    lines = []
    lines.append("# 新闻与公告（辅助决策）")
    lines.append(f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    rows = []

    # 1. 个股新闻
    lines.append("## 一、个股新闻（持仓/自选）")
    all_holdings = list(holdings)
    for code, name in holdings:
        df = fetch_stock_news(code, name)
        if df is None or df.empty:
            continue
        lines.append(f"\n### {code} {name}")
        for _, r in df.head(8).iterrows():
            title = str(r.get("新闻标题", ""))
            if not is_relevant(title, code, name, all_holdings):
                print(f"[FILTER] {code} {name} 剔除不相关新闻: {title[:40]}")
                continue
            time_ = str(r.get("发布时间", ""))
            src = str(r.get("文章来源", ""))
            imp = flag_importance(title)
            lines.append(f"- [{time_}] {title}（{src}）{('  ⚠️影响:' + imp) if imp else ''}")
            rows.append({"类型": "个股新闻", "代码": code, "名称": name,
                         "标题": title, "时间": time_, "来源": src,
                         "影响标签": imp, "链接": r.get("新闻链接", "")})
        time.sleep(0.3)

    # 2. 当日公告（持仓股）
    latest_date = time.strftime("%Y%m%d")
    notices = fetch_notices(latest_date)
    if notices is not None and len(notices) > 0:
        notices["代码"] = notices["代码"].astype(str).str.zfill(6)
        hold_codes = [c for c, _ in holdings]
        mine = notices[notices["代码"].isin(hold_codes)]
        if len(mine) > 0:
            lines.append("\n## 二、持仓股当日公告")
            for _, r in mine.iterrows():
                title = str(r.get("公告标题", ""))
                imp = flag_importance(title)
                lines.append(f"- {r['代码']} {r['名称']}: {title}{('  ⚠️影响:' + imp) if imp else ''}")
                rows.append({"类型": "公告", "代码": r["代码"], "名称": r["名称"],
                             "标题": title, "时间": str(r.get("公告日期", "")),
                             "来源": "东方财富公告", "影响标签": imp, "链接": r.get("网址", "")})
    else:
        lines.append("\n## 二、持仓股当日公告（获取失败）")

    # 3. 财经要闻（前10条）
    g = fetch_global_news()
    em = g.get("em")
    if em is not None and len(em) > 0:
        lines.append("\n## 三、财经要闻（东方财富）")
        for _, r in em.head(10).iterrows():
            title = str(r.get("标题", ""))
            lines.append(f"- {title}")
            rows.append({"类型": "要闻", "代码": "", "名称": "",
                         "标题": title, "时间": str(r.get("发布时间", "")),
                         "来源": "东方财富", "影响标签": "", "链接": r.get("链接", "")})
    cls = g.get("cls")
    if cls is not None and len(cls) > 0:
        lines.append("\n## 四、财联社电报（前8条）")
        for _, r in cls.head(8).iterrows():
            title = str(r.get("标题", ""))
            lines.append(f"- {title}")
            rows.append({"类型": "电报", "代码": "", "名称": "",
                         "标题": title, "时间": str(r.get("发布时间", "")),
                         "来源": "财联社", "影响标签": "", "链接": ""})

    report = "\n".join(lines)
    md_path = os.path.join(OUT, "新闻公告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)

    if rows:
        pd.DataFrame(rows).to_csv(os.path.join(OUT, "新闻公告.csv"),
                                  index=False, encoding="utf-8-sig")
    print(f"\n[OK] 新闻公告.md / 新闻公告.csv 已保存到 {OUT}")
