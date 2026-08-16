---
name: skill-merge
description: '自动检查并合并可合并的 VS Code Copilot 技能（SKILL.md）。Use when: 合并技能、整合技能、技能重复、去重 SKILL.md、清理冗余技能、技能架构优化、检测技能重叠、合并脚本重复、技能太多了。涉及「合并技能」「技能去重」「整合技能」「skill merge」「技能清理」「精简技能」等任务时使用。'
user-invocable: true
---

# 技能自动合并（skill-merge）

自动检查工作区技能目录（`.github/skills/`），发现内容/脚本重复的技能并安全合并，保持技能架构精简、无冗余。

## 何时使用
- 用户说「合并技能」「去重」「整合一下技能」「技能太多了」「精简技能」
- 发现两个技能 SKILL.md 内容重叠、或 scripts/ 目录文件大量重复
- 新增技能后需要评估与现有技能的关系
- 定期维护技能架构时

## 核心原则
1. **一个职责一个技能**：合并后每个技能只有一个清晰职责，不重复
2. **知识优先**：合并的本质是合并知识（SKILL.md 内容），脚本去重是副产物
3. **description 是合并关键**：被合并技能的触发词必须并入保留技能的 description，否则合并后会丢失发现能力（这是最常见的合并失败原因）
4. **安全第一**：删除目录前必须确认保留技能已包含被删技能的全部脚本与知识
5. **保留主技能**：一般保留功能更全、脚本更完整的技能，把重复技能并入其中

## 步骤 1：合并检测
对 `.github/skills/*/` 下每个技能做两两对比：
- **内容重叠**：A 的 SKILL.md 某章节是否就是 B 的整篇（如"A 的步骤 4.5"= B 全文）
- **脚本重复**：`list_dir` 对比 scripts/ 下的文件名（如 common.py、fetch_financials.py 同时存在）
- **引用关系**：SKILL.md 是否互相引用（如"复用 X 技能的 common.py"）
- **职责范围**：是否同一领域（如都是 A 股分析）下的细分

### 判定标准
| 信号 | 判定 |
|------|------|
| 整篇 SKILL.md 是另一技能某步骤的展开 | 🔀 可合并 |
| scripts/ 目录 ≥50% 同名重复 | 🔀 可合并 |
| 明确互相引用（复用对方脚本） | 🔀 可合并 |
| 独立外部系统（服务/API 完全不同，如 TradingAgents 平台） | ✅ 保留 |
| 职责完全不同（如技能维护 vs 股票分析） | ✅ 保留 |

## 步骤 2：合并执行
以「把 B 并入 A」为例：
1. **内容合并**：把 B 独有的章节/步骤并入 A 的 SKILL.md 对应位置（保持 A 章节结构清晰）
2. **description 合并**：把 B 的触发词（"Use when:" 部分）并入 A 的 description
   - 保持 description 用引号包裹（含冒号时必须引号）
   - 总长度尽量 < 500 字符
3. **脚本去重**：确认 A 的 scripts/ 已包含 B 的全部脚本；缺失的复制过去
4. **交叉引用更新**：搜索其他技能中引用 B 的地方（`grep_search`），改为引用 A
5. **删除冗余**：确认无误后删除 B 目录：`Remove-Item -Recurse -Force <B目录>`
6. **验证**：`get_errors` 检查 A 的 frontmatter 无错误

## 步骤 3：合并检查清单
- [ ] A 的 SKILL.md 包含 B 的全部独有知识
- [ ] A 的 description 包含 B 的全部触发关键词
- [ ] A 的 scripts/ 包含 B 的全部脚本
- [ ] 其他技能无对 B 的失效引用（grep 确认）
- [ ] B 目录已删除
- [ ] `get_errors` 无错误
- [ ] 合并结论记录到 `/memories/repo/`

## 典型合并案例（本工作区）
- `financial-analysis` → 并入 `stock-analysis`（财报分析即 stock-analysis 的步骤 4.5，脚本完全重复）
- `stock-daily-update` → 并入 `stock-combined-analysis`（每日更新即综合分析的增量模式，daily_update.py 重复）

## 注意事项
- **description 冒号必须引号包裹**（YAML 语法），否则 silent failure
- 合并后立即 `get_errors` 验证
- 两个技能若各自独立完整（都是主技能），不要强行合并——宁可保留
- 合并前用 git/备份保护：`Copy-Item -Recurse` 到临时目录再操作
- 合并是「有损操作」：被删除技能的历史细节若 A 未覆盖，需先补入 A

## 参考
- 模板与规范见 `agent-customization` 技能的 skills.md（Location 表：Skills 在 `.github/skills/<name>/`）
- 技能内容维护另见 `skill-auto-update`
- 合并历史记录到 `/memories/repo/skill-merge-history.md`
