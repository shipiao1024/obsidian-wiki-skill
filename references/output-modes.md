# Output Modes

`wiki_query.py` supports nine output modes via the `--mode` flag.

## Modes

### brief (default)

Current behaviour. Returns top excerpts from matched candidate pages, with supplementary evidence and raw-source verification when applicable.

```powershell
python scripts/wiki_query.py "端到端自动驾驶的技术挑战" --vault "D:\Vault"
```

### briefing

Structured briefing. Assembles a one-page overview combining:
- **相关来源** — links + one-line summaries of top candidate pages
- **核心主张** — extracted claims with source attribution
- **争议与冲突** — contradictions detected from typed edges and source pages
- **相关开放问题** — open/partial questions from `wiki/questions/`
- **相关立场** — active/challenged stances from `wiki/stances/` with confidence level

Use when you need a complete picture before a meeting, decision, or deep-dive.

```powershell
python scripts/wiki_query.py "BEV感知方案的对比" --mode briefing --vault "D:\Vault"
```

### draft-context

Copy-paste-ready material pack with citations. Produces:
- Numbered source summaries (each tagged with `[[ref]]`)
- Knowledge-base relation excerpts
- Raw article excerpts (up to 800 chars each) for precise quoting

Designed for pasting into an LLM conversation as grounded context.

```powershell
python scripts/wiki_query.py "Transformer在自动驾驶中的应用" --mode draft-context --vault "D:\Vault"
```

### contradict

Find the strongest rebuttal. Given a claim, scans:
- **立场中的反对证据** — steel-man counter-arguments from stance pages
- **来源中的冲突信号** — source pages that mention contradictions
- **潜在对立面** — sentences containing negation patterns near claim terms

The question is auto-stripped of prefixes like "反驳", "反对", "挑战", "质疑" to extract the target claim.

```powershell
python scripts/wiki_query.py "反驳纯视觉方案足够安全的观点" --mode contradict --vault "D:\Vault"
```

### digest

Multi-source aggregation. Collects relevant sources, stances, questions, syntheses, and briefs by term overlap scoring. Three sub-types via `--digest-type`:

- **deep** (default): background + core views + cross-perspective comparison + unresolved questions
- **compare**: core views, applicable scenarios, strengths, weaknesses in markdown table
- **timeline**: Mermaid gantt chart + chronological event list

```powershell
python scripts/wiki_query.py "自动驾驶技术路线" --mode digest --vault "D:\Vault"
python scripts/wiki_query.py "BEV vs 端到端" --mode digest --digest-type compare --vault "D:\Vault"
```

### essay

Draft essay from stances + syntheses + sources. Assembles arguments, counter-arguments, and evidence into a coherent narrative.

```powershell
python scripts/wiki_query.py "端到端自动驾驶的可行性" --mode essay --vault "D:\Vault"
```

### reading-list

Recommended reading path sorted by dependency. Topological sort of relevant pages — foundational content first, advanced content last.

```powershell
python scripts/wiki_query.py "Transformer架构" --mode reading-list --vault "D:\Vault"
```

### talk-track

Meeting material pack. Assembles stance arguments, rebuttals, and open questions into a structured briefing for discussion.

```powershell
python scripts/wiki_query.py "纯视觉vs多传感器" --mode talk-track --vault "D:\Vault"
```

### deep-research

Hypothesis-driven research combining vault knowledge with targeted web searches. Produces a structured analysis with evidence-labeled conclusions, dependency tracking, scenario stress testing, and pre-mortem.

Use when the topic is strategically important, depends on external reality, and framing risk exists. The host agent follows a 9-phase protocol (see `references/deep-research-protocol.md`) using `deep_research.py` CLI commands.

```powershell
python scripts/wiki_query.py "端到端自动驾驶的量产可行性" --mode deep-research --vault "D:\Vault"
```

## Output Page

All modes write a page to `wiki/outputs/` with `mode` recorded in frontmatter. The `mode` field is also logged in `wiki/log.md`.

## Host Agent Integration

When the user asks a question, the host agent should:
1. Default to `brief` mode for factual lookups.
2. Use `briefing` mode when the user needs a structured overview.
3. Use `draft-context` mode when the user says "prepare context" or "gather materials".
4. Use `contradict` mode when the user says "rebut", "challenge", or "find counter-arguments".
5. Use `digest` mode when the user wants a multi-source synthesis or comparison.
6. Use `essay` mode when the user wants a draft write-up.
7. Use `reading-list` mode when the user wants to know what to read and in what order.
8. Use `talk-track` mode when the user is preparing for a meeting or discussion.
9. Use `deep-research` mode when the topic is strategically important, depends on external reality, and framing risk exists. The host agent then follows the 9-phase protocol (see `references/deep-research-protocol.md`).
