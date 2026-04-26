# Cross-Project Access

Other Claude Code projects can reference this Obsidian wiki vault for knowledge retrieval without modifying it directly.

## Tiered Read Strategy

When another project needs context from this vault, follow this tiered approach to minimize token cost:

| Tier | File | Approximate tokens | When to use |
|------|------|--------------------|-------------|
| 1 | `wiki/hot.md` | ~500 | Quick check for recent activity, active stances, open questions |
| 2 | `wiki/index.md` | ~1000 | Find relevant page references by topic |
| 3 | Domain `_index` | ~300 | Navigate a specific topic area |
| 4 | Individual page | ~100-300 | Read specific source, brief, concept, entity, or comparison |

Always start from Tier 1. Only descend to lower tiers when the hot cache doesn't answer the question.

## CLAUDE.md Path Reference

Add a path reference in another project's `CLAUDE.md`:

```markdown
## Knowledge Vault Reference

For domain knowledge about [your topics], read the Obsidian wiki vault at:
- Hot cache (read first): `<vault-path>/wiki/hot.md`
- Full index: `<vault-path>/wiki/index.md`
- Specific pages: `<vault-path>/wiki/<folder>/<slug>.md`

Vault path discovery: the vault is auto-discovered via domain-aware routing (`~/.claude/obsidian-wiki/vaults.json`) or `%APPDATA%\obsidian\obsidian.json` fallback.
Only read from `wiki/` layer; never write directly.
```

Replace `<vault-path>` with the actual vault path. If the vault path varies, use the discovery logic from `wiki_ingest.py` or `wiki_query.py`.

## Read-Only Principle

External projects MUST only **read** from the `wiki/` layer. They should never:

- Write directly to `wiki/`, `raw/`, or any vault directory
- Modify frontmatter or page content
- Delete pages

If an external project needs to ingest new content into the vault, it must invoke the `obsidian-wiki` skill through Claude Code, which routes through the standard 5-stage pipeline (fetch -> ingest -> compile -> apply -> review).

## Vault Path Discovery

The vault path can be discovered automatically:

1. **Multi-vault registry**: Read `~/.claude/obsidian-wiki/vaults.json` which lists all registered vaults with paths and focus domains. `resolve_vault(article_domains=...)` auto-selects the vault with the highest domain overlap against each vault's `purpose.md` focus areas.
2. **Auto-discovery**: Read `%APPDATA%\obsidian\obsidian.json` and select the unique open vault (or unique registered vault if none is open). This is the fallback logic used by `wiki_ingest.py` and `wiki_query.py`.
3. **Explicit path**: Pass `--vault <path>` to any script.
4. **CLAUDE.md reference**: Hardcode the vault path in a project's `CLAUDE.md` for consistency.

In a multi-vault setup, prefer option 1 (domain-aware routing) over option 2 (single-vault auto-discovery).

## Page Type Quick Reference

| Folder | Type | Content | Fidelity |
|--------|------|---------|----------|
| `wiki/hot.md` | system-hot | Recent context cache (~500 tokens) | System metadata |
| `wiki/index.md` | system-index | Full vault directory | Navigation |
| `wiki/log.md` | system-log | Append-only ingest/query log | Audit trail |
| `wiki/briefs/` | brief | Lossy summary, key points | Low (quick scan) |
| `wiki/sources/` | source | Distilled with provenance | Medium (reliable but not ground truth) |
| `wiki/concepts/` | concept | Definitions, relations | Knowledge layer |
| `wiki/entities/` | entity | People, orgs, products | Knowledge layer |
| `wiki/domains/` | domain | Topic area overviews | Knowledge layer |
| `wiki/syntheses/` | synthesis | Cross-source analysis | Knowledge layer |
| `wiki/questions/` | question | Open/partial/resolved questions | Knowledge layer |
| `wiki/stances/` | stance | Position tracking with evidence | Knowledge layer |
| `wiki/comparisons/` | comparison | A-vs-B structured comparisons | Knowledge layer |
| `wiki/outputs/` | output | Query results, delta drafts, session summaries | Working layer (temporary) |
| `raw/articles/` | raw-source | Immutable original text | Ground truth (highest) |

When accuracy matters, always go back to `raw/articles/` for verification.