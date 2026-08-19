---
name: tradingagents-analysis
description: '使用本机 TradingAgents-CN（多智能体 AI 股票分析平台）对 A 股/港股股票进行自动分析。Use when: 分析 A 股个股、持仓股多智能体分析、生成 AI 投资研究报告、批量分析股票、自选股批量 AI 分析、港股个股分析（如 09988 阿里巴巴）、通过 API 驱动 TradingAgents-CN 分析、查看/获取分析任务结果。'
argument-hint: '可选：输入要分析的股票代码，如 600030 600036'
---

# TradingAgents-CN 股票分析

通过本机部署的 TradingAgents-CN（FastAPI + Vue3 + 多智能体 LLM 框架）对 A 股股票进行自动化分析。平台使用 DeepSeek 等大模型，由市场/新闻/基本面分析师 + 多空辩论 + 风险分析 + 交易员 + 组合经理等智能体协作生成研究报告。

## 前置条件

服务必须全部运行（本机便携式部署，端口固定）：

| 服务 | 端口 | 状态检查 |
|------|------|----------|
| 后端 API | 8000 | `http://127.0.0.1:8000/api/health` |
| 前端 | 3000 | `http://127.0.0.1:3000` |
| MongoDB | 27017 | 本机便携版 |
| Redis | 6379 | 本机便携版（密码 tradingagents123） |
| Worker | - | 分析任务执行进程 |

如果服务未运行，使用启动脚本：
```powershell
powershell -ExecutionPolicy Bypass -File "TradingAgents-CN\.dbs\start_local.ps1"
```

**Worker 必须单独启动**（否则任务只排队不执行）：
```powershell
cd "c:\Users\kongs\Documents\股票\TradingAgents-CN"
.\.venv\Scripts\python.exe "c:\Users\kongs\Documents\股票\TradingAgents-CN\app\worker.py"
```
> ⚠️ 不要用 `python -m app.worker`（`app/worker` 是包目录会报错），必须直接运行 `app/worker.py`。

## 分析流程

### 1. 数据同步（分析前必须完成）

分析前需同步目标股票的历史行情和财务数据，否则分析结果数据错误。

**定向同步指定股票**（推荐，快）：
```python
POST http://127.0.0.1:8000/api/stock-sync/batch
Body: {"symbols": ["600030","600036"], "sync_historical": true, "data_source": "akshare"}
Header: Authorization: Bearer <token>
```

**全市场同步**（首次，慢）：
```powershell
cd "c:\Users\kongs\Documents\股票\TradingAgents-CN"
.\.venv\Scripts\python.exe cli/akshare_init.py --full --force --historical-days 365
```
> 必须加 `--force`，否则检测到已有基础信息会跳过整个初始化。
> 历史行情保存到 `tradingagents.stock_daily_quotes` 集合（不是 tradingagentscn）。

### 2. 登录获取 Token

```python
POST http://127.0.0.1:8000/api/auth/login
Body: {"username": "admin", "password": "admin123"}
→ 返回 data.access_token，后续请求加 Header: Authorization: Bearer <token>
```

### 3. 提交分析任务

```python
POST http://127.0.0.1:8000/api/analysis/analyze
Body: {
  "symbol": "600030",
  "parameters": {
    "market_type": "A股",          # ⚠️ 必须写"A股"！Worker 默认是"美股"
    "llm_provider": "deepseek",     # deepseek / dashscope 等
    "llm_model": "deepseek-chat",
    "analysts": ["market", "news", "fundamentals"],  # ⚠️ 小写键！不能写 "Bull Analyst"
    "research_depth": "标准"        # 快速/标准/深度
  }
}
→ 返回 task_id
```

### 4. 监控进度（从 Redis 读取）

任务状态在 **Redis**（Worker 更新），API 的 `/tasks/{id}/status` 查不到 Worker 任务（会 404）：
```python
# Redis 键：qa:task:<task_id> 的 hash 字段 status/symbol/result
# 状态：queued → processing → completed / failed
redis-cli -a tradingagents123
> HGETALL qa:task:<task_id>
```

或直接查看 Worker 日志：`TradingAgents-CN\.dbs\worker*.log`（显示分析进度、各智能体输出）。

### 5. 获取结果

任务完成后，Redis `qa:task:<task_id>` 的 `result` 字段保存完整分析报告（JSON，含 state 和 decision）。报告也会写入 `TradingAgents-CN\data\analysis_results\` 目录。

## 持仓股分析（推荐用法）

自动读取同花顺导出的 `持仓.xls`，分析账户全部持仓股：

```powershell
cd "c:\Users\kongs\Documents\股票"
.\.venv\Scripts\python.exe ".github\skills\tradingagents-analysis\scripts\analyze_stocks.py" --holdings
```

脚本会自动：
1. 读取 `持仓.xls`（GBK 编码、制表符分隔的文本，用 `pandas.read_csv(sep='\t', encoding='gbk')` 解析）
2. 提取证券代码列（`证券代码`，6 位数字；跳过 ETF 等非个股）
3. 定向同步这些股票的数据
4. 逐只提交分析任务

> `持仓.xls` 关键列：`证券代码`、`证券名称`、`股票余额`、`成本价`、`市价`、`市值`、`仓位占比(%)`

## 便捷脚本

运行 [scripts/analyze_stocks.py](./scripts/analyze_stocks.py) 可一键完成：登录 → 同步 → 提交 → 监控 → 输出结果：

```powershell
# 分析单只/多只股票（自动同步数据）
cd "c:\Users\kongs\Documents\股票"
.\.venv\Scripts\python.exe ".github\skills\tradingagents-analysis\scripts\analyze_stocks.py" 600030 600036

# 分析全部持仓股
.\.venv\Scripts\python.exe ".github\skills\tradingagents-analysis\scripts\analyze_stocks.py" --holdings
```
## 自选股批量 AI 分析（含港股，推荐）

运行 [scripts/analyze_watchlist.py](./scripts/analyze_watchlist.py) 对自选池/指定代码做批量 AI 分析，完成后自动合并结果并重新生成综合报告：

```powershell
cd "c:\Users\kongs\Documents\股票"
# 默认自选池（002371/600584/000977/601138/002916/002028 + 港股 09988）
.\venv\Scripts\python.exe ".github\skills\tradingagents-analysis\scripts\analyze_watchlist.py"

# 指定代码（逗号分隔，支持港股 5 位数字）
.\venv\Scripts\python.exe ".github\skills\tradingagents-analysis\scripts\analyze_watchlist.py" --codes=600030,09988

# 只提交不监控
.\venv\Scripts\python.exe ".github\skills\tradingagents-analysis\scripts\analyze_watchlist.py" --submit
```

脚本特点：
1. **港股支持**：5 位数字代码（如 09988）自动用 `market_type="港股"`（`is_hk()` 判断：`.HK` 后缀或 4-5 位数字）
2. **任务复用**：先读 `output/watchlist_tasks.json`，已有 task_id 不重复提交（省 API 费用）；只补提交新增代码
3. **结果合并**：完成后自动写入 `output/combined_ai.json` 并同步 `combined_analysis.json` 的 ai 字段，再重新生成 `分析报告/持仓自选综合分析.html`（调 stock-analysis 的 `build_portfolio_analysis.py`）
4. **长跑监控**：每 60 秒轮询 Redis `qa:task:<id>`，默认超时 7200 秒

⚠️ 运行前必须：①后端 8000 已启动；②Worker 已启动（见上文）；③根 `.venv` 已装 redis/pymongo（`pip install redis pymongo`）
⚠️ **参数坑**：脚本开头用位置参数做工作区路径，`--submit/--codes` 等以 `-` 开头的参数必须用 `_pos = [a for a in sys.argv[1:] if not a.startswith("--")]` 过滤，否则会被误当路径（OUT 写错目录、复用失效、误重新提交浪费 API）
⚠️ **并发限制（重要）**：TradingAgents 全局并发上限 3，同时只允许 3 个任务在跑，多的排队（queued）；批量分析时勿反复重复提交。**单个 Worker 进程是串行的**（`app/worker.py` 的 `worker_loop` 用 `blpop` 一次取一个任务、`await process_task` 处理完才取下一个）——**要真正并发必须启动多个 Worker 进程**（最多 3 个，对应 `app/services/queue/keys.py` 的 `GLOBAL_CONCURRENT_LIMIT=3`/`DEFAULT_USER_CONCURRENT_LIMIT=3`；并发检查基于 Redis `qa:processing` 全局集合 + `qa:user_processing:<user>` 用户集合大小）。多 Worker 通过 BLPOP 竞争 `qa:ready` 队列天然并行。启动方式（后台各起一个）：`Start-Process` 或 async 终端分别运行 2~3 个 `.venv\Scripts\python.exe app\worker.py`
⚠️ **AI 结果解析坑（2026-08-15 踩过）**：Redis `result` 的 `analysis_result.decision` 有两种结构——持仓股用 `decision` 键、**自选股 SignalProcessor 用 `action` 键**；且 `confidence` 是 0-1 小数（0.75 要 ×100 显示为 75%）。解析必须 `decision.get("decision") or decision.get("action")` + confidence ≤1 时 ×100。修复脚本：[scripts/reparse_ai.py](./scripts/reparse_ai.py) 可重新解析全部已完成任务的决策并合并 `combined_ai.json`/`combined_analysis.json`（配合 `watchlist_tasks.json`）
⚠️ **Worker 崩溃恢复**：任务卡在 processing 且无 Worker 存活时，需手动 `HSET qa:task:<id> status queued` + `SREM qa:processing <id>` + `RPUSH qa:ready <id>` 重置回队列，再重启 Worker（从 TradingAgents-CN 目录、`.venv`，勿用系统 Python）；Worker 处理任务时若崩溃会丢结果，重跑即可
## 报告导出

分析完成后，报告保存在系统内，可通过 API 导出（Markdown / Word / PDF）：

```python
# 1. 列出分析报告，找到 report_id
GET http://127.0.0.1:8000/api/reports/list
Header: Authorization: Bearer <token>

# 2. 下载报告（markdown / json / docx / pdf）
GET http://127.0.0.1:8000/api/reports/<report_id>/download?format=markdown
Header: Authorization: Bearer <token>
```

> Word/PDF 导出需要 pandoc（后端 Docker 镜像内置，本地部署需 `pip install pypandoc` + pandoc 可执行文件）。

## 故障排查

### 任务失败（Redis 中 status=failed）
1. 读取失败原因：`redis-cli -a tradingagents123 HGETALL qa:task:<task_id>` 的 `result` 字段（JSON）
2. 常见错误及修复：

| 错误 | 原因 | 修复 |
|------|------|------|
| `美股代码格式错误` | 未传 `market_type`，Worker 默认美股 | 参数加 `"market_type": "A股"` |
| `should_continue_Bull Analyst 不存在` | analysts 用了英文名 | 用 `["market","news","fundamentals","social"]` |
| `KeyError: 'bull_history'` | 图状态合并丢失消息 | 已修复（values 模式），若复现检查 `trading_graph.py` 的 `propagate` |
| `Object of type HumanMessage is not JSON serializable` | 分析**实际已成功**（报告已存 MongoDB），但 worker 把 result 写入 Redis 时序列化失败，任务被误标 failed | ①已修 `app/worker.py` 的 `json.dumps` 加 `default=_json_default`；②若已发生，直接**从 MongoDB `analysis_reports` 重建 result**（解析 reports.markdown 的 投资建议/置信度/目标价/止损价/分析推理），更新 Redis `status=completed`，无需重新分析 |
| `字典更新序列长度错误` | langgraph 版本不兼容 | 保持 langgraph 0.6.7（勿升 1.x） |
| `股票代码不存在或信息无效` | 东财接口不可达，基础信息获取失败 | 确认 MongoDB 数据源已启用（见下） |

### 任务排队不执行
- **Worker 未运行**：`python app/worker.py`（不要用 `-m app.worker`）
- 检查 Worker 日志：`TradingAgents-CN\.dbs\worker*.log`

### 数据源问题
- **东方财富不可达**：`push2his.eastmoney.com` 连接失败是常见现象，已加新浪回退（`tradingagents/dataflows/providers/china/akshare.py` 的 `get_historical_data`）
- **MongoDB 数据源未启用**：检查 `system_configs.data_source_configs` 是否含 `{"type":"mongodb","enabled":true,"priority":100}`；否则分析会走东财接口可能失败

### 服务状态检查
```powershell
# 端口检查
Test-NetConnection 127.0.0.1 -Port 8000   # 后端
Test-NetConnection 127.0.0.1 -Port 3000   # 前端
Test-NetConnection 127.0.0.1 -Port 27017  # MongoDB
Test-NetConnection 127.0.0.1 -Port 6379   # Redis
```

## 关键注意事项（踩坑记录）

1. **market_type 必须显式传 "A股"**：Worker 默认 `params.get("market_type", "美股")`，不传会把 A 股当美股，报"美股代码格式错误"。
2. **analysts 用小写键**：`["market","news","fundamentals","social"]`。传 "Bull Analyst" 会报 `should_continue_Bull Analyst` 不存在。
3. **数据源已启用 MongoDB**：系统配置 `system_configs.data_source_configs` 已添加 mongodb（priority=100），优先从已同步数据读取，避免东方财富接口不可达问题。
4. **东方财富接口可能不可达**：`push2his.eastmoney.com` 直连/代理都会连接失败。已在 `tradingagents/dataflows/providers/china/akshare.py` 的 `get_historical_data` 添加新浪财经（`stock_zh_a_daily`）回退。
5. **依赖版本已锁定**：langgraph 0.6.7 / langchain 0.3.27（不要升级到 1.x，API 不兼容）。
6. **分析耗时**：每只股票约 15-20 分钟（3 个分析师 + 多空辩论 + 风险 + 交易员 + 组合经理，每次 LLM 调用 20-40 秒）。
7. **系统代理 127.0.0.1:7897**：会影响东方财富请求，但新浪数据源不受影响。
8. **默认账号**：admin / admin123。

## 结果解读

分析报告含多个智能体的结论：
- **Market/News/Fundamentals Analyst**：市场面、新闻面、基本面分析
- **Bull/Bear Researcher**：多空辩论
- **Risky/Safe/Neutral Analyst**：风险分析
- **Trader**：交易建议
- **Portfolio Manager**：最终投资决策（买入/持有/卖出及理由）
