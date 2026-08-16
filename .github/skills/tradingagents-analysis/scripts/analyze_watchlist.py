# -*- coding: utf-8 -*-
"""
自选股 TradingAgents AI 分析（后台长跑）— tradingagents 技能版
针对自选池中尚未做过 AI 分析的个股（002371/600584/000977/601138/002916/002028）及港股（09988）
流程：登录 → 定向同步(A股) → 提交 → 监控(Redis) → 解析结果 → 合并 combined_ai.json/combined_analysis.json → 重新生成本地 HTML 报告
特点：
  - 港股支持：5位数字代码（如 09988）自动用 market_type="港股"
  - 任务复用：watchlist_tasks.json 里已有 task_id 不重复提交（省 API 费用）
  - 结果合并：自动合并到 output/combined_ai.json 并同步 combined_analysis.json，重新生成 分析报告/持仓自选综合分析.html

用法：
  python analyze_watchlist.py                  # 默认自选池
  python analyze_watchlist.py --codes=600030,09988   # 指定代码
  python analyze_watchlist.py --submit          # 只提交任务，不监控
  python analyze_watchlist.py --timeout 7200
"""
import os
import sys
import json
import time
import argparse
import subprocess

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
OUT = os.path.join(BASE, "output")
# 仅接受不带 -- 的位置参数作为工作区路径（--submit/--codes 等不能误当路径）
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
if _pos:
    BASE = _pos[0]
    OUT = os.path.join(BASE, "output")
BASE_URL = "http://127.0.0.1:8000"
REDIS_URL = "redis://:tradingagents123@127.0.0.1:6379/0"
USERNAME, PASSWORD = "admin", "admin123"

WATCH_STOCKS = ["002371", "600584", "000977", "601138", "002916", "002028", "09988"]  # 自选池个股（含港股阿里巴巴 09988）


def api_request(method, path, data=None, token=None, timeout=90):
    import urllib.request
    req = urllib.request.Request(BASE_URL + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    body = json.dumps(data).encode() if data is not None else None
    try:
        resp = urllib.request.urlopen(req, body, timeout=timeout)
        return resp.status, json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")[:500]
    except Exception as e:
        return None, str(e)


def login():
    st, r = api_request("POST", "/api/auth/login", {"username": USERNAME, "password": PASSWORD})
    if st != 200:
        print(f"[ERR] 登录失败: {r}")
        sys.exit(1)
    print("[OK] 登录成功")
    return r["data"]["access_token"]


def sync_stocks(token, symbols):
    # 港股代码（5位数字/.HK）由分析时的 HKDataService 自动获取，此处只同步 A 股
    a_symbols = [s for s in symbols if s.isdigit() and len(s) == 6]
    if not a_symbols:
        print("[SYNC] 无可同步的 A 股代码（港股自动获取）")
        return
    st, r = api_request("POST", "/api/stock-sync/batch",
                        {"symbols": a_symbols, "sync_historical": True, "data_source": "akshare"}, token)
    if st == 200:
        d = r.get("data", {})
        hist = d.get("historical_sync", {})
        fin = d.get("financial_sync", {})
        print(f"[SYNC] 完成: 历史 {hist.get('total_records', 0)} 条 | 财务 {fin.get('success_count', '?')}/{len(a_symbols)}")
    else:
        print(f"[WARN] 同步失败: {str(r)[:200]}")


def is_hk(symbol):
    """港股判断：5位数字（如 09988）或 .HK 后缀"""
    return symbol.upper().endswith(".HK") or (symbol.isdigit() and len(symbol) in (4, 5))


def submit(token, symbol):
    market_type = "港股" if is_hk(symbol) else "A股"
    params = {
        "market_type": market_type, "llm_provider": "deepseek", "llm_model": "deepseek-chat",
        "analysts": ["market", "news", "fundamentals"], "research_depth": "标准",
    }
    st, r = api_request("POST", "/api/analysis/analyze", {"symbol": symbol, "parameters": params}, token, timeout=60)
    if st != 200:
        print(f"[ERR] {symbol}({market_type}) 提交失败: {str(r)[:200]}")
        return None
    tid = r.get("task_id")
    print(f"[SUBMIT] {symbol} ({market_type}) -> {tid}")
    return tid


def get_status(task_id):
    try:
        import redis
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        data = r.hgetall(f"qa:task:{task_id}")
        if data:
            return data.get("status"), data.get("result")
    except Exception as e:
        print(f"[WARN] Redis 读取失败: {e}")
    return None, None


def parse_result(result_json):
    """解析 AI 结果，提取决策（兼容多种结构：decision 或 action 字段）"""
    try:
        data = json.loads(result_json)
    except Exception:
        return {"raw": str(result_json)[:300]}
    ar = data.get("analysis_result", data)
    decision = ar.get("decision", {})
    if isinstance(decision, dict):
        # 兼容两种键名：decision（持仓股）或 action（自选股 SignalProcessor 输出）
        dec = decision.get("decision") or decision.get("action") or "未知"
        conf = decision.get("confidence")
        try:
            if conf is not None and 0 < float(conf) <= 1:
                conf = round(float(conf) * 100, 1)  # 0.75 -> 75.0(%)
        except (ValueError, TypeError):
            pass
        return {
            "decision": dec,
            "reasoning": str(decision.get("decision_reasoning") or decision.get("reasoning") or "")[:500],
            "confidence": conf,
            "target_price": decision.get("target_price"),
            "stop_loss": decision.get("stop_loss"),
        }
    return {"decision": str(decision)[:100]}


def monitor(tasks, timeout=7200):
    """轮询 Redis 直到全部完成，返回 {symbol: ai_result}"""
    results = {}
    start = time.time()
    pending = dict(tasks)
    while pending and time.time() - start < timeout:
        time.sleep(60)
        for sym in list(pending.keys()):
            status, result = get_status(pending[sym])
            if status == "completed" and result:
                results[sym] = parse_result(result)
                results[sym]["ai_date"] = time.strftime("%Y-%m-%d")
                results[sym]["reused"] = False
                print(f"[DONE] {sym} 分析完成")
                pending.pop(sym)
            elif status == "failed":
                results[sym] = {"error": (result or "任务失败")[:300]}
                print(f"[ERR] {sym} 分析失败: {str(result)[:150]}")
                pending.pop(sym)
            else:
                print(f"[WAIT] {sym} {status}...（已 {int((time.time()-start)/60)} 分钟）")
    if pending:
        print(f"[WARN] 超时未完成: {list(pending.keys())}")
    return results


def merge_and_report(ai_results):
    """合并结果到 combined_ai.json，并重新生成综合报告"""
    # 合并到 combined_ai.json
    ai_path = os.path.join(OUT, "combined_ai.json")
    existing = {}
    if os.path.exists(ai_path):
        with open(ai_path, encoding="utf-8") as f:
            existing = json.load(f)
    for sym, res in ai_results.items():
        if "error" in res:
            continue
        existing[sym] = res
    with open(ai_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=1)
    print(f"[OK] combined_ai.json 已更新（共 {len(existing)} 只）")

    # 同步到 combined_analysis.json 的 ai 字段
    ca_path = os.path.join(OUT, "combined_analysis.json")
    if os.path.exists(ca_path):
        with open(ca_path, encoding="utf-8") as f:
            ca = json.load(f)
        for sym, res in ai_results.items():
            if "error" in res:
                continue
            if sym not in ca.get("stocks", {}):
                ca["stocks"][sym] = {"quant": {}, "ai": {}, "news": []}
            ca["stocks"][sym]["ai"] = res
        with open(ca_path, "w", encoding="utf-8") as f:
            json.dump(ca, f, ensure_ascii=False, indent=1)
        print("[OK] combined_analysis.json 已同步")

    # 重新生成本地 HTML 综合分析报告
    report_script = os.path.join(BASE, ".github", "skills", "stock-analysis", "scripts", "build_portfolio_analysis.py")
    if os.path.exists(report_script):
        subprocess.run([sys.executable, report_script], cwd=BASE, timeout=120)
    else:
        subprocess.run([sys.executable, os.path.join(OUT, "build_portfolio_analysis.py")], cwd=BASE, timeout=120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true", help="只提交任务不监控")
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--codes", help="指定代码列表（逗号分隔，如 600030,09988），默认用自选池 WATCH_STOCKS")
    args = parser.parse_args()

    watch = args.codes.split(",") if args.codes else WATCH_STOCKS
    watch = [c.strip() for c in watch if c.strip()]
    print(f"[OK] 目标 {len(watch)} 只: {watch}")

    token = login()

    # 优先复用已提交的 task_ids（避免重复提交浪费 API 费用）
    tasks = {}
    tasks_path = os.path.join(OUT, "watchlist_tasks.json")
    if os.path.exists(tasks_path):
        with open(tasks_path, encoding="utf-8") as f:
            saved = json.load(f)
        if saved:
            # 全部任务都纳入（已 completed 的由 monitor 首轮立即解析合并）
            tasks = dict(saved)
            print(f"[OK] 复用已提交任务（{len(tasks)} 个）: {list(tasks.keys())}")

    if not tasks:
        sync_stocks(token, watch)
        for sym in watch:
            tid = submit(token, sym)
            if tid:
                tasks[sym] = tid
            time.sleep(1)
        if not tasks:
            print("[ERR] 全部提交失败")
            sys.exit(1)
        with open(tasks_path, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=1)
        print(f"[OK] 已提交 {len(tasks)} 个任务")
    else:
        # 已有部分任务：只补提交缺失的（如新增港股阿里巴巴）
        new_added = False
        for sym in watch:
            if sym in tasks:
                continue
            tid = submit(token, sym)
            if tid:
                tasks[sym] = tid
                new_added = True
            time.sleep(1)
        if new_added:
            with open(tasks_path, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=1)
            print(f"[OK] 补充提交完成，当前共 {len(tasks)} 个任务")

    if args.submit:
        print("[OK] 仅提交模式，task_ids 已在 watchlist_tasks.json")
        return

    print("[MONITOR] 开始监控（每 60 秒轮询，预计 15-20 分钟/只）...")
    results = monitor(tasks, timeout=args.timeout)
    if results:
        merge_and_report(results)
    print("[DONE] 全部流程完成")


if __name__ == "__main__":
    main()
