---
name: stock-combined-analysis
description: '对 A 股持仓/自选股做「量化 + AI」双引擎综合分析（含每日增量更新模式）。整合 stock-analysis（AkShare 技术面/估值/持仓盈亏）与 tradingagents-analysis（TradingAgents 多智能体 AI 研判），交叉验证共识与分歧，生成综合 HTML 报告。Use when: 综合分析股票、量化信号与 AI 观点对照、持仓股双引擎研判、生成综合研究报告、技术面+AI 决策结合、每日更新股票分析、每日研判、持仓股每日快照、daily update、更新今天的分析、简化重复分析流程。'
argument-hint: '可选：股票代码，如 600030；默认分析全部持仓股'
---

# 股票综合双引擎分析

将**量化引擎**（客观技术/估值信号）与 **AI 引擎**（TradingAgents 多智能体深度研判）结合，对每只股票交叉验证，输出综合研究报告。

## 两个引擎

| 引擎 | 技能 | 产出 |
|------|------|------|
| 量化引擎 | `stock-analysis` | 技术指标（MA/MACD/RSI/KDJ/BOLL）、估值（PE/PB）、持仓盈亏/成本/仓位 |
| AI 引擎 | `tradingagents-analysis` | TradingAgents 多智能体分析（市场/新闻/基本面 + 多空辩论 + 风险 + 组合决策） |
| 消息面 | `news-analysis` | 个股新闻/公告 + 情绪打分（利好/利空/中性）+ 技术位联动（现价/支撑/压力） |

## 何时使用
- 用户要求"综合分析"持仓/自选股
- 需要对照技术面信号与 AI 观点（共识/分歧）
- 生成含持仓盈亏 + AI 研判的综合 HTML 报告
- 量化信号与 AI 建议矛盾时辅助决策

## 前置条件
- 两个引擎的服务均须运行：
  - TradingAgents-CN 后端(8000) + Worker + MongoDB(27017) + Redis(6379)（见 `tradingagents-analysis` 技能）
  - Python 环境 `.venv`（含 akshare/pandas/numpy/matplotlib）
- 数据获取遵循 `.github/instructions/股票数据获取.instructions.md`

## 流程

### 步骤 1：确定分析标的
读取 `持仓.xls`（GBK+Tab 分隔，`pd.read_csv(sep="\t", encoding="gbk")`），提取 6 位股票代码（剔除 ETF/基金，即 5 开头或代码含字母的跳过）。也可用命令行指定代码。

### 步骤 2：量化分析（快，先跑）
对每只股票：
1. **行情**：新浪优先（`ak.stock_zh_a_daily(symbol='sh600030')`），东财失败回退
2. **技术指标**：`pandas/numpy` 计算 MA5/10/20、MACD(12,26,9)、RSI(14)、KDJ(9,3,3)、BOLL(20,2)
3. **技术结论**：站上/跌破20日线、MACD金叉/死叉、RSI超买(>70)超卖(<30)、股价在BOLL/60日区间位置
4. **估值**：`ak.stock_zh_valuation_baidu(symbol, '市盈率(TTM)')` 和 `'市净率'`
5. **持仓**：从持仓表取成本价、盈亏、市值、仓位占比

### 步骤 3：AI 分析（慢，后台跑）
通过 TradingAgents-CN API 提交分析（参数见 `tradingagents-analysis` 技能）：
```python
POST /api/analysis/analyze
{"symbol": code, "parameters": {
    "market_type": "A股", "llm_provider": "deepseek",
    "llm_model": "deepseek-chat",
    "analysts": ["market", "news", "fundamentals"],
    "research_depth": "标准"}}
```
从 Redis `qa:task:<id>` 监控状态，取 `result`（含 decision）。

### 步骤 4：综合研判（核心）
对每只股票合并两引擎结论，做交叉验证：
- **共识**：量化信号与 AI 论点方向一致（如均看多 → 强信号）
- **分歧**：方向不一致（如 RSI 超卖但 AI 看空 → 谨慎，标出分歧点）
- **结合持仓**：AI 建议（买入/持有/卖出）对照当前成本价、盈亏、仓位，评估可行性
- 量化关键位（支撑/压力/止损）与 AI 观点结合给出综合评级

### 步骤 5：生成综合报告
生成 `output/股票综合分析报告.html`（内嵌 K 线图 + 指标图，含）：
- 每只股票卡片：量化信号、AI 决策、共识/分歧、综合评级、**📰 消息面**（新闻/公告 + 情绪 + 关键位）
- 持仓视角：成本/盈亏/仓位 vs 建议
- 数据截止日期、免责声明

## 脚本

- [scripts/combined_analysis.py](./scripts/combined_analysis.py) — 主流程：读持仓 → 量化 → 提交 AI → 监控 → 合并 JSON
- [scripts/daily_update.py](./scripts/daily_update.py) — 每日增量更新（AI 每天重新分析一次，仅当天复用，见下文）
- [scripts/build_combined_report.py](./scripts/build_combined_report.py) — 从合并 JSON 生成 HTML 报告

```powershell
cd "c:\Users\kongs\Documents\股票"
# 一键综合（默认全部持仓股）
.\.venv\Scripts\python.exe ".github\skills\stock-combined-analysis\scripts\combined_analysis.py"

# 指定股票
.\.venv\Scripts\python.exe ".github\skills\stock-combined-analysis\scripts\combined_analysis.py" 600030 600036

# 跳过量化/AI 某步
.\.venv\Scripts\python.exe ".github\skills\stock-combined-analysis\scripts\combined_analysis.py" --skip-quant
.\.venv\Scripts\python.exe ".github\skills\stock-combined-analysis\scripts\combined_analysis.py" --skip-ai
```

## 每日增量更新模式（AI 每天重新分析）

日常更新持仓股分析时：量化层每天跑（快），**AI 层默认每天重新分析一次**（每只 15-20 分钟 + DeepSeek API 费用）。仅同一天内复用（避免同一天重复跑两次），跨天即过期重跑；如需省费用可用 `--max-age N` 放宽有效期：

| 环节 | 策略 |
|------|------|
| 读持仓.xls | 每天读（持仓可能变化） |
| 量化分析（行情/MA/MACD/RSI/KDJ/BOLL/PE/PB） | **每天跑**（每只几秒） |
| 新闻/公告分析（`news-analysis`，含情绪+技术位） | **每天跑**（每只几秒，并入报告「📰 消息面」区块） |
| AI 分析（TradingAgents 多智能体） | **默认每天重跑**（`--max-age 0` 仅当天复用；`--max-age N` 放宽为 N 天内复用）；**推荐 `--round-robin`**：按周一到周五轮询，每只每周更新一次 |
| 全市场数据同步 | **只对持仓股定向增量同步**（不全市场） |

### 一键每日更新
```powershell
cd "c:\Users\kongs\Documents\股票"
.\\.venv\\Scripts\\python.exe ".github\skills\stock-combined-analysis\scripts\daily_update.py"
```
脚本自动完成：读持仓 → 定向增量同步 → 量化层（每天更新）→ **消息面层（新闻/公告+情绪+技术位）** → AI 层（默认每天重跑，仅当天复用；查 MongoDB 最近报告判断是否过期）→ 合并 JSON（含 `news` 字段）→ 生成 HTML 报告。

### 常用参数
```powershell
# 指定股票
...daily_update.py 600030 600036
# 强制重跑所有 AI 分析（同一天也重跑）
...daily_update.py --refresh-ai
# 放宽 AI 有效期到 3 天（省 API 费用；默认 0=每天重跑）
...daily_update.py --max-age 3
# 【推荐】AI 按周一到周五轮询：每只每周更新一次，时间平均（量化/新闻仍每天全量）
...daily_update.py --round-robin
# 跳过数据同步 / 只更新 JSON 不生成 HTML
...daily_update.py --no-sync
...daily_update.py --skip-report
```

### AI 轮询模式（`--round-robin`，推荐日常使用）
量化层、新闻层仍**每天全量更新**（每只几秒，便宜）；只有 TradingAgents AI 层改为轮询：
- **股票池** = 持仓股 + 自选池（`WATCH_STOCKS`，与 `analyze_watchlist.py` 一致），另自动并入旧报告已有股票
- **分桶**：按固定顺序 `i % 5` 分配到周一到周五，如 11 只 → 周一 3 只、周二~周五各 2 只；每只固定在某天、每周更新一次
- **周末不轮询**（A 股不开盘）；无历史 AI 结果的新股票立即补跑，不等轮询
- **未轮到的股票**：保留旧 AI 结果并标注「复用」；轮到的当天已跑过则复用、否则重跑（`max_age=0`，防止同一天重复提交）
- **港股 09988** 自动用 `market_type="港股"` 提交
- `--refresh-ai` 会覆盖轮询、强制重跑全部（适合每周手动全量复查）

### 每日更新注意事项（踩坑记录）
1. **AI 复用依赖 MongoDB**：查 `tradingagentscn.analysis_reports`，需 `pymongo`。根 `.venv` 可能没有，先安装：`.\\.venv\\Scripts\\python.exe -m pip install pymongo redis -i https://pypi.tuna.tsinghua.edu.cn/simple`
2. **服务未运行**：登录失败直接退出；MongoDB 查询失败重试 3 次后视为"无历史结果"并重新提交 AI（会花时间）
3. **`--refresh-ai` 后任务失败**：见 `tradingagents-analysis` 技能故障排查（尤其 `HumanMessage is not JSON serializable` 已修复，勿删 worker.py 的 `_json_default`）
4. **不要重复提交**：若误提交了重复 AI 任务，清理 Redis `qa:ready` 队列和 queued 任务（避免浪费 API 费用）
5. **全市场同步**（`akshare_init.py --full`）只在首次/数据大更新时跑，日常用定向增量同步即可
6. **报告 AI 行会标注"分析日期 YYYY-MM-DD（复用）"**——复用说明 AI 观点来自那天，非当天重跑

## 注意事项
- 量化数据有延迟（行情截止到最近交易日），报告注明截止日期
- AI 分析每只约 15-20 分钟，批量分析时耐心等待或分批次
- TradingAgents 任务失败排查见 `tradingagents-analysis` 技能的故障排查章节
- 综合评级仅为研究参考，不构成投资建议
