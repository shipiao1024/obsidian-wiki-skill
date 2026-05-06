#!/usr/bin/env python
"""Initialize an Obsidian Wiki vault: create directory structure, purpose.md, and persist vault path.

Usage:
    python scripts/init_vault.py --vault <path>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.shared import WIKI_DIRS, resolve_vault, load_vault_registry, save_vault_registry, VAULTS_JSON


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize an Obsidian Wiki vault.")
    parser.add_argument("--vault", type=Path, required=True, help="Obsidian vault root path.")
    return parser.parse_args()


PURPOSE_TEMPLATE = """\
---
title: "知识库目的声明"
type: "system-config"
---

# 知识库目的声明

## 核心问题

- 最想搞清楚什么？（填写你的核心研究问题）

## 关注领域

- 持续跟踪的主题（填写关注领域，每行一个）

## 排除范围

- 明确不关注什么？（填写排除范围，入库时会跳过这些内容的分类法页面创建）
"""


def init_vault(vault: Path) -> None:
    vault = vault.resolve()
    vault.mkdir(parents=True, exist_ok=True)

    # Create directory structure
    created: list[str] = []
    for d in WIKI_DIRS:
        dir_path = vault / d
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            created.append(d)

    # Create system files if they don't exist
    system_files = {
        "wiki/index.md": "---\ntitle: \"Wiki Index\"\ntype: \"system-index\"\n---\n\n# Wiki Index\n\n> 先扫描本页，再按需打开相关页面。\n",
        "wiki/log.md": "---\ntitle: \"Wiki Log\"\ntype: \"system-log\"\n---\n\n# Wiki Log\n",
        "wiki/hot.md": "---\ntitle: \"Hot Cache\"\ntype: \"system-cache\"\n---\n\n# Hot Cache\n\n## Recent Ingests\n\n- （空）\n\n## Recent Queries\n\n- （空）\n",
    }

    for rel_path, content in system_files.items():
        file_path = vault / rel_path
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
            created.append(rel_path)

    # Create purpose.md if it doesn't exist
    purpose_path = vault / "purpose.md"
    if not purpose_path.exists():
        purpose_path.write_text(PURPOSE_TEMPLATE, encoding="utf-8")
        created.append("purpose.md")

    # Persist vault path to vaults.json (multi-vault registry)
    registry = load_vault_registry()
    existing = [i for i, e in enumerate(registry) if e.get("path") == str(vault)]
    if existing:
        # Update existing entry
        registry[existing[0]]["path"] = str(vault)
        registry[existing[0]]["name"] = vault.name
    else:
        # Add new entry; mark as default if this is the first vault
        is_first = len(registry) == 0
        registry.append({"path": str(vault), "name": vault.name, "default": is_first})
    # Ensure exactly one default
    has_default = any(e.get("default") for e in registry)
    if not has_default and registry:
        registry[0]["default"] = True
    save_vault_registry(registry)

    # Also write legacy vault.conf for backwards compatibility
    conf_dir = Path.home() / ".claude" / "obsidian-wiki"
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_path = conf_dir / "vault.conf"
    conf_path.write_text(str(vault), encoding="utf-8")

    # Configure Obsidian graph filter (knowledge-layer only, hide raw/sources/briefs/outputs noise)
    try:
        from export_main_graph import write_obsidian_graph_config
        config_paths = write_obsidian_graph_config(vault)
        created.extend(config_paths)
    except Exception:
        pass  # Obsidian config is nice-to-have, not blocking

    print(f"Vault initialized: {vault}")
    if created:
        print(f"Created: {', '.join(created)}")
    print(f"Vault registry saved to: {VAULTS_JSON}")
    print(f"Edit {purpose_path} to define your knowledge base scope.")


def main() -> int:
    args = parse_args()
    init_vault(args.vault)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
