#!/usr/bin/env python3
"""
TradingAgents-CN 一键股票分析脚本
=================================
自动完成：登录 → 定向同步数据 → 提交分析 → 监控进度 → 输出结果

用法:
    python analyze_stocks.py 600030 600036 600941
    python analyze_stocks.py --no-sync 600030     # 跳过数据同步
    python analyze_stocks.py --deep 600030        # 深度分析

依赖: requests（或系统环境变量中的 urllib，本脚本使用 requests）
"""
import sys
import time
import json
import argparse
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # 股票/ 目录
sys.path.insert(0, str(PROJECT_ROOT))

BASE_URL = "http://127.0.0.1:8000"
REDIS_URL = "redis://:tradingagents123@127.0.0.1:6379/0"

USERNAME = "admin"
PASSWORD = "admin123"


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
        print(f"❌ 登录失败: {r}")
        sys.exit(1)
    print(f"✅ 登录成功: {USERNAME}")
    return r["data"]["access_token"]


def sync_stocks(token, symbols):
    st, r = api_request("POST", "/api/stock-sync/batch",
                        {"symbols": symbols, "sync_historical": True, "data_source": "akshare"}, token)
    if st == 200:
        d = r.get("data", {})
        hist = d.get("historical_sync", {})
        fin = d.get("financial_sync", {})
        print(f"✅ 数据同步完成: 历史 {hist.get('total_records', 0)} 条 | "
              f"财务 {fin.get('success_count', 0)}/{len(symbols)} 只")
    else:
        print(f"⚠️ 数据同步失败: {r}")


def submit_analysis(token, symbol, depth="标准"):
    params = {
        "market_type": "A股",
        "llm_provider": "deepseek",
        "llm_model": "deepseek-chat",
        "analysts": ["market", "news", "fundamentals"],
        "research_depth": depth,
    }
    st, r = api_request("POST", "/api/analysis/analyze",
                        {"symbol": symbol, "parameters": params}, token)
    if st != 200:
        print(f"❌ {symbol} 提交失败: {r}")
        return None
    task_id = r.get("task_id")
    print(f"📤 {symbol} 已提交, task_id={task_id}")
    return task_id


def get_task_status(symbol, task_id):
    """从 Redis 读取任务状态（Worker 在 Redis 中更新）"""
    try:
        import redis
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        data = r.hgetall(f"qa:task:{task_id}")
        if data:
            return data.get("status"), data.get("result")
    except Exception as e:
        print(f"⚠️ Redis 读取失败: {e}")
    return None, None


def read_holdings(holdings_file=None):
    """读取同花顺导出的持仓文件，提取股票代码"""
    import pandas as pd
    path = holdings_file or str(PROJECT_ROOT / "持仓.xls")
    if not Path(path).exists():
        print(f"❌ 未找到持仓文件: {path}")
        sys.exit(1)
    # 同花顺持仓文件实际是 GBK 编码的制表符分隔文本
    df = pd.read_csv(path, sep="\t", encoding="gbk")
    print(f"📋 读取持仓: {len(df)} 条")
    print(df[["证券代码", "证券名称", "市值", "仓位占比(%)"]].to_string(index=False))
    # 提取 6 位数字股票代码，跳过 ETF 等
    symbols = []
    for code in df["证券代码"].astype(str):
        code = code.zfill(6)
        if code.isdigit() and len(code) == 6:
            symbols.append(code)
    print(f"📌 待分析股票: {symbols}")
    return symbols


def export_reports(token, output_dir=None, format="markdown"):
    """导出最近的分析报告"""
    import urllib.request
    output_dir = output_dir or str(PROJECT_ROOT / "output")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    st, r = api_request("GET", "/api/reports/list", token=token)
    if st != 200:
        print(f"❌ 报告列表获取失败: {r}")
        return

    reports = r.get("data", {}).get("reports", r.get("data", []))
    if isinstance(reports, dict):
        reports = reports.get("items", [])
    if not reports:
        print("ℹ️ 暂无分析报告")
        return

    print(f"📄 找到 {len(reports)} 份报告:")
    for rep in reports[:10]:
        rep_id = rep.get("id") or rep.get("_id")
        symbol = rep.get("stock_symbol", "?")
        print(f"  {rep_id} | {symbol}")

    # 导出最近一份
    rep = reports[0]
    rep_id = rep.get("id") or rep.get("_id")
    symbol = rep.get("stock_symbol", "stock")
    fname = f"{symbol}_report.{'md' if format == 'markdown' else format}"
    out_path = Path(output_dir) / fname
    url = f"{BASE_URL}/api/reports/{rep_id}/download?format={format}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        with open(out_path, "wb") as f:
            f.write(resp.read())
        print(f"✅ 报告已导出: {out_path}")
    except Exception as e:
        print(f"❌ 报告导出失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="TradingAgents-CN 一键分析")
    parser.add_argument("symbols", nargs="*", help="股票代码，如 600030")
    parser.add_argument("--holdings", action="store_true", help="分析持仓.xls 中的持仓股")
    parser.add_argument("--holdings-file", type=str, help="自定义持仓文件路径")
    parser.add_argument("--no-sync", action="store_true", help="跳过数据同步")
    parser.add_argument("--deep", action="store_true", help="深度分析")
    parser.add_argument("--export", choices=["markdown", "docx", "pdf", "json"], help="导出最近报告")
    parser.add_argument("--timeout", type=int, default=3600, help="最大等待秒数")
    args = parser.parse_args()

    if args.export:
        token = login()
        export_reports(token, format=args.export)
        return

    if args.holdings:
        symbols = read_holdings(args.holdings_file)
    else:
        symbols = [s.zfill(6) for s in args.symbols]

    if not symbols:
        parser.print_help()
        sys.exit(1)

    depth = "深度" if args.deep else "标准"

    print("=" * 60)
    print("🚀 TradingAgents-CN 股票分析")
    print("=" * 60)

    token = login()

    if not args.no_sync:
        sync_stocks(token, symbols)

    # 提交任务
    tasks = {}
    for sym in symbols:
        tid = submit_analysis(token, sym, depth)
        if tid:
            tasks[sym] = tid

    if not tasks:
        print("❌ 没有任务提交成功")
        sys.exit(1)

    # 监控进度
    print("\n📡 监控分析进度（每 60 秒检查一次）...")
    start = time.time()
    pending = set(tasks.keys())
    results = {}

    while pending and time.time() - start < args.timeout:
        time.sleep(60)
        for sym in list(pending):
            status, result = get_task_status(sym, tasks[sym])
            if status == "completed" and result:
                results[sym] = result
                print(f"✅ {sym} 分析完成")
                pending.discard(sym)
            elif status == "failed":
                print(f"❌ {sym} 分析失败: {(result or '')[:200]}")
                pending.discard(sym)
            elif status == "processing":
                print(f"⏳ {sym} 分析中...")
            # queued/None 继续等待

    # 输出结果
    print("\n" + "=" * 60)
    print("📊 分析结果")
    print("=" * 60)
    for sym, result in results.items():
        try:
            data = json.loads(result)
            decision = data.get("analysis_result", {}).get("decision", {})
            print(f"\n【{sym}】")
            print(f"  决策: {decision.get('decision', '未知')}")
            print(f"  理由: {str(decision.get('decision_reasoning', ''))[:300]}")
        except Exception as e:
            print(f"\n【{sym}】原始结果: {str(result)[:500]}")

    if not results:
        print("⚠️ 超时或未获取到结果，请检查 Worker 日志：TradingAgents-CN\\.dbs\\worker*.log")


if __name__ == "__main__":
    main()
