# -*- coding: utf-8 -*-
"""
一键执行完整股票分析流水线（Python 版本，无编码坑）
用法:
  python run_all.py                 # 完整流程（含行情/估值获取）
  python run_all.py --skip-market   # 跳过行情获取（用已有缓存）
  python run_all.py --skip-valuation
  python run_all.py --base "D:\股票"   # 指定工作区
  python run_all.py --keep-going    # 某步失败继续

流程: 行情 -> 估值 -> 账户盈亏 -> 技术面 -> 亏损复盘 -> 成本 -> 报告打包
"""
import os
import subprocess
import sys

# ---------- 路径 ----------
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", "..", "..", ".."))
OUT = os.path.join(BASE, "output")


def parse_args():
    args = {"skip_market": False, "skip_valuation": False,
            "keep_going": False, "base": BASE}
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--skip-market":
            args["skip_market"] = True
        elif a == "--skip-valuation":
            args["skip_valuation"] = True
        elif a == "--keep-going":
            args["keep_going"] = True
        elif a == "--base" and i + 1 < len(argv):
            args["base"] = argv[i + 1]
            i += 1
        elif a.startswith("--base="):
            args["base"] = a.split("=", 1)[1]
        i += 1
    return args


def main():
    args = parse_args()
    base = args["base"]
    out = os.path.join(base, "output")
    os.makedirs(out, exist_ok=True)

    # Python 解释器：优先工作区 .venv
    venv_py = os.path.join(base, ".venv", "Scripts", "python.exe")
    py = venv_py if os.path.exists(venv_py) else sys.executable

    pos_file = os.path.join(base, "持仓.xls")
    tr_file = os.path.join(base, "交易记录.xls")

    print("=" * 56)
    print("股票账户综合分析 - 一键流水线")
    print("=" * 56)
    print(f"工作区 : {base}")
    print(f"输出目录: {out}")
    print(f"Python : {py}")
    print()

        ("1/15 获取行情",         "fetch_market.py",         args["skip_market"], False, []),
        ("2/15 获取估值",         "fetch_valuation.py",      args["skip_valuation"], False, []),
        ("3/15 财报分析(A股)",    "fetch_financials.py",     False, False, []),
        ("4/15 美股财报(中美联动)", "fetch_financials.py",   False, False,
         ["--codes=AMAT:us:应用材料,FRO:us:Frontline"]),
        ("5/15 新闻公告",         "fetch_news.py",           False, False, []),
        ("6/15 账户盈亏",         "account_analysis.py",     False, True, []),
        ("7/15 技术面分析",       "technical_analysis.py",   False, False, []),
        ("8/15 股息数据",         "fetch_dividend.py",       False, False, []),
        ("9/15 涨幅透支",         "fetch_price_history.py",  False, False, []),
        ("10/15 量价分析",        "fetch_volume_price.py",   False, False, []),
        ("11/15 中美联动对比",    "fetch_global_market.py",  False, False, []),
        ("12/15 亏损复盘",        "loss_review.py",          False, False, []),
        ("13/15 成本分析",        "cost_analysis.py",        False, False, []),
        ("14/15 生成报告+打包",   "build_report.py",         False, False, []),
        ("15/15 持仓自选综合",    "build_portfolio_analysis.py", False, False, []),
    ]

    failed = []
    for name, script, skip, need_files, extra_args in steps:
        print(f">>> {name} ...")
        if skip:
            print("    [跳过]")
            continue
        if need_files and (not os.path.exists(pos_file) or not os.path.exists(tr_file)):
            print("    [错误] 缺少同花顺导出文件: 持仓.xls / 交易记录.xls")
            if not args["keep_going"]:
                sys.exit(1)
            failed.append(name)
            continue
        script_path = os.path.join(SCRIPTS_DIR, script)
        cmd = [py, script_path, base, out] + list(extra_args)
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"    [失败] {name} (exit={r.returncode})")
            if not args["keep_going"]:
                print("提示: 可用 --keep-going 让失败后继续执行")
                sys.exit(1)
            failed.append(name)
        else:
            print("    [完成]")

    print()
    print("=" * 56)
    if not failed:
        print("全部步骤完成！")
        print(f"报告: {os.path.join(out, '账户综合分析报告.html')}")
        print(f"打包: {os.path.join(base, '账户分析打包.zip')}")
    else:
        print(f"有步骤失败: {', '.join(failed)}")
    print("=" * 56)


if __name__ == "__main__":
    main()
