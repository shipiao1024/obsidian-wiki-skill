"""Vault bootstrap, raw page writing, transcript, and asset handling."""

from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path

from pipeline.shared import (
    Article,
    FRONTMATTER,
    IMAGE,
    WIKI_DIRS,
    parse_frontmatter,
    transcript_fidelity,
    transcript_page_link,
    transcript_page_name,
)
from pipeline.structure_fix import fix_structure


def build_agents_md() -> str:
    return textwrap.dedent(
        """\
        # LLM Wiki Operating Rules

        这是一个基于 Obsidian 的本地 LLM Wiki。目标不是临时问答，而是把来源材料持续编译成可积累的知识库。

        ## Layer Rules

        - `raw/` 只放原始来源。只能新增，不要改写原文内容。
        - `wiki/` 由 AI 维护。摘要、概念、实体、综合分析、查询结果都写在这里。
        - `wiki/briefs/` 是有损压缩层，只用于快速浏览、导航和低成本检索。
        - `wiki/sources/` 是保真提炼层，比 `briefs/` 更可靠，但仍然不是最终证据。
        - 最终证据始终在 `raw/`。高风险结论、细节争议、引用核对时必须回看原文。
        - 每次查询优先读取 `wiki/index.md`，必要时再读取相关页面。
        - 每次 ingest 都要更新 `wiki/index.md` 和 `wiki/log.md`。

        ## Ingest Rules

        - 每个原始来源至少生成两个页面：`wiki/sources/` 保真页、`wiki/briefs/` 快读页。
        - 如果来源引入了稳定概念或重要实体，新增或更新 `wiki/concepts/`、`wiki/entities/`。
        - 如果来源改变了某个主题域的理解，更新对应 `wiki/domains/` 或 `wiki/syntheses/`。

        ## Writing Rules

        - 结论必须可追溯到原始来源。
        - 不要把未经证实的推断写成事实。
        - 优先使用 wikilinks 连接已有页面。
        - `wiki/log.md` 采用追加写入，不回写历史记录。

        ## Query Rules

        - 粗粒度问题先读 `wiki/index.md`、`wiki/briefs/`、`wiki/sources/`。
        - 如果问题涉及数字、精确定义、引用原话、作者真实立场、时间先后关系，必须读取 `raw/articles/`。
        - 如果 `brief` 与 `source` 不一致，以 `source` 为准；如果 `source` 与 `raw` 不一致，以 `raw` 为准。
        """
    )


def ensure_bootstrap(vault: Path) -> None:
    for rel in WIKI_DIRS:
        (vault / rel).mkdir(parents=True, exist_ok=True)

    agents = vault / "AGENTS.md"
    if not agents.exists():
        agents.write_text(build_agents_md(), encoding="utf-8")

    index_path = vault / "wiki" / "index.md"
    if not index_path.exists():
        index_path.write_text(
            '---\n'
            'title: "Wiki Index"\n'
            'type: "system-index"\n'
            'graph_role: "system"\n'
            'graph_include: "false"\n'
            'lifecycle: "canonical"\n'
            '---\n\n'
            "# Wiki Index\n\n> 先读本页，再决定要打开哪些具体页面。\n",
            encoding="utf-8",
        )

    log_path = vault / "wiki" / "log.md"
    if not log_path.exists():
        log_path.write_text(
            '---\n'
            'title: "Wiki Log"\n'
            'type: "system-log"\n'
            'graph_role: "system"\n'
            'graph_include: "false"\n'
            'lifecycle: "canonical"\n'
            '---\n\n'
            "# Wiki Log\n\n",
            encoding="utf-8",
        )

    hot_path = vault / "wiki" / "hot.md"
    if not hot_path.exists():
        hot_path.write_text(
            '---\n'
            'title: "Hot Cache"\n'
            'type: "system-hot"\n'
            'graph_role: "system"\n'
            'graph_include: "false"\n'
            'lifecycle: "canonical"\n'
            '---\n\n'
            "# Hot Cache\n\n> Recent context (~500 words). Updated on ingest/query/session-end.\n\n"
            "## Recent Ingests\n\n- （空）\n\n"
            "## Recent Queries\n\n- （空）\n\n"
            "## Active Stances\n\n- （空）\n\n"
            "## Open Questions\n\n- （空）\n",
            encoding="utf-8",
        )


def rewrite_image_links(text: str, article_assets_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        url = match.group(2)
        filename = Path(url).name
        if filename:
            embed = f"![[raw/assets/{article_assets_dir.name}/{filename}]]"
            return embed
        return match.group(0)

    rewritten = IMAGE.sub(replace, text)
    rewritten = re.sub(r"(!\[\[[^\]]+\]\])([^\s\n])", r"\1\n\2", rewritten)
    return rewritten


def copy_directory_contents(src_dir: Path, dst_dir: Path, force: bool) -> None:
    if not src_dir.exists():
        return
    if dst_dir.exists() and force:
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)


def copy_assets(src_images: Path, dst_assets: Path, force: bool) -> None:
    copy_directory_contents(src_images, dst_assets, force)


def build_transcript_page(article: Article, slug: str) -> str:
    lines = [
        "---",
        f'title: "{article.title}"',
        'type: "raw-transcript"',
        f'transcript_stage: "{article.transcript_stage or "transcript"}"',
        f'transcript_source: "{article.transcript_source or "unknown"}"',
        f'fidelity: "{transcript_fidelity(article)}"',
        'graph_role: "document"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        f'slug: "{slug}"',
    ]
    if article.author:
        lines.append(f'author: "{article.author}"')
    if article.date:
        lines.append(f'date: "{article.date}"')
    if article.source:
        lines.append(f'source: "{article.source}"')
    if article.transcript_language:
        lines.append(f'language: "{article.transcript_language}"')
    if article.quality:
        lines.append(f'quality: "{article.quality}"')
    if article.transcript_confidence_hint:
        lines.append(f'confidence_hint: "{article.transcript_confidence_hint}"')
    if article.transcript_audio_asset:
        lines.append(f'audio_asset: "raw/assets/{slug}/{article.transcript_audio_asset}"')
    if article.transcript_subtitle_asset:
        lines.append(f'subtitle_asset: "raw/assets/{slug}/{article.transcript_subtitle_asset}"')
    lines.extend(["---", "", article.transcript_body.strip(), ""])
    content, _ = fix_structure("\n".join(lines))
    return content


def build_raw_page(article: Article, slug: str, article_assets_dir: Path) -> str:
    original = article.md_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(original)
    lines = [
        "---",
        f'title: "{article.title}"',
        'type: "raw-source"',
        'fidelity: "ground-truth"',
        'graph_role: "document"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        f'slug: "{slug}"',
    ]
    if article.author:
        lines.append(f'author: "{article.author}"')
    if article.date:
        lines.append(f'date: "{article.date}"')
    if article.source:
        lines.append(f'source: "{article.source}"')
    if article.transcript_source:
        lines.append(f'transcript_source: "{article.transcript_source}"')
    if article.transcript_stage:
        lines.append(f'transcript_stage: "{article.transcript_stage}"')
    if article.transcript_confidence_hint:
        lines.append(f'transcript_confidence_hint: "{article.transcript_confidence_hint}"')
    lines.extend(["---", ""])
    if article.transcript_body:
        lines.extend(
            [
                "## 来源说明",
                "",
                f"- 文稿来源：{article.transcript_source or 'unknown'}",
                f"- 原始文稿：{transcript_page_link(article, slug)}",
            ]
        )
        if article.transcript_subtitle_asset:
            lines.append(f"- 字幕资产：`raw/assets/{slug}/{article.transcript_subtitle_asset}`")
        if article.transcript_audio_asset:
            lines.append(f"- 音频资产：`raw/assets/{slug}/{article.transcript_audio_asset}`")
        lines.extend(
            [
                "",
                "## 内容摘要",
                "",
                "- 该页作为来源总页，完整视频文稿单独存放在 transcript 页中。",
                f"- transcript stage: `{article.transcript_stage or 'transcript'}`",
                f"- confidence hint: `{article.transcript_confidence_hint or 'unknown'}`",
                "",
            ]
        )
    else:
        lines.append(rewrite_image_links(body.strip(), article_assets_dir))
        lines.append("")
    content, _ = fix_structure("\n".join(lines))
    return content