# Changelog

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