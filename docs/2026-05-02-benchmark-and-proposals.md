# 深度对标分析与改进提案

日期：2026-05-02
基线：V1.2.2 (Optimization & Hardening)
对标对象：`llm_wiki-main-app`（桌面应用）、`llm-wiki-skill-main-Chinese`（中文 Skill 版）

---

## 一、对标分析

### 1.1 桌面应用（llm_wiki-main-app）核心架构

**技术栈**：TypeScript / React / Electron / Zustand

**深度研究**：
- 手动触发：用户在 ResearchPanel 输入 topic 或从 Review 项点击 "Deep Research"
- 队列系统：`research-store` 管理并发（maxConcurrent），支持多个研究任务排队
- 多查询策略：`optimizeResearchTopic.ts` 用 LLM 根据 knowledge gap + wiki purpose 生成 2-3 条精准搜索查询
- 自动入库：研究结果保存到 `wiki/queries/` 后，自动调用 `autoIngest()` 生成实体、概念、交叉引用
- 流式渲染：synthesis 实时流式显示，支持 `<think>` 标签折叠

**健康维护**：
- 结构化 lint：`runStructuralLint()` 检查孤立页、断链、无出链页（确定性检查）
- 语义 lint：`runSemanticLint()` 用 LLM 检查矛盾、过时、缺失页、建议
- Review 自动清理：`sweepResolvedReviews()` 两阶段——规则匹配（文件名/frontmatter title/affectedPages）+ LLM 批量判断（batch=40, max=5 batches）
- 重复检测：`runDuplicateDetection()` 用 LLM 扫描 entity/concept 页，分组疑似重复，用户确认后排队合并
- 维护 UI：`maintenance-section.tsx` 提供扫描、确认、合并、跳过的完整交互

**知识图谱洞察**（`graph-insights.ts`）：
- 惊人连接检测：跨社区、跨类型、peripheral-to-hub 的边，打分排序
- 知识缺口检测：孤立节点（degree≤1）、稀疏社区（cohesion<0.15）、桥节点（连接≥3社区）
- `optimizeResearchTopic.ts`：根据 gap 类型生成针对性研究 topic + 搜索查询

**知识富化**（`enrich-wikilinks.ts`）：
- LLM 返回 `{term, target}` JSON 替代完整重写，代码做字符串替换
- 安全设计：只替换首次出现、跳过已有 wikilink、不动 frontmatter

**入库流程**：
- 两步 LLM：Step 1 结构化分析 → Step 2 生成 FILE/REVIEW blocks
- REVIEW blocks 自动进入 Review 队列，支持 `SEARCH:` 字段供 Deep Research 使用
- 页面合并：已有页面用 LLM 合并而非覆盖，合并前自动备份

### 1.2 中文 Skill 版（llm-wiki-skill-main-Chinese）核心架构

**技术栈**：纯 SKILL.md + Shell/Node 脚本（无 TypeScript/React）

**工作流路由**：10 个工作流（init / ingest / batch-ingest / query / digest / lint / status / graph / delete / crystallize）

**入库流程**：
- 两步 LLM：Step 1 结构化 JSON（entities/topics/connections/contradictions）→ Step 2 页面生成
- 置信度标注：EXTRACTED / INFERRED / AMBIGUOUS / UNVERIFIED，每条带 evidence 字段
- Step 1 验证：`validate-step1.sh` 检查 JSON schema，失败自动回退单步
- 缓存机制：`cache.sh check/update/invalidate`，基于内容 hash 去重
- 来源适配器：`source-registry.sh` + `adapter-state.sh` 统一管理外挂状态

**健康检查（lint）**：
- Step 0 脚本机械检查：`lint-runner.sh` 检查孤立页、断链、index 一致性、图片资产、source-signal 覆盖
- Step 1 AI 判断：矛盾信息、交叉引用缺失、置信度报告、补充建议
- 每 10 个素材后主动建议 lint

**知识图谱**：
- `graph-analysis.js`：Louvain 社区检测、3 信号边权重（共引强度/来源重叠/类型亲和度）
- 洞察生成：surprising_connections、isolated_nodes、bridge_nodes、sparse_communities
- `buildLearning()`：推荐起始节点、路径视图/社区视图/全局视图
- 交互式 HTML：东方编辑部 × 数字山水风，支持搜索/社区筛选/节点详情

**独特功能**：
- **crystallize（结晶化）**：将对话中的有价值内容提取为 wiki 页面
- **digest（深度综合）**：跨素材深度报告，支持 3 种格式（深度报告/对比表/时间线）
- **purpose.md**：研究方向文件，指导所有入库的取舍和权重
- **别名词表**：`.wiki-schema.md` 中的同义词映射，查询/入库时自动展开
- **隐私自查**：入库前让用户确认无敏感信息

### 1.3 我们的系统（Obsidian-wiki-skill-V1.2）差距分析

| 维度 | 桌面应用 | 中文 Skill | 我们的系统 | 差距 |
|------|---------|-----------|-----------|------|
| 深度研究触发 | 手动 + Review 项触发 | 手动 + digest 工作流 | 手动触发 | 缺少前端轻量识别 |
| 研究结果反馈 | autoIngest 自动生成实体/概念 | digest 生成 synthesis 页 | 独立报告，不自动拆解 | 报告结论不回流 |
| 健康维护 | 自动 sweep + LLM 判断 | 脚本机械检查 + AI 判断 | 全手动触发 | 无自动维护 |
| 知识沉淀 | Review 队列 + 页面合并 | crystallize + purpose.md | apply_approved_delta 手动 | 缺少对话价值捕获 |
| 图谱洞察 | graph-insights.ts 规则 | Louvain + 3 信号 + 学习路径 | 无图谱功能 | 完全缺失 |
| 重复检测 | LLM 扫描 + 手动合并 | 别名词表 | 无 | 完全缺失 |
| 置信度标注 | 无 | EXTRACTED/INFERRED/AMBIGUOUS/UNVERIFIED | [Fact]/[Inference]/[Assumption] | 已有，但缺 evidence |
| 缓存/去重 | ingest-cache.ts | cache.sh | 无 | 缺失 |
| 多语言 | output-language.ts 自动检测 | WIKI_LANG 配置 | 中文固定 | 低优先级 |

---

## 二、改进提案

基于对标分析，针对用户提出的三个改进方向，结合两个参考系统的最佳实践：

### 提案 A：对话价值捕获 — "好问题"识别与结晶化

**问题**：用户与 LLM 的高质量问答是最高价值数据来源，但当前无法自动识别和固化。

**对标参考**：
- 中文 Skill 的 `crystallize` 工作流：用户主动提供内容 → 提取核心洞见 → 保存到 `wiki/synthesis/sessions/`
- 桌面应用的 Review 队列：LLM 在入库时生成 REVIEW blocks，自动进入待处理队列

**设计**：

#### A1. 新增 `crystallize` 行为指南

在 `references/` 下新增 `crystallize-guide.md`：

**触发条件**：
- 用户说"结晶化"、"crystallize"、"把这段对话记进知识库"
- LLM 判断当前对话包含高价值洞见时主动建议（≥3 个跨素材综合观点）

**流程**：
1. 用户提供内容（文字粘贴或明确引用某段上下文）
2. LLM 提取：核心洞见（3-5 条）、关键决策和原因、值得记录的结论
3. 生成 `wiki/synthesis/sessions/{主题}-{日期}.md`
4. 更新 log.md

**与现有系统集成**：
- 结晶化页面的 frontmatter 包含 `type: synthesis`、`origin: crystallize`、`derived: true`
- 不自动参与 claim_evolution（来源是对话推断，非一手素材）
- 后续 ingest 可引用结晶化页面作为补充材料，但关系统一按 `[Inference]` 处理

#### A2. 查询持久化增强

当前查询输出到 `wiki/outputs/`，生命周期为 `temporary`。增强为：

**自动持久化建议**：当查询引用了 ≥3 个来源的综合分析时，主动建议保存为 query 页面。

**query 页面规范**：
- frontmatter：`type: query`、`derived: true`、`origin: conversation`
- 保存路径：`wiki/outputs/{date}-{short-hash}.md`（避免命名冲突）
- 自引用防护：后续 ingest 不主动扫描 `wiki/outputs/`，只有当前问题确实需要时才读取

### 提案 B：深度研究前端轻量识别

**问题**：深度研究触发完全手动，缺少"在触发前先做轻量识别"的能力。

**对标参考**：
- 桌面应用的 `optimizeResearchTopic.ts`：根据 knowledge gap 类型 + wiki purpose 生成精准搜索查询
- 桌面应用的 `graph-insights.ts`：自动检测知识缺口（孤立节点、稀疏社区、桥节点）
- 中文 Skill 的 `digest` 工作流：先搜索相关页面 → 深度阅读 → 生成综合报告

**设计**：

#### B1. 新增 `pre-research` 轻量识别阶段

在 `deep-research-protocol.md` 的 Phase 0 之前插入 Pre-Phase：

**触发**：用户说"深入研究"、"deep research"时，先执行轻量识别再进入正式研究。

**步骤**：

1. **领域方向识别**（1 轮 LLM 调用）：
   - 输入：用户问题 + `wiki/index.md` + `wiki/hot.md`
   - 输出：领域标签 + 与现有知识库的关联度评分（0-100）
   - 关联度 < 30 时提示："这个话题与现有知识库关联度较低，建议先做基础入库再深度研究"

2. **Top 3 依赖识别**（vault 搜索，无 LLM 调用）：
   - 搜索 vault 中与主题最相关的 3 个已有页面
   - 输出：依赖列表 + 每个页面的核心观点摘要（≤50 字）
   - 如果依赖页面 < 3 个，提示："现有知识库覆盖不足，建议先补充基础素材"

3. **研究方向确认**（向用户展示）：
   ```
   识别到的研究方向：{领域标签}
   与现有知识库关联度：{score}/100

   已有相关知识：
   - [[页面1]]：{核心观点}
   - [[页面2]]：{核心观点}
   - [[页面3]]：{核心观点}

   建议研究路径：{1-2 句话}

   是否继续深度研究？
   ```

4. **用户确认后**进入正式 Phase 1（意图扩展）

**实现位置**：
- 新增 `scripts/pipeline/pre_research.py`：`--collect-only` 输出领域标签 + 依赖列表
- 新增 `references/prompts/pre_research.md`：LLM prompt 约束
- 修改 `references/research-guide.md`：在 Phase 0 前插入 Pre-Phase 描述

#### B2. 研究结果自动拆解回流

**问题**：深度研究报告保存到 `wiki/research/` 后，结论不回流为 wiki 页面。

**对标参考**：桌面应用在研究完成后自动调用 `autoIngest()`，将研究结果作为新素材入库。

**设计**：

在 `deep-research-protocol.md` 的 Phase 9（报告生成）之后新增 Phase 10：

**Phase 10：结论回流**

1. 从研究报告中提取：
   - 稳定结论（≥70% 置信度）→ 候选 entity/concept 页面
   - 工作假说（40-70%）→ 标记为 `[Hypothesis X%]`，不生成独立页面
   - 关键边界条件 → 更新已有页面的边界条件段

2. LLM 判断哪些结论值得生成独立页面：
   - 输入：研究报告 + 现有 wiki 结构
   - 输出：JSON 列表 `[{slug, type, content_summary, confidence}]`

3. 生成页面时标注来源：
   - frontmatter：`origin: deep-research`、`sources: ["research/{slug}--report.md"]`
   - 正文：每条结论带 `[Fact]`/`[Inference]`/`[Hypothesis X%]` 标签

4. 不自动写入——展示给用户确认后执行：
   ```
   深度研究报告中有 {N} 条结论值得沉淀为 wiki 页面：
   - {结论1}（置信度 {X}%）→ 建议创建 wiki/sources/{slug}.md
   - {结论2}（置信度 {Y}%）→ 建议更新 [[已有页面]]

   是否执行？
   ```

**实现位置**：
- 修改 `scripts/pipeline/deep_research.py`：新增 `--extract-conclusions` 模式
- 新增 `references/prompts/conclusion_extraction.md`：LLM 提取结论的 prompt 约束
- 修改 `references/research-guide.md`：新增 Phase 10 描述

### 提案 C：自动化健康维护

**问题**：所有 4 个维护场景（lint、claim evolution、synthesis refresh、review queue）需要手动触发。

**对标参考**：
- 桌面应用的 `sweepResolvedReviews()`：ingest 队列清空后自动触发，规则匹配 + LLM 批量判断
- 桌面应用的 `runDuplicateDetection()`：手动触发但结果自动进入合并队列
- 中文 Skill 的 lint 触发：每 10 个素材后主动建议

**设计**：

#### C1. 维护建议自动生成

**问题**：用户不知道什么时候该跑维护。

**方案**：新增 `stale_report.py --auto-suggest` 模式。

**输出 schema**：
```json
{
  "suggestions": [
    {
      "type": "stale_synthesis",
      "target": "syntheses/自动驾驶--综合分析",
      "severity": "medium",
      "reason": "综合页最后更新 30 天前，期间新增 3 篇来源",
      "suggested_command": "refresh_synthesis.py --domain 自动驾驶 --collect-only"
    },
    {
      "type": "pending_reviews",
      "count": 5,
      "severity": "low",
      "reason": "5 个审核项超过 7 天未处理",
      "suggested_command": "review_queue.py --collect-only"
    },
    {
      "type": "low_confidence_claims",
      "count": 8,
      "severity": "medium",
      "reason": "8 个低置信度主张超过 14 天未验证",
      "suggested_command": "wiki_lint.py --collect-only"
    }
  ],
  "last_maintenance": "2026-04-15",
  "days_since_maintenance": 17
}
```

**触发时机**：
- 每次用户进入对话时，LLM 读取 `--auto-suggest` 输出
- 如果有 medium/high severity 建议，在对话开头展示维护提示
- 用户可以选择立即执行或稍后处理

**实现位置**：
- 修改 `scripts/stale_report.py`：新增 `--auto-suggest` 模式
- 修改 `references/maintenance-guide.md`：新增"自动维护建议"段

#### C2. 入库后自动 lint 触发

**对标参考**：中文 Skill 每 10 个素材后主动建议 lint。

**方案**：在 `log.md` 中追踪素材计数，每 10 个素材后在对话中建议运行 lint。

**实现**：
- LLM 在每次入库完成后读取 `log.md` 的 ingest 记录数
- 如果是 10 的倍数，主动建议："已有 {N} 篇素材，建议运行健康检查"
- 不自动执行——用户确认后再触发

#### C3. Review 项自动清理（对标桌面应用的 sweep）

**问题**：`wiki/outputs/` 中的临时页面积累后无人清理。

**方案**：新增 `review_queue.py --sweep` 模式，对标桌面应用的 `sweepResolvedReviews()`。

**两阶段清理**：
1. 规则匹配：
   - `missing-page` 类型：检查 affectedPages 是否已存在 → 自动解决
   - `temporary` lifecycle 页面：检查是否已被 synthesis 吸收 → 标记为可清理
2. LLM 判断：
   - 对剩余 pending 项，批量发送给 LLM 判断是否已解决
   - batch=20, max=3 batches（比桌面应用更保守）

**实现位置**：
- 修改 `scripts/review_queue.py`：新增 `--sweep` 模式
- 新增 `references/prompts/review_sweep.md`：LLM 判断 prompt

---

## 三、实施优先级

| 提案 | 工作量 | 优先级 | 依赖 |
|------|--------|--------|------|
| A1. crystallize 行为指南 | S | P1 | 无 |
| A2. 查询持久化增强 | S | P1 | 无 |
| B1. pre-research 轻量识别 | M | P2 | 需新增脚本 + prompt |
| B2. 研究结果自动拆解回流 | M | P2 | 需新增脚本 + prompt |
| C1. 维护建议自动生成 | M | P2 | 需修改 stale_report.py |
| C2. 入库后自动 lint 触发 | S | P3 | 仅行为指南修改 |
| C3. Review 项自动清理 | L | P3 | 需新增 sweep 模式 + prompt |

**建议实施顺序**：
```
Phase 1（立即）：A1 + A2 → 结晶化 + 查询增强
Phase 2（短期）：B1 + C1 → 前端识别 + 维护建议
Phase 3（中期）：B2 + C3 → 研究回流 + Review 清理
Phase 4（长期）：C2 → 入库后 lint 触发
```

---

## 四、详细规格（逻辑闭环）

### 4.1 提案 C 详细规格：Review 自动清理

**来源**：桌面应用 `sweep-reviews.ts` 完整逻辑提取。

#### 触发时机

桌面应用的触发条件：**ingest 队列清空后自动触发**。即每次入库完成后，自动扫描 pending review 项。

我们的对等实现：每次 LLM 完成入库操作后，在展示入库结果前，自动执行一次 sweep。

#### 阶段 1：规则匹配（确定性，无 LLM 调用）

遍历所有 `status: pending` 的 review 项，按 type 分类处理：

**规则 R1 — missing-page 类型**：
```
条件：review.type == "missing-page"
逻辑：
  1. 从 review.title 提取候选页面名（去除 "Missing page:" 前缀，normalize）
  2. 从 review.affectedPages 提取文件名（取 basename，去 .md）
  3. 在 wiki/ 目录下检查这些候选名是否已存在：
     - 精确文件名匹配（kebab-case）
     - frontmatter title 匹配
  4. 如果任意候选名匹配到已存在页面 → 标记为 resolved
结果：该 review 项标记为 auto-resolved（规则匹配）
```

**规则 R2 — duplicate 类型**：
```
条件：review.type == "duplicate"
逻辑：
  1. 获取 review.affectedPages 列表
  2. 检查每个页面是否仍然存在于 wiki/ 中
  3. 如果任意页面已不存在（被用户删除或合并）→ 标记为 resolved
     （因为重复场景已改变，review 不再适用）
结果：该 review 项标记为 auto-resolved（规则匹配）
```

**规则 R3 — contradiction / suggestion / confirm 类型**：
```
条件：review.type 为 contradiction / suggestion / confirm
逻辑：跳过，不做规则匹配（需要人工判断）
结果：进入阶段 2（LLM 判断）
```

#### 阶段 2：LLM 语义判断（对阶段 1 剩余项）

**批次参数**（对标桌面应用）：
- batch_size = 20（桌面应用用 40，我们更保守）
- max_batches = 3（桌面应用用 5，我们更保守）
- 提前终止：如果某批次 resolved = 0，停止后续批次

**LLM Prompt**（对标桌面应用的 judgeBatch）：
```
你正在清理一个个人知识库的过时审核队列。
在最近的入库操作后，某些审核项可能不再有效：
缺失的页面可能已创建，重复项可能已合并，引用的概念可能已添加。

当前知识库页面列表（文件名，可选 title）：
{page_list}

待判断的审核项：
{review_list}

对每个审核项，判断其底层条件是否已被当前知识库状态解决。
保守原则：只有在你确信该问题不再存在时，才标记为 resolved。
对于矛盾、确认、需要人工判断的项，默认保持 pending。

输出格式（严格 JSON）：
{"resolved": ["id1", "id2"]}
如果没有项被解决：{"resolved": []}
不要添加 markdown fences 或其他文本。
```

**输出校验**（对标桌面应用的 extractJsonObject）：
1. 从 LLM 响应中提取 JSON 对象（处理 fences、prose 包裹）
2. 验证 `resolved` 字段是数组
3. 只接受属于当前 batch 的 ID（防止幻觉 ID）
4. 任何解析失败 → 返回空集（保守策略）

#### 与现有系统集成

**改动文件**：
- `scripts/review_queue.py`：新增 `--sweep` 模式
- `references/prompts/review_sweep.md`：LLM 判断 prompt
- `references/maintenance-guide.md`：新增 sweep 触发说明

**CLI 接口**：
```powershell
# 阶段 1：规则匹配（确定性）
python scripts/review_queue.py --vault <vault> --sweep --rules-only

# 阶段 1+2：规则匹配 + LLM 判断
python scripts/review_queue.py --vault <vault> --sweep

# 输出 JSON：
{
  "rule_resolved": [{"id": "...", "reason": "page now exists"}],
  "llm_resolved": [{"id": "...", "reason": "llm-judged"}],
  "still_pending": [...]
}
```

---

### 4.2 提案 B 详细规格：深度研究前端识别

**来源**：桌面应用 `optimize-research-topic.ts` + `graph-insights.ts` 完整逻辑提取。

#### Pre-Phase：轻量识别（对标桌面应用的 optimizeResearchTopic）

**输入**：用户的研究主题（自然语言）

**步骤 1：知识库关联度评估**（对标桌面应用的 findRelevantPages）

```
逻辑：
1. 读取 wiki/index.md 获取所有页面条目
2. 用 term overlap 计算主题与每个页面的相关性：
   - 分词：主题按空格/标点拆分为 terms
   - 匹配：页面标题 + frontmatter tags 中包含任一 term → 候选
   - 排序：按 term 命中数降序
3. 取 top-3 页面作为上下文来源
4. 计算关联度评分：
   - top-3 页面的 term 覆盖率 × 100
   - 如果 top-3 为空 → 关联度 = 0
```

**步骤 2：知识缺口检测**（对标桌面应用的 detectKnowledgeGaps）

从 `wiki_lint.py --collect-only` 的输出中提取：
- `low_confidence_claims`：低置信度主张数
- `orphan_pages`：孤立页面数
- `broken_links`：断链数

按严重程度映射（对标桌面应用的 gap severity 表）：

| 缺口类型 | 条件 | 严重程度 | 建议操作 |
|---------|------|---------|---------|
| isolated-node | 孤立页面数 ≥ 5 | medium | 建议先补充交叉引用 |
| knowledge-gap | 主题相关页面 < 3 | high | 建议先做基础入库 |
| low-confidence | 低置信度主张 ≥ 10 | medium | 建议先验证已有主张 |
| fresh-start | 关联度 = 0 | high | 建议先建立基础框架 |

**步骤 3：搜索查询生成**（对标桌面应用的优化查询逻辑）

```
输入：用户主题 + top-3 页面摘要 + wiki purpose
输出：2-3 条优化后的搜索查询

生成规则：
1. 主查询：直接使用用户主题
2. 补充查询：基于 top-3 页面的上下文生成
   - 如果 top-3 包含 synthesis 页面 → 生成更新查询
   - 如果 top-3 包含 source 页面 → 生成深度查询
   - 否则 → 生成广度查询
3. 查询去重：normalize 后比较，跳过已存在的查询
```

**步骤 4：向用户展示预研结果**

```
预研分析：

研究主题：{topic}
知识库关联度：{score}/100

已有相关知识（top-3）：
- [[页面1]]：{frontmatter title 或首行摘要}
- [[页面2]]：{同上}
- [[页面3]]：{同上}

知识缺口：
- {gap_type}：{description}（严重程度：{severity}）

建议搜索策略：
1. {query_1}
2. {query_2}
3. {query_3}

建议操作：{action_suggestion}

是否继续深度研究？
```

**与现有系统集成**：

改动文件：
- `scripts/pipeline/deep_research.py`：新增 `--pre-research` 模式
- `references/prompts/pre_research.md`：搜索查询生成 prompt
- `references/research-guide.md`：新增 Pre-Phase 描述

CLI 接口：
```powershell
python scripts/pipeline/deep_research.py --vault <vault> --pre-research --topic "<topic>" --json

# 输出 JSON：
{
  "relevance_score": 75,
  "top_pages": [{"path": "...", "title": "...", "summary": "..."}],
  "gaps": [{"type": "knowledge-gap", "severity": "high", "description": "..."}],
  "suggested_queries": ["query 1", "query 2"],
  "action_suggestion": "建议先补充 2 篇基础素材再深度研究"
}
```

---

### 4.3 提案 A 详细规格：结晶化

**来源**：中文 Skill `crystallize` 工作流完整逻辑提取。

#### 触发条件

**用户主动触发**（必须）：
- 关键词：结晶化、crystallize、把这段对话记进知识库、这段对话很有价值
- 用户必须主动提供内容（文字粘贴或明确引用某段上下文）
- Claude 不自动提取当前会话

**LLM 主动建议触发**（可选）：
- 当查询结果引用了 ≥3 个来源的综合分析时
- 当对话中出现了跨素材的新洞见时
- 建议语："这段对话中有几个值得固化的洞见，是否要结晶化保存到知识库？"

#### 处理流程

**Step 1：内容提取**（LLM 执行）

输入：用户提供的内容

输出 JSON：
```json
{
  "insights": [
    {"statement": "核心洞见 1", "confidence": "INFERRED", "evidence": "推理依据"},
    {"statement": "核心洞见 2", "confidence": "INFERRED", "evidence": "推理依据"}
  ],
  "decisions": [
    {"decision": "关键决策", "reason": "决策原因"}
  ],
  "conclusions": [
    {"conclusion": "值得记录的结论", "confidence": "INFERRED"}
  ]
}
```

置信度规则（对标中文 Skill）：
- `INFERRED`：来自对话推断，非一手素材（默认）
- 不使用 `EXTRACTED`（因为没有原始素材可回溯）

**Step 2：页面生成**

保存路径：`wiki/synthesis/sessions/{主题}-{日期}.md`

Frontmatter：
```yaml
---
type: synthesis
origin: crystallize
derived: true
created: {日期}
updated: {日期}
tags: []
related: []
sources: []
---
```

内容结构（对标中文 Skill 的 synthesis-template）：
```markdown
# {主题} — 对话结晶

> 来源：对话结晶化 | 生成日期：{日期}

## 核心洞见
- 洞见 1 <!-- confidence: INFERRED -->
- 洞见 2 <!-- confidence: INFERRED -->

## 关键决策
- 决策 1：原因

## 结论
- 结论 1 <!-- confidence: INFERRED -->

## 原始对话摘录
> {用户提供的原始内容，保留关键段落}
```

**Step 3：更新 log.md**

追加：`## {日期} crystallize | {主题}`

#### 与现有系统的关系

- **不自动参与 claim_evolution**：crystallize 来源是对话推断，不是一手素材
- **后续 ingest 可引用**：作为补充材料，但关系统一按 `[Inference]` 处理
- **自引用防护**：后续 ingest 不主动扫描 `wiki/synthesis/sessions/`，只有当前问题确实需要时才读取

---

## 五、实施优先级（修订）

| 提案 | 工作量 | 优先级 | 理由 |
|------|--------|--------|------|
| A1. crystallize 行为指南 | S（纯文档） | P1 | 最小改动，最高价值 |
| C3. Review sweep（规则+LLM） | M（脚本+prompt） | P1 | 解决 outputs 积压问题 |
| B1. pre-research 识别 | M（脚本+prompt） | P2 | 改善研究体验 |
| C1. 维护建议自动生成 | M（脚本改造） | P2 | 减少手动触发 |
| B2. 研究结论回流 | L（脚本+prompt+指南） | P3 | 需要较多改动 |
| C2. 入库后 lint 建议 | S（纯文档） | P3 | 仅行为指南修改 |

**修订理由**：C3 提升到 P1，因为 `wiki/outputs/` 积压是最直接的痛点，且规则匹配部分（阶段 1）是纯确定性逻辑，不需要 LLM 调用，可以快速实现。

---

## 六、验收标准

### Phase 1 完成标准
- [ ] `references/crystallize-guide.md` 存在且包含完整的触发条件、处理流程、页面模板
- [ ] `review_queue.py --sweep --rules-only` 可执行，正确处理 missing-page 和 duplicate 两种规则
- [ ] `references/prompts/review_sweep.md` 存在且包含完整的 LLM prompt
- [ ] 测试套件全部通过

### Phase 2 完成标准
- [ ] `deep_research.py --pre-research --topic "X" --json` 输出关联度评分 + top-3 页面 + 缺口 + 查询建议
- [ ] `stale_report.py --auto-suggest` 输出结构化 JSON，包含 3 种维护建议类型
- [ ] 测试套件全部通过

### Phase 3 完成标准
- [ ] 深度研究报告保存后展示结论回流建议，用户确认后自动拆解
- [ ] `review_queue.py --sweep`（含 LLM 判断）可执行，batch=20, max=3 batches
- [ ] 测试套件全部通过
