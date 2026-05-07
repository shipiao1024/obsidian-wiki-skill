"""Vault resolution, multi-vault registry, and URL helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .pipeline_types import Article, DEFAULT_DOMAINS, PROPOSAL_THRESHOLD
from .text_utils import parse_frontmatter, sanitize_filename

CONF_DIR = Path.home() / ".claude" / "obsidian-wiki"
VAULTS_JSON = CONF_DIR / "vaults.json"
VAULT_CONF = CONF_DIR / "vault.conf"


def video_id_from_url(url: str) -> str:
    yt_match = re.search(r"[?&]v=([A-Za-z0-9_-]{3,})", url)
    if yt_match:
        return yt_match.group(1)
    short_yt_match = re.search(r"youtu\.be/([A-Za-z0-9_-]{3,})", url)
    if short_yt_match:
        return short_yt_match.group(1)
    bv_match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if bv_match:
        video_id = bv_match.group(1)
        split = urlsplit(url)
        params = dict(parse_qsl(split.query, keep_blank_values=True))
        page = params.get("p", "").strip()
        if page:
            return f"{video_id}:p{page}"
        return video_id
    douyin_match = re.search(r"douyin\.com/video/(\d+)", url)
    if douyin_match:
        return douyin_match.group(1)
    douyin_short_match = re.search(r"v\.douyin\.com/([A-Za-z0-9]+)", url)
    if douyin_short_match:
        return douyin_short_match.group(1)
    return sanitize_filename(url)


def normalize_collection_url(source_id: str, url: str) -> str:
    split = urlsplit(url.strip())
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    path = split.path.rstrip("/") or "/"
    if source_id == "video_playlist_youtube":
        list_id = query.get("list", "").strip()
        if list_id:
            return urlunsplit((split.scheme, split.netloc.lower(), "/playlist", urlencode({"list": list_id}), ""))
    if source_id == "video_playlist_bilibili":
        sid = query.get("sid", "").strip()
        if sid and "channel/" in path:
            return urlunsplit((split.scheme, split.netloc.lower(), path, urlencode({"sid": sid}), ""))
    if source_id == "video_playlist_douyin":
        return urlunsplit((split.scheme, split.netloc.lower(), path, "", ""))
    if source_id == "video_collection_douyin":
        return urlunsplit((split.scheme, split.netloc.lower(), path, "", ""))
    canonical_query = urlencode(sorted(query.items()))
    return urlunsplit((split.scheme, split.netloc.lower(), path, canonical_query,))


def transcript_fidelity(article: Article) -> str:
    if article.transcript_source == "platform_subtitle":
        return "source-provided"
    if article.transcript_source == "embedded_subtitle":
        return "embedded-source"
    if article.transcript_source == "asr":
        return "machine-transcribed"
    return "derived"


def transcript_page_name(article: Article) -> str:
    return article.transcript_stage or "transcript"


def transcript_page_link(article: Article, slug: str) -> str:
    return f"[[raw/transcripts/{slug}--{transcript_page_name(article)}]]"


def load_vault_registry() -> list[dict[str, object]]:
    """Load all registered vaults from vaults.json (or migrate from vault.conf)."""
    if VAULTS_JSON.exists():
        try:
            data = json.loads(VAULTS_JSON.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    if VAULT_CONF.exists():
        vault_path = Path(VAULT_CONF.read_text(encoding="utf-8").strip())
        if vault_path.exists():
            return [{"path": str(vault_path), "name": vault_path.name, "default": True}]

    return []


def save_vault_registry(entries: list[dict[str, object]]) -> None:
    """Persist vault registry to vaults.json."""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    VAULTS_JSON.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_purpose_md(vault: Path) -> dict[str, list[str] | list[dict]]:
    """Read purpose.md from a vault and extract Value Points, focus/exclude domain lists.

    Returns:
        {
            "focus": ["认知科学", ...],       # flat domain list (backward compat, union of VP domains + ## 关注领域)
            "exclude": ["自动驾驶", ...],      # flat exclude list (backward compat)
            "value_points": [                   # structured intent anchors (from ## 价值锚点)
                {
                    "title": "理解学习的底层机制",
                    "intent": "想搞清楚...",
                    "domains": ["认知科学", "学习方法论"],
                    "questions": ["刻意练习为什么有效？...", ...]
                },
            ]
        }

    Old format (## 关注领域 + ## 排除范围 only) returns value_points: [] with
    focus populated from flat list. New format (## 价值锚点) additionally parses
    Value Points and union-merges their domains into focus.
    """
    purpose_path = vault / "purpose.md"
    if not purpose_path.exists():
        return {"focus": [], "exclude": [], "value_points": []}

    text = purpose_path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)

    focus: list[str] = []
    exclude: list[str] = []
    value_points: list[dict] = []
    section = ""

    # --- Parse flat sections (backward compat) ---
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## 关注领域"):
            section = "focus"
            continue
        elif stripped.startswith("## 排除范围"):
            section = "exclude"
            continue
        elif stripped.startswith("## 价值锚点"):
            section = "value_points"
            continue
        elif stripped.startswith("## ") and section in ("focus", "exclude"):
            section = ""
            continue
        if section in ("focus", "exclude") and stripped.startswith("- "):
            domain = stripped[2:].strip()
            if domain:
                if section == "focus":
                    focus.append(domain)
                elif section == "exclude":
                    exclude.append(domain)

    # --- Parse Value Points (## 价值锚点 → ### subsections) ---
    vp_section_start = body.find("## 价值锚点")
    if vp_section_start >= 0:
        # Extract only the ## 价值锚点 section (stop at next ## heading)
        vp_body = body[vp_section_start:]
        next_h2 = re.search(r"\n##\s+(?!#)", vp_body[1:])  # skip the opening ## 价值锚点 itself
        if next_h2:
            vp_body = vp_body[:next_h2.start() + 1]
        # Split by ### headings
        vp_parts = re.split(r"^###\s+", vp_body, flags=re.MULTILINE)
        for part in vp_parts[1:]:  # skip pre-first-### text
            lines = part.splitlines()
            if not lines:
                continue
            title = lines[0].strip()
            intent = ""
            domains: list[str] = []
            questions: list[str] = []
            for line in lines[1:]:
                stripped = line.strip()
                if stripped.startswith(">"):
                    intent = stripped.lstrip("> ").strip()
                elif stripped.startswith("关联领域:") or stripped.startswith("关联领域："):
                    domain_line = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped.split("：", 1)[1].strip()
                    domains = [d.strip() for d in domain_line.replace(",", "，").split("，") if d.strip()]
                elif stripped.startswith("- "):
                    questions.append(stripped[2:].strip())
            if title:
                value_points.append({
                    "title": title,
                    "intent": intent,
                    "domains": domains,
                    "questions": questions,
                })

    # Union Value Point domains into focus (if VP has domains not already in flat focus)
    vp_domains = set()
    for vp in value_points:
        vp_domains.update(vp.get("domains", []))
    for d in vp_domains:
        if d not in focus:
            focus.append(d)

    return {"focus": focus, "exclude": exclude, "value_points": value_points}


def map_domains_to_value_points(
    domains: list[str],
    value_points: list[dict],
) -> list[dict]:
    """Map a list of domains to the Value Points they serve.

    Returns list of matched Value Points with overlap info:
    [
        {"title": "...", "intent": "...", "matched_domains": ["认知科学"], "overlap_count": 1},
    ]
    """
    results: list[dict] = []
    for vp in value_points:
        vp_domains = set(vp.get("domains", []))
        matched = [d for d in domains if d in vp_domains or any(v in d or d in v for v in vp_domains)]
        if matched:
            results.append({
                "title": vp["title"],
                "intent": vp.get("intent", ""),
                "matched_domains": matched,
                "overlap_count": len(matched),
            })
    results.sort(key=lambda x: x["overlap_count"], reverse=True)
    return results


def select_vault_by_domains(article_domains: list[str]) -> Path | None:
    """Match article domains against all vaults' Value Points and focus domains.

    Scoring: overlap with Value Point domains counts 2x,
    overlap with flat focus list counts 1x.
    """
    registry = load_vault_registry()
    if not registry:
        return None

    best_vault: Path | None = None
    best_score = -1

    for entry in registry:
        vault = Path(entry["path"])
        if not vault.exists():
            continue
        purpose = parse_purpose_md(vault)
        focus = purpose.get("focus", [])
        value_points = purpose.get("value_points", [])

        score = 0
        # Flat focus overlap (1x weight)
        for d in article_domains:
            if d in focus or any(f in d or d in f for f in focus):
                score += 1
        # Value Point overlap (2x weight)
        for vp in value_points:
            vp_domains = set(vp.get("domains", []))
            for d in article_domains:
                if d in vp_domains or any(v in d or d in v for v in vp_domains):
                    score += 2

        if score > best_score:
            best_score = score
            best_vault = vault.resolve()

    return best_vault if best_score > 0 else None


def resolve_vault(explicit: Path | None = None, article_domains: list[str] | None = None) -> Path:
    """Resolve vault path: explicit arg > domain match > vaults.json default > vault.conf > obsidian.json > error."""
    if explicit:
        return explicit.resolve()

    if article_domains and article_domains != ["待归域"]:
        matched = select_vault_by_domains(article_domains)
        if matched:
            return matched

    registry = load_vault_registry()
    if registry:
        default_entries = [e for e in registry if e.get("default")]
        if default_entries:
            vault = Path(default_entries[0]["path"])
            if vault.exists():
                return vault.resolve()
        vault = Path(registry[0]["path"])
        if vault.exists():
            return vault.resolve()

    if VAULT_CONF.exists():
        vault = Path(VAULT_CONF.read_text(encoding="utf-8").strip())
        if vault.exists():
            return vault.resolve()

    return _discover_obsidian_vault()


def _discover_obsidian_vault() -> Path:
    """Discover Obsidian vault from obsidian.json (fallback for resolve_vault)."""
    import os

    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("APPDATA is not set. Pass --vault explicitly.")

    config_path = Path(appdata) / "obsidian" / "obsidian.json"
    if not config_path.exists():
        raise SystemExit(
            f"Obsidian config not found at {config_path}. Pass --vault explicitly."
        )

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse Obsidian config: {config_path}") from exc

    vaults = config.get("vaults", {})
    if not isinstance(vaults, dict) or not vaults:
        raise SystemExit("No registered Obsidian vaults found. Pass --vault explicitly.")

    open_vaults: list[Path] = []
    all_vaults: list[Path] = []
    for meta in vaults.values():
        if not isinstance(meta, dict):
            continue
        path = meta.get("path")
        if not path:
            continue
        vault = Path(path)
        all_vaults.append(vault)
        if meta.get("open") is True:
            open_vaults.append(vault)

    existing_open = [p for p in open_vaults if p.exists()]
    if len(existing_open) == 1:
        return existing_open[0]
    if len(existing_open) > 1:
        raise SystemExit("Multiple open Obsidian vaults detected. Pass --vault explicitly.")

    existing_all = [p for p in all_vaults if p.exists()]
    if len(existing_all) == 1:
        return existing_all[0]

    raise SystemExit("Could not determine a single Obsidian vault automatically.")


def load_domain_keywords(vault: Path | None = None) -> dict[str, list[str]]:
    """Load domain keywords, preferring vault-specific purpose.md over global defaults.

    Reads focus_domains from purpose.md and maps them to keyword lists.
    Falls back to DEFAULT_DOMAINS (from types.py) if no vault or no purpose.md.
    Future: purpose.md could include per-domain keyword overrides.
    """
    if vault is None:
        return dict(DEFAULT_DOMAINS)

    purpose = parse_purpose_md(vault)
    focus = purpose.get("focus", [])
    if not focus:
        return dict(DEFAULT_DOMAINS)

    # For now, use focus domains as domain names with DEFAULT_DOMAINS keywords where available.
    # Domains not in DEFAULT_DOMAINS get the domain name itself as the only keyword.
    result: dict[str, list[str]] = {}
    for domain in focus:
        if domain in DEFAULT_DOMAINS:
            result[domain] = DEFAULT_DOMAINS[domain]
        else:
            result[domain] = [domain]
    return result if result else dict(DEFAULT_DOMAINS)


# ---------------------------------------------------------------------------
# Domain Proposal accumulator
# ---------------------------------------------------------------------------

def load_domain_proposals(vault: Path) -> dict:
    """Load domain proposals accumulator from wiki/domain-proposals.json."""
    proposals_path = vault / "wiki" / "domain-proposals.json"
    if proposals_path.exists():
        try:
            return json.loads(proposals_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"unclaimed_domains": {}, "proposed_value_points": [], "last_updated": ""}


def save_domain_proposals(vault: Path, proposals: dict) -> None:
    """Persist domain proposals accumulator."""
    proposals_path = vault / "wiki" / "domain-proposals.json"
    proposals_path.parent.mkdir(parents=True, exist_ok=True)
    proposals["last_updated"] = datetime.now().isoformat()
    proposals_path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")


def update_domain_proposals(
    vault: Path,
    compiled_domains: list[str],
    domain_reasons: dict[str, str],
    source_slug: str,
    source_title: str,
    source_date: str,
) -> list[dict]:
    """Update domain proposals accumulator with new compile domains.

    For each domain in compiled_domains:
    - If domain maps to a Value Point or focus list, skip (claimed)
    - If domain is in exclude list, skip
    - Otherwise, add to unclaimed_domains accumulator

    Returns list of domains that have reached proposal threshold
    (source_count >= PROPOSAL_THRESHOLD and status == "accumulating").
    """
    purpose = parse_purpose_md(vault)
    claimed_domains = set()
    for vp in purpose.get("value_points", []):
        claimed_domains.update(vp.get("domains", []))
    claimed_domains.update(purpose.get("focus", []))
    exclude_domains = set(purpose.get("exclude", []))

    proposals = load_domain_proposals(vault)
    new_proposable: list[dict] = []

    for domain in compiled_domains:
        if domain in claimed_domains or domain in exclude_domains or domain == "待归域":
            continue

        if domain not in proposals["unclaimed_domains"]:
            proposals["unclaimed_domains"][domain] = {
                "source_count": 0,
                "first_seen": source_date,
                "latest_source": f"sources/{source_slug}",
                "reasons": [],
                "cross_domain_insights_count": 0,
                "proposed_at": None,
                "status": "accumulating",
            }

        entry = proposals["unclaimed_domains"][domain]
        entry["source_count"] += 1
        entry["latest_source"] = f"sources/{source_slug}"
        if domain_reasons.get(domain):
            entry["reasons"].append(domain_reasons[domain])

        if entry["source_count"] >= PROPOSAL_THRESHOLD and entry["status"] == "accumulating":
            entry["status"] = "proposable"
            entry["proposed_at"] = datetime.now().isoformat()
            new_proposable.append({
                "domain": domain,
                "source_count": entry["source_count"],
                "reasons_sample": entry["reasons"][-3:],
                "latest_source": entry["latest_source"],
            })

    save_domain_proposals(vault, proposals)
    return new_proposable