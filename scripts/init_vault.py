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

## 价值锚点

### （锚点名称，如"理解学习的底层机制"）
> 为什么关注这个？想搞清楚什么本质问题？
关联领域: （填写关联的领域名，逗号分隔）
- 具体想回答的问题或想验证的假设

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

    # Create AGENTS.md (Codex project-level instructions) if it doesn't exist
    agents_path = vault / "AGENTS.md"
    if not agents_path.exists():
        agents_content = """\
# Obsidian Wiki Operating Rules

知识库随意图生长。入库是编译不是归档，领域从内容涌现，知识围绕意图组织。

## 三层架构

- **意图层** — `purpose.md` 价值锚点，表达为什么关注
- **涌现层** — `wiki/domain-proposals.json`，领域从内容涌现，≥3 篇来源触发提案
- **物理层** — `raw/` 不可变证据 + `wiki/` AI 编译知识层

## Layer Rules

- `raw/` 只放原始来源。只能新增，不要改写原文内容
- `wiki/` 由 AI 维护。摘要、概念、实体、综合分析、查询结果都写在这里
- `wiki/briefs/` 有损压缩层，快速浏览和导航
- `wiki/sources/` 保真提炼层，比 briefs 更可靠，但不是最终证据
- 最终证据始终在 `raw/`。高风险结论、细节争议、引用核对必须回看原文
- 每次查询优先读取 `wiki/index.md`，必要时再读取相关页面
- 每次 ingest 更新 `wiki/index.md` 和 `wiki/log.md`

## Value Point Rules

- `purpose.md` 的 `## 价值锚点` 表达意图（为什么关注），不是分类标签（关注什么）
- 入库时 compile 产出的 domain 不匹配已有 Value Point → 累积到 `wiki/domain-proposals.json`
- 同一 domain ≥3 篇来源 → 系统提议成为新锚点
- 跨域洞察指向其他 vault 关注领域 → 自动补充检索，标记为 `cross_vault_supplementary`

## Ingest Rules

- 每个原始来源至少生成 `wiki/sources/` 和 `wiki/briefs/`
- 来源引入稳定概念或重要实体 → 新增或更新 `wiki/concepts/`、`wiki/entities/`
- 来源改变主题域理解 → 更新 `wiki/domains/` 或 `wiki/syntheses/`
- 同一概念/实体在多个 source 中稳定出现才建独立页；单次提及保留为候选
- 立场影响（reinforce/contradict/extend）自动检测并写入 `wiki/stances/`

## Writing Rules

- 结论必须可追溯到原始来源
- 不要把未经证实的推断写成事实
- 优先使用 `[[wikilinks]]` 连接已有页面
- `wiki/log.md` 追加写入，不回写历史记录
- `wiki/outputs/` 是临时工作产物，不是正式知识层

## Query Rules

- 粗粒度问题先读 `wiki/index.md`、`wiki/briefs/`、`wiki/sources/`
- 涉及数字、精确定义、引用原话、作者真实立场、时间先后关系 → 必须读取 `raw/articles/`
- brief 与 source 不一致以 source 为准；source 与 raw 不一致以 raw 为准
- 跨 vault 补充结果权威性低于主 vault 结果
"""
        agents_path.write_text(agents_content, encoding="utf-8")
        created.append("AGENTS.md")

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
