# -*- coding: utf-8 -*-
"""
股票综合双引擎分析 - 主编排
================================
流程：读持仓 → 量化分析(技术面+估值+持仓) → 提交TradingAgents AI分析 → 监控 → 合并JSON

用法:
    python combined_analysis.py               # 默认分析全部持仓股
    python combined_analysis.py 600030 600036 # 指定股票
    python combined_analysis.py --skip-quant  # 跳过量化（用已有缓存）
    python combined_analysis.py --skip-ai     # 跳过AI（用已有AI结果）
    python combined_analysis.py --timeout 5400

输出: output/combined_analysis.json
"""
import os
import sys
import json
import time
import argparse
import traceback
from pathlib import Path

import pandas as pd
import numpy as np

# ---------- 路径 ----------
SCRIPTS_DIR = Path(__file__).resolve().parent
BASE = SCRIPTS_DIR.parents[3]          # 股票/ 工作区根
OUT = BASE / "output"
PROJECT = BASE / "TradingAgents-CN"    # TradingAgents-CN 目录

# TradingAgents-CN API
BASE_URL = "http://127.0.0.1:8000"
REDIS_URL = "redis://:tradingagents123@127.0.0.1:6379/0"
USERNAME = "admin"
PASSWORD = "admin123"

# 持仓文件
POS_FILE = BASE / "持仓.xls"

os.makedirs(OUT, exist_ok=True)


# ============================================================
# 持仓读取
# ============================================================
def read_holdings():
    """读取同花顺持仓，返回 DataFrame"""
    if not POS_FILE.exists():
        print(f"[WARN] 未找到持仓文件: {POS_FILE}")
        return None
    # 同花顺 .xls 是 GBK 编码 + Tab 分隔文本
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
        # 剔除 ETF/基金（沪 5 开头，深 1 开头基金，或名称含 ETF/基金/LOF）
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
    # 1) 新浪（稳定）
    try:
        df = ak.stock_zh_a_daily(symbol=sh, start_date=start, end_date=end, adjust="qfq")
        df = df.rename(columns={"date": "trade_date"})
        return df[["trade_date", "open", "high", "low", "close", "volume", "amount"]], "sina"
    except Exception:
        pass
    # 2) 东财（功能全，失败回退）
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
    # MA
    d["MA5"] = close.rolling(5).mean()
    d["MA10"] = close.rolling(10).mean()
    d["MA20"] = close.rolling(20).mean()
    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    d["DIF"] = ema12 - ema26
    d["DEA"] = d["DIF"].ewm(span=9, adjust=False).mean()
    d["MACD"] = (d["DIF"] - d["DEA"]) * 2
    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    d["RSI"] = 100 - 100 / (1 + rs)
    # KDJ
    low9 = d["low"].rolling(9).min()
    high9 = d["high"].rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    d["K"] = rsv.ewm(com=2, adjust=False).mean()
    d["D"] = d["K"].ewm(com=2, adjust=False).mean()
    d["J"] = 3 * d["K"] - 2 * d["D"]
    # BOLL(20,2)
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
    # 均线
    if pd.notna(last["MA20"]):
        if c > last["MA20"]:
            points.append("站上20日线")
        else:
            points.append("跌破20日线")
    # MACD
    if pd.notna(prev["DIF"]) and pd.notna(last["DIF"]):
        if prev["DIF"] <= prev["DEA"] and last["DIF"] > last["DEA"]:
            points.append("MACD金叉")
        elif prev["DIF"] >= prev["DEA"] and last["DIF"] < last["DEA"]:
            points.append("MACD死叉")
    # RSI
    if pd.notna(last["RSI"]):
        if last["RSI"] > 70:
            points.append(f"RSI超买({last['RSI']:.0f})")
        elif last["RSI"] < 30:
            points.append(f"RSI超卖({last['RSI']:.0f})")
    # BOLL
    if pd.notna(last["BOLL_UP"]) and pd.notna(last["BOLL_LOW"]):
        pos = (c - last["BOLL_LOW"]) / (last["BOLL_UP"] - last["BOLL_LOW"])
        if pos > 0.9:
            points.append("触及布林上轨")
        elif pos < 0.1:
            points.append("触及布林下轨")
    # 60日区间
    if len(d) >= 60:
        hi60 = d["close"].tail(60).max()
        lo60 = d["close"].tail(60).min()
        pct = (c - lo60) / (hi60 - lo60) * 100 if hi60 > lo60 else 50
        points.append(f"60日区间位置{pct:.0f}%")
    # 趋势：MA5 vs MA20
    if pd.notna(last["MA5"]) and pd.notna(last["MA20"]):
        points.append("短中期均线多头" if last["MA5"] > last["MA20"] else "短中期均线空头")

    signal = "偏多" if (last["MA5"] > last["MA20"] and c > last["MA20"]) else \
             ("偏空" if (last["MA5"] < last["MA20"] and c < last["MA20"]) else "震荡")
    return {
        "signal": signal,
        "points": points,
        "last_close": round(float(c), 2),
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

    return {
        "symbol": symbol,
        "technical": tech,
        "valuation": val,
        "position": position,
    }


# ============================================================
# TradingAgents AI 分析
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
    params = {
        "market_type": "A股",
        "llm_provider": "deepseek",
        "llm_model": "deepseek-chat",
        "analysts": ["market", "news", "fundamentals"],
        "research_depth": "标准",
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


def run_ai_analysis(token, symbols, timeout=5400):
    """提交并监控 AI 分析"""
    print(f"\n[AI] 提交 {len(symbols)} 只股票的 TradingAgents 分析...")
    tasks = {}
    for sym in symbols:
        tid = submit_ai(token, sym)
        if tid:
            tasks[sym] = tid
            print(f"[AI] {sym} 已提交: {tid[:8]}...")

    if not tasks:
        print("[ERR] 所有 AI 任务提交失败")
        return {}

    print(f"[AI] 监控中（每 90 秒检查，超时 {timeout}s）...")
    start = time.time()
    results = {}
    pending = set(tasks.keys())

    while pending and time.time() - start < timeout:
        time.sleep(90)
        for sym in list(pending):
            status, result = get_ai_status(tasks[sym])
            if status == "completed" and result:
                results[sym] = parse_ai_result(result)
                print(f"[AI] ✅ {sym} 分析完成")
                pending.discard(sym)
            elif status == "failed":
                results[sym] = {"error": (result or "任务失败")[:200]}
                print(f"[AI] ❌ {sym} 分析失败")
                pending.discard(sym)
            else:
                print(f"[AI] {sym} {status}...")

    if pending:
        print(f"[WARN] 超时未完成: {pending}")
    return results


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="股票综合双引擎分析")
    parser.add_argument("symbols", nargs="*", help="股票代码（默认全部持仓股）")
    parser.add_argument("--skip-quant", action="store_true", help="跳过量化分析（用已有JSON）")
    parser.add_argument("--skip-ai", action="store_true", help="跳过AI分析")
    parser.add_argument("--timeout", type=int, default=5400, help="AI分析超时秒数")
    args = parser.parse_args()

    print("=" * 56)
    print("股票综合双引擎分析（量化 + AI）")
    print("=" * 56)

    holdings = read_holdings()
    symbols = get_target_symbols(args.symbols, holdings)

    merged = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "stocks": {}}

    # ---- 量化层 ----
    quant_path = OUT / "combined_quant.json"
    if args.skip_quant and quant_path.exists():
        quant_data = json.loads(quant_path.read_text(encoding="utf-8"))
        print("[OK] 使用已有量化数据")
    else:
        quant_data = {}
        for sym in symbols:
            pos = get_position_info(holdings, sym)
            q = quant_analysis(sym, pos)
            quant_data[sym] = q
            time.sleep(0.5)
        quant_path.write_text(json.dumps(quant_data, ensure_ascii=False, indent=1),
                              encoding="utf-8")
        print(f"[OK] 量化数据已保存: {quant_path}")

    # ---- AI 层 ----
    ai_data = {}
    if not args.skip_ai:
        token = login()
        if token:
            ai_data = run_ai_analysis(token, symbols, timeout=args.timeout)
            ai_path = OUT / "combined_ai.json"
            ai_path.write_text(json.dumps(ai_data, ensure_ascii=False, indent=1),
                               encoding="utf-8")
            print(f"[OK] AI结果已保存: {ai_path}")
    else:
        ai_path = OUT / "combined_ai.json"
        if ai_path.exists():
            ai_data = json.loads(ai_path.read_text(encoding="utf-8"))
            print("[OK] 使用已有AI结果")

    # ---- 合并 ----
    for sym in symbols:
        merged["stocks"][sym] = {
            "quant": quant_data.get(sym, {}),
            "ai": ai_data.get(sym, {}),
        }

    out_path = OUT / "combined_analysis.json"
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] 综合数据已保存: {out_path}")
    print(f"[NEXT] 生成报告: python .github\\skills\\stock-combined-analysis\\scripts\\build_combined_report.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STOP] 用户中断")
    except Exception:
        traceback.print_exc()
