---
name: obsidian-wiki
description: Use when Codex or Claude needs to ingest WeChat articles, web pages, selected video URLs, local files, or pasted text into a Windows-based Obsidian knowledge vault, preserve immutable raw sources, generate source and brief pages, maintain index and log files, and operate a host-agent-first raw/wiki workflow.
---

# Obsidian Wiki Skill

## Trigger

**Hard trigger** (always activate):
- User message contains a known ingest URL pattern: `mp.weixin.qq.com`, `bilibili.com/video`, `youtube.com/watch`, `youtu.be/`, `douyin.com/video`
- User message contains explicit intent keywords: `落盘`, `入库`, `ingest`, `归档`, `save to wiki`, `存到知识库`

**Soft trigger** (activate when vault context exists):
- User message contains: `知识库`, `wiki`, `query the vault`, `维护知识库`, `日常维护`, `lint`, `review`
- User says `autoresearch`, `自动研究`, `深入研究`, `deep research`, `深度分析`, `系统分析`

**Do NOT trigger**:
- User only asks to summarize, translate, or explain an article without ingest intent
- User asks a general question unrelated to the vault

## What This Skill Does

Two-layer knowledge workflow: `raw/` stores immutable sources; `wiki/` stores AI-maintained knowledge pages. Host agent (Claude Code) is the primary entry; local Python scripts support fetch, ingest, compile, apply, lint, review, and archive. Obsidian provides filesystem navigation, full-text search, backlinks, graph view.

## Do NOT Load

- `docs/` directory — user-facing documentation, not for runtime context
- `README.md`, `README.en.md` — project overview, not skill reference

## Conditional Reference Loading

**Do NOT load all reference files at once.** Load ONLY what the current task requires:

| Task | Load These | When |
|------|-----------|------|
| Ingest | workflow.md + pipeline-scripts.md | URL / file / text to ingest |
| Compile | workflow.md + pipeline-scripts.md | Prepare compile payload |
| Apply | workflow.md + pipeline-scripts.md | Write back compiled JSON |
| Query | query-scripts.md + output-modes.md | Question about vault content |
| Review | review-scripts.md | Lint, health check, review queue |
| Video collection | video-rules.md + pipeline-scripts.md | Video playlist / channel URL |
| Save conversation | interaction.md | "save" / "保存对话" |
| Autoresearch | autoresearch-protocol.md + workflow.md | "autoresearch" / "自动研究" / "深入调查" / "知识库补盲" |
| Deep research | deep-research-protocol.md + workflow.md | "deep research" / "深入研究" / "深度分析" / "系统分析" |
| First-time setup | setup.md | First invocation or dep failure |

## Script Entrypoints (names only)

init_vault.py, wiki_ingest.py, wiki_ingest_wechat.py (legacy), llm_compile_ingest.py, apply_compiled_brief_source.py, wiki_lint.py, wiki_size_report.py, stale_report.py, delta_compile.py, refresh_synthesis.py, review_queue.py, archive_outputs.py, graph_cleanup.py, graph_trim.py, export_main_graph.py, apply_approved_delta.py, wiki_query.py, install_video_cookies.py, import_jobs.py, question_ledger.py, stance_manager.py, source_adapters.py, adapter_result_to_article.py, deep_research.py

Script details and PowerShell examples: load the relevant scripts-*.md file for the current pipeline stage.

## References

- `references/workflow.md` — operating modes, pipeline stages, vault structure, operating model, page conventions
- `references/interaction.md` — routing rules, status vocabulary, user prompts, host-agent execution style
- `references/pipeline-scripts.md` — ingest / compile / apply script details
- `references/review-scripts.md` — lint / review / maintenance script details
- `references/query-scripts.md` — query script details
- `references/helper-scripts.md` — cookie install, question ledger, stance manager, import jobs
- `references/video-rules.md` — video processing, collection protection, cookie rules
- `references/output-modes.md` — wiki_query.py output modes
- `references/setup.md` — environment setup, dependencies, first-time vault configuration
- `references/cross-project-access.md` — read-only vault access from other projects
- `references/deep-research-protocol.md` — 9-phase deep research protocol, hypothesis-driven research, evidence labels, dependency ledger, scenario stress testing, pre-mortem
- `references/autoresearch-protocol.md` — 3-phase broad exploration protocol for vault gap filling
- `references/comparison-schema.md` — comparison page schema and trigger conditions
- `references/question-schema.md` — question page schema
- `references/stance-schema.md` — stance page schema
