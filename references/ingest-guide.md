# 入库行为指南

入库工作流：把原始素材编译为可积累知识。五阶段流水线：fetch → ingest → compile → apply → review。

## 定位

| 场景 | 你做什么 | 脚本做什么 |
|------|---------|-----------|
| URL 入库 | 判断来源类型、选择编译策略、审核结果 | 抓取、写入 raw/、生成 payload、回写正式页 |
| 文件入库 | 同上 | 同上（本地文件不需抓取） |
| 批量入库 | 逐篇执行 + 汇总报告 | 同上 |
| autoresearch | 多轮搜索 + 每轮入库 | 同上 |

---

## Step 0: 判断来源类型

| 来源 | 识别信号 | 处理方式 |
|------|---------|---------|
| 微信 URL | `mp.weixin.qq.com` | `wiki_ingest.py` 自动路由 |
| 通用网页 URL | 其他 http/https | `wiki_ingest.py` 自动路由 |
| YouTube URL | `youtube.com/watch`、`youtu.be/` | 视频适配器（字幕优先，ASR 回退） |
| Bilibili URL | `bilibili.com/video`、`b23.tv/` | 视频适配器 |
| 抖音 URL | `douyin.com/video`、`v.douyin.com/` | 视频适配器 |
| 本地文件 | `.md`、`.txt`、`.html`、`.pdf` 路径 | 文件适配器 |
| 纯文本 | 用户直接粘贴 | `--text` 参数 |

**不要**对视频 URL 调用网页抓取工具——视频 URL 只走视频适配器。

---

## Step 1: 定位 Vault

1. 从 `vault.conf` 获取默认 vault 路径
2. 抓取完成后，脚本自动调用 `detect_domains()` + `resolve_vault()` 按 `purpose.md` 域匹配
3. 域匹配最高 vault 自动选定，不需要反复询问用户
4. 只有当内容域与所有已有 vault 都不匹配时，才建议创建新 vault

---

## Step 2: 选择编译策略

编译时按 `references/prompts/ingest_compile_prompt_v2.md` 约束生成结构化 JSON。

三种编译模式，**默认 prepare-only**（agent 交互编译）：

| 模式 | 适用场景 | 标志 | 能力 |
|------|---------|------|------|
| `prepare-only` | **默认**。agent 在对话中编译 | 无需额外参数 | full（含跨域联想、主张清单、知识提案） |
| `api-compile` | 无人值守、批量处理 | `--api-compile`（需 WECHAT_WIKI_API_KEY） | full |
| `heuristic` | 快速入库、不需要 LLM 分析 | `--no-llm-compile` | basic（启发式 brief/source，无跨域联想） |

> **设计原则**：默认路径不依赖外部 API key。`prepare-only` 让 LLM agent 在对话中基于 payload 完成编译，是最常用的交互场景。`api-compile` 是 opt-in，仅在需要无人值守批量处理时启用。

> **注意**：`cross_domain_insights`（跨域联想）和 `claim_inventory`（主张清单）仅在 LLM 编译模式下可产出。启发式模式的 `compile_quality` 为 `raw-extract`，不包含这些高级分析。

### 推荐流程（prepare-only，默认）

```
1. wiki_ingest.py 抓取 + 生成 prepare-only payload
2. 你在当前对话中基于 payload 生成结构化 JSON，保存为 result.json
3. apply_compiled_brief_source.py --validate-only 校验 JSON 结构
4. 校验通过后，apply_compiled_brief_source.py 回写正式页
```

如果需要更精细的 payload 控制，可在步骤 1 和 2 之间插入：
```
llm_compile_ingest.py --prepare-only --lean --raw "D:\Vault\raw\articles\<slug>.md"
```
`--lean` 参数移除 system_prompt/user_prompt，上下文占用减少 ~80%。

`--validate-only` 检查三项：结构完整性（字段存在性、枚举值合法性）、grounding（引用是否可在原文找到）、证据密度（成熟度等级）。校验失败时 JSON 不会被应用，避免生成损坏页面。

### 何时用哪种

- 用户说"入库"/"整理这篇" → 默认 prepare-only（无需额外参数）
- 用户说"快速入库"/"批量处理" → `--no-llm-compile`（启发式，不等 LLM）
- 用户说"先抓取不要编译" → 默认即可（prepare-only payload 可忽略）
- 用户说"无人值守"/"批量" → `--api-compile`（需配置 API key）

---

## Step 3: 执行入库

### 单篇入库（默认 prepare-only）

```powershell
# 1. 抓取 + 生成 prepare-only payload（默认行为，无需额外参数）
python scripts/wiki_ingest.py --vault "D:\Vault" "https://..."

# 2. 基于 payload 在对话中生成 JSON，保存为 result.json

# 3. 校验 JSON 结构（推荐）
python scripts/apply_compiled_brief_source.py `
  --vault "D:\Vault" `
  --raw "D:\Vault\raw\articles\<slug>.md" `
  --compiled-json "path/to/result.json" `
  --validate-only

# 4. 校验通过后回写
python scripts/apply_compiled_brief_source.py `
  --vault "D:\Vault" `
  --raw "D:\Vault\raw\articles\<slug>.md" `
  --compiled-json "path/to/result.json"
```

如果需要更精细的 payload 控制，在步骤 1 和 2 之间插入：

> **PDF 自动生成**：apply 完成后，`ingest_orchestrator` 自动调用 `pdf_utils.brief_to_pdf()` 为 brief 生成带封面的 PDF（`wiki/briefs/{slug}.pdf`）。PDF 生成失败时静默跳过，不影响入库主流程。排版规格和主题选择见 `references/pdf-output.md`。
```powershell
python scripts/llm_compile_ingest.py `
  --vault "D:\Vault" `
  --raw "D:\Vault\raw\articles\<slug>.md" `
  --title "标题" `
  --prepare-only --lean
```

### 批量入库

```powershell
# 逐篇执行，脚本内置保护机制：
# - 同 slug 已存在时自动跳过（除非 --force）
# - 视频合集有 collection limit、请求间隔、失败退避
python scripts/wiki_ingest.py --vault "D:\Vault" "URL1" "URL2" "URL3"
```

### 本地文件入库

```powershell
python scripts/wiki_ingest.py --vault "D:\Vault" "D:\path\to\file.pdf"
python scripts/wiki_ingest.py --vault "D:\Vault" --text "粘贴的文本内容"
```

---

## Step 4: 审核编译结果

编译完成后，检查：

1. **编译质量**：`structured`（LLM 编译）vs `raw-extract`（启发式）
2. **骨架与关键判断**：brief.skeleton.generators 和 key_points 是否完整
3. **跨域联想**：是否有 cross_domain_insights（含 migration_conclusion）
4. **开放问题**：是否有值得追踪的 open_questions
5. **立场影响**：是否影响已有 stance 页面

### Delta 输出处理

当编译结果包含 `update_proposals` 时，脚本会在 `wiki/outputs/` 下生成 delta 页面（如 `delta-<slug>-<target>.md`）。Delta 是对已有知识页面的增量修改提案。

**Delta 页面结构**：
- `target_page`：要修改的目标页面
- `action`：操作类型（draft_delta 等）
- `reason`：修改原因
- `evidence`：支撑证据
- `patch`：具体修改建议（summary_delta、content、questions_open）

**处理流程**：
1. 打开 delta 页面，阅读修改提案
2. 判断是否同意修改理由和证据
3. 如果同意：手动将 patch 内容合并到目标页面，或使用 `apply_approved_delta.py` 自动合并
4. 如果不同意：标记为 rejected（修改 frontmatter `status: "rejected"`）
5. 处理完后删除 delta 页面，或标记为 archived

**注意**：delta 页面默认 `lifecycle: "review-needed"`，不会被自动清理。定期运行 `review` 检查积压。

---

## Step 5: 影响分析 + 展示报告

入库完成后**必须**展示影响报告，不能只返回"写入完成"。

### 5a. 脚本收集数据

`ingest_report.py` 负责机械数据收集（读 frontmatter、统计数量），不做语义判断。

```powershell
python scripts/pipeline/ingest_report.py --collect-only --vault "D:\Vault" --slug "<slug>" --title "标题"
```

输出 `ingest_collect.json`，结构：

```json
{
  "new_source": {
    "slug": "xxx",
    "title": "标题",
    "domains": ["领域1"],
    "quality": "high",
    "compile_mode": "structured"
  },
  "compiled_payload": {
    "knowledge_proposals": {},
    "open_questions": [],
    "cross_domain_insights": [],
    "stance_impacts": []
  },
  "existing_sources": [
    {"slug": "sources/xxx", "title": "...", "domains": ["..."], "quality": "...", "date": "...", "core_summary": "..."}
  ],
  "existing_questions": [],
  "existing_stances": [],
  "recent_activity": []
}
```

### 5b. LLM 影响分析

基于脚本收集的数据，按 `references/prompts/ingest_impact.md` 约束分析：

**分析内容**：
1. 从 `existing_sources` 中找语义相关来源（基于内容，非标题关键词）
2. 评估入库影响（新概念、立场冲突/支撑、问题推进、跨域联想）
3. 建议 1-3 个具体可执行的下一步

**输出 JSON**：

```json
{
  "related_sources": [
    {"slug": "sources/xxx", "relevance": "high|medium", "reason": "基于内容语义的判断理由"}
  ],
  "impact": {
    "new_concepts": [],
    "stance_effects": [{"stance": "stances/X", "effect": "reinforce|contradict|extend", "detail": "..."}],
    "question_progress": [{"question": "questions/Y", "progress": "partial|resolved", "detail": "..."}],
    "cross_domain_signals": [{"concept": "A", "target_domain": "B", "bridge_logic": "..."}]
  },
  "suggested_next_steps": [
    {"action": "追问|深挖|入库|维护", "description": "具体可执行的操作", "priority": 1}
  ],
  "summary": "一句话入库影响概述"
}
```

**约束**：
- 相关性基于内容语义，不靠标题关键词
- 跨域联想只在有明确 bridge logic 时输出
- compiled_payload 为空时标注 "data_limited"

### 5c. 展示报告

入库完成后，必须按 `ingest-quickstart.md` 中"入库完成必选输出"模板展示结果。核心原则：
- 骨架直接引用 brief.skeleton.generators narrative 原文，不拆子维度
- 关键判断直接引用 brief.key_points 原文
- 不展示置信度分布
- 跨域联想必须含迁移结论
- 冲突只展示高置信度矛盾
- 不自由发挥非模板维度

---

## 特殊场景

### autoresearch 模式

围绕一个主题做多轮自主搜索和入库：

1. 读 `wiki/hot.md` 和 `wiki/index.md` 确定已有覆盖
2. Round 1：WebSearch(broad) → top 3 URLs → 入库
3. Round 2：WebSearch(deeper angles) → top 2 URLs → 入库
4. Round 3：WebSearch(specific evidence) → top 1 URL → 入库
5. 每轮搜索后检查已有覆盖，避免重复入库

触发词：`autoresearch`、`自动研究`、`深入调查`、`知识库补盲`

### save 模式

把对话中的有价值讨论保存为 wiki 页面：

| 类型 | 写入路径 | 适用场景 |
|------|---------|---------|
| synthesis | wiki/syntheses/ | 跨来源综合讨论 |
| concept | wiki/concepts/ | 新概念定义 |
| source | wiki/sources/ | 来源讨论 |
| decision | wiki/stances/ | 决策或判断 |
| session | wiki/outputs/ | 会话摘要 |

触发词：`save`、`保存对话`、`记录讨论`

### 已存在跳过

当 `raw/articles/` + `wiki/sources/` + `wiki/briefs/` 已存在同 slug 时，脚本自动跳过。除非用户明确说"重新入库"或"覆盖"，此时加 `--force`。

---

## 入库后自动检查

入库完成后，自动执行以下检查（L1 自动检查 + 通知，不打断用户）。

### 1. 健康评分检查

入库完成后，自动运行 `wiki_lint.py --collect-only`，计算健康评分。

**触发条件**：
- 评分 < 80 分
- 评分较上次下降 ≥ 5 分

**通知方式**（追加入库报告末尾）：
```
知识库健康评分：{score}/100（较上次 {change}）。说 "lint" 查看详情。
```

### 2. 综合页 Freshness 检查

入库完成后，检查本次入库涉及的 domain 是否有对应的 synthesis 页需要更新。

**判断逻辑**：
1. 从本次入库的 source 页面提取 domain（frontmatter tags 或目录）
2. 检查 `wiki/syntheses/` 下是否有对应 domain 的综合页
3. 如果有，比较综合页的 `updated` 日期 vs 新来源的 `created` 日期
4. 如果新来源更晚 → 建议刷新

**通知方式**：
```
本次入库新增了 {domain} 领域的来源。综合页 [[syntheses/{domain}--综合分析]] 可能需要更新。说 "刷新综合" 可执行。
```

### 3. 审核队列积压检查

入库完成后，统计 `wiki/outputs/` 中 `lifecycle: temporary` 的文件数。

**触发条件**：
- ≥ 10 个 → 通知
- ≥ 20 个 → 高优先通知

**通知方式**：
```
outputs/ 中有 {N} 个待处理项目。说 "review" 查看审核队列。
```

### 4. 入库计数里程碑

入库完成后，统计 `log.md` 中 `## ingest` 的记录数。每 10 的倍数时建议 lint。

**通知方式**：
```
已有 {N} 篇素材入库。建议运行健康检查。说 "lint" 可执行。
```

### 执行约定

- 以上检查在入库报告展示**之后**追加，不打断主流程
- 如果无异常，不追加任何提示
- 多个检查同时触发时，合并为一行（优先级：健康评分 > 审核队列 > 综合刷新 > 里程碑）
- 不自动执行修复操作，只通知

---

## 入库后引导

### 不要做的事

- 不要入库后主动推荐 deep-research——那是追问场景的触发点
- 不要把单次提到的名词直接升格成 concept/entity 正式节点
- 不要默认直连外部 API，除非用户明确要无人值守
- 不要对单条视频 URL 调用网页抓取工具

### Deep-research 引导时机

入库后引导**不要**主动推荐 deep-research。触发时机是追问场景中：

- 用户围绕内容追问时，问题同时具备：战略重要性 + 依赖外部事实验证 + 框架风险
- 用户主动说"深入研究"/"深度分析"/"deep research"

例外：高信号入库的开放问题如果明确涉及战略判断，可以加一行提示："此问题涉及外部验证，追问时可升级到 deep-research"

---

## 边界

- **你负责**：来源类型判断、编译策略选择、语义编译（prepare-only 模式）、结果审核、**影响分析**（相关来源识别、跨域联想、下一步建议）
- **脚本负责**：抓取、写入 raw/、生成 payload、回写正式页、重建索引、更新日志、**收集影响分析数据**（读 frontmatter、统计数量）
- **不主动修改**：正式 wiki 页面的编译结果，除非用户要求调整
- **不要做的事**：用标题关键词判断来源相关性（交给 LLM 语义分析）
