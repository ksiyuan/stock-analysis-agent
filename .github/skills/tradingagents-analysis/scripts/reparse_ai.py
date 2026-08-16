# -*- coding: utf-8 -*-
"""重新解析 watchlist 全部任务的 AI 决策（修复 action/confidence 解析后）并合并"""
import sys, os, json, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import redis

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
_pos = [a for a in sys.argv[1:] if not a.startswith('--')]
if _pos:
    BASE = _pos[0]
OUT = os.path.join(BASE, "output")
r = redis.Redis.from_url("redis://:tradingagents123@127.0.0.1:6379/0", decode_responses=True)


def parse_result(result_json):
    try:
        data = json.loads(result_json)
    except Exception:
        return {"raw": str(result_json)[:300]}
    ar = data.get("analysis_result", data)
    decision = ar.get("decision", {})
    if isinstance(decision, dict):
        dec = decision.get("decision") or decision.get("action") or "未知"
        conf = decision.get("confidence")
        try:
            if conf is not None and 0 < float(conf) <= 1:
                conf = round(float(conf) * 100, 1)
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


def main():
    tasks = json.load(open(os.path.join(OUT, "watchlist_tasks.json"), encoding="utf-8"))
    # 合并到 combined_ai.json
    ai_path = os.path.join(OUT, "combined_ai.json")
    existing = json.load(open(ai_path, encoding="utf-8")) if os.path.exists(ai_path) else {}
    for sym, tid in tasks.items():
        raw = r.hget(f"qa:task:{tid}", "result")
        status = r.hget(f"qa:task:{tid}", "status")
        if not raw or status != "completed":
            print(f"[SKIP] {sym} status={status}")
            continue
        res = parse_result(raw)
        res["ai_date"] = time.strftime("%Y-%m-%d")
        res["reused"] = False
        existing[sym] = res
        print(f"[OK] {sym}: {res['decision']} 目标{res['target_price']} 置信{res['confidence']}%")
    with open(ai_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=1)
    print(f"[OK] combined_ai.json 已更新（共 {len(existing)} 只）")

    # 同步 combined_analysis.json
    ca_path = os.path.join(OUT, "combined_analysis.json")
    if os.path.exists(ca_path):
        ca = json.load(open(ca_path, encoding="utf-8"))
        for sym, res in existing.items():
            if "raw" in res or "error" in res:
                continue
            if sym not in ca.get("stocks", {}):
                ca["stocks"][sym] = {"quant": {}, "ai": {}, "news": []}
            ca["stocks"][sym]["ai"] = res
        with open(ca_path, "w", encoding="utf-8") as f:
            json.dump(ca, f, ensure_ascii=False, indent=1)
        print("[OK] combined_analysis.json 已同步")


if __name__ == "__main__":
    main()
