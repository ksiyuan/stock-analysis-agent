# A 股股票分析 Copilot Agent

基于 **VS Code Copilot 技能（Skills）** + **AkShare 数据源** 的 A 股持仓 / 自选股量化分析 Agent。

在任何新机器上克隆本仓库 → 用 VS Code 打开为工作区 → 一键安装依赖，即可获得与本地完全一致的股票分析 Agent（技能、指令、脚本全部同步）。

---

## 目录结构

```
.
├── .github/
│   ├── instructions/
│   │   └── 股票数据获取.instructions.md   # Copilot 指令：数据源优先级 / 代理 / 代码规范
│   └── skills/                           # Copilot 技能（Agent 大脑，自动被 VS Code 识别）
│       ├── stock-analysis/               # 量化分析主技能：账户盈亏/技术面/财报/红利/复盘/报告
│       ├── news-analysis/                # 新闻公告抓取 + 情绪打分 + 消息面×技术面联动
│       ├── stock-combined-analysis/      # 量化+AI 双引擎综合分析 + 每日增量更新
│       ├── tradingagents-analysis/       # TradingAgents-CN 多智能体 AI 深度研判（可选）
│       ├── skill-auto-update/            # 自动维护技能（沉淀新经验）
│       └── skill-merge/                  # 技能去重合并
├── demo_akshare.py                       # AkShare 入门示例（K线+技术指标）
├── requirements.txt                      # Python 依赖（已验证版本）
├── setup.ps1                             # 新机一键安装脚本
└── sync.ps1                              # 本地更新推送到 GitHub
```

> ⚠️ 个人数据（`持仓.xls` / `交易记录.xls` / `output/` / `分析报告/` / `api.txt`）已被 `.gitignore` 排除，不会上传。

---

## 新机器部署（Windows）

### 1. 安装 Python 3.12
从 https://www.python.org/downloads/ 安装，**务必勾选 “Add Python to PATH”**。

### 2. 安装 VS Code + GitHub Copilot 扩展
- 安装 VS Code：https://code.visualstudio.com/
- 安装扩展：`GitHub Copilot`（含 Copilot Chat，支持 Skills）

### 3. 克隆仓库
```powershell
git clone https://github.com/<你的用户名>/stock-analysis-agent.git
cd stock-analysis-agent
```

### 4. 一键安装依赖
```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```
脚本会自动：创建 `.venv` → 用清华镜像安装 `requirements.txt` → 检查 `api.txt`。

### 5. 配置 API 密钥（可选，AI 分析需要）
在工作区根目录创建 `api.txt`，内容为你的 DeepSeek API Key：
```
sk-xxxxxxxxxxxxxxxx
```
⚠️ 该文件已被 `.gitignore` 排除，只存在本地，不会上传到 GitHub。

### 6.（可选）部署 AI 深度研判引擎 TradingAgents-CN
TradingAgents-CN 是**独立仓库**（约 4GB），需单独克隆部署：
```powershell
git clone https://github.com/hsliuping/TradingAgents-CN.git
```
部署要点（MongoDB/Redis/后端/前端/Worker）见 `.github/skills/tradingagents-analysis/SKILL.md`。
不部署也不影响量化分析，AI 引擎仅用于深度研判。

### 7. 打开工作区
用 VS Code 打开克隆目录，`.github/skills/` 与 `.github/instructions/` 会被 Copilot 自动识别。

---

## 使用方法

在 VS Code 中与 Copilot 对话即可触发对应技能：

| 你说什么 | 触发技能 | 产出 |
|---|---|---|
| 「分析我的持仓」 | stock-analysis | 账户盈亏 / 技术面 / 财报 / 红利 / 复盘 / 综合分析报告 |
| 「更新今天的分析」 | stock-combined-analysis | 每日增量（量化每天跑，AI 按需复用） |
| 「看下 XX 的新闻公告」 | news-analysis | 新闻公告.md/csv + 情绪标注 + 技术位联动 |
| 「用 AI 深度分析 XX」 | tradingagents-analysis | TradingAgents 多智能体研判（需引擎） |
| 「更新技能 / 记下来」 | skill-auto-update | 把新经验沉淀进 SKILL.md |

**报告输出约定**：最终报告统一输出到 `分析报告/`（醒目位置），`output/` 只放中间数据（CSV/JSON/pkl）。

---

## 网络环境注意（重要）

- **东方财富接口**（`push2his.eastmoney.com`）经代理时通时断，脚本已内置重试 + 新浪回退
- **新浪数据源最稳定**（`stock_zh_a_daily`），是首选回退
- pip 安装请用清华镜像（`setup.ps1` 已内置）
- 如使用 Clash 等代理，保持系统代理即可；**不要设置 `NO_PROXY=*` 强制直连**

---

## 本地更新 → 推送到 GitHub（同步）

本仓库就是日常工作的工作区，改技能 / 改脚本后一键推送：

```powershell
.\sync.ps1 "更新说明"
```

或手动执行：

```powershell
git add -A
git commit -m "更新说明"
git push
```

新机器上拉取更新：

```powershell
git pull
```

---

## 常见问题

- **图表中文乱码**：需注册系统中文字体（`msyh.ttc`/`simhei.ttf`），脚本已内置处理
- **控制台 emoji 乱码**：Windows 控制台 GBK 编码不支持 emoji，脚本用 `[OK]` 替代
- **同花顺导出的 xls 打不开**：那是「假 xls」（Tab 分隔文本），需用 `pd.read_csv(sep='\t', encoding='gbk')` 解析，脚本已内置
- **数据不完整 / 东财接口报错**：脚本有自动重试与回退，重跑一次即可
