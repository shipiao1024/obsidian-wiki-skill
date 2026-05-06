# V2 验证架构改造计划

> 版本: V1.2 → V2.0
> 日期: 2026-05-01
> 目标: 删除启发式路径、LLM 接管所有智能判断、引入置信度序数模型 + 接地校验

---

## 一、改造总览

### 三个方向性决策

| # | 决策 | 影响范围 |
|---|------|---------|
| 1 | extractors.py 脚本提取完全交给 LLM | 删除智能提取函数，保留 slug 工具函数 |
| 2 | 置信度从 high/medium/low 统一改为序数标签 | 全局：prompt → normalize → validate → page builders → Article model |
| 3 | 删除启发式路径 | ingest_orchestrator.py + page_builders.py 删除 heuristic 分支 |

### 改造顺序（依赖关系决定）

```
Phase 1: LLM prompt + schema（源头）
  ↓
Phase 2: normalize + validate（中间层）
  ↓
Phase 3: extractors.py 瘦身 + page builders 清理（下游）
  ↓
Phase 4: ingest_orchestrator.py 删除 heuristic 分支（编排层）
  ↓
Phase 5: dependency_ledger.py 统一序数模型（辅助系统）
  ↓
Phase 6: 测试全面更新
```

---

## 二、Phase 1 — LLM Prompt + Schema 修改

### 1.1 修改 `references/prompts/ingest_compile_prompt_v2.md`

**新增要求 LLM 输出的字段：**

- `claim_inventory[].evidence_type` — 枚举值：`fact / inference / assumption / hypothesis / disputed / gap`
- `claim_inventory[].grounding_quote` — 原文中支撑该 claim 的关键句（1-2 句，必须是原文原话）
- `knowledge_proposals.domains[].grounding_quote` — 原文中出现该领域关键词的上下文
- `knowledge_proposals.concepts[].grounding_quote` — 原文中出现该概念的上下文
- `knowledge_proposals.entities[].grounding_quote` — 原文中出现该实体的上下文

**修改 confidence 枚举：**

从：
```
"confidence": "high | medium | low"
```
改为：
```
"confidence": "Seeded | Preliminary | Working | Supported | Stable"
```

**在 prompt 中增加约束：**

```markdown
11. `evidence_type` 标注每条 claim 的证据类型：
    - `fact`：原文直接陈述，有明确出处
    - `inference`：基于两条以上事实推导
    - `assumption`：未经验证的前提
    - `hypothesis`：可检验的推测
    - `disputed`：有可信来源持相反观点
    - `gap`：需要但未找到的信息

12. `grounding_quote` 必须是原文原话，不得编造或改写。
    - 如果原文中找不到对应句，该字段填空字符串
    - 空 grounding_quote 的 claim 在下游会被标记为 [Assumption-anchored]

13. confidence 使用序数标签，定义如下：
    - `Seeded`：仅有方向，无证据支撑
    - `Preliminary`：初始证据，单薄或片面
    - `Working`：足够形成可行动判断，但有已知缺口
    - `Supported`：多源独立确认，无可信反驳
    - `Stable`：完整验证链，可用于高承诺决策
```

### 1.2 修改输出 JSON schema（在 prompt 末尾）

在 `claim_inventory` 条目中增加：
```json
{
  "claim": "",
  "claim_type": "observation | interpretation | prediction | falsification",
  "evidence_type": "fact | inference | assumption | hypothesis | disputed | gap",
  "confidence": "Seeded | Preliminary | Working | Supported | Stable",
  "grounding_quote": "",
  "evidence": [],
  "suggested_destination": [],
  "verification_needed": false
}
```

在 `knowledge_proposals` 的 domains/concepts/entities 条目中增加：
```json
{
  "name": "",
  "action": "link_existing | create_candidate | promote_to_official_candidate | no_page",
  "reason": "",
  "confidence": "Seeded | Preliminary | Working | Supported | Stable",
  "evidence": [],
  "grounding_quote": ""
}
```

---

## 三、Phase 2 — Normalize + Validate 修改

### 2.1 修改 `scripts/llm_compile_ingest.py`

**`coerce_confidence()` (L476-481)**：
```python
# 当前
VALID = {"high", "medium", "low"}
# 改为
VALID_ORDINAL = {"Seeded", "Preliminary", "Working", "Supported", "Stable"}
```

**`normalize_claim_inventory()` (L573-596)**：
- confidence 使用新的 coerce_confidence（序数标签）
- 新增 evidence_type 字段校验（枚举：fact/inference/assumption/hypothesis/disputed/gap）
- 新增 grounding_quote 字段提取

**`normalize_proposal_list()` (L484-508)**：
- confidence 使用序数标签
- 新增 grounding_quote 字段提取

**`normalize_review_hints()` (L627-636)**：
- priority 保持 high/medium/low（这是优先级，不是置信度）

### 2.2 修改 `scripts/pipeline/validate_compile.py`

**新增校验项：**

```python
VALID_ORDINAL = {"Seeded", "Preliminary", "Working", "Supported", "Stable"}
VALID_EVIDENCE_TYPE = {"fact", "inference", "assumption", "hypothesis", "disputed", "gap"}
```

- claim_inventory 每条必须有 evidence_type（枚举校验）
- claim_inventory 的 confidence 改为校验序数标签
- knowledge_proposals 的 confidence 改为校验序数标签
- grounding_quote 为可选字段（不要求非空，但必须是 string）

**新增 `grounding_validate()` 函数：**

```python
def grounding_validate(payload: dict, raw_text: str) -> tuple[bool, list[str]]:
    """校验 LLM 输出的 grounding_quote 是否在原文中可找到。

    返回 (passed, violations)。
    """
```

逻辑：
1. 遍历 claim_inventory，对每条有 grounding_quote 的 claim：
   - 在 raw_text 中搜索 grounding_quote 的子串
   - 如果找不到 → violation（LLM 可能编造了引用）
2. 遍历 knowledge_proposals，对每条有 grounding_quote 的 proposal：
   - 同上
3. 返回 violations 列表

**新增 `density_check()` 函数：**

```python
def density_check(payload: dict) -> tuple[str, list[str]]:
    """证据密度检查，返回 (maturity_level, warnings)。

    maturity_level: "grounded" | "compiled" | "raw"
    """
```

逻辑：
1. 统计 claim_inventory 中各 evidence_type 的数量
2. 如果所有 claim 都是 assumption/hypothesis 且无 grounding_quote → "raw"
3. 如果有 fact/inference 类 claim 且通过 grounding 校验 → "grounded"
4. 否则 → "compiled"

### 2.3 新增 `scripts/pipeline/grounding_validate.py`

独立模块，包含：
- `grounding_validate(payload, raw_text)` — 文本回查
- `keyword_coverage(text, reference)` — 关键词覆盖率计算
- `density_check(payload)` — 密度检查

---

## 四、Phase 3 — extractors.py 瘦身 + Page Builders 清理

### 3.1 `scripts/pipeline/extractors.py` 改造

**保留的函数（纯工具，无智能判断）：**
- `concept_slug()` — slug 生成
- `entity_slug()` — slug 生成
- `domain_slug()` — slug 生成
- `comparison_slug()` — slug 生成
- `page_mention_count()` — 计数工具
- `mature_concepts()` — 过滤工具
- `mature_entities()` — 过滤工具
- `existing_taxonomy_links()` — 链接检查
- `vault_domain_distribution()` — 读取现有 domain 页面
- `detect_domain_mismatch()` — 改为接受外部传入的 domains 列表（不再自己调 detect_domains）

**删除的函数（智能判断，交给 LLM）：**
- `detect_domains()` — 删除
- `extract_entities()` — 删除
- `extract_concepts()` — 删除
- `extract_content_questions()` — 删除（LLM 的 open_questions 已覆盖）
- `extract_content_topics()` — 删除
- `_extract_clean_concepts()` — 删除
- `_extract_concepts_by_frequency()` — 删除

**保留的辅助（仍被 detect_domain_mismatch 间接使用）：**
- `extract_content_topics()` — 保留，仅用于 detect_domain_mismatch 的 suggested_domain 生成
- 或改为从 LLM output 的 knowledge_proposals.domains 中取 suggested_domain

**决策：** `extract_content_topics()` 和 `_extract_clean_concepts()` 是否保留？
→ 建议保留 `extract_content_topics()`，因为它只用于 detect_domain_mismatch 的建议域名生成，这是一个降级场景下的辅助功能，不影响主路径。

### 3.2 `scripts/pipeline/page_builders.py` 改造

**删除的函数：**
- `build_brief_page()` — 删除（启发式 brief 生成）
- `build_source_page()` — 删除（启发式 source 生成）
- `_heuristic_skeleton()` — 删除
- `_extract_numeric_data()` — 删除

**保留的函数：**
- `build_brief_page_from_compile()` — 保留，修改置信度显示逻辑
- `build_source_page_from_compile()` — 保留，修改置信度显示逻辑
- `build_concept_page()` — 保留
- `build_entity_page()` — 保留
- `build_domain_page()` — 保留
- `build_synthesis_page()` — 保留，修改 claim 评分逻辑
- `build_comparison_page()` — 保留
- `write_page()` / `upsert_page()` / `article_output_exists()` — 保留
- `merge_links_section()` / `replace_links_section()` / `render_frontmatter()` — 保留

**修改 `build_brief_page_from_compile()`：**

- claim 的置信度显示从 `[ct|high]` 改为 `[ct|Supported]` 等序数标签
- 新增 evidence_type 显示：`[fact|Supported]` 而非 `[interpretation|high]`
- conf_dist 统计从 high/medium/low 改为序数标签计数
- frontmatter 中 claim_confidence_high/medium/low 改为 claim_confidence_stable/supported/working/preliminary/seeded

**修改 `build_source_page_from_compile()`：**

- 同上置信度显示修改
- 新增 grounding_quote 在关键判断中的显示（可选）

**修改 `build_synthesis_page()`：**

- `_extract_claims_from_source()` 中的 CLAIM_PATTERN 匹配需要适配新的 evidence_type 标签格式
- `_score_claim()` 中的 CONF_WEIGHT 从 `{"high": 6, "medium": 3, "low": 1}` 改为序数权重

### 3.3 `scripts/pipeline/taxonomy.py` 改造

**修改 `ensure_taxonomy_pages()`：**

当前逻辑混合了脚本提取和 LLM 提取：
```python
concept_names = mature_concepts(vault, extract_concepts(article, limit=8))  # 脚本
entity_names = mature_entities(vault, extract_entities(article, limit=8))    # 脚本
for name in promoted_taxonomy_names_from_payload(compiled_payload, "concepts"):  # LLM
    ...
```

改为：只用 LLM 提取的结果：
```python
concept_names = promoted_taxonomy_names_from_payload(compiled_payload, "concepts")
entity_names = promoted_taxonomy_names_from_payload(compiled_payload, "entities")
```

同时从 compile_shape_from_payload 中提取 LLM 识别的 concepts 和 entities（knowledge_proposals 中 action 为 link_existing 或 create_candidate 的）。

**删除对 extractors.py 智能函数的导入：**
```python
# 删除
from .extractors import extract_concepts, extract_entities
# 保留
from .extractors import concept_slug, domain_slug, entity_slug, mature_concepts, mature_entities, page_mention_count
```

---

## 五、Phase 4 — ingest_orchestrator.py 删除启发式分支

### 4.1 `scripts/pipeline/ingest_orchestrator.py` 改造

**删除 heuristic 分支（L148-150）：**
```python
# 删除
else:
    write_page(brief_path, build_brief_page(article, slug, compile_mode="heuristic", lifecycle=lifecycle), force)
    write_page(source_path, build_source_page(vault, article, slug, compile_mode="heuristic", lifecycle=lifecycle), force)
```

改为：compile 失败时直接报错，不生成页面。

**修改 imports：**
```python
# 删除
from .page_builders import build_brief_page, build_source_page
# 保留
from .page_builders import build_brief_page_from_compile, build_source_page_from_compile
```

**修改 `_determine_lifecycle()`：**

confidence 检查从 `"high"` 改为序数标签：
```python
# 当前
has_high = any(
    isinstance(c, dict) and c.get("confidence", "").strip().lower() == "high"
    for c in article.claim_inventory
)
# 改为
has_supported_or_stable = any(
    isinstance(c, dict) and c.get("confidence", "").strip() in ("Supported", "Stable")
    for c in article.claim_inventory
)
```

**修改置信度提取逻辑（L119-135）：**

从 claim_inventory 中提取 dominant confidence 的逻辑改为使用序数标签。

**删除 `--no-llm-compile` 参数的影响：**

当 compile 失败时，不再降级到启发式，而是：
- 返回 status: "failed"
- 不生成 brief/source 页面
- 在 compile_reason 中记录失败原因

### 4.2 `scripts/pipeline/compile.py` 改造

**修改 `try_llm_compile()`：**

validation 失败时的 fallback 信息从 "Heuristic fallback used." 改为 "Compile validation failed."

**修改 `compile_reason_from_payload()`：**

删除 "Heuristic fallback used." 分支。

### 4.3 `scripts/llm_compile_ingest.py` 改造

**删除 v1.0 相关代码：**

- `prepare_compile_payload()` — 删除（v1.0 prompt 准备）
- `build_user_prompt()` — 删除（v1.0 user prompt）
- `load_prompt()` — 删除（v1.0 prompt 加载）
- `normalize_result()` — 删除（v1.0 结果规范化）
- `compile_article()` — 删除（v1.0 编译入口）
- `prompt_path()` — 删除
- `DEFAULT_DOMAINS` / `DOMAIN_MIN_SCORE` — 删除（从 llm_compile_ingest.py 中删除，types.py 中保留）
- `detect_domains()` — 删除（llm_compile_ingest.py 中的副本）

**保留的函数：**
- `prepare_compile_payload_v2()` — 保留
- `build_user_prompt_v2()` — 保留
- `load_prompt_v2()` — 保留
- `normalize_result_v2()` — 保留
- `compile_article_v2()` — 保留
- `compile_article_auto()` — 简化，只调用 v2
- 所有 normalize_* 辅助函数 — 保留
- `extract_json()` — 保留
- `env_config()` — 保留
- `call_openai_compatible()` — 保留

---

## 六、Phase 5 — dependency_ledger.py 统一序数模型

### 6.1 修改 `scripts/pipeline/dependency_ledger.py`

**置信度模型从百分比改为序数：**

```python
# 当前
CONFIDENCE_LABELS = {
    (0, 20): "Preliminary",
    (20, 40): "Developing",
    (40, 60): "Working",
    (60, 80): "Supported",
    (80, 100): "Stable",
}
# 改为
ORDINAL_LEVELS = ("Seeded", "Preliminary", "Working", "Supported", "Stable")
```

**修改 `confidence_label()`：**
- 从百分比映射改为直接返回序数标签
- 如果输入是百分比，转换为序数（向后兼容）

**修改 `init_ledger_page()`：**
- H 节点的 confidence 从 `25%` 改为 `Preliminary`

**修改 `update_hypothesis_confidence()`：**
- 接受序数标签而非百分比

**修改 `propagate_confidence()`：**
- 使用序数比较而非数值比较
- min 操作改为取序数层级最低的

**修改 `check_evidence_sufficiency()`：**
- Preliminary 检查从 `< 20%` 改为 `== "Seeded"`

---

## 七、Phase 6 — 测试全面更新

### 需要修改的测试文件

| 测试文件 | 修改内容 |
|---------|---------|
| `test_validate_compile.py` | confidence 从 high/medium/low 改为序数标签；新增 evidence_type 校验测试；新增 grounding_validate 测试 |
| `test_extractors.py` | 删除智能提取函数的测试（detect_domains, extract_entities, extract_concepts 等）；保留 slug 工具和 vault 操作的测试 |
| `test_ingest_orchestrator.py` | 删除 heuristic fallback 测试；修改 confidence 断言为序数标签 |
| `test_page_builders.py` | 删除 build_brief_page / build_source_page 测试；修改 build_brief_page_from_compile / build_source_page_from_compile 测试 |
| `test_compile.py` | 删除 v1.0 相关测试；修改 confidence 校验 |
| `test_llm_compile_ingest_v2.py` | 修改 confidence 枚举；新增 evidence_type 和 grounding_quote 测试 |
| `test_dependency_ledger.py` | 修改百分比置信度为序数标签 |
| `test_taxonomy.py` | 如果有测试 extract_concepts/extract_entities 的调用，改为测试 LLM 提取结果 |
| `conftest.py` | v2_payload fixture 中的 confidence 从 high/medium/low 改为序数标签；新增 evidence_type 和 grounding_quote 字段 |
| `test_e2e_pipeline.py` | 如有涉及 heuristic 路径的测试，删除或改为测试 compile 失败场景 |

### 新增测试

| 测试文件 | 内容 |
|---------|------|
| `test_grounding_validate.py` | grounding_validate() 的各种场景：完全匹配、部分匹配、无匹配、空 quote |
| `test_density_check.py` | density_check() 的各种场景：全 assumption → raw、有 fact + grounding → grounded、混合 → compiled |

---

## 八、文件变更清单（按执行顺序）

### Phase 1: Prompt + Schema
1. `references/prompts/ingest_compile_prompt_v2.md` — 修改 prompt，增加 evidence_type/grounding_quote/序数 confidence

### Phase 2: Normalize + Validate
2. `scripts/llm_compile_ingest.py` — 修改 coerce_confidence、normalize_claim_inventory、normalize_proposal_list
3. `scripts/pipeline/validate_compile.py` — 修改枚举校验，新增 grounding_validate + density_check
4. `scripts/pipeline/grounding_validate.py` — 新建，接地校验模块

### Phase 3: Extractors + Page Builders
5. `scripts/pipeline/extractors.py` — 删除智能提取函数，保留 slug 工具
6. `scripts/pipeline/page_builders.py` — 删除 build_brief_page/build_source_page，修改 from_compile 版本
7. `scripts/pipeline/taxonomy.py` — 删除对 extract_concepts/extract_entities 的调用

### Phase 4: Orchestrator + Compile
8. `scripts/pipeline/ingest_orchestrator.py` — 删除 heuristic 分支，修改 confidence 逻辑
9. `scripts/pipeline/compile.py` — 修改 fallback 信息
10. `scripts/llm_compile_ingest.py` — 删除 v1.0 代码（与 Phase 2 合并执行）

### Phase 5: Dependency Ledger
11. `scripts/pipeline/dependency_ledger.py` — 百分比 → 序数

### Phase 6: Tests
12. `tests/conftest.py` — 修改 v2_payload fixture
13. `tests/test_validate_compile.py` — 修改 + 新增
14. `tests/test_extractors.py` — 删除智能提取测试
15. `tests/test_ingest_orchestrator.py` — 删除 heuristic 测试
16. `tests/test_page_builders.py` — 删除 + 修改
17. `tests/test_compile.py` — 修改
18. `tests/test_llm_compile_ingest_v2.py` — 修改
19. `tests/test_dependency_ledger.py` — 修改
20. `tests/test_grounding_validate.py` — 新建
21. `tests/test_density_check.py` — 新建
22. `tests/test_e2e_pipeline.py` — 修改（如有）

### 文档
23. `modification-record.md` — 记录 V2.0 变更
24. `CHANGELOG.md` — 新增 V2.0 版本条目

---

## 九、风险和降级策略

### 风险 1: LLM 不输出 grounding_quote
- **降级**：grounding_validate 对空 quote 不报错，仅标记为 [Assumption-anchored]
- **不阻断**主流程

### 风险 2: LLM 输出的 confidence 不是序数标签
- **降级**：coerce_confidence 对非序数值默认返回 "Preliminary"
- **validate 阶段**报错并拒绝该 payload

### 风险 3: 删除 heuristic 后 LLM 不可用时无法入库
- **降级**：返回 status: "failed"，不生成页面，保留 raw 文件
- **用户**可手动运行 prepare-only 模式获取 payload 后重试

### 风险 4: 现有 vault 中已有 high/medium/low 标记的页面
- **不迁移**：已有页面不修改，新入库的页面使用新标签
- **读取时**：两种标签并存，显示层做兼容

---

## 十、预期收益

1. **质量门禁**：LLM 输出从"结构对就行"升级为"内容必须接地"
2. **可追溯性**：每条 claim 可以追溯到原文具体段落
3. **置信度精度**：5 级序数比 3 级 high/medium/low 提供更细粒度的决策支持
4. **代码简化**：删除 ~500 行启发式代码和 ~300 行脚本提取代码
5. **单一职责**：LLM 负责智能判断，脚本负责结构化操作
