# AGENTS.md — A 股股票分析 Copilot Agent

基于 **VS Code Copilot Skills + AkShare** 的 A 股持仓/自选股量化分析项目。本文件是 AI 代理的「着陆页」，只收录最关键的、不易被发现的约定；详细流程一律链接到技能与记忆文件，不在此重复。

## 项目概览

- 全貌与部署见 [README.md](README.md)。
- 核心知识在技能与记忆里，动手前先查：
  - `.github/skills/*/SKILL.md` — 6 个技能的完整流程 + 用户交易策略 + 全部历史踩坑
  - `/memories/repo/stock-data-network.md` — 网络/编码/口径/踩坑速查（最重要）
  - `.github/instructions/股票数据获取.instructions.md` — 数据源优先级 / AkShare 接口（applyTo `**/*.py`，写 .py 时自动生效）
  - `.github/instructions/报告输出规范.instructions.md` — 报告输出位置 / 必备内容 / 格式约定（applyTo `分析报告/**`）
  - `.github/agents/报告审查.agent.md` — 报告交付前按用户策略核查评级逻辑的只读审查代理

## 架构：技能体系

| 任务 | 技能 | 主要脚本 |
|---|---|---|
| 持仓/财报/技术分析/复盘/报告 | `stock-analysis` | `scripts/run_all.py`（15 步流水线）、`common.py` |
| 新闻公告抓取+情绪打分 | `news-analysis` | `scripts/fetch_news.py` |
| 量化+AI 双引擎综合/每日更新 | `stock-combined-analysis` | `scripts/daily_update.py`、`combined_analysis.py` |
| TradingAgents-CN 多智能体 AI 研判 | `tradingagents-analysis` | `scripts/analyze_stocks.py`、`analyze_watchlist.py` |
| 沉淀新经验 / 技能去重 | `skill-auto-update` / `skill-merge` | 流程指导，无脚本 |

按任务关键词触发对应技能；任务结束后按 `skill-auto-update` 流程把新坑/新口径写回 SKILL.md 与 `/memories/repo/`。

## 运行（最重要）

- **解释器**：一律用工作区根 `.venv\Scripts\python.exe`（Python 3.12.10），不要用系统 Python；TradingAgents-CN 有独立 `.venv/`，勿混用。
- **脚本**：优先 `.github/skills/<技能>/scripts/` 下的规范版；`output/` 根目录里的同名/历史脚本（`account_analysis.py`、`technical_analysis.py` 等）是早期调试副本，**不要误用**。
- **输出位置**：最终报告 → `分析报告/`；中间数据（CSV/JSON/pkl/图表）→ `output/`。

```powershell
.\.venv\Scripts\python.exe ".github\skills\stock-analysis\scripts\run_all.py"
.\.venv\Scripts\python.exe ".github\skills\news-analysis\scripts\fetch_news.py --codes=600030,600036"
```

## 高频约定（易踩坑，务必遵守）

- **编码**：源码 UTF-8；控制台 print 用 `[OK]`/`[FAIL]`（Windows GBK 控制台不支持 emoji）；CSV 写出 `utf-8-sig`；同花顺导出 `.xls` 是「假 xls」（GBK+Tab 分隔），用 `pd.read_csv(sep='\t', encoding='gbk')` 解析；`.ps1` 含中文必须存 **UTF-8 带 BOM**。
- **股票代码**：A 股统一 `.astype(str).str.zfill(6)` 补前导零；美股代码不补零。
- **网络**：系统代理 `127.0.0.1:7897`（Clash），**禁止 `NO_PROXY=*` 直连**；东财接口时通时断，必须 3 次重试 + 失败回退新浪数据源（封装在技能 `common.py`）。
- **脚本参数**：用 `_pos=[a for a in sys.argv[1:] if not a.startswith("--")]` 过滤，否则 `--codes=xxx` 会被当成输出路径、写到错误目录。
- **依赖安装**：pip 用清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
- **口径**：已实现盈亏用「发生金额」移动加权（红股 0 成本）；资金流口径 = 市值 − 累计净投入；报告注明数据截止日期。

## 数据安全

`持仓.xls`/`交易记录.xls`/`api.txt`/`output/`/`分析报告/` 均被 `.gitignore` 排除，不得上传、不得把密钥硬编码进代码。
