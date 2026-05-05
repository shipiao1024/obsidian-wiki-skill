# Pipeline Scripts

Core ingest/compile/apply scripts for the Claude-obsidian-wiki-skill pipeline. Read this file when performing an ingest operation.

For vault contract and routing rules, see `references/workflow.md` and `references/interaction.md`.

---

## wiki_ingest.py

Primary orchestrator entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_ingest.py `
  --vault "D:\Obsidian\MyVault" `
  "https://mp.weixin.qq.com/s/..."
```

What the primary orchestrator script does:

- Bootstraps `raw/`, `wiki/`, and `AGENTS.md` if missing.
- Routes URL input through the source registry.
- **Domain-aware auto-routing**: After fetch, calls `detect_domains()` then `resolve_vault(article_domains=...)` to scan all vaults' `purpose.md` focus domains and auto-select the vault with the highest domain overlap. When auto-routed to a non-default vault, outputs `Auto-routed to vault: <path> (matched domains: ...)` to stderr.
- Currently supports these URL source kinds directly:
  - WeChat article URLs
  - Generic web URLs
  - YouTube URLs
  - Bilibili URLs (including `b23.tv/` short links)
  - Douyin URLs (including `v.douyin.com/` short links)
- Fetches WeChat articles through `wechat-article-to-markdown`.
- Fetches generic web pages through `baoyu-url-to-markdown` when configured.
- Fetches video transcripts through `yt-dlp`, preferring subtitles and falling back to ASR.
- For video sites blocked by platform checks, can pass browser-state or cookie-file settings through the video adapter environment variables.
- Writes raw article pages into `raw/articles/`.
- Copies article images into `raw/assets/`.
- Generates one `wiki/sources/` page and one `wiki/briefs/` page per article.
- Uses `scripts/llm_compile_ingest.py` for v1/v2 compilation when configured, else falls back to heuristic extraction.
- Generates first-pass `wiki/domains/` pages and only creates `wiki/concepts/` / `wiki/entities/` after repeated source-level mentions.
- When v2 compile returns `update_proposals`, writes review-ready `delta-compile` drafts into `wiki/outputs/`.
- When v2 compile returns `knowledge_proposals`, prefers proposal-driven `domains` and can promote `concepts/entities` into official taxonomy pages.
- When v2 compile returns `comparisons`, auto-creates `wiki/comparisons/` pages.
- When v2 compile returns `cross_domain_insights`, includes cross-domain associative reasoning in the impact report (deep structural isomorphisms between new content's domain and existing vault domains).
- After ingestion completes, emits an impact report via `pipeline/ingest_report.py` containing: brief link, content topics (prefer LLM `knowledge_proposals` over heuristic), content-derived questions (prefer LLM `open_questions` over heuristic), cross-domain insights, domain mismatch detection, compile quality status, and next-step suggestions.
- Generates or updates a first-pass domain synthesis page in `wiki/syntheses/`.
- After ingestion, rebuilds knowledge graph (Mermaid/HTML) and claim evolution page.
- Updates `wiki/hot.md` with ingest context.
- Rebuilds `wiki/index.md`.
- Appends entries to `wiki/log.md`.

How to position this script:

- This is the primary orchestrator for `fetch+heuristic` and `fetch+api-compile`.
- It is not the only user-facing entrypoint; in the preferred workflow the you conversation is still the primary entrypoint.
- When `raw/articles` + `wiki/sources` + `wiki/briefs` already exist for a slug, it skips that article unless `--force` is supplied.
- Local file and plain text adapters are also supported through this same entrypoint.

Use `--input-dir` to reprocess an existing upstream output without fetching again.

## wiki_ingest_wechat.py

Legacy shim that forwards to `wiki_ingest.py`. Retained for backward compatibility. The primary entrypoint is now `wiki_ingest.py`.

## llm_compile_ingest.py

Compile entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\llm_compile_ingest.py `
  --vault "D:\Obsidian\MyVault" `
  --raw "D:\Obsidian\MyVault\raw\articles\<slug>.md" `
  --title "文章标题" `
  --prepare-only --lean
```

What the compile script does:

- Reads the raw article and a small amount of related wiki context.
- In `--prepare-only` mode, emits a compile context package for Codex/Claude interactive use.

- `--lean` flag: strips `system_prompt` and `user_prompt` from the output payload, and filters noisy/corrupted synthesis excerpts. Reduces context payload by ~80% (from ~58KB to ~10KB). The you itself is an LLM and doesn't need these fields — they are designed for external API calls. The lean payload retains `metadata`, `context` (with `purpose`, `related_domains`, `related_sources`, `related_syntheses`, `detected_domains`, `pending_deltas`), and `expected_output_schema_version`. Stripped fields: `system_prompt`, `user_prompt`, `existing_source`, `existing_brief`. Synthesis excerpts matching ASR transcript noise patterns are blanked.
- In API mode, can call an OpenAI-compatible chat completion endpoint.
- Outputs v2.0 schema: wrapped compile output including `compile_target`、`document_outputs`、`knowledge_proposals`、`update_proposals`、`claim_inventory`、`open_questions`、`cross_domain_insights`、`stance_impacts`、`review_hints`.
- Does not overwrite official pages by itself.
- Supports a local mock JSON file through `WECHAT_WIKI_COMPILE_MOCK_FILE` for offline pipeline validation.

Recommended Codex/Claude interactive flow:

```text
1. Run wiki_ingest.py to fetch the article into raw/
2. Run llm_compile_ingest.py --prepare-only --lean
3. Let the current Codex/Claude conversation produce one structured JSON result
4. Save that JSON locally
5. Run apply_compiled_brief_source.py to write wiki/briefs and wiki/sources, and emit `delta-compile` drafts from `update_proposals`
```

The `--lean` flag is recommended for LLM-first mode: you don't need `system_prompt`/`user_prompt` (those are for external LLM APIs), and noisy synthesis excerpts are filtered out. Without `--lean`, the full payload (~58KB) is suitable for piping to an external OpenAI-compatible API.

In LLM-first mode, you do the semantic work. The local scripts should remain responsible for context packaging, file writes, lint, and review workflows.

## apply_compiled_brief_source.py

Interactive apply entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\apply_compiled_brief_source.py `
  --vault "D:\Obsidian\MyVault" `
  --raw "D:\Obsidian\MyVault\raw\articles\<slug>.md" `
  --compiled-json "D:\path\to\compiled_result.json" `
  --force
```

What the interactive apply script does:

- Accepts a Codex/Claude-produced structured compile JSON.
- Renders and writes `wiki/briefs/` and `wiki/sources/`.
- `claim_inventory` is now propagated from compiled JSON through to page builder (no longer discarded in `to_legacy_compile_shape()`).
- Brief/source pages include `## 关键判断` section rendering per-claim `[type|confidence]` format with `⚠️需验证` markers.
- Frontmatter includes `claim_confidence_high/medium/low` counts alongside existing `confidence` field.
- When `review_hints.needs_human_review=True` or source confidence is low with no high claims, pages are created with `lifecycle: "candidate"` instead of `lifecycle: "official"`.
- Candidate pages display `[!warning] 候选页待审` callout and split claims into `## 关键判断` (high/medium) + `## 待验证判断` (low).
- Refreshes taxonomy/synthesis scaffolding, preferring v2 proposal-driven `domains`.
- Concept/entity pages inherit `lifecycle: "candidate"` from their source page when source is candidate.
- After ingestion, rebuilds `wiki/claim-evolution.md` with reinforce/contradict/extend claim relationships.
- Emits `wiki/outputs/*.md` `delta-compile` drafts from `update_proposals` instead of overwriting official pages directly.
- Rebuilds `wiki/index.md` and appends a `compile_apply_v2` event to `wiki/log.md` when the payload is v2.
- A sample LLM result lives at `references/examples/agent_interactive_compiled_result.json`.