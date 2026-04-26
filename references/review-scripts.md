# Review & Maintenance Scripts

Review and maintenance scripts for the Claude-obsidian-wiki-skill pipeline. Read this file when performing maintenance, lint, or review operations.

---

## wiki_lint.py

Health check entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_lint.py --vault "D:\Obsidian\MyVault"
```

What the health check script does:

- Reports missing `brief/source` pairs, orphan pages, empty taxonomy folders, and broken wikilinks.
- Reports low-quality `source` pages through `low_quality_sources` when frontmatter marks them as `quality: low`.
- Scans `delta-compile` claim blocks for low-confidence or evidence-free claim inventory items.
- Scans `delta-compile`、`source`、`synthesis` pages for obvious claim conflicts such as `会/不会`、`支持/反对` around the same core phrase.

## wiki_size_report.py

Size report entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_size_report.py `
  --vault "D:\Obsidian\MyVault"
```

What the size report does:

- Counts wiki pages and rough token pressure by folder.
- Reports whether the vault is still in the comfortable `index-first` range.
- Gives an explicit signal for when to consider adding a local search tool.

## stale_report.py

Stale report entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\stale_report.py `
  --vault "D:\Obsidian\MyVault"
```

With blind-spots report:

```powershell
python Claude-obsidian-wiki-skill\scripts\stale_report.py `
  --vault "D:\Obsidian\MyVault" --blind-spots
```

What the stale report does:

- Flags repeated ingests and repeated queries from `wiki/log.md`.
- Flags taxonomy pages that still contain placeholder language after accumulating multiple sources.
- Flags taxonomy pages whose linked `source` pages are newer than the taxonomy page itself.
- Helps decide where to run a focused recompile instead of manually scanning the whole vault.
- With `--blind-spots`, also generates `wiki/blind-spots.md` containing:
  - Orphan taxonomy pages (no inbound source links)
  - Missing cross-links between concept/entity pages in the same domain
  - Domains with no questions or stances
  - Topics frequently mentioned in sources but missing from taxonomy
  - Open questions with no progress clues

## delta_compile.py

Delta compile entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\delta_compile.py `
  --vault "D:\Obsidian\MyVault"
```

What the delta compile script does:

- Reads the current high-churn signals from `wiki/log.md`.
- Generates review-ready recompilation drafts into `wiki/outputs/`.
- Produces candidate replacements for `brief/source` wording and recurring query answers.
- Does not overwrite official pages directly; the drafts are meant for human review first.

## refresh_synthesis.py

Synthesis refresh entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\refresh_synthesis.py `
  --vault "D:\Obsidian\MyVault"
```

What the synthesis refresh script does:

- Rebuilds `wiki/syntheses/*.md` from their currently linked `sources/*`.
- Prefers structural judgement sentences over narrative setup.
- Produces a clearer `当前结论 / 核心判断 / 待验证` structure for later query work.

## review_queue.py

Review queue entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\review_queue.py `
  --write
```

What the review queue script does:

- Builds a focused pending-review page at `wiki/review_queue.md`.
- Lists only `temporary` and `review-needed` outputs.
- Adds an explicit `冲突候选` section for outputs involved in claim conflicts.
- Prioritizes conflicted `delta-compile` drafts ahead of ordinary pending outputs.
- Separates duplicate output titles from the active queue.
- Keeps absorbed history out of the day-to-day queue while preserving auditability.

## archive_outputs.py

Archive duplicate outputs entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\archive_outputs.py `
  --apply
```

What the archive script does:

- Detects duplicate output titles in `wiki/outputs/`.
- Keeps the newest live candidate for each title.
- Marks older duplicates as `lifecycle: archived`.
- Rebuilds `wiki/index.md` and appends an `archive_outputs` event to `wiki/log.md`.

## graph_cleanup.py

Graph cleanup entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\graph_cleanup.py `
  --vault "D:\Obsidian\MyVault"
```

What the graph cleanup script does:

- Backfills `graph_role` and `graph_include` for existing pages.
- Marks `index.md` and `log.md` as system pages.
- Marks `raw/`、`sources/`、`briefs/` as document pages outside the main graph.
- Marks `outputs/` as working pages outside the main graph.
- Keeps `domains/`、`syntheses/`、mature `concepts/`、mature `entities/` as the main graph layer.

## graph_trim.py

Graph trim entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\graph_trim.py `
  --vault "D:\Obsidian\MyVault" `
  --demote-concept "BEV" `
  --demote-concept "规划" `
  --demote-domain "商业分析" `
  --demote-synthesis "商业分析--综合分析"
```

What the graph trim script does:

- Demotes selected low-signal pages out of the main graph without deleting them.
- Preserves the files for later reuse or promotion.
- Is useful when the vault is structurally correct but the graph still looks noisy.

Built-in graph policy:

```powershell
python Claude-obsidian-wiki-skill\scripts\graph_trim.py `
  --vault "D:\Obsidian\MyVault" `
  --apply-policy
```

Policy rules:

- `raw/`、`sources/`、`briefs/`、`outputs/`、`index/log` never belong to the main graph.
- `concepts/` and `entities/` stay out of the main graph unless they already have at least 2 linked sources and are no longer placeholder pages.
- `domains/` and `syntheses/` stay out of the main graph until they are supported by at least 2 linked sources.
- Manual demotion is still available for pages that are structurally valid but visually noisy.

## export_main_graph.py

Main graph export entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\export_main_graph.py `
  --vault "D:\Obsidian\MyVault"
```

With typed edges:

```powershell
python Claude-obsidian-wiki-skill\scripts\export_main_graph.py `
  --vault "D:\Obsidian\MyVault" --typed-edges
```

What the main graph export script does:

- Scans only the knowledge layer: `wiki/concepts/`、`wiki/entities/`、`wiki/domains/`、`wiki/syntheses/`.
- Ignores `index/log/raw/source/brief/output` even if those pages contain many links.
- Exports `wiki/graph-view.md`, which contains:
  - A Mermaid main graph that can be opened directly inside Obsidian.
  - A copy-ready Obsidian graph filter guide for the same knowledge-layer view.
- Is useful when Obsidian's raw global graph is too noisy, but you still want to stay inside Obsidian instead of switching to a separate visualization tool.
- **`--vault` is mandatory when content has been auto-routed to a non-default vault**: The host agent must pass the vault path where content was actually ingested, not rely on `vault.conf`/`vaults.json` defaults. Otherwise the graph will be generated in the wrong vault.
- With `--typed-edges`, also generates `wiki/typed-graph.md` with classified edge types:
  - `belongs_to` — concept/entity → domain
  - `mentions` — source/brief → concept/entity/domain
  - `supports` — stance → source (reinforce)
  - `contradicts` — stance → source (contradict)
  - `answers` — source → question
  - `evolves` — synthesis → source

## apply_approved_delta.py

Approved delta apply entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\apply_approved_delta.py `
  "outputs/<slug>"
```

What the apply script does:

- Applies an approved `output` or `delta-compile` page into official wiki pages.
- `delta-source` rewrites the corresponding `source` / `brief` sections.
- `delta-query` or a normal `output` is absorbed into a `synthesis` page.
- Marks the original output as `accepted + absorbed`.
- Appends an `apply_delta` event to `wiki/log.md`.
- Rebuilds `wiki/index.md` while hiding absorbed outputs from the main outputs section.