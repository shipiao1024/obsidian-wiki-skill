# 维护行为指南

知识库日常维护。核心原则：**脚本收集数据 → LLM 做判断 → 脚本执行写入**。

## 架构

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  脚本：收集    │ →  │  LLM：判断    │ →  │  脚本：执行    │
│  结构化 JSON   │    │  结构化 JSON   │    │  写文件/渲染   │
└──────────────┘    └──────────────┘    └──────────────┘
```

脚本不做语义判断（相关性、矛盾、重要性）。LLM 不做文件 I/O 和计数。

---

## 维护场景总览

| 场景 | 触发词 | 脚本收集 | LLM 判断 | 脚本执行 |
|------|--------|---------|---------|---------|
| 健康检查 | lint / 体检 | 断链、孤立页、索引、低置信主张 | 矛盾检测、交叉引用、修复建议 | 写报告 |
| 主张演化 | 主张分析 / claim | 所有主张对 | 关系分类（reinforce/contradict/extend） | 写 claim-evolution.md |
| 综合刷新 | 刷新综合 / synthesis | 来源文本 + 关键判断 | 综合结论 + 核心判断 | 写 synthesis 页 |
| 审核队列 | review / 待审 | 输出列表 + delta 草稿 | 优先级排序 + 审核建议 | 写 review_queue.md |
| Review Sweep | sweep / 自动清理 | 待处理 output + 规则匹配结果 | 语义判断 resolved/pending | 修改 lifecycle |
| 自动维护建议 | 状态 / 维护建议 | stale_report 数据 | 无需 LLM | 输出建议 JSON |

---

## 场景 1：健康检查

触发词：`lint`、`体检`、`日常维护`、`检查知识库`

### Step 1: 脚本收集机械数据

```powershell
python scripts/wiki_lint.py --vault "D:\Vault" --collect-only
```

`--collect-only` 输出 JSON 到 stdout，不写报告：

```json
{
  "broken_links": [
    {"source": "sources/slug1", "target": "concepts/X", "line": 42}
  ],
  "orphan_pages": [
    {"path": "concepts/Y", "inbound_links": 0}
  ],
  "index_mismatches": [
    {"in_index": "sources/slug2", "file_exists": false}
  ],
  "low_confidence_claims": [
    {"path": "sources/slug3", "claim": "...", "confidence": "low"}
  ],
  "candidate_pages": [
    {"path": "concepts/Z", "lifecycle": "candidate", "mention_count": 3}
  ],
  "page_sample": [
    {"path": "sources/slug4", "frontmatter": {...}, "body_excerpt": "...(前500字)"}
  ]
}
```

其中 `page_sample` 是随机抽样的 10 个页面的摘要，供 LLM 做语义检查。

### Step 2: LLM 语义分析

**你的角色**：知识库质量审计员。你判断语义问题，不判断格式问题（格式问题脚本已报告）。

**输入**：Step 1 的 JSON。

**分析任务**：

1. **矛盾检测**：阅读 `page_sample` 中的页面内容，识别语义上真正矛盾的主张。注意——措辞差异不是矛盾，逻辑上不可同时为真才是矛盾。

2. **交叉引用建议**：检查 `page_sample` 中相关主题的页面是否应该互相链接但没有。

3. **候选页升级判断**：对 `candidate_pages` 中 mention_count >= 2 的页面，判断是否已具备升级条件（定义不再是占位符、有实质内容）。

4. **修复建议**：对脚本发现的每个问题（断链、孤立页），给出具体可执行的修复操作。

**输出 JSON schema**：

```json
{
  "contradictions": [
    {
      "page_a": "sources/slug1",
      "claim_a": "具体主张文本",
      "page_b": "sources/slug2",
      "claim_b": "具体主张文本",
      "severity": "high|medium",
      "explanation": "为什么这两个主张矛盾"
    }
  ],
  "missing_cross_references": [
    {
      "page_a": "concepts/X",
      "page_b": "concepts/Y",
      "reason": "为什么应该建立链接"
    }
  ],
  "upgrade_candidates": [
    {
      "path": "concepts/Z",
      "current_status": "candidate",
      "recommended_status": "seed|developing",
      "reason": "为什么可以升级"
    }
  ],
  "repair_suggestions": [
    {
      "type": "broken_link|orphan|index_mismatch",
      "target": "page/path",
      "action": "具体修复操作，如'在 sources/slug1 中将 [[X]] 改为 [[Y]]'"
    }
  ],
  "summary": {
    "health_score": 85,
    "critical_issues": 0,
    "warnings": 3,
    "suggestions": 5
  }
}
```

**约束**：

- 只报告真正的语义矛盾，不报告措辞差异
- 修复建议必须具体到页面和操作，不泛泛而谈
- 不确定的判断不列入输出
- 不要自己去读取文件——所有数据已在输入 JSON 中

**健康评分规则**（供 `health_score` 参考）：

| 扣分项 | 每个扣分 |
|--------|----------|
| 语义矛盾（high severity） | -5 |
| 语义矛盾（medium severity） | -3 |
| 断链 | -2 |
| 孤立页 | -1 |
| 索引不一致 | -2 |
| 低置信主张未处理 | -1 |

满分 100，扣完为止，最低 0。

### Step 3: 脚本执行写入

```powershell
python scripts/wiki_lint.py --vault "D:\Vault" --apply-report lint_result.json
```

脚本读取 LLM 输出的 JSON，渲染为 `wiki/review_queue.md` 中的健康检查段落。

### Step 4: 向用户汇报

只汇报需要用户决策的项：

```
健康检查完成。评分：85/100

需要关注：
- 🔴 2 处语义矛盾（sources/slug1 vs sources/slug2）
- 🟡 3 个候选页可升级
- 🟡 2 条断链需修复

要处理哪些？回复编号。
```

---

## 场景 2：主张演化分析

触发词：`主张分析`、`claim`、`演化追踪`

### Step 1: 脚本收集所有主张

```powershell
python scripts/wiki_lint.py --vault "D:\Vault" --collect-claims
```

输出 JSON：

```json
{
  "claims": [
    {
      "path": "sources/slug1",
      "section": "关键判断",
      "claim_type": "causal",
      "confidence": "high",
      "claim_text": "端到端架构消除了模块间的信息损失"
    }
  ],
  "total_count": 42,
  "sources_count": 15
}
```

### Step 2: LLM 分析主张关系

**你的角色**：知识图谱分析师。你从主张文本中识别语义关系。

**输入**：Step 1 的 JSON。

**分析任务**：

对所有主张两两比较，识别语义上相关的对，判断关系类型。

**关系判断标准**：

| 关系 | 定义 | 示例 |
|------|------|------|
| reinforce | 两个主张在同一个方向上互相支撑 | "BEV 感知有效" + "BEV+Transformer 精度更高" |
| contradict | 两个主张逻辑上不可同时为真 | "高精地图是必须的" + "无图方案达到同等精度" |
| extend | 一个主张在另一个基础上增加新信息 | "端到端是趋势" + "端到端需要中央计算架构支撑" |

**关键约束**：

- 矛盾判断需要**逻辑推理**，不是关键词对立。"会/不会"只是表面模式，真正的矛盾是"X 是必要的" vs "X 可以被替代"
- 只匹配语义上真正相关的主张对。两个主张碰巧讨论同一个领域但角度完全不同，不算相关
- 不确定关系类型时标注 `"uncertain"`，不要猜
- 比较复杂度控制：如果总主张数 > 50，先按 domain 分组，只在组内和跨组的高频概念之间比较

**输出 JSON schema**：

```json
{
  "relationships": [
    {
      "left_text": "主张A文本",
      "left_source": "sources/slug1",
      "left_confidence": "high",
      "right_text": "主张B文本",
      "right_source": "sources/slug2",
      "right_confidence": "medium",
      "relationship": "reinforce|contradict|extend|uncertain",
      "reasoning": "为什么是这个关系——引用具体的逻辑"
    }
  ],
  "statistics": {
    "total_pairs_analyzed": 120,
    "reinforce": 15,
    "contradict": 3,
    "extend": 8,
    "uncertain": 2
  }
}
```

### Step 3: 脚本执行写入

```powershell
python scripts/claim_evolution.py --vault "D:\Vault" --apply claim_result.json
```

渲染为 `wiki/claim-evolution.md`：

```markdown
# 主张演化追踪

> 分析日期：YYYY-MM-DD | 分析主张数：42 | 发现关系：28

## 矛盾主张（3 对）

### [[sources/slug1]] vs [[sources/slug2]]
- 主张 A：端到端架构消除了模块间的信息损失
- 主张 B：模块化架构在特定场景下信息保留更完整
- 关系：contradict
- 分析：两者对"信息损失"的定义不同——A 指端到端训练的梯度流，B 指模块化系统的可解释性信息

## 强化主张（15 对）
...

## 延伸主张（8 对）
...
```

---

## 场景 3：综合页刷新

触发词：`刷新综合`、`synthesis`、`更新综合页`

### Step 1: 脚本收集来源数据

```powershell
python scripts/refresh_synthesis.py --vault "D:\Vault" --domain "自动驾驶" --collect-only
```

输出 JSON：

```json
{
  "synthesis_path": "syntheses/自动驾驶--综合分析",
  "linked_sources": [
    {
      "slug": "sources/slug1",
      "title": "文章标题",
      "quality": "high",
      "date": "2024-03-15",
      "core_summary": "核心摘要段落原文",
      "key_claims": [
        {"type": "causal", "confidence": "high", "text": "..."}
      ],
      "one_sentence": "一句话结论"
    }
  ],
  "existing_synthesis": {
    "current_conclusion": "现有结论文本",
    "core_claims": ["现有主张列表"]
  },
  "source_count": 8
}
```

### Step 2: LLM 生成综合内容

**你的角色**：知识综合分析师。你从多个来源中提炼可靠的综合结论。

**输入**：Step 1 的 JSON。

**分析任务**：

1. 阅读所有来源的 `core_summary` 和 `key_claims`
2. 识别多来源一致的共识
3. 识别来源之间的分歧
4. 形成当前最可靠的综合结论
5. 标注哪些主张需要进一步验证

**判断标准**：

| 主张状态 | 条件 | 标注 |
|---------|------|------|
| 共识 | 3+ 来源一致，无反对 | `[high]` |
| 主流 | 2 来源一致，无反对 | `[medium]` |
| 争议 | 有支持也有反对 | `[low] + [disputed]` |
| 孤证 | 仅 1 来源 | `[low]` |
| 缺口 | 明显应该有但没有的信息 | 列入 knowledge_gaps |

**约束**：

- 只使用输入数据中明确存在的信息，不推断、不编造
- 综合结论必须可追溯到至少一个 high/medium 来源
- 不要把多个来源的措辞拼接成"综合"——要形成自己的判断
- 如果来源之间有根本分歧，不要强行统一，而是并列呈现

**输出 JSON schema**：

```json
{
  "current_conclusion": "≤200字的综合结论",
  "core_claims": [
    {
      "text": "主张内容",
      "confidence": "high|medium|low",
      "evidence_type": "consensus|mainstream|disputed|single_source",
      "supporting_sources": ["sources/slug1", "sources/slug2"]
    }
  ],
  "divergences": [
    {
      "topic": "分歧主题",
      "positions": [
        {"view": "观点A", "sources": ["sources/slug1"]},
        {"view": "观点B", "sources": ["sources/slug2"]}
      ]
    }
  ],
  "pending_verification": ["需要进一步验证的主张"],
  "knowledge_gaps": ["明显的知识缺口"]
}
```

### Step 3: 脚本执行写入

```powershell
python scripts/refresh_synthesis.py --vault "D:\Vault" --apply synthesis_result.json
```

渲染为 `wiki/syntheses/{domain}--综合分析.md`。

---

## 场景 4：审核队列

触发词：`review`、`待审`、`审核队列`

### Step 1: 脚本收集待审项

```powershell
python scripts/review_queue.py --vault "D:\Vault" --collect-only
```

输出 JSON：

```json
{
  "pending_outputs": [
    {
      "path": "outputs/2024-03-15--xxx",
      "type": "query|delta-compile",
      "lifecycle": "temporary|review-needed",
      "title": "...",
      "created": "2024-03-15",
      "sources_cited": 3
    }
  ],
  "candidate_pages": [
    {
      "path": "concepts/Z",
      "lifecycle": "candidate",
      "mention_count": 3,
      "last_updated": "2024-03-10"
    }
  ],
  "low_confidence_claims": [
    {
      "path": "sources/slug1",
      "claim": "...",
      "confidence": "low"
    }
  ],
  "absorbed_count": 12,
  "archived_count": 5
}
```

### Step 2: LLM 排序和建议

**你的角色**：知识库运营经理。你决定哪些待审项优先处理。

**输入**：Step 1 的 JSON。

**分析任务**：

1. 按优先级对待审项排序
2. 对每个待审项给出处理建议（批准/归档/跳过）
3. 对可升级的候选页给出升级建议

**优先级判断标准**（从高到低）：

1. delta-compile 草稿中有矛盾主张 → 最高优先
2. 候选页 mention_count >= 3 → 高优先（已具备升级条件）
3. delta-compile 草稿 → 中优先
4. 普通 temporary output → 低优先
5. 已被后续 output 覆盖的旧 output → 建议归档

**输出 JSON schema**：

```json
{
  "prioritized_items": [
    {
      "path": "outputs/xxx",
      "priority": 1,
      "action": "approve|archive|skip|review",
      "reason": "为什么建议这个操作"
    }
  ],
  "upgrade_recommendations": [
    {
      "path": "concepts/Z",
      "action": "upgrade",
      "from_lifecycle": "candidate",
      "to_lifecycle": "official",
      "reason": "3+ 来源确认，定义已实质化"
    }
  ],
  "summary": {
    "high_priority": 2,
    "medium_priority": 5,
    "suggest_archive": 3,
    "suggest_upgrade": 2
  }
}
```

### Step 3: 向用户汇报

```
审核队列（按优先级排序）：

🔴 高优先：
1. outputs/xxx — delta-compile 草稿含矛盾主张，建议审核
2. concepts/Z — 3+ 来源确认，建议升级为 official

🟡 中优先：
3. outputs/yyy — 普通查询结果，建议批准吸收
4. outputs/zzz — 建议归档（被后续 output 覆盖）

要处理哪些？回复编号。
```

### Step 4: 回写已批准的 delta 草稿

当用户确认某个 delta 草稿值得沉淀时：

```powershell
python scripts/apply_approved_delta.py "outputs/<slug>" --vault "D:\Vault"
```

回写后原 output 标记为 `absorbed`，不再出现在审核队列中。

如果自动找不到目标 synthesis，可显式指定：

```powershell
python scripts/apply_approved_delta.py "outputs/<slug>" --vault "D:\Vault" --target "syntheses/主题--综合分析"
```

**引导模板**（向用户展示）：

```
已批准的 delta 草稿：
  → [[outputs/{slug}]]
  回写命令：apply_approved_delta.py "outputs/{slug}"
  目标综合页：{auto-detected or manual}
```

---

## 维护后统一重建

完成所有维护操作后，建议统一重建索引，确保 index.md 反映所有维护操作的最终状态：

```powershell
python scripts/wiki_query.py --vault "D:\Vault" --rebuild-index
```

当维护流程涉及多个脚本（如 lint → claim → refresh → delta）时，索引可能在中途过时。统一重建可消除不一致。

---

## 场景 5：Review Sweep（自动清理）

触发词：`sweep`、`自动清理`、`清理 outputs`

### 设计目标

对标桌面应用的 `sweepResolvedReviews()`，自动识别并清理已过时的待处理 output。分两步：规则匹配（确定性）+ LLM 语义判断（对剩余项）。

### Step 1: 脚本收集 + 规则匹配

```powershell
python scripts/review_queue.py --vault "D:\Vault" --sweep
```

脚本执行：
1. 收集所有 `lifecycle: temporary` 或 `review-needed` 的 output
2. 应用 R1 规则（missing-page：所有引用页面已存在 → auto-resolved）
3. 应用 R2 规则（superseded：同标题多个 output，保留最新 → 旧的 auto-resolved）
4. 输出 auto_resolved 列表 + remaining 列表（分批，batch=20）

### Step 2: LLM 语义判断

按 `references/prompts/review_sweep.md` 约束，对规则匹配后剩余的项做语义判断。

**保守策略**：
- contradiction/suggestion 类型默认保持 pending
- 只有内容已被完全吸收或明确失效的项才标记为 resolved
- 不确定时保持 pending

**批次控制**：
- batch = 20, max_batches = 3
- 提前终止：某批次 resolved = 0 则停止

### Step 3: 脚本执行

```powershell
python scripts/review_queue.py --vault "D:\Vault" --apply-sweep sweep_result.json
```

脚本读取 LLM 输出，将 resolved 项的 lifecycle 改为 archived。

### Step 4: 向用户汇报

```
自动清理完成：
  规则匹配：{N1} 项已解决（引用页面已存在/被更新版本覆盖）
  语义判断：{N2} 项已解决（内容已被吸收）
  保留待审：{N3} 项仍有独立价值
  
要查看剩余待审项？说 "review"。
```

---

## 场景 6：自动维护建议

触发词：`状态`、`维护建议`、`有什么要做的`

### 设计目标

基于 vault 当前状态，自动生成结构化维护建议，按严重程度分级展示。

### 执行方式

```powershell
python scripts/stale_report.py --vault "D:\Vault" --auto-suggest
```

输出 JSON schema：
```json
{
  "suggestions": [
    {
      "type": "stale_synthesis|pending_outputs|stale_pages|low_health_score|maintenance_overdue|ingest_milestone|duplicate_outputs",
      "severity": "high|medium|low",
      "reason": "具体原因",
      "suggested_action": "建议操作",
      "suggested_command": "对应脚本命令"
    }
  ],
  "last_maintenance": "2026-04-15",
  "days_since_maintenance": 17,
  "health_score": 72,
  "pending_outputs": 12,
  "ingest_count": 30
}
```

### 展示规则

按严重程度分层展示：

- **high severity**：对话开头主动展示
  ```
  知识库有 {N} 项需要关注：
  - {reason}。说 "{suggested_action}" 可查看详情。
  ```
- **medium severity**：入库完成后自然时机展示
- **low severity**：不主动提示，用户问"状态"时展示

### 自动触发时机

- 每次进入对话时，LLM 读取 `--auto-suggest` 输出
- 有 high severity → 对话开头展示维护提示
- 无 high severity → 不主动提示

---

## 通用约束

### 数据边界

- LLM 只使用脚本收集的 JSON 数据做判断，不自己去读取文件
- 如果需要额外信息（如某个页面的完整内容），提示用户运行额外的收集命令

### 质量门控

每个 LLM 输出的 JSON 必须：
- 符合定义的 schema（字段完整、类型正确）
- reasoning 字段不为空（不能只给结论不给理由）
- 不包含输入数据中不存在的信息（防止幻觉）

### 写入边界

- 脚本只写入 LLM 输出中明确指定的文件
- 不自动修改正式 wiki 页面（sources/、briefs/、concepts/ 等），除非用户明确确认
- 所有写入记录到 `wiki/log.md`

### 人在 loop 中

- 健康检查：报告自动生成，修复操作需用户确认
- 主张演化：分析自动生成，用户审核后决定是否采纳
- 综合刷新：新结论生成后展示给用户，确认后写入
- 审核队列：排序和建议自动生成，实际操作（批准/归档）需用户确认
