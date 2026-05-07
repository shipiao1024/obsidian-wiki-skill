# Changelog

## 2.1 (2026-05-07) — Value Point + Domain Proposal Architecture

### Design Philosophy

V2.0 解决了"入库时预计算的认知结构没有被查询时消费"的问题。V2.1 解决"领域无法涌现、路由是死代码、跨 vault 检索断裂"的问题。

核心设计转变：purpose.md 从"预设分类标签"升级为"意图锚点（Value Point）+ 涌现领域"双层结构。

**三原则**：
- Value Point 表达用户意图（为什么关注），不是分类标签（关注什么）
- 领域从内容中涌现，不要求预先声明——Domain Proposal 机制连接两者
- 单 vault 为默认，多 vault 是可选优化——拆分由体量+内聚度+用户意图触发

### Features

- **Value Point 数据结构**：purpose.md 新增 `## 价值锚点` 段，支持 `### 标题` + `>` 意图陈述 + `关联领域:` + `-` 具体问题的结构化意图声明。`parse_purpose_md()` 返回 `value_points` 列表，同时保持 `focus`/`exclude` 向后兼容
- **Domain Proposal 机制**：入库时 compile 产出的 domain 如不匹配任何 Value Point 或关注领域，自动累积到 `wiki/domain-proposals.json`。同一 domain 累积 ≥3 个来源后，入库影响报告显示"新领域提案"，建议用户添加为价值锚点或归入排除范围
- **跨 Vault 补充检索**：`wiki_retrieve.py` 检索时，如果 `cross_domain_insights` 指向其他 vault 的关注领域，自动从目标 vault 补充检索 top-3 结果，附加 bridge_logic 和来源 vault 标注。补充结果权威性低于主 vault
- **Vault 路由建议**：入库后检查 compile 产出的 domain 与当前 vault 的匹配度，如更匹配其他 vault，影响报告追加"路由建议"段
- **Source 迁移工具**：新增 `reroute_vault.py`，可将已入库的 source 从一个 vault 迁移到另一个 vault（移动 raw/briefs/sources + 重建两边索引）
- **select_vault_by_domains 增强**：Value Point 关联的 domain 匹配权重 2x，flat focus list 匹配权重 1x
- **map_domains_to_value_points()**：新函数，将 domain 列表映射到匹配的 Value Point，返回匹配度排序结果

### Changed

- `pipeline/vault_config.py`：`parse_purpose_md()` 返回结构扩展（新增 `value_points` 键）；新增 `map_domains_to_value_points()`、`load_domain_proposals()`、`save_domain_proposals()`、`update_domain_proposals()` 四个函数；`select_vault_by_domains()` 增加 Value Point 2x 权重逻辑
- `pipeline/ingest_orchestrator.py`：入库后调用 `update_domain_proposals()` 追踪未认领领域；新增 post-compile vault 路由建议检查；影响报告追加"新领域提案"和"路由建议"段
- `pipeline/pipeline_types.py`：新增 `PROPOSAL_THRESHOLD = 3` 常量
- `init_vault.py`：`PURPOSE_TEMPLATE` 增加 `## 价值锚点` 段及填写指引
- `wiki_index_v2.py`：`domains_index` 每个域新增 `cross_domain_insights_count` 字段；索引构建完成后自动统计跨域洞察计数
- `wiki_retrieve.py`：新增 `_cross_vault_supplementary_retrieve()` 函数；`retrieve_with_reading()` 新增 `cross_vault: bool = True` 参数；补充结果放入 `result["cross_vault_supplementary"]` 和 `cognitive_context["cross_vault_supplementary"]`
- `references/query-guide.md`：Step 2a 检索流程增加第 5 步"跨 Vault 补充检索"；新增跨 Vault 补充检索处理原则
- `references/prompts/query_synthesis.md`：来源可信度表新增"中低 — 跨 Vault 补充结果"级别
- New script: `scripts/reroute_vault.py`

### Backward Compatibility

- 旧格式 purpose.md（无 `## 价值锚点`）→ `parse_purpose_md()` 返回 `value_points: []`，`focus` 仍从 `## 关注领域` 提取
- 所有下游读 `purpose["focus"]` 和 `purpose["exclude"]` 的代码完全不受影响
- `retrieve_with_reading()` 的 `cross_vault` 参数默认 True，单 vault 注册时自动返回空补充结果
- `select_vault_by_domains()` 无 Value Point 时退化为纯 flat focus 匹配（与原逻辑等价）

## 2.0 (2026-05-07) — Cognitive Compilation System

### Features

- **Markdown 结构修复模块** (`pipeline/structure_fix.py`)：三阶段纯 stdlib 结构修复，确保 Obsidian 渲染兼容
  - 阶段1：数学块/列表块/表格块前后自动补空行
  - 阶段2：多行数学块（`$$...$$`）内部首尾空行清理
  - 阶段3：单行数学块（如 `$$E=mc^2$$`）前后补空行
  - 代码围栏（` ``` ` / `~~~`）内的 `$$` 不被误处理
  - Frontmatter 剥离/回贴保护
- **Compile prompt 新增 Obsidian 渲染规范**：6 条强制规则（数学/列表/表格空行、callout 语法、代码围栏、连续空行），从源头预防结构问题
- **wiki_lint 新增 `structure_violations` 检查**：扫描 wiki/ 所有页面，报告缺少空行的块级元素

### Changed

- `pipeline/page_builders.py`：7 个 `build_*_page` 函数返回前统一调用 `fix_structure()`
- `pipeline/ingest.py`：`build_raw_page()` 和 `build_transcript_page()` 返回前调用 `fix_structure()`
- `references/prompts/ingest_compile_prompt_v2.md`：新增"Markdown 渲染规范（Obsidian 兼容）"section
- `scripts/wiki_lint.py`：`collect_lint_data()` 和 `main_legacy()` 新增 `structure_violations` 输出字段

### Test Suite

- **新增 25 个测试用例**：覆盖数学块（多行/单行/内部清理）、列表块、表格块、代码围栏保护、frontmatter 保护、rules 开关控制、空内容边界、detect_structure_violations 诊断

## 1.1.1 (2026-05-01) — Optimization & Test Suite

### Bug Fixes

- **P0-1**: `WIKI_DIRS` 追加 `wiki/research`，修复 `ensure_bootstrap()` 不创建该目录的问题
- **P0-2**: `validate_compile.py` 对 `cross_domain_insights` 改为软验证，单个 malformed 条目不再阻断整个 compile 结果
- **M5**: `wiki_ingest.py` CRLF → LF 行尾修复，解决 Linux/macOS shebang 执行错误
- **M8**: `ingest_orchestrator._get_compile()` 改为直接 import compile 模块，消除间接路径

### Refactoring

- **M1-M3**: kwiki stub 文件替换为 deprecation exit（fetch/ingest/apply 三个纯 stub 文件）
- **M4**: kwiki/__main__.py 移除已废弃的 fetch/ingest/apply 路由
- **M9**: source_adapters.py 从 wildcard import 改为显式重导出（5 个符号）
- **M10**: vault_config.py 新增 `load_domain_keywords()` 函数，支持从 purpose.md 读取领域配置
- **M11-M15**: 合并 wiki_lint.py、review_queue.py、claim_evolution.py 中的重复代码到 text_utils.py
- **P2-1/P2-2**: DEFAULT_DOMAINS 从 types.py 迁移到 vault_config.py，extractors.py 和 shared.py 改为从 vault_config 导入
- **P2-3**: ingest_orchestrator.py 提取 `_determine_lifecycle()` 和 `_apply_purpose_filter()` 函数

### Test Suite

- **新增 79 个测试用例**：覆盖 7 个核心模块（validate_compile、text_utils、types、compile、page_builders、vault_config、ingest_orchestrator）
- **新增 extractors.py 测试**（~30 用例）：覆盖 detect_domains、extract_entities、extract_concepts、slug helpers 等
- **新增 taxonomy.py 测试**（~15 用例）：覆盖 ensure_comparison_page、check_and_upgrade_status、ensure_taxonomy_pages 等
- **新增 E2E 管道测试**（14 用例）：覆盖 heuristic 路径、v2 compile 路径、vault 结构完整性
- **修复 8 个预存测试失败**：yt-dlp subprocess mock 泄漏、web adapter 断言、wechat adapter mock、compile reason mock 路径
- **修复 3 个 collection adapter 测试**：重写为匹配实际单次调用行为（无 cookie 降级）
- **最终结果**：265 tests, 265 passed, 0 failed

### Environment & Tooling

- **新增 `check_and_test.bat`**：环境检查 + 全量测试一键脚本
- **环境依赖分析**：确认核心 pipeline 纯 stdlib，所有源类型适配器可选

## 1.1.0 (2026-05-01)

### Features

- **Confidence propagation pipeline**: `claim_inventory` from v2 compile now flows through apply to page builder (was previously discarded at `to_legacy_compile_shape()`). Per-claim confidence (high/medium/low) is visible on brief/source pages.
- **Candidate lifecycle gating**: Low-confidence or `needs_human_review` sources are created with `lifecycle: "candidate"` instead of `lifecycle: "official"`. Candidate pages display a warning callout and are excluded from main navigation until 2+ sources confirm them.
- **Claim rendering on brief/source**: New `## 关键判断` section with `[type|confidence]` format. Frontmatter includes `claim_confidence_high/medium/low` counts. Low-claims marked with `⚠️需验证`.
- **Claim-based synthesis projection**: `refresh_synthesis.py` now extracts claims from source `## 关键判断` sections, ranks by confidence-weighted scoring, and generates synthesis conclusions from claims rather than raw text. Falls back to raw sentence scoring when no claims available.
- **Claim evolution tracking**: New `claim_evolution.py` detects reinforce/contradict/extend relationships between claims across sources. Produces `wiki/claim-evolution.md`. Auto-triggered after each ingest.
- **Review pipeline activation**: `review_queue.py` adds `低置信判断`, `可升级候选页`, `矛盾主张` sections. `wiki_lint.py` adds `low_confidence_claims` and `candidate_pages` to output. `collect_claims` now scans briefs in addition to sources/syntheses/outputs.
- **Write-path layering**: Candidate pages split claims into `## 关键判断` (high/medium) and `## 待验证判断` (low). Official pages keep all claims in one section. Concept/entity pages inherit candidate lifecycle from their source.

### Changed

- `pipeline/types.py`: `VALID_PAGE_STATUS` adds `"candidate"` (first position). `STATUS_UPGRADE_THRESHOLDS` adds `"candidate": 2`. `Article` adds `claim_inventory` field.
- `pipeline/compile.py`: `compile_shape_from_payload()` extracts and returns `claim_inventory`.
- `apply_compiled_brief_source.py`: `to_legacy_compile_shape()` extracts and returns `claim_inventory`.
- `pipeline/ingest_orchestrator.py`: lifecycle determination from `review_hints` + confidence; passes `lifecycle` and `source_lifecycle` to page builders and taxonomy.
- `pipeline/page_builders.py`: All 4 build functions accept `lifecycle` parameter; candidate callout; claim split by confidence.
- `pipeline/taxonomy.py`: `ensure_taxonomy_pages()` accepts `source_lifecycle`; concept/entity pages inherit candidate lifecycle; candidate→seed upgrade path.
- `refresh_synthesis.py`: Claim-based evidence extraction with fallback; confidence-labeled core judgments.
- `review_queue.py`: New `CLAIM_PATTERN`, `low_confidence_claims()`, `upgradable_candidate_pages()`, and three new page sections.
- `wiki_lint.py`: `collect_claims()` scans briefs; output adds `low_confidence_claims` and `candidate_pages`.
- New script: `claim_evolution.py`.

## 1.0.1 (2026-04-27)

### Bug Fixes

- **apply_compiled_brief_source.py**: 修复 v2 compile 中 `knowledge_proposals` 的 `create_candidate` 概念/实体未被写入 source 页候选区的问题。原先 `candidate_concepts` 和 `candidate_entities` 硬编码为空列表 `[]`，现在从 `knowledge_proposals.concepts` 和 `knowledge_proposals.entities` 中提取 `action == "create_candidate"` 的条目正确填充。

## 1.0.0 (2026-04-26)

First public release of obsidian-wiki-skill.

### Features

- **Multi-source ingestion**: WeChat articles, web pages, YouTube, Bilibili, Douyin, local files, plain text
- **8 query modes**: brief, briefing, draft-context, contradict, digest, essay, reading-list, talk-track
- **Two-layer vault**: immutable `raw/` evidence layer + AI-compiled `wiki/` knowledge layer
- **Deep research protocol**: hypothesis-driven 9-phase research with evidence labels and dependency tracking
- **Autoresearch protocol**: 3-phase broad exploration for vault gap filling
- **Review & maintenance**: lint, stale reports, delta compile, synthesis refresh, review queue, graph operations
- **Video processing**: playlist/channel support, cookie management, ASR fallback
- **Cross-project access**: read-only vault access from other projects
- **Structured schemas**: comparison, question, and stance page schemas
- **Sub-tool**: wechat-article-for-ai MCP server for WeChat article extraction

### Authors

- shipiao1024