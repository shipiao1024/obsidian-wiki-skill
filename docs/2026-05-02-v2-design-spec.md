# V2 功能设计规格

日期：2026-05-02
基线：V1.2.2 (Optimization & Hardening)
设计准则：**用户无感知、零负担** — 所有判断由 LLM 完成，用户只做最终确认。

---

## 一、洞见识别（Insight Detection）

### 1.1 设计目标

在对话过程中，LLM 自动识别有价值的问答对，写入过程数据库（`wiki/outputs/`），在回答末尾轻量引导用户确认是否正式入库。用户不需要了解"结晶化"概念，不需要主动触发。

### 1.2 判断标准

#### 好问题的信号

| 信号 | 判断规则 | 权重 |
|------|---------|------|
| Q1. 概念澄清 | 问题暴露了知识库中某个概念的模糊定义或边界不清。例如："A 和 B 的区别到底是什么？" — 说明现有页面没有把两者区分清楚 | 高（2 分） |
| Q2. 框架挑战 | 问题质疑了知识库中某个已有结论或假设。例如："如果 X 的前提不成立呢？" — 说明用户在挑战现有框架 | 高（2 分） |
| Q3. 跨域连接 | 问题将两个原本不相关的领域联系起来。例如："A 领域的 X 方法能不能用在 B 领域？" — 说明用户在做跨域思考 | 中（1 分） |
| Q4. 决策驱动 | 问题的答案将直接影响用户的决策或方向。例如："我应该选 A 方案还是 B 方案？" — 说明答案有实际后果 | 中（1 分） |
| Q5. 缺口暴露 | 问题指向了知识库中完全没有覆盖的领域。搜索 vault 后发现 < 2 个相关页面 | 低（0.5 分） |

#### 好答案的信号

| 信号 | 判断规则 | 权重 |
|------|---------|------|
| A1. 多源综合 | 答案引用了 ≥ 3 个不同来源页面，且做了交叉分析（不是简单罗列） | 高（2 分） |
| A2. 矛盾解决 | 答案澄清了知识库中两个或多个来源之间的矛盾，给出了判断 | 高（2 分） |
| A3. 新连接发现 | 答案发现了知识库中未被记录的实体/概念之间的关系 | 中（1 分） |
| A4. 决策框架 | 答案提供了可操作的决策框架或评估维度（不只是信息，而是判断方法） | 中（1 分） |
| A5. 边界明确 | 答案明确了某个概念的适用范围和不适用范围 | 低（0.5 分） |

#### 触发规则

```
单轮问答 = 1 个问题 + 1 个答案

评分 = 所有命中的信号权重之和

触发阈值：总分 ≥ 3 分

示例：
  Q1(2) + A1(2) = 4 → 触发（概念澄清 + 多源综合）
  Q3(1) + A1(2) + A3(1) = 4 → 触发（跨域连接 + 多源综合 + 新连接）
  Q5(0.5) + A5(0.5) = 1 → 不触发
  Q4(1) + A4(1) = 2 → 不触发（需要更多信号）
  A1(2) + A2(2) = 4 → 触发（即使没有好问题信号，好答案本身也够）
```

### 1.3 执行方式

LLM 在生成回答的过程中自然判断，不需要额外的 LLM 调用。

**判断时机**：回答生成完成后、向用户展示前。

**判断依据**：
- LLM 知道用户问了什么（问题在上下文中）
- LLM 知道自己引用了哪些来源（生成过程中跟踪 `[[页面名]]` 引用）
- LLM 知道自己是否做了跨来源综合（自己正在做的事情）
- LLM 知道搜索 vault 后找到了多少相关页面

### 1.4 过程数据库

**存储位置**：`wiki/outputs/{date}--insight--{short-title}.md`

**Frontmatter**：
```yaml
---
type: query
mode: insight              # 标记为"对话洞见"（区别于普通查询结果）
lifecycle: temporary       # 复用现有 staging 机制
origin: conversation       # 来源是对话
date: {日期}
sources: [引用的来源列表]
signals:                   # 记录触发信号
  - Q1: "概念澄清：A 和 B 的区别"
  - A1: "多源综合：引用了 3 个来源"
---
```

**内容结构**：
```markdown
# {洞见标题}

> 来源：对话 | 日期：{日期}

## 问题
{用户的问题}

## 核心回答
{回答的精华部分，≤300 字}

## 来源引用
- [[来源1]]：{引用的关键段落}
- [[来源2]]：{引用的关键段落}
```

### 1.5 引导交互

**触发时机**：回答末尾，自然衔接。

**交互方式**：一行轻量提示，不打断回答流程。

```
[回答内容...]

---
识别到有价值的洞见，暂存于 [[outputs/{slug}]]。说 "沉淀" 可升级为正式知识页。
```

**用户行为**：
- 说"沉淀" → 执行 `apply_approved_delta.py` 流程
- 什么都不说 → 保留在 `wiki/outputs/`，下次维护时统一处理

### 1.6 Prompt 约束

新增 `references/prompts/insight_detection.md`：

```markdown
# 洞见识别约束

你在回答用户问题的同时，判断这轮问答是否有价值。

## 判断时机
回答生成完成后、向用户展示前。

## 判断规则
按以下信号评分（可叠加）：

好问题信号：
- Q1 概念澄清（2 分）：问题暴露了知识库中概念的模糊定义
- Q2 框架挑战（2 分）：问题质疑了已有结论或假设
- Q3 跨域连接（1 分）：问题连接了两个不相关的领域
- Q4 决策驱动（1 分）：答案将直接影响决策
- Q5 缺口暴露（0.5 分）：vault 中 < 2 个相关页面

好答案信号：
- A1 多源综合（2 分）：引用 ≥ 3 个来源且做了交叉分析
- A2 矛盾解决（2 分）：澄清了来源之间的矛盾
- A3 新连接发现（1 分）：发现了未记录的实体/概念关系
- A4 决策框架（1 分）：提供了可操作的判断方法
- A5 边界明确（0.5 分）：明确了概念的适用范围

总分 ≥ 3 → 触发。

## 触发后操作
1. 写入 wiki/outputs/{date}--insight--{short-title}.md
2. frontmatter 设 mode: insight, lifecycle: temporary, origin: conversation
3. 在回答末尾追加一行提示

## 不触发时
正常回答，不追加任何提示。
```

---

## 二、深度研究轻量触发（Lightweight Deep Research Trigger）

### 2.1 设计目标

用户问问题时，LLM 自动判断"这个问题需要深度研究还是查询就够了"，在回答中轻量引导用户升级。

### 2.2 查询 vs 深度研究的边界

| 维度 | 查询 | 深度研究 |
|------|------|---------|
| 信息来源 | vault 内部 | vault + 外部联网 |
| 置信度 | 基于已有来源 | 需要外部验证 |
| 时间范围 | 当前知识库快照 | 可能涉及最新信息 |
| 输出 | 即时回答 | 结构化报告（Why/What/How/Trace） |
| 触发 | 用户问任何问题 | 用户说"深入研究"或 LLM 判断需要 |

**核心判断**：vault 中的信息是否足够回答这个问题？

### 2.3 触发信号

现有 `deep_research_triggers.py` 的 5 个触发条件是**入库后**检测的（基于 compile payload）。这里设计的是**对话中**的触发条件，两者互补。

#### 对话中的触发信号

| 信号 | 判断规则 | 优先级 |
|------|---------|--------|
| D1. 外部事实依赖 | 答案需要验证外部事实（最新数据、事件、政策），vault 中没有 | high |
| D2. 多源矛盾 | 搜索 vault 后发现 ≥ 2 个来源对同一问题有矛盾回答 | high |
| D3. 高风险决策 | 问题涉及重大决策（方向选择、架构决策、投资判断），且 vault 信息不充分 | high |
| D4. 低覆盖度 | 搜索 vault 后发现 < 2 个相关页面，需要外部补充 | medium |
| D5. 时间敏感 | 问题涉及"最新的"、"最近的"、"当前的"，vault 内容可能已过时 | medium |
| D6. 用户追问 | 用户在同一个话题上追问 ≥ 3 轮，说明查询结果不满足需求 | low |

#### 触发规则

```
满足以下任一条件时，建议升级到深度研究：
  - 任一 high 优先级信号命中
  - ≥ 2 个 medium 优先级信号命中
  - 1 个 medium + 用户追问 ≥ 3 轮
```

### 2.4 引导交互

**不打断回答**。先用 vault 内的信息回答，然后在末尾轻量引导。

```
[基于 vault 的回答...]

---
这个问题涉及 [外部最新信息 / 来源矛盾 / vault 覆盖不足]，当前回答可能不完整。说 "深入研究" 可启动系统调研。
```

**用户行为**：
- 说"深入研究" → 进入 `research-guide.md` 的 Phase 1
- 什么都不说 → 当前回答已足够

### 2.5 与现有触发机制的关系

| 机制 | 时机 | 触发来源 | 输出 |
|------|------|---------|------|
| `deep_research_triggers.py` | 入库后 | compile payload 中的 claim/inference | 格式化的建议文本 |
| 对话中触发（新增） | 回答时 | vault 搜索结果 + 问题特征 | 一行轻量提示 |

两者互补：
- 入库触发：检测"已有知识中的结构性问题"（矛盾、缺口、置信度断崖）
- 对话触发：检测"用户当前问题超出 vault 能力"（外部依赖、低覆盖、时间敏感）

### 2.6 Prompt 约束

修改 `references/query-guide.md` 的 Step 3（综合回答）末尾，新增：

```markdown
### 深度研究引导

回答生成后，判断是否需要建议升级到深度研究。

触发信号（满足任一 high 或 ≥ 2 个 medium）：
- D1（high）：答案需要验证外部事实，vault 中没有
- D2（high）：≥ 2 个来源对同一问题有矛盾回答
- D3（high）：问题涉及重大决策，vault 信息不充分
- D4（medium）：vault 中 < 2 个相关页面
- D5（medium）：问题涉及时间敏感信息
- D6（low）：用户在同一话题追问 ≥ 3 轮

触发时，在回答末尾追加一行提示，说明原因（不重复回答内容）。
不触发时不追加。
```

---

## 三、自动化维护（Automated Maintenance）

### 3.1 设计目标

将现有 4 个维护场景（lint、claim evolution、synthesis refresh、review queue）分层自动化，减少用户手动触发的频率。

### 3.2 维护分层模型

| 层级 | 定义 | 用户感知 | 操作 |
|------|------|---------|------|
| L0 全自动 | 脚本执行，无需 LLM，无需用户确认 | 无 | 索引重建、log 追加 |
| L1 自动检查 + 通知 | 脚本收集 + LLM 判断，结果通知用户 | 一行提示 | 健康评分、stale 检测 |
| L2 自动检查 + 确认 | 脚本收集 + LLM 判断 + 展示建议，用户确认后执行 | 展示建议 + 等待确认 | 综合刷新、claim 演化 |
| L3 手动触发 | 用户主动发起 | 用户主动 | 深度研究、crystallize |

### 3.3 各场景的自动化规则

#### 场景 1：健康检查（lint）— L1 自动检查 + 通知

**现有行为**：用户说"lint"才触发。

**自动化方案**：每次入库完成后，自动运行 `wiki_lint.py --collect-only`，计算健康评分，只在评分下降时通知用户。

**触发条件**：
```
每次入库完成后（log.md 追加 ingest 记录后）
  → 自动运行 wiki_lint.py --collect-only
  → 计算健康评分（按现有评分规则）
  → 如果评分 < 80 或评分较上次下降 ≥ 5 分
    → 在入库结果末尾追加一行提示
```

**通知方式**：
```
已消化：{素材标题}
[入库结果...]

---
知识库健康评分：{score}/100（较上次 {change}）。说 "lint" 查看详情。
```

**不自动修复**：只通知，不执行修复操作。修复需要用户确认。

**实现**：
- 修改 `references/ingest-guide.md`：入库完成后追加 lint 自动检查步骤
- 不需要新增脚本（复用现有 `wiki_lint.py --collect-only`）

#### 场景 2：主张演化（claim evolution）— L2 自动检查 + 确认

**现有行为**：用户说"主张分析"才触发。

**自动化方案**：基于 stale_report.py 的检测结果，当发现 stale taxonomy pages 时，建议运行 claim evolution。

**触发条件**：
```
stale_report.py 检测到以下任一情况：
  - stale_taxonomy_pages 数量 ≥ 3（页面时间戳早于引用来源）
  - placeholder_pages_with_multiple_sources 数量 ≥ 2
  → 建议运行 claim evolution
```

**通知方式**：
```
发现 {N} 个页面需要更新（来源比页面更新）。说 "主张分析" 可追踪主张演化。
```

**实现**：
- 修改 `references/maintenance-guide.md`：新增"自动维护建议"段
- 不需要新增脚本

#### 场景 3：综合刷新（synthesis refresh）— L2 自动检查 + 确认

**现有行为**：用户说"刷新综合"才触发。

**自动化方案**：当 synthesis 页引用的来源数发生变化时，建议刷新。

**触发条件**：
```
入库完成后，检查本次入库涉及的 domain：
  - 如果该 domain 已有 synthesis 页
  - 且本次入库新增了该 domain 的来源
  → 建议刷新该 domain 的综合页
```

**判断逻辑**（对标桌面应用的 stale detection）：
```
1. 从本次入库的 source 页面提取 domain（frontmatter tags 或目录）
2. 检查 wiki/syntheses/ 下是否有对应 domain 的综合页
3. 如果有，比较综合页的 updated 日期 vs 新来源的 created 日期
4. 如果新来源更晚 → 建议刷新
```

**通知方式**：
```
本次入库新增了 {domain} 领域的来源。综合页 [[syntheses/{domain}--综合分析]] 可能需要更新。说 "刷新综合" 可执行。
```

**实现**：
- 修改 `references/ingest-guide.md`：入库完成后追加综合页 freshness 检查

#### 场景 4：审核队列（review queue）— L1 自动检查 + 通知

**现有行为**：用户说"review"才触发。

**自动化方案**：定期检查 pending outputs 数量，超过阈值时通知。

**触发条件**：
```
每次入库完成后：
  - 统计 wiki/outputs/ 中 lifecycle: temporary 的文件数
  - 如果 ≥ 10 → 通知用户
  - 如果 ≥ 20 → 高优先通知
```

**通知方式**：
```
outputs/ 中有 {N} 个待处理项目。说 "review" 查看审核队列。
```

**Review 自动清理**（新增 sweep 逻辑）：

对标桌面应用的 `sweepResolvedReviews()`，在通知前先自动清理已失效的项。

**规则 R1 — missing-page 类型**：
```
条件：output 的 frontmatter 含 mode: insight 或 type: query
逻辑：
  1. 从 output 内容中提取引用的 [[页面名]]
  2. 检查这些页面是否已存在于 wiki/ 中
  3. 如果所有引用页面都已存在 → 标记为可清理（resolved）
```

**规则 R2 — 被覆盖的 output**：
```
条件：多个 output 标题相同或高度相似
逻辑：
  1. 按 created 日期排序
  2. 保留最新的，旧的标记为可清理
```

**规则 R3 — LLM 判断**（对规则 R1/R2 剩余项）：
```
批次参数：batch = 20, max_batches = 3
提前终止：某批次 resolved = 0 则停止
保守策略：contradiction/suggestion 类型默认保持 pending
```

**实现**：
- 修改 `scripts/review_queue.py`：新增 `--sweep` 模式
- 新增 `references/prompts/review_sweep.md`：LLM 判断 prompt
- 修改 `references/maintenance-guide.md`：新增 sweep 说明

### 3.4 维护建议自动生成

**问题**：用户不知道什么时候该跑哪个维护操作。

**方案**：新增 `stale_report.py --auto-suggest` 模式，输出结构化建议 JSON。

**输出 schema**：
```json
{
  "suggestions": [
    {
      "type": "stale_synthesis",
      "target": "syntheses/自动驾驶--综合分析",
      "severity": "medium",
      "reason": "综合页最后更新 30 天前，期间新增 3 篇来源",
      "suggested_action": "刷新综合",
      "suggested_command": "refresh_synthesis.py --domain 自动驾驶 --collect-only"
    },
    {
      "type": "pending_outputs",
      "count": 12,
      "severity": "low",
      "reason": "12 个待处理项目超过 7 天未处理",
      "suggested_action": "审核队列",
      "suggested_command": "review_queue.py --collect-only"
    },
    {
      "type": "stale_pages",
      "count": 5,
      "severity": "medium",
      "reason": "5 个页面时间戳早于引用来源",
      "suggested_action": "主张分析",
      "suggested_command": "claim_evolution.py --collect-only"
    },
    {
      "type": "low_health_score",
      "score": 72,
      "severity": "high",
      "reason": "健康评分低于 80",
      "suggested_action": "健康检查",
      "suggested_command": "wiki_lint.py --collect-only"
    }
  ],
  "last_maintenance": "2026-04-15",
  "days_since_maintenance": 17,
  "health_score": 72
}
```

**触发时机**：
- 每次用户进入对话时，LLM 读取 `--auto-suggest` 输出
- 如果有 high severity → 在对话开头展示维护提示
- 如果有 medium severity → 在自然时机（如入库完成后）展示
- low severity → 不主动提示，用户问"状态"时展示

**通知方式**（对话开头，仅 high severity）：
```
知识库有 1 项需要关注：健康评分 72/100。说 "lint" 可查看详情。
```

**实现**：
- 修改 `scripts/stale_report.py`：新增 `--auto-suggest` 模式
- 修改 `references/maintenance-guide.md`：新增"自动维护建议"段

### 3.5 入库后自动 lint 计数

**对标参考**：中文 Skill 每 10 个素材后主动建议 lint。

**方案**：在入库完成后，读取 log.md 的 ingest 记录数，每 10 的倍数时建议。

**触发条件**：
```
入库完成后：
  1. 统计 log.md 中 "## ingest" 的记录数
  2. 如果是 10 的倍数 → 建议 lint
```

**通知方式**：
```
已有 {N} 篇素材入库。建议运行健康检查。说 "lint" 可执行。
```

---

## 四、智能检索（Smart Retrieval）

### 4.1 设计目标

解决大规模知识库中 LLM 认知负担过重的问题。入库几百篇后，LLM 无法高效 grep 搜索整个 vault——每次查询重复扫描相同页面，噪声大、效率低，违背"脚本做机械操作、LLM 做语义判断"的设计原则。

**核心思路**：用语义索引替代全文扫描，用评分排序替代 LLM 逐页判断，用结构化上下文包替代 raw grep 结果。

### 4.2 三层架构

```
用户问题
  ↓
[1] 语义索引（wiki_index_v2.py --rebuild）
  ↓  wiki/semantic-index.json
[2] 智能检索（wiki_retrieve.py --query）
  ↓  结构化上下文包（JSON）
[3] LLM 综合回答
```

#### 层 1：语义索引

**脚本**：`wiki_index_v2.py --rebuild`

**产出**：`wiki/semantic-index.json`

**索引结构**：
```json
{
  "domains": {
    "自动驾驶": {
      "sources": ["sources/xxx", "sources/yyy"],
      "concepts": ["concepts/bev感知"],
      "entities": ["entities/tesla"],
      "last_updated": "2026-04-15"
    }
  },
  "concepts": {
    "bev感知": {
      "ref": "concepts/bev感知",
      "title": "BEV 感知",
      "status": "developing",
      "confidence": "Working",
      "domains": ["自动驾驶"],
      "sources": ["sources/xxx"],
      "related_concepts": ["端到端", "occupancy-network"]
    }
  },
  "entities": { "同上结构" },
  "claims": [
    {
      "text": "BEV 感知的主要局限是...",
      "confidence": "Working",
      "source": "sources/xxx",
      "source_title": "...",
      "domain": "自动驾驶"
    }
  ],
  "relationships": [
    {"from": "stances/xxx", "to": "sources/yyy", "type": "supports"}
  ],
  "sources": {
    "xxx": {
      "ref": "sources/xxx",
      "title": "...",
      "domains": ["自动驾驶"],
      "confidence": "Working",
      "date": "2026-04-15",
      "quality": "good",
      "related_concepts": ["bev感知", "端到端"]
    }
  },
  "stats": {
    "total_sources": 50,
    "total_concepts": 20,
    "total_entities": 15,
    "total_domains": 5,
    "total_claims": 120,
    "total_relationships": 30,
    "built_at": "2026-05-02T10:00:00"
  }
}
```

**提取逻辑**：
- domains：从 frontmatter tags 和 `## 主题域` 段链接提取
- concepts/entities：从 wiki/concepts/、wiki/entities/ 目录扫描
- claims：从 `## 关键判断` 段的 `- [类型|置信度] 声明` 模式提取
- relationships：从 stance 页的 `## 支持证据` / `## 反对证据` 段提取

**更新时机**：每次入库完成后自动重建（L0 层全自动）

#### 层 2：智能检索

**脚本**：`wiki_retrieve.py --query "问题" --top-k 5 --read 3`

**评分公式**：
```
score = title_match × 8
      + slug_match × 6
      + claim_match × 3
      + domain_overlap × 4
      + concept_overlap × 3
      + folder_base_weight (sources=6, briefs=5, syntheses=4, ...)
      + status_boost (evergreen=4, mature=3, developing=1)
      + confidence_boost (Stable=4, Supported=3, Working=2)
      + recency_boost (30天内=3, 90天内=2, 180天内=1)
```

**输出结构**（结构化上下文包）：
```json
{
  "query": "BEV感知的局限性",
  "terms": ["BEV感知", "局限性"],
  "top_pages": [
    {"ref": "sources/xxx", "title": "...", "score": 8.5, "domains": ["自动驾驶"], "confidence": "Working"}
  ],
  "claims": [
    {"text": "...", "confidence": "Working", "source": "sources/xxx"}
  ],
  "relationships": [...],
  "page_contents": [
    {"ref": "sources/xxx", "核心摘要": "...", "关键判断": "...", "score": 8.5}
  ],
  "total_scored": 25
}
```

**参数说明**：
- `--top-k`：返回页数（默认 5，深度综合时用 8）
- `--read`：深度阅读页数（默认 3，反驳材料时用 5）
- `--types`：限定搜索范围（如 `source,concept`）
- `--json`：输出 JSON 到 stdout

#### 层 3：LLM 综合

LLM 消费结构化上下文包，无需自己 grep 搜索。上下文包中的 `page_contents` 已包含关键段落，通常不需要再读全文。仅当问题涉及精确数字、原文引用时，才回到 `raw/articles/` 验证。

### 4.3 与旧查询流程的对比

| 维度 | 旧流程（LLM grep） | 新流程（智能检索） |
|------|-------------------|-------------------|
| 搜索方式 | LLM 逐个 grep 关键词 | 脚本查语义索引，评分排序 |
| 排序依据 | LLM 靠标题和目录判断 | 综合 8 个维度的评分公式 |
| 上下文消耗 | 每次读 5-10 个完整页面 | 预提取关键段落，通常不需再读全文 |
| 可扩展性 | 页面越多，grep 越慢越噪声 | 索引一次，查询 O(n) |
| 一致性 | LLM 每次搜索策略可能不同 | 脚本行为确定，可复现 |

### 4.4 兜底机制

当 `semantic-index.json` 不存在（未运行 `--rebuild`）时，退回旧的 grep 搜索流程。确保系统在任何状态下都能工作。

### 4.5 Prompt 约束

修改 `references/query-guide.md` 的 Step 2（搜索 Vault）：

```markdown
## Step 2: 搜索 Vault（智能检索）

首选 wiki_retrieve.py 智能检索。脚本从语义索引中评分排序，输出结构化上下文包。

### 2a. 智能检索（首选）
运行：python scripts/wiki_retrieve.py --vault "D:\Vault" --query "用户问题" --top-k 5 --read 3

### 2b. 语义索引查询（补充）
运行：python scripts/wiki_index_v2.py --vault "D:\Vault" --query "概念"

### 2c. Grep 兜底（仅在索引不可用时）
退回旧的 grep 搜索流程。
```

---

## 五、实施计划

### Phase 1：洞见识别（S 工作量）✅ 已完成

| 改动 | 文件 | 类型 | 状态 |
|------|------|------|------|
| 新增洞见识别 prompt 约束 | `references/prompts/insight_detection.md` | 新增 | ✅ |
| query-guide.md 新增洞见识别段 | `references/query-guide.md` | 修改 | ✅ |
| interaction.md 新增轻量提示段 | `references/interaction.md` | 修改 | ✅ |

### Phase 2：深度研究触发（S 工作量）✅ 已完成

| 改动 | 文件 | 类型 | 状态 |
|------|------|------|------|
| query-guide.md 新增深度研究引导段 | `references/query-guide.md` | 修改 | ✅ |
| research-guide.md 新增对话触发说明 | `references/research-guide.md` | 修改 | ✅ |

### Phase 3：自动维护（M 工作量）✅ 已完成

| 改动 | 文件 | 类型 | 状态 |
|------|------|------|------|
| 新增 review sweep prompt | `references/prompts/review_sweep.md` | 新增 | ✅ |
| review_queue.py 新增 --sweep 模式 | `scripts/review_queue.py` | 修改 | ✅ |
| stale_report.py 新增 --auto-suggest 模式 | `scripts/stale_report.py` | 修改 | ✅ |
| ingest-guide.md 新增入库后自动检查 | `references/ingest-guide.md` | 修改 | ✅ |
| maintenance-guide.md 新增自动维护段 | `references/maintenance-guide.md` | 修改 | ✅ |

### Phase 4：智能检索（M 工作量）✅ 已完成

| 改动 | 文件 | 类型 | 状态 |
|------|------|------|------|
| 语义索引构建器 | `scripts/wiki_index_v2.py` | 新增 | ✅ |
| 智能检索脚本 | `scripts/wiki_retrieve.py` | 新增 | ✅ |
| query-guide.md Step 2 重设计 | `references/query-guide.md` | 修改 | ✅ |
| SPEC.md 查询架构更新 | `docs/SPEC.md` | 修改 | ✅ |
| SKILL.md 脚本入口更新 | `SKILL.md` | 修改 | ✅ |

### 验收标准

- [x] 洞见识别：对话中引用 ≥ 3 来源的综合回答自动写入 outputs/，末尾有提示
- [x] 深度研究触发：vault 覆盖不足时末尾有升级提示
- [x] 健康检查：入库后自动评分，评分下降时有提示
- [x] 审核队列：outputs/ 积压 ≥ 10 时有提示，sweep 自动清理已失效项
- [x] 维护建议：`--auto-suggest` 输出结构化 JSON
- [x] 智能检索：`wiki_retrieve.py` 输出结构化上下文包，query-guide.md Step 2 使用新流程
- [ ] 所有测试通过（待集成测试）
