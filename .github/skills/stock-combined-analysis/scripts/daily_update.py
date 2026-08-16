# -*- coding: utf-8 -*-
"""
股票综合双引擎 - 每日增量更新（自包含版）
==========================================
每天更新分析时，跳过"没必要重复"的重活：
  - 量化层（行情/指标/估值）: 每天跑（快，每只几秒）
  - AI 层（TradingAgents）: 默认复用最近结果（有有效期），到期或 --refresh-ai 才重跑
  - 数据同步: 只对持仓股做定向增量同步（不全市场全量）

用法:
    python daily_update.py                    # 默认全部持仓股，AI 每天重新分析一次
    python daily_update.py 600030 600036      # 指定股票
    python daily_update.py --refresh-ai       # 强制重跑所有 AI 分析（同一天也重跑）
    python daily_update.py --max-age 3        # AI 结果 3 天内复用（默认 0=仅当天复用，每天重跑）
    python daily_update.py --round-robin      # AI 按周一到周五轮询（每只每周更新一次），量化/新闻仍每天全量
    python daily_update.py --no-sync          # 跳过数据同步
    python daily_update.py --skip-report      # 只更新 JSON 不生成 HTML

依赖: pandas, numpy, akshare, requests/urllib, pymongo, redis
      （pymongo/redis 在根 .venv 可能需安装：
       ./.venv/Scripts/python.exe -m pip install pymongo redis）

输出:
    output/combined_analysis.json  (合并数据)
    output/股票综合分析报告.html      (HTML 报告)
"""
import os
import sys
import json
import time
import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ---------- 路径 ----------
SCRIPTS_DIR = Path(__file__).resolve().parent
BASE = SCRIPTS_DIR.parents[3]          # 股票/ 工作区根
OUT = BASE / "output"
PROJECT = BASE / "TradingAgents-CN"    # TradingAgents-CN 目录

BASE_URL = "http://127.0.0.1:8000"
REDIS_URL = "redis://:tradingagents123@127.0.0.1:6379/0"
MONGO_URL = "mongodb://127.0.0.1:27017/"
USERNAME = "admin"
PASSWORD = "admin123"
POS_FILE = BASE / "持仓.xls"
# 自选池（与 tradingagents-analysis/analyze_watchlist.py 一致，供 --round-robin 轮询使用）
WATCH_STOCKS = ["002371", "600584", "000977", "601138", "002916", "002028", "09988"]

os.makedirs(OUT, exist_ok=True)


# ============================================================
# 持仓读取
# ============================================================
def read_holdings():
    """读取同花顺持仓，返回 DataFrame"""
    if not POS_FILE.exists():
        print(f"[WARN] 未找到持仓文件: {POS_FILE}")
        return None
    df = pd.read_csv(POS_FILE, sep="\t", encoding="gbk")
    df.columns = [str(c).strip() for c in df.columns]
    df["证券代码"] = df["证券代码"].astype(str).str.zfill(6)
    print(f"[OK] 读取持仓 {len(df)} 条")
    return df


def get_target_symbols(args_symbols, holdings_df):
    """确定分析标的：命令行优先，否则持仓股（剔除ETF/基金）"""
    if args_symbols:
        return [s.zfill(6) for s in args_symbols]
    if holdings_df is None:
        print("[ERR] 未指定股票且无持仓文件")
        sys.exit(1)
    symbols = []
    for _, row in holdings_df.iterrows():
        code = str(row["证券代码"]).zfill(6)
        name = str(row.get("证券名称", "")).strip()
        if code[0] in ("5", "1"):
            continue
        if any(k in name for k in ("ETF", "LOF", "基金")):
            continue
        symbols.append(code)
    print(f"[OK] 目标股票: {symbols}")
    return symbols


def get_position_info(holdings_df, code):
    """从持仓表提取某股票持仓信息"""
    if holdings_df is None:
        return None
    rows = holdings_df[holdings_df["证券代码"] == code]
    if rows.empty:
        return None
    r = rows.iloc[0]
    return {
        "name": str(r.get("证券名称", code)),
        "qty": float(r.get("股票余额", 0)),
        "cost": float(r.get("成本价", 0)),
        "price": float(r.get("市价", 0)),
        "pnl": float(r.get("盈亏", 0)),
        "pnl_pct": float(r.get("盈亏比(%)", 0)),
        "market_value": float(r.get("市值", 0)),
        "position_pct": float(r.get("仓位占比(%)", 0)),
    }


# ============================================================
# 量化分析（遵循 股票数据获取.instructions.md）
# ============================================================
def get_hist(symbol, days=250):
    """获取历史行情：新浪优先，东财失败回退"""
    import akshare as ak
    end = time.strftime("%Y%m%d")
    start = time.strftime("%Y%m%d", time.localtime(time.time() - days * 86400))
    sh = ("sh" + symbol) if symbol.startswith("6") else ("sz" + symbol)
    try:
        df = ak.stock_zh_a_daily(symbol=sh, start_date=start, end_date=end, adjust="qfq")
        df = df.rename(columns={"date": "trade_date"})
        return df[["trade_date", "open", "high", "low", "close", "volume", "amount"]], "sina"
    except Exception:
        pass
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                start_date=start, end_date=end, adjust="qfq")
        df = df.rename(columns={"日期": "trade_date", "开盘": "open", "收盘": "close",
                                "最高": "high", "最低": "low", "成交量": "volume",
                                "成交额": "amount"})
        return df[["trade_date", "open", "high", "low", "close", "volume", "amount"]], "eastmoney"
    except Exception:
        return None, None


def compute_indicators(df):
    """计算 MA/MACD/RSI/KDJ/BOLL"""
    d = df.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d.sort_values("trade_date").reset_index(drop=True)
    close = d["close"]
    d["MA5"] = close.rolling(5).mean()
    d["MA10"] = close.rolling(10).mean()
    d["MA20"] = close.rolling(20).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    d["DIF"] = ema12 - ema26
    d["DEA"] = d["DIF"].ewm(span=9, adjust=False).mean()
    d["MACD"] = (d["DIF"] - d["DEA"]) * 2
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    d["RSI"] = 100 - 100 / (1 + rs)
    low9 = d["low"].rolling(9).min()
    high9 = d["high"].rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    d["K"] = rsv.ewm(com=2, adjust=False).mean()
    d["D"] = d["K"].ewm(com=2, adjust=False).mean()
    d["J"] = 3 * d["K"] - 2 * d["D"]
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    d["BOLL_MID"] = mid
    d["BOLL_UP"] = mid + 2 * std
    d["BOLL_LOW"] = mid - 2 * std
    return d


def technical_conclusion(d):
    """生成技术面结论"""
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else last
    c = last["close"]
    points = []
    if pd.notna(last["MA20"]):
        points.append("站上20日线" if c > last["MA20"] else "跌破20日线")
    if pd.notna(prev["DIF"]) and pd.notna(last["DIF"]):
        if prev["DIF"] <= prev["DEA"] and last["DIF"] > last["DEA"]:
            points.append("MACD金叉")
        elif prev["DIF"] >= prev["DEA"] and last["DIF"] < last["DEA"]:
            points.append("MACD死叉")
    if pd.notna(last["RSI"]):
        if last["RSI"] > 70:
            points.append(f"RSI超买({last['RSI']:.0f})")
        elif last["RSI"] < 30:
            points.append(f"RSI超卖({last['RSI']:.0f})")
    if pd.notna(last["BOLL_UP"]) and pd.notna(last["BOLL_LOW"]):
        pos = (c - last["BOLL_LOW"]) / (last["BOLL_UP"] - last["BOLL_LOW"])
        if pos > 0.9:
            points.append("触及布林上轨")
        elif pos < 0.1:
            points.append("触及布林下轨")
    if len(d) >= 60:
        hi60 = d["close"].tail(60).max()
        lo60 = d["close"].tail(60).min()
        pct = (c - lo60) / (hi60 - lo60) * 100 if hi60 > lo60 else 50
        points.append(f"60日区间位置{pct:.0f}%")
    if pd.notna(last["MA5"]) and pd.notna(last["MA20"]):
        points.append("短中期均线多头" if last["MA5"] > last["MA20"] else "短中期均线空头")

    signal = "偏多" if (last["MA5"] > last["MA20"] and c > last["MA20"]) else \
             ("偏空" if (last["MA5"] < last["MA20"] and c < last["MA20"]) else "震荡")
    return {
        "signal": signal, "points": points, "last_close": round(float(c), 2),
        "last_date": str(d.iloc[-1]["trade_date"].date()),
        "ma20": round(float(last["MA20"]), 2) if pd.notna(last["MA20"]) else None,
        "rsi": round(float(last["RSI"]), 1) if pd.notna(last["RSI"]) else None,
        "macd": round(float(last["MACD"]), 4) if pd.notna(last["MACD"]) else None,
        "boll_low": round(float(last["BOLL_LOW"]), 2) if pd.notna(last["BOLL_LOW"]) else None,
        "boll_up": round(float(last["BOLL_UP"]), 2) if pd.notna(last["BOLL_UP"]) else None,
    }


def get_valuation(symbol, tries=3):
    """获取 PE(TTM) / PB（百度估值）"""
    import akshare as ak
    result = {}
    for indicator, key in (("市盈率(TTM)", "pe_ttm"), ("市净率", "pb")):
        val = None
        for _ in range(tries):
            try:
                df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator=indicator, period="全部")
                df = df.dropna()
                if not df.empty:
                    val = round(float(df.iloc[-1]["value"]), 2)
                break
            except Exception:
                time.sleep(1)
        result[key] = val
        time.sleep(0.3)
    return result


def quant_analysis(symbol, position):
    """单只股票的量化分析"""
    print(f"[QUANT] {symbol} 获取行情...")
    df, source = get_hist(symbol)
    if df is None or df.empty or len(df) < 30:
        print(f"[WARN] {symbol} 行情获取失败")
        return {"symbol": symbol, "error": "行情获取失败", "source": source}
    d = compute_indicators(df)
    tech = technical_conclusion(d)
    tech["source"] = source
    tech["rows"] = len(d)
    print(f"[QUANT] {symbol} 获取估值...")
    val = get_valuation(symbol)
    return {"symbol": symbol, "technical": tech, "valuation": val, "position": position}


# ============================================================
# TradingAgents AI（API + 复用）
# ============================================================
def api_request(method, path, data=None, token=None):
    import urllib.request
    req = urllib.request.Request(BASE_URL + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    body = json.dumps(data).encode() if data is not None else None
    try:
        resp = urllib.request.urlopen(req, body, timeout=60)
        return resp.status, json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")[:500]


def login():
    st, r = api_request("POST", "/api/auth/login", {"username": USERNAME, "password": PASSWORD})
    if st != 200:
        print(f"[ERR] 登录失败: {r}")
        return None
    print("[OK] TradingAgents-CN 登录成功")
    return r["data"]["access_token"]


def submit_ai(token, symbol):
    is_hk = len(symbol) in (4, 5)  # 5 位数字为港股（如 09988）
    params = {
        "market_type": "港股" if is_hk else "A股",
        "llm_provider": "deepseek", "llm_model": "deepseek-chat",
        "analysts": ["market", "news", "fundamentals"], "research_depth": "标准",
    }
    st, r = api_request("POST", "/api/analysis/analyze", {"symbol": symbol, "parameters": params}, token)
    if st != 200:
        print(f"[ERR] {symbol} 提交失败: {r}")
        return None
    return r.get("task_id")


def get_ai_status(task_id):
    try:
        import redis
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        data = r.hgetall(f"qa:task:{task_id}")
        if data:
            return data.get("status"), data.get("result")
    except Exception:
        pass
    return None, None


def parse_ai_result(result_json):
    """从 AI 结果提取决策信息"""
    try:
        data = json.loads(result_json)
        ar = data.get("analysis_result", data)
        decision = ar.get("decision", {})
        if isinstance(decision, dict):
            return {
                "decision": decision.get("decision", "未知"),
                "reasoning": str(decision.get("decision_reasoning", ""))[:500],
                "confidence": decision.get("confidence"),
                "target_price": decision.get("target_price"),
                "stop_loss": decision.get("stop_loss"),
            }
        return {"decision": str(decision)[:200]}
    except Exception:
        return {"raw": str(result_json)[:500]}


def parse_ai_from_markdown(md):
    """从 MongoDB 报告 markdown 提取决策（与 parse_ai_result 结构一致）"""
    import re
    d = {"decision": "未知", "confidence": None, "target_price": None,
         "stop_loss": None, "reasoning": ""}
    m = re.search(r"\*\*投资建议\*\*\s*\|\s*([^\s|]+)", md)
    if m:
        d["decision"] = m.group(1).strip()
    m = re.search(r"\*\*置信度\*\*\s*\|\s*([\d.]+)%", md)
    if m:
        d["confidence"] = float(m.group(1))
    m = re.search(r"\*\*目标价位\*\*\s*\|\s*([\d.]+)", md)
    if m:
        d["target_price"] = float(m.group(1))
    m = re.search(r"###\s*分析推理\s*\n(.*?)(?:\n---|\n##|\Z)", md, re.S)
    if m:
        d["reasoning"] = m.group(1).strip()[:500]
    m = re.search(r"止损价\s*([\d.]+)", md)
    if m:
        d["stop_loss"] = float(m.group(1))
    return d


def get_latest_ai_from_mongo(symbol, retries=3):
    """从 MongoDB analysis_reports 取该股票最新 completed 报告并解析决策"""
    last_exc = None
    for attempt in range(retries):
        try:
            import pymongo
            client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
            db = client["tradingagentscn"]
            doc = db["analysis_reports"].find_one(
                {"stock_symbol": symbol, "status": "completed"},
                sort=[("timestamp", -1)],
            )
            if not doc:
                return {"found": False}
            md = (doc.get("reports") or {}).get("markdown", "")
            d = parse_ai_from_markdown(md)
            d["ai_date"] = str(doc.get("timestamp") or doc.get("analysis_date") or "")[:10]
            d["found"] = True
            return d
        except Exception as e:
            last_exc = e
            time.sleep(1)
    print(f"[AI] {symbol} MongoDB 查询失败: {last_exc}")
    return {"found": False}


def is_ai_fresh(ai_entry, max_age_days):
    """判断 AI 结果是否在有效期内"""
    if not ai_entry or not ai_entry.get("found"):
        return False
    d = ai_entry.get("ai_date", "")
    if not d:
        return False
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return (datetime.now() - dt).days <= max_age_days
    except Exception:
        return False


def run_ai_with_reuse(token, symbols, max_age_days=7, refresh_ai=False, timeout=5400):
    """AI 层：有效期内复用，否则重跑"""
    print(f"\n[AI] 处理 {len(symbols)} 只（有效期 {max_age_days} 天，"
          f"{'强制刷新' if refresh_ai else '仅当天复用/过期重跑'}）")
    results = {}
    to_run = []
    for sym in symbols:
        latest = get_latest_ai_from_mongo(sym)
        if not refresh_ai and is_ai_fresh(latest, max_age_days):
            results[sym] = {k: latest[k] for k in
                            ("decision", "reasoning", "confidence", "target_price", "stop_loss")}
            results[sym]["ai_date"] = latest["ai_date"]
            results[sym]["reused"] = True
            print(f"[AI] {sym} 复用最近分析（{latest['ai_date']}）")
        else:
            to_run.append(sym)
            print(f"[AI] {sym} 需要重新分析"
                  + (f"（最近 {latest.get('ai_date', '无')} 已过期）" if latest.get("found") else "（无历史结果）"))

    if to_run:
        print(f"[AI] 提交 {len(to_run)} 只新任务...")
        tasks = {}
        for sym in to_run:
            tid = submit_ai(token, sym)
            if tid:
                tasks[sym] = tid
                print(f"[AI] {sym} 已提交: {tid[:8]}...")
        if tasks:
            start = time.time()
            pending = set(tasks.keys())
            while pending and time.time() - start < timeout:
                time.sleep(90)
                for sym in list(pending):
                    status, result = get_ai_status(tasks[sym])
                    if status == "completed" and result:
                        results[sym] = parse_ai_result(result)
                        results[sym]["reused"] = False
                        results[sym]["ai_date"] = datetime.now().strftime("%Y-%m-%d")
                        print(f"[AI] OK {sym} 分析完成")
                        pending.discard(sym)
                    elif status == "failed":
                        results[sym] = {"error": (result or "任务失败")[:200]}
                        print(f"[AI] ERR {sym} 分析失败")
                        pending.discard(sym)
                    else:
                        print(f"[AI] {sym} {status}...")
            if pending:
                print(f"[WARN] 超时未完成: {pending}")
    return results


def sync_holdings(token, symbols):
    """只对目标股票做定向增量同步（不全市场全量）"""
    try:
        st, r = api_request("POST", "/api/stock-sync/batch",
                            {"symbols": symbols, "sync_historical": True,
                             "data_source": "akshare"}, token)
        if st == 200:
            d = r.get("data", {})
            hist = d.get("historical_sync", {})
            print(f"[SYNC] 定向同步完成: 历史 {hist.get('total_records', 0)} 条")
        else:
            print(f"[WARN] 同步失败: {r}")
    except Exception as e:
        print(f"[WARN] 同步异常: {e}")


# ============================================================
# AI 轮询（--round-robin）：持仓+自选池按周一到周五分桶，每只每周更新一次
# ============================================================
def load_old_combined():
    """读取上一次综合数据（轮询模式用于保留未轮到股票的旧 AI 结果）"""
    p = OUT / "combined_analysis.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_poll_pool(holdings_symbols):
    """AI 轮询池 = 持仓股（顺序在前） + 自选池 + 旧报告已有股票（去重）"""
    pool = list(holdings_symbols)
    for c in WATCH_STOCKS:
        if c not in pool:
            pool.append(c)
    old = load_old_combined()
    if old:
        for c in old.get("stocks", {}):
            if c not in pool:
                pool.append(c)
    return pool


def pick_ai_today(pool, old_ai):
    """按星期几分桶（周一=0 ... 周五=4）：今天只重跑 i%5==今天 的股票；
    无历史 AI 结果的新股票立即补跑，不等轮询。周末不轮询。"""
    weekday = datetime.now().weekday()
    if weekday >= 5:
        return [s for s in pool if not old_ai.get(s)]
    return [s for i, s in enumerate(pool) if i % 5 == weekday or not old_ai.get(s)]


# ============================================================
# 新闻/公告分析（复用 news-analysis 技能脚本）
# ============================================================
def run_news_analysis(symbols):
    """抓取标的股新闻/公告，返回 {code: [ {标题,时间,来源,影响标签,情绪,链接,现价,支撑,压力} ]}
    通过子进程调用 news-analysis/scripts/fetch_news.py，然后解析 output/新闻公告.csv"""
    import subprocess
    # news-analysis 技能在 .github/skills/ 下，与 stock-combined-analysis 同级
    news_script = SCRIPTS_DIR.parent.parent / "news-analysis" / "scripts" / "fetch_news.py"
    if not news_script.exists():
        print(f"[NEWS] 未找到 {news_script}，跳过新闻分析")
        return {}
    try:
        r = subprocess.run(
            [sys.executable, str(news_script), "--codes=" + ",".join(symbols)],
            capture_output=True, timeout=180)
        if r.returncode != 0:
            print(f"[NEWS] 抓取脚本退出码 {r.returncode}（继续解析已有输出）")
    except Exception as e:
        print(f"[NEWS] 抓取失败: {e}")
        return {}

    csv_path = OUT / "新闻公告.csv"
    if not csv_path.exists():
        print("[NEWS] 无新闻公告.csv，跳过")
        return {}
    df = pd.read_csv(csv_path)

    def _norm_code(v):
        """CSV 代码列可能是 float(600941.0)/空，统一成 6 位字符串"""
        try:
            return str(int(float(v))).zfill(6)
        except (ValueError, TypeError):
            return ""

    df["代码"] = df["代码"].apply(_norm_code)
    result = {}
    for code in symbols:
        sub = df[df["代码"] == code]
        items = []
        for _, r in sub.iterrows():
            items.append({
                "类型": str(r.get("类型", "")),
                "标题": str(r.get("标题", "")),
                "时间": str(r.get("时间", "")),
                "来源": str(r.get("来源", "")),
                "影响标签": str(r.get("影响标签", "")),
                "情绪": str(r.get("情绪", "中性")),
                "链接": str(r.get("链接", "")),
                "现价": r.get("现价"), "支撑": r.get("支撑"), "压力": r.get("压力"),
            })
        result[code] = items
    n_total = sum(len(v) for v in result.values())
    print(f"[NEWS] 完成，共 {n_total} 条新闻/公告")
    return result


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="股票综合双引擎 - 每日增量更新")
    parser.add_argument("symbols", nargs="*", help="股票代码（默认全部持仓股）")
    parser.add_argument("--refresh-ai", action="store_true", help="强制重跑所有 AI 分析")
    parser.add_argument("--max-age", type=int, default=0, help="AI 结果有效期（天），默认 0=仅当天复用、每天重新分析")
    parser.add_argument("--no-sync", action="store_true", help="跳过数据同步")
    parser.add_argument("--skip-report", action="store_true", help="只更新 JSON，不生成 HTML")
    parser.add_argument("--timeout", type=int, default=5400, help="AI 等待超时秒数")
    parser.add_argument("--round-robin", action="store_true",
                        help="AI 层按周一到周五轮询（每只每周更新一次）；量化/新闻仍每天全量")
    args = parser.parse_args()

    print("=" * 56)
    print("股票综合双引擎 - 每日增量更新")
    print("=" * 56)

    holdings = read_holdings()
    symbols = get_target_symbols(args.symbols, holdings)
    if not symbols:
        print("[ERR] 无分析标的")
        sys.exit(1)

    token = login()
    if not token:
        sys.exit(1)

    if not args.no_sync:
        sync_holdings(token, symbols)
    else:
        print("[SYNC] 跳过数据同步")

    print("\n[QUANT] 量化分析（每天更新）...")
    quant_data = {}
    for sym in symbols:
        pos = get_position_info(holdings, sym)
        q = quant_analysis(sym, pos)
        quant_data[sym] = q
        time.sleep(0.3)

    # 新闻/公告分析（消息面，辅助决策）
    print("\n[NEWS] 新闻/公告分析...")
    news_data = run_news_analysis(symbols)

    ai_data = {}
    if args.round_robin:
        # 轮询模式：只重跑今天轮到的股票，其余复用旧 AI 结果（量化/新闻仍每天全量更新）
        old = load_old_combined() or {}
        old_stocks = old.get("stocks", {})
        old_ai = {c: v.get("ai", {}) for c, v in old_stocks.items()
                  if isinstance(v, dict) and v.get("ai")}
        pool = get_poll_pool(symbols)
        if args.refresh_ai:
            today_ai = list(pool)
            print(f"[AI] --refresh-ai 覆盖轮询，重跑全部 {len(pool)} 只")
        else:
            today_ai = pick_ai_today(pool, old_ai)
            wd_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
            print(f"[AI] 轮询池 {len(pool)} 只；今天({wd_name})重跑 {len(today_ai)} 只: {today_ai}")
        # 轮到的股票：仅当天复用（max_age=0），避免同一天重复提交；--refresh-ai 则强制全跑
        ai_data = run_ai_with_reuse(token, today_ai, max_age_days=0,
                                    refresh_ai=args.refresh_ai, timeout=args.timeout)
        # 未轮到的：保留旧 AI 数据（标记复用）
        for c in pool:
            if c in ai_data:
                continue
            old_a = old_ai.get(c)
            if old_a:
                ai_data[c] = dict(old_a)
                ai_data[c]["reused"] = True
                print(f"[AI] {c} 未轮到，复用旧分析（{old_a.get('ai_date', '?')}）")
            else:
                print(f"[WARN] {c} 无 AI 结果且未轮到（新股票请手动 --refresh-ai 或指定代码分析）")
    else:
        ai_data = run_ai_with_reuse(token, symbols,
                                    max_age_days=args.max_age,
                                    refresh_ai=args.refresh_ai,
                                    timeout=args.timeout)

    old = load_old_combined() or {}
    merged = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "stocks": dict(old.get("stocks", {}))}
    for sym in symbols:
        merged["stocks"][sym] = {
            "quant": quant_data.get(sym, {}),
            "ai": ai_data.get(sym, {}),
            "news": news_data.get(sym, []),
        }
    # 自选股等不在持仓 symbols 里的：只更新 AI 字段（quant/news 保留旧数据）
    for c, a in ai_data.items():
        if c not in merged["stocks"]:
            merged["stocks"][c] = {}
        merged["stocks"][c]["ai"] = a

    out_path = OUT / "combined_analysis.json"
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] 综合数据已保存: {out_path}")

    print("\n" + "=" * 56)
    print("每日研判摘要")
    print("=" * 56)
    for sym in merged["stocks"]:
        stk = merged["stocks"][sym]
        q = stk.get("quant", {})
        a = stk.get("ai", {})
        tech = q.get("technical", {})
        q_sig = tech.get("signal", "-")
        ai_dec = a.get("decision", "无")
        ai_date = a.get("ai_date", "-")
        reused = "（复用" + ai_date + "）" if a.get("reused") else ""
        # 新闻情绪摘要
        n_items = stk.get("news", []) or []
        n_bad = sum(1 for it in n_items if it.get("情绪") == "利空")
        n_good = sum(1 for it in n_items if it.get("情绪") == "利好")
        news_s = f" | 新闻 {len(n_items)}条(利空{n_bad}/利好{n_good})" if n_items else ""
        print(f"  {sym}: 量化={q_sig} | AI={ai_dec}{reused}{news_s}")

    if not args.skip_report:
        print("\n[REPORT] 生成 HTML 报告...")
        # 复用 stock-combined-analysis 的构建脚本（共享同一输出格式）
        build = SCRIPTS_DIR.parent.parent / "stock-combined-analysis" / "scripts" / "build_combined_report.py"
        import subprocess
        r = subprocess.run([sys.executable, str(build)], capture_output=True,
                           text=True, encoding="utf-8", errors="ignore")
        if r.returncode == 0:
            for line in (r.stdout or "").strip().splitlines()[-3:]:
                print(f"  {line}")
        else:
            print(f"[ERR] 报告生成失败: {r.stderr[:300]}")
    print("\n[OK] 每日更新完成")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STOP] 用户中断")
    except Exception:
        traceback.print_exc()
