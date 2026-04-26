# Query Scripts

Query scripts for the Claude-obsidian-wiki-skill pipeline. Read this file when performing a wiki query.

---

## wiki_query.py

Query entrypoint:

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_query.py `
  "这篇文章如何看待 AIDV 对 EEA 的冲击？"
```

With output mode:

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_query.py `
  "BEV感知方案的对比" --mode briefing

python Claude-obsidian-wiki-skill\scripts\wiki_query.py `
  "Transformer在自动驾驶中的应用" --mode draft-context

python Claude-obsidian-wiki-skill\scripts\wiki_query.py `
  "反驳纯视觉方案足够安全的观点" --mode contradict
```

What the query script does:

- Reads `wiki/hot.md` first for recent context, then `wiki/index.md` and ranks candidate pages from it.
- Prefers `wiki/sources/` and `wiki/briefs/`, with `wiki/syntheses/` and `wiki/comparisons/` as supporting context.
- Gives ranking boost to `mature`/`evergreen` pages (score +2/+1) over `seed`/`developing` pages.
- When the question contains precision signals such as numbers, dates, quotes, definitions, or author stance, it also reads linked `raw/articles/`.
- Supports eight output modes via `--mode`:
  - `brief` (default) — top excerpts from candidate pages.
  - `briefing` — structured briefing with sources, claims, controversies, open questions, and stances.
  - `draft-context` — copy-paste-ready material pack with citations for LLM context.
  - `contradict` — strongest rebuttal from stance pages, source contradictions, and negation-pattern matches.
  - `digest` — multi-source aggregation. Sub-types via `--digest-type`:
    - `deep` (default): background + core views + cross-perspective comparison + unresolved questions
    - `compare`: core views, applicable scenarios, strengths, weaknesses in markdown table
    - `timeline`: Mermaid gantt chart + chronological event list
  - `essay` — draft essay from stances + syntheses + sources.
  - `reading-list` — recommended reading path sorted by dependency.
  - `talk-track` — meeting material pack with stance arguments, rebuttals, and open questions.
- Writes the answer into `wiki/outputs/` by default.
- Updates `wiki/hot.md` with recent query context.
- Appends the query event (with mode) to `wiki/log.md`.
- Rebuilds `wiki/index.md` so the new output is discoverable.
- Marks `wiki/outputs/` pages as graph-hidden working artifacts, not primary knowledge nodes.

Full mode descriptions and usage examples: `references/output-modes.md`.