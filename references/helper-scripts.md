# Helper Scripts

Helper scripts and pipeline modules for the Claude-obsidian-wiki-skill. Read this file only when you need cookie management, question tracking, or stance management.

---

## install_video_cookies.py

Cookie install helper:

```powershell
python Claude-obsidian-wiki-skill\scripts\install_video_cookies.py `
  --source-file "D:\path\to\cookies.txt"
```

or:

```powershell
Get-Content "D:\path\to\cookies.txt" | python Claude-obsidian-wiki-skill\scripts\install_video_cookies.py --stdin
```

What the cookie install script does:

- Copies a user-provided Netscape-format `cookies.txt` into the `Claude-obsidian-wiki-skill/` directory.
- Supports `--source-file` for a direct file path.
- Supports `--stdin` for piped content.
- Used when the user already has a local `cookies.txt` elsewhere and explicitly wants help installing it into the skill directory.

## import_jobs.py

What the import jobs script does:

- Manages batch video collection job state in `wiki/import-jobs/*.md`.
- Tracks per-job progress, pause state, cooldown, and failure reasons.
- Supports collection protection knobs including limit, delay, backoff, jitter, failure threshold, and platform cooldown.
- Marks jobs as `paused` when consecutive failures trip the threshold.
- Records `last_failure_reason` and `cooldown_until` on paused jobs.

## question_ledger.py

Question ledger management:

```powershell
python Claude-obsidian-wiki-skill\scripts\question_ledger.py list --vault "D:\Obsidian\MyVault"
python Claude-obsidian-wiki-skill\scripts\question_ledger.py create --vault "D:\Obsidian\MyVault" --question "自动驾驶端到端方案的可靠性如何验证？"
python Claude-obsidian-wiki-skill\scripts\question_ledger.py check --vault "D:\Obsidian\MyVault" --source-title "端到端自动驾驶" --source-slug "e2e-av" --keywords 自动驾驶 端到端 验证 可靠性
python Claude-obsidian-wiki-skill\scripts\question_ledger.py resolve --vault "D:\Obsidian\MyVault" --slug "e2e-av-reliability" --note "被新论文完整回答"
```

What the question ledger script does:

- `list`: Shows all open/partial questions from `wiki/questions/`. Supports `--json` output.
- `create`: Creates a new question page in `wiki/questions/` with status `open`.
- `check`: Checks whether a new source (by title + keywords) might answer any open/partial questions. Uses keyword overlap matching (≥3 keyword overlap triggers a match).
- `resolve`: Marks a question page as `resolved` with an update note.

Question page schema and status transitions are documented in `references/question-schema.md`.

## Evolution Tracking (pipeline module)

The `pipeline/evolution.py` module generates `wiki/evolution.md` showing knowledge change over time. It can be called directly:

```python
from pipeline.evolution import write_evolution_page
write_evolution_page(vault)
```

What the evolution report contains:

- Overview statistics (total ingests, queries, active stances, open questions).
- Domain knowledge accumulation (sources per domain).
- Stance evolution (confidence drift and update history).
- Question progress by status (open / partial / resolved / dropped).
- Recent timeline from `wiki/log.md` (last 20 events).

## Blind-Spots Report (pipeline module)

The `pipeline/blindspots.py` module generates `wiki/blind-spots.md` identifying knowledge gaps. It is invoked via `stale_report.py --blind-spots` or directly:

```python
from pipeline.blindspots import write_blind_spots_page
write_blind_spots_page(vault)
```

What the blind-spots report contains:

- Orphan taxonomy pages (no inbound source links).
- Missing cross-links between concept/entity pages in the same domain.
- Domains with no questions or stances.
- Topics frequently mentioned in sources but missing from taxonomy.
- Open questions with no progress clues.

## Typed Edges (pipeline module)

The `pipeline/typed_edges.py` module generates `wiki/typed-graph.md` with classified relationship edges. It is invoked via `export_main_graph.py --typed-edges` or directly:

```python
from pipeline.typed_edges import write_typed_graph_page
write_typed_graph_page(vault)
```

Edge types:

- `belongs_to` — concept/entity → domain
- `mentions` — source/brief → concept/entity/domain
- `supports` — stance → source (reinforce)
- `contradicts` — stance → source (contradict)
- `answers` — source → question
- `evolves` — synthesis → source

## Stance Manager (pipeline module)

The `pipeline/stance.py` module manages stance pages. It is invoked from `ingest_orchestrator.py` during ingest or can be called directly via `scripts/stance_manager.py`:

```powershell
python Claude-obsidian-wiki-skill\scripts\stance_manager.py list --vault "D:\Obsidian\MyVault"
python Claude-obsidian-wiki-skill\scripts\stance_manager.py create --vault "D:\Obsidian\MyVault" --topic "纯视觉方案安全性"
python Claude-obsidian-wiki-skill\scripts\stance_manager.py impact --vault "D:\Obsidian\MyVault" --topic "纯视觉方案安全性" --source-slug "lidar-vs-vision" --impact contradict --evidence "新实验数据显示夜间场景下纯视觉方案误检率显著高于多传感器融合方案"
```

Impact types: `reinforce` (巩固), `contradict` (反驳), `extend` (延伸), `neutral` (无关).