# Version Lock: v1.1.0 — Confidence Propagation Pipeline

**Date**: 2026-05-01
**Version**: 1.1.0
**Freeze tag**: `2026.05.01-confidence-pipeline`

## Motivation

Two diagnostic articles (04-12 "出发点决定架构", 04-27 "事实责任分离") reflected the skill's own blind spots back onto itself. The core contradiction: `claim_inventory` existed in v2 compile JSON with per-claim confidence (high/medium/low), but the apply stage discarded it, leaving only a vague page-level `confidence: "high"`. Confidence data was "present but not flowing" — the root cause of all downstream issues.

## What Changed

### Phase 0: Claim data penetration through apply layer
- `claim_inventory` no longer discarded at `to_legacy_compile_shape()`. Propagated to page builder.
- `compile_shape_from_payload()` and `to_legacy_compile_shape()` both return `"claim_inventory"` key.
- `Article` dataclass gains `claim_inventory: list[dict]` field.

### Phase 1: Claim inventory rendering on brief/source pages
- New `## 关键判断` section with `[type|confidence] claim` format.
- Frontmatter adds `claim_confidence_high/medium/low` count fields.
- Heuristic pages get placeholder: "待 LLM 编译补充关键判断。"

### Phase 2: Candidate lifecycle gating
- `lifecycle: "candidate"` for `needs_human_review=True` or low confidence with no high claims.
- `VALID_PAGE_STATUS` adds `"candidate"` (first position).
- Candidate pages show `[!warning] 候选页待审` callout.
- `candidate → seed` upgrade: 2+ sources with high-confidence claims mentioning the concept.
- `review_queue.py` adds `## 候选页待审` section.

### Phase 3: Synthesis pages project from claims, not raw text
- `refresh_synthesis.py` extracts claims from source `## 关键判断` sections.
- Confidence-weighted scoring: high=6, medium=3, low=1.
- "当前结论" built from top high/medium claims.
- "核心判断" shows `[confidence]` labels and source links.
- Fallback to raw sentence scoring when no claims found.
- `build_synthesis_page()` in `page_builders.py` also uses claims for initial creation.

### Phase 4: Review pipeline activation
- `review_queue.py` adds `低置信判断`, `可升级候选页`, `矛盾主张` sections.
- `wiki_lint.py` extends `collect_claims()` to scan briefs. Output adds `low_confidence_claims` and `candidate_pages` keys.

### Phase 5: Claim evolution tracking
- New `scripts/claim_evolution.py` using `claim_keywords` and `claims_conflict` from `wiki_lint`.
- Classifies relationships as reinforce/contradict/extend.
- Writes `wiki/claim-evolution.md`. Auto-triggered after each ingest.
- `review_queue.py` adds `## 矛盾主张` section from evolution data.

### Phase 6: Write-path layering
- Candidate pages: claims split into `## 关键判断` (high/medium) + `## 待验证判断` (low).
- Official pages: all claims in same section.
- Concept/entity pages inherit candidate lifecycle from source.

## Verified

- All 8 synthesis pages rebuild successfully with `refresh_synthesis.py`.
- `review_queue.py --write` produces new sections with correct report keys.
- `wiki_lint.py` returns `low_confidence_claims` and `candidate_pages` keys.
- `claim_evolution.py` detects 1 reinforce pair in live vault.
- End-to-end: 04-27 article applied to vault → brief page shows `lifecycle: "official"` (7 high claims), `## 关键判断` with 8 claims.
- All imports clean: `pipeline.ingest_orchestrator`, `pipeline.page_builders`, `pipeline.taxonomy`, `claim_evolution`, `review_queue`, `wiki_lint`.

## No Technical Debt

- No dead fields: `review_hints.needs_human_review` now gates lifecycle determination (was previously a write-only field).
- No orphan functions: `check_and_upgrade_status()` candidate→seed path is active.
- No hard-coded lifecycle: all page builders accept `lifecycle` parameter dynamically.
- No duplicated extraction: `extract_claims_from_source()` in `refresh_synthesis.py` and `_extract_claims_from_source()` in `page_builders.py` both extract raw markdown sections (not plain_text), matching `CLAIM_PATTERN` regex.
- Backward compatible: existing pages without `## 关键判断` sections use fallback paths; `candidate` lifecycle defaults to `official` for heuristic/legacy pages.

## Optimization Pass (2026-05-01)

基于 `docs/obsidian-wiki-skill-analysis.md` 审计报告，执行了以下优化：

### P0 Bug 修复
- `WIKI_DIRS` 追加 `wiki/research`，修复 bootstrap 遗漏
- `validate_compile.py` 对 `cross_domain_insights` 改为软验证，避免单个 malformed 条目阻断整个 compile

### P1 结构清理
- kwiki stub 文件清理（fetch/ingest/apply → deprecation exit）
- `source_adapters.py` 显式重导出替代 wildcard import
- 重复代码合并（FRONTMATTER/SECTION_PATTERN/CLAIM_PATTERN/parse_frontmatter/section_body）
- DEFAULT_DOMAINS 从 types.py 迁移到 vault_config.py
- `ingest_orchestrator.py` 提取 `_determine_lifecycle()` 和 `_apply_purpose_filter()`

### 测试套件
- 265 tests, 265 passed, 0 failed
- 覆盖：validate_compile、text_utils、types、compile、page_builders、vault_config、ingest_orchestrator、extractors、taxonomy、E2E pipeline

### 设计决策确认
- collection adapter 保持单次调用设计，不做 cookie 降级（与 video adapter 的三级降级不同）
- 原因：抖音等平台无法获取 cookie，公开播放列表通常不需要 cookie

## Out of Scope (Future Work)

- Claim auto-update when new sources reinforce/contradict existing claims (manual review required for contradictions).
- Synthesis auto-refresh on ingest (currently manual `refresh_synthesis.py` trigger).
- Confidence drift tracking over time (stance pages already track this, but not at claim granularity).