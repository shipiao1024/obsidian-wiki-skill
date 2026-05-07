#!/usr/bin/env python
"""Re-route a source from one vault to another based on domain matching.

Moves raw files, wiki pages, and updates taxonomy references.

Usage:
  python scripts/reroute_vault.py --slug <slug> --source-vault <path> --target-vault <path>
  python scripts/reroute_vault.py --slug <slug>  # auto-detect target vault from domain match
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.vault_config import resolve_vault, parse_purpose_md, select_vault_by_domains
from pipeline.shared import resolve_vault as _resolve_vault_default
from pipeline.encoding_fix import fix_windows_encoding


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-route a source between vaults.")
    parser.add_argument("--slug", required=True, help="Source slug to move.")
    parser.add_argument("--source-vault", type=Path, help="Current vault path.")
    parser.add_argument("--target-vault", type=Path, help="Target vault path (auto-detect if omitted).")
    return parser.parse_args()


def _move_file(src: Path, dst: Path) -> bool:
    """Move a file, creating destination directory if needed."""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return True


def reroute_slug(slug: str, source_vault: Path, target_vault: Path) -> dict:
    """Move a source (and associated pages) from source vault to target vault.

    Moves:
      - raw/articles/<slug>.md
      - raw/assets/<slug>/ (directory)
      - raw/transcripts/<slug>--*.md
      - wiki/briefs/<slug>.md
      - wiki/sources/<slug>.md

    Does NOT move:
      - concept/entity/domain/synthesis/stance pages (they stay in source vault)
      - wiki/outputs/ pages

    After moving, rebuilds indexes in both vaults.
    """
    moved_files: list[str] = []
    errors: list[str] = []

    # File pairs to move: (source_vault relative, target_vault relative)
    file_pairs = [
        f"raw/articles/{slug}.md",
        f"wiki/briefs/{slug}.md",
        f"wiki/sources/{slug}.md",
    ]

    for rel in file_pairs:
        src = source_vault / rel
        dst = target_vault / rel
        if _move_file(src, dst):
            moved_files.append(rel)
        else:
            if src.exists():
                errors.append(f"Failed to move {rel}")

    # Move assets directory
    assets_src = source_vault / "raw" / "assets" / slug
    assets_dst = target_vault / "raw" / "assets" / slug
    if assets_src.exists() and assets_src.is_dir():
        assets_dst.mkdir(parents=True, exist_ok=True)
        for f in assets_src.iterdir():
            shutil.move(str(f), str(assets_dst / f.name))
        shutil.rmtree(str(assets_src))
        moved_files.append(f"raw/assets/{slug}/")

    # Move transcript files
    transcripts_src = source_vault / "raw" / "transcripts"
    transcripts_dst = target_vault / "raw" / "transcripts"
    if transcripts_src.exists():
        for f in transcripts_src.glob(f"{slug}--*.md"):
            transcripts_dst.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(transcripts_dst / f.name))
            moved_files.append(f"raw/transcripts/{f.name}")

    # Rebuild indexes in both vaults
    for vault in (source_vault, target_vault):
        index_path = vault / "wiki" / "semantic-index.json"
        if index_path.exists():
            # Remove stale index so next retrieve triggers rebuild
            index_path.unlink()
            moved_files.append(f"{vault.name}/semantic-index.json (removed for rebuild)")

        # Rebuild wiki/index.md via the pipeline
        try:
            from pipeline.index_log import rebuild_index
            rebuild_index(vault)
            moved_files.append(f"{vault.name}/wiki/index.md (rebuilt)")
        except Exception as e:
            errors.append(f"Failed to rebuild index for {vault.name}: {e}")

    return {
        "slug": slug,
        "source_vault": str(source_vault),
        "target_vault": str(target_vault),
        "moved_files": moved_files,
        "errors": errors,
    }


def main() -> int:
    fix_windows_encoding()
    args = parse_args()

    # Resolve source vault
    source_vault = args.source_vault or _resolve_vault_default()
    source_vault = source_vault.resolve()

    # Resolve target vault
    if args.target_vault:
        target_vault = args.target_vault.resolve()
    else:
        # Auto-detect: read source's domains and find best match
        source_page = source_vault / "wiki" / "sources" / f"{args.slug}.md"
        if not source_page.exists():
            print(f"Source page not found: {source_page}")
            return 1

        # Extract domains from source page frontmatter or body
        from pipeline.text_utils import parse_frontmatter
        text = source_page.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)

        # Try frontmatter domains, then ## 主题域 section
        domains = meta.get("domains", [])
        if not domains:
            import re
            for line in body.splitlines():
                if line.strip().startswith("## 主题域"):
                    # Extract [[domains/xxx]] links
                    domain_links = re.findall(r"\[\[domains/([^]]+)\]\]", body[body.index(line):])
                    domains = domain_links[:5]
                    break

        if not domains:
            print("No domains found in source page. Specify --target-vault explicitly.")
            return 1

        target_vault = select_vault_by_domains(domains)
        if not target_vault:
            print(f"No matching vault found for domains: {domains}")
            return 1

    if source_vault == target_vault:
        print("Source and target vault are the same. No action needed.")
        return 0

    result = reroute_slug(args.slug, source_vault, target_vault)

    print(f"Moved '{args.slug}' from {source_vault.name} to {target_vault.name}")
    print(f"  Files moved: {len(result['moved_files'])}")
    for f in result['moved_files']:
        print(f"    {f}")
    if result['errors']:
        print(f"  Errors: {len(result['errors'])}")
        for e in result['errors']:
            print(f"    {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())