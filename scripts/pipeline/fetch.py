"""URL/file/text input collection, adapter invocation, and collection import orchestration."""

from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from pipeline.shared import (
    Article,
    normalize_collection_url,
    parse_frontmatter,
    sanitize_filename,
    slugify_article,
    video_id_from_url,
)


def collect_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls)
    if args.file:
        for line in args.file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return [u for u in urls if u.startswith("http://") or u.startswith("https://")]


def collect_local_files(args: argparse.Namespace) -> list[Path]:
    values = list(args.urls)
    if args.file:
        for line in args.file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                values.append(line)
    paths: list[Path] = []
    for value in values:
        if value.startswith("http://") or value.startswith("https://"):
            continue
        path = Path(value).expanduser()
        if path.exists() and path.is_file():
            paths.append(path.resolve())
    return paths


def default_tool_dir() -> Path | None:
    env_val = os.environ.get("KWIKI_WECHAT_TOOL_DIR") or os.environ.get("WECHAT_ARTICLE_FOR_AI_DIR")
    if env_val:
        candidate = Path(env_val)
        if candidate.exists():
            return candidate
    cwd_candidate = Path.cwd() / ".tools" / "wechat-article-for-ai"
    if cwd_candidate.exists():
        return cwd_candidate
    skill_candidate = Path(__file__).resolve().parents[2] / ".tools" / "wechat-article-for-ai"
    if skill_candidate.exists():
        return skill_candidate
    return None


def create_runtime_input_dir(runtime_root: Path) -> tuple[Path, callable]:
    runtime_root.mkdir(parents=True, exist_ok=True)
    input_dir = runtime_root / f"wechat-archive-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    input_dir.mkdir(parents=True, exist_ok=False)

    def cleanup() -> None:
        shutil.rmtree(input_dir, ignore_errors=True)

    return input_dir, cleanup


def run_fetch(args: argparse.Namespace, urls: list[str], output_dir: Path) -> None:
    if not urls:
        raise SystemExit("No valid mp.weixin.qq.com URLs provided.")

    tool_dir = (args.tool_dir or default_tool_dir())
    if tool_dir:
        tool_dir = tool_dir.resolve()
    if not tool_dir or not (tool_dir / "main.py").exists():
        raise SystemExit(
            "wechat-article-for-ai not found. Set --tool-dir, KWIKI_WECHAT_TOOL_DIR, or install to .tools/wechat-article-for-ai/."
        )

    cmd = [args.python, str(tool_dir / "main.py"), *urls, "-o", str(output_dir), "--force"]
    if args.no_images:
        cmd.append("--no-images")
    if args.no_headless:
        cmd.append("--no-headless")
    if args.verbose:
        cmd.append("--verbose")

    env = os.environ.copy()
    if args.deps_dir:
        env["PYTHONPATH"] = os.pathsep.join(
            [str(args.deps_dir), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)

    subprocess.run(cmd, cwd=tool_dir, env=env, check=True)


def load_articles(input_dir: Path) -> list[Article]:
    articles: list[Article] = []
    for md_path in sorted(input_dir.glob("*/*.md")):
        if md_path.parent.name == "debug":
            continue
        text = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        title = meta.get("title") or md_path.stem
        articles.append(
            Article(
                title=title,
                author=meta.get("author", ""),
                date=meta.get("date", ""),
                source=meta.get("source", ""),
                body=body.strip(),
                src_dir=md_path.parent,
                md_path=md_path,
            )
        )
    return articles


def load_article_from_supported_url(
    args: argparse.Namespace,
    url: str,
    source_id: str,
    input_dir: Path,
    staged_root: Path,
    index: int,
) -> Article:
    from adapter_result_to_article import adapter_result_to_article
    from source_adapters import run_adapter_for_source

    work_dir = input_dir / f"adapter-{index + 1}"
    adapter_result = run_adapter_for_source(
        source_id=source_id,
        input_value=url,
        work_dir=work_dir,
        tool_dir=args.tool_dir,
        deps_dir=args.deps_dir,
        options={
            "no_images": args.no_images,
            "headless": not args.no_headless,
            "verbose": args.verbose,
        },
    )
    if adapter_result.get("status") != "ok":
        raise SystemExit(
            f"Adapter failed for {url}: {adapter_result.get('status')} - {adapter_result.get('reason', '')}"
        )
    return adapter_result_to_article(result=adapter_result, staging_root=staged_root)


def load_articles_from_video_collection(
    args: argparse.Namespace,
    source_id: str,
    collection_url: str,
    input_dir: Path,
    staged_root: Path,
    index: int,
    vault: Path | None = None,
    collection_contexts: list[dict[str, object]] | None = None,
) -> list[Article]:
    from adapter_result_to_article import adapter_result_to_article
    from import_jobs import completed_video_ids, completed_video_items, ensure_import_job, load_import_job
    from source_adapters import expand_video_collection_urls, run_adapter_for_source
    from source_registry import match_source_from_url, pre_normalize_url

    normalized_collection_url = normalize_collection_url(source_id, collection_url)
    expanded_urls = expand_video_collection_urls(
        source_id=source_id,
        input_value=normalized_collection_url,
        work_dir=input_dir / f"playlist-{index + 1}",
    )

    completed_ids: set[str] = set()
    existing_completed_items: list[dict[str, str]] = []
    max_items = 20
    job_path: Path | None = None
    cooldown_until = ""
    if vault is not None:
        job_path = ensure_import_job(vault, source_id, normalized_collection_url, max_items_per_run=20)
        job = load_import_job(job_path)
        completed_ids = completed_video_ids(job)
        existing_completed_items = completed_video_items(job)
        cooldown_until = str(job.get("meta", {}).get("cooldown_until", "") or "")
        try:
            max_items = int(str(job.get("meta", {}).get("max_items_per_run", "20")) or "20")
        except ValueError:
            max_items = 20
        max_items = max(1, min(max_items, 20))
    collection_limit = getattr(args, "collection_limit", None)
    if collection_limit is not None:
        try:
            max_items = min(max_items, max(1, min(int(collection_limit), 20)))
        except (TypeError, ValueError):
            pass

    if cooldown_until:
        try:
            cooldown_dt = datetime.strptime(cooldown_until, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            cooldown_dt = None
        if cooldown_dt is not None and cooldown_dt > datetime.now():
            if collection_contexts is not None and job_path is not None:
                collection_contexts.append(
                    {
                        "source_kind": source_id,
                        "source_url": normalized_collection_url,
                        "job_path": job_path,
                        "discovered_items": [],
                        "existing_completed_items": existing_completed_items,
                        "planned_items": [],
                        "failed_items": [],
                        "forced_status": "paused",
                        "last_failure_reason": f"冷却中，直到 {cooldown_until}",
                        "cooldown_until": cooldown_until,
                    }
                )
            return []

    discovered_items: list[dict[str, str]] = []
    deduped_urls: list[str] = []
    seen_ids: set[str] = set()
    for expanded_url in expanded_urls:
        video_id = video_id_from_url(expanded_url)
        if video_id in seen_ids:
            continue
        seen_ids.add(video_id)
        discovered_items.append({"video_id": video_id, "video_url": expanded_url})
        if video_id in completed_ids:
            continue
        deduped_urls.append(expanded_url)
        if len(deduped_urls) >= max_items:
            break

    planned_items = [
        {"video_id": video_id_from_url(expanded_url), "video_url": expanded_url}
        for expanded_url in deduped_urls
    ]

    articles: list[Article] = []
    failed_items: list[dict[str, str]] = []
    forced_status = ""
    last_failure_reason = ""
    cooldown_until = ""
    consecutive_failures = 0
    delay_seconds = max(float(getattr(args, "collection_delay_seconds", 0.0) or 0.0), 0.0)
    failure_threshold = max(int(getattr(args, "collection_failure_threshold", 3) or 3), 1)
    backoff_seconds = max(float(getattr(args, "collection_backoff_seconds", 5.0) or 0.0), 0.0)
    jitter_seconds = max(float(getattr(args, "collection_jitter_seconds", 0.5) or 0.0), 0.0)
    cooldown_seconds = max(int(getattr(args, "collection_platform_cooldown_seconds", 1800) or 0), 0)
    for sub_index, expanded_url in enumerate(deduped_urls, start=1):
        expanded_source_id = match_source_from_url(expanded_url)
        if expanded_source_id not in {"video_url_youtube", "video_url_bilibili", "video_url_douyin"}:
            continue
        work_dir = input_dir / f"adapter-{index + 1}-{sub_index}"
        adapter_result = run_adapter_for_source(
            source_id=expanded_source_id,
            input_value=expanded_url,
            work_dir=work_dir,
            tool_dir=args.tool_dir,
            deps_dir=args.deps_dir,
            options={
                "no_images": args.no_images,
                "headless": not args.no_headless,
                "verbose": args.verbose,
            },
        )
        if adapter_result.get("status") != "ok":
            failure_reason = f"{adapter_result.get('status')} - {adapter_result.get('reason', '')}".strip()
            print(
                f"Video adapter failed for {expanded_url}: {failure_reason}",
                file=sys.stderr,
            )
            failed_items.append(
                {
                    "video_id": video_id_from_url(expanded_url),
                    "video_url": expanded_url,
                }
            )
            consecutive_failures += 1
            last_failure_reason = failure_reason
            if consecutive_failures >= failure_threshold:
                forced_status = "paused"
                last_failure_reason = f"连续失败达到阈值: {failure_reason}"
                if cooldown_seconds > 0:
                    cooldown_until = (datetime.now() + timedelta(seconds=cooldown_seconds)).strftime("%Y-%m-%d %H:%M:%S")
                break
            if sub_index < len(deduped_urls):
                jitter = random.uniform(0.0, jitter_seconds) if jitter_seconds > 0 else 0.0
                sleep_seconds = backoff_seconds + jitter
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
            continue
        article = adapter_result_to_article(result=adapter_result, staging_root=staged_root)
        article.collection_source_kind = source_id
        article.collection_source_url = normalized_collection_url
        article.collection_video_id = video_id_from_url(expanded_url)
        articles.append(article)
        consecutive_failures = 0
        if delay_seconds > 0 and sub_index < len(deduped_urls):
            time.sleep(delay_seconds)
    if collection_contexts is not None and job_path is not None:
        collection_contexts.append(
            {
                "source_kind": source_id,
                "source_url": normalized_collection_url,
                "job_path": job_path,
                "discovered_items": discovered_items,
                "existing_completed_items": existing_completed_items,
                "planned_items": planned_items,
                "failed_items": failed_items,
                "forced_status": forced_status,
                "last_failure_reason": last_failure_reason,
                "cooldown_until": cooldown_until,
            }
        )
    return articles


def update_collection_import_jobs(
    collection_contexts: list[dict[str, object]],
    collection_results: dict[tuple[str, str], list[dict[str, str]]],
) -> None:
    from import_jobs import update_import_job

    for context in collection_contexts:
        source_kind = str(context.get("source_kind", ""))
        source_url = str(context.get("source_url", ""))
        job_path = context.get("job_path")
        if not source_kind or not source_url or not isinstance(job_path, Path):
            continue

        discovered_items = list(context.get("discovered_items", []))
        existing_completed_items = list(context.get("existing_completed_items", []))
        planned_items = list(context.get("planned_items", []))
        failed_items = list(context.get("failed_items", []))
        forced_status = str(context.get("forced_status", ""))
        last_failure_reason = str(context.get("last_failure_reason", ""))
        cooldown_until = str(context.get("cooldown_until", ""))
        run_results = collection_results.get((source_kind, source_url), [])

        completed_by_id: dict[str, dict[str, str]] = {
            str(item.get("video_id", "")): {
                "video_id": str(item.get("video_id", "")),
                "source_slug": str(item.get("source_slug", "")),
            }
            for item in existing_completed_items
            if item.get("video_id") and item.get("source_slug")
        }
        processed_count = 0
        skipped_count = 0
        for item in run_results:
            status = str(item.get("status", ""))
            video_id = str(item.get("video_id", ""))
            source_slug = str(item.get("source_slug", ""))
            if status not in {"ingested", "skipped"} or not video_id or not source_slug:
                continue
            completed_by_id[video_id] = {"video_id": video_id, "source_slug": source_slug}
            if status == "ingested":
                processed_count += 1
            else:
                skipped_count += 1

        completed_items = list(completed_by_id.values())
        completed_ids = {item["video_id"] for item in completed_items}
        remaining_items = [
            item
            for item in discovered_items
            if str(item.get("video_id", "")) and str(item.get("video_id", "")) not in completed_ids
        ]
        failed_count = len(failed_items)
        update_import_job(
            path=job_path,
            source_kind=source_kind,
            source_url=source_url,
            discovered_items=discovered_items,
            completed_items=completed_items,
            remaining_items=remaining_items,
            status=forced_status or ("completed" if not remaining_items else "active"),
            processed_count=processed_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            last_failure_reason=last_failure_reason,
            cooldown_until=cooldown_until,
        )


def summarize_collection_statuses(collection_contexts: list[dict[str, object]]) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for context in collection_contexts:
        source_kind = str(context.get("source_kind", "") or "")
        source_url = str(context.get("source_url", "") or "")
        job_path = context.get("job_path")
        forced_status = str(context.get("forced_status", "") or "")
        last_failure_reason = str(context.get("last_failure_reason", "") or "")
        cooldown_until = str(context.get("cooldown_until", "") or "")
        discovered_items = list(context.get("discovered_items", []))
        existing_completed_items = list(context.get("existing_completed_items", []))

        completed_ids = {
            str(item.get("video_id", ""))
            for item in existing_completed_items
            if str(item.get("video_id", ""))
        }
        run_results = list(context.get("run_results", []))
        completed_ids.update(
            str(item.get("video_id", ""))
            for item in run_results
            if str(item.get("status", "")) in {"ingested", "skipped"} and str(item.get("video_id", ""))
        )
        remaining_items = [
            item
            for item in discovered_items
            if str(item.get("video_id", "")) and str(item.get("video_id", "")) not in completed_ids
        ]

        collection_status = forced_status or ("completed" if not remaining_items else "active")
        summaries.append(
            {
                "source_kind": source_kind,
                "source_url": source_url,
                "collection_status": collection_status,
                "collection_reason": last_failure_reason,
                "job_path": str(job_path) if isinstance(job_path, Path) else "",
                "cooldown_until": cooldown_until,
            }
        )
    return summaries


def load_articles_from_urls(
    args: argparse.Namespace,
    urls: list[str],
    input_dir: Path,
    vault: Path | None = None,
    collection_contexts: list[dict[str, object]] | None = None,
) -> list[Article]:
    from source_registry import match_source_from_url, pre_normalize_url

    staged_root = input_dir / "staged"
    staged_root.mkdir(parents=True, exist_ok=True)
    articles: list[Article] = []
    fallback_urls: list[str] = []

    for index, url in enumerate(urls):
        url = pre_normalize_url(url)
        source_id = match_source_from_url(url)
        playlist_ids = {"video_playlist_youtube", "video_playlist_bilibili", "video_playlist_douyin", "video_collection_douyin"}
        if source_id in playlist_ids:
            try:
                articles.extend(
                    load_articles_from_video_collection(
                        args=args,
                        source_id=source_id,
                        collection_url=url,
                        input_dir=input_dir,
                        staged_root=staged_root,
                        index=index,
                        vault=vault,
                        collection_contexts=collection_contexts,
                    )
                )
            except RuntimeError as exc:
                # yt-dlp playlist expand failed (e.g. Douyin blocks --flat-playlist);
                # fallback to web adapter to capture page metadata as a single article
                from adapter_result_to_article import adapter_result_to_article as _ara
                from source_adapters import run_adapter_for_source
                adapter_result = run_adapter_for_source(
                    source_id="web_url",
                    input_value=url,
                    work_dir=input_dir / f"adapter-{index + 1}-fallback",
                    options=None,
                )
                if adapter_result and adapter_result.get("status") == "ok":
                    article = _ara(result=adapter_result, staging_root=staged_root)
                    articles.append(article)
                else:
                    reason = adapter_result.get("reason", str(exc)) if adapter_result else str(exc)
                    print(f"WARNING: Collection expand and web fallback both failed for {url}: {reason}")
            continue

        if source_id not in {"wechat_url", "web_url", "video_url_youtube", "video_url_bilibili", "video_url_douyin"}:
            fallback_urls.append(url)
            continue
        articles.append(
            load_article_from_supported_url(
                args=args,
                url=url,
                source_id=source_id,
                input_dir=input_dir,
                staged_root=staged_root,
                index=index,
            )
        )

    if fallback_urls:
        run_fetch(args, fallback_urls, input_dir)
        articles.extend(load_articles(input_dir))

    return articles


def load_articles_from_inputs(
    args: argparse.Namespace,
    input_dir: Path,
    vault: Path | None = None,
    collection_contexts: list[dict[str, object]] | None = None,
) -> list[Article]:
    from adapter_result_to_article import adapter_result_to_article
    from source_adapters import run_adapter_for_source
    from source_registry import match_source_from_file, match_source_from_url, pre_normalize_url

    staged_root = input_dir / "staged"
    staged_root.mkdir(parents=True, exist_ok=True)
    articles: list[Article] = []
    fallback_urls: list[str] = []

    for index, url in enumerate(collect_urls(args)):
        url = pre_normalize_url(url)
        source_id = match_source_from_url(url)
        playlist_ids = {"video_playlist_youtube", "video_playlist_bilibili", "video_playlist_douyin", "video_collection_douyin"}
        if source_id in playlist_ids:
            try:
                articles.extend(
                    load_articles_from_video_collection(
                        args=args,
                        source_id=source_id,
                        collection_url=url,
                        input_dir=input_dir,
                        staged_root=staged_root,
                        index=index,
                        vault=vault,
                        collection_contexts=collection_contexts,
                    )
                )
            except RuntimeError as exc:
                from adapter_result_to_article import adapter_result_to_article as _ara
                from source_adapters import run_adapter_for_source
                adapter_result = run_adapter_for_source(
                    source_id="web_url",
                    input_value=url,
                    work_dir=input_dir / f"adapter-{index + 1}-fallback",
                    options=None,
                )
                if adapter_result and adapter_result.get("status") == "ok":
                    article = _ara(result=adapter_result, staging_root=staged_root)
                    articles.append(article)
                else:
                    reason = adapter_result.get("reason", str(exc)) if adapter_result else str(exc)
                    print(f"WARNING: Collection expand and web fallback both failed for {url}: {reason}")
            continue
        if source_id not in {"wechat_url", "web_url", "video_url_youtube", "video_url_bilibili", "video_url_douyin"}:
            fallback_urls.append(url)
            continue
        articles.append(
            load_article_from_supported_url(
                args=args,
                url=url,
                source_id=source_id,
                input_dir=input_dir,
                staged_root=staged_root,
                index=index,
            )
        )

    for index, path in enumerate(collect_local_files(args), start=len(articles) + 1):
        source_id = match_source_from_file(path)
        if not source_id:
            raise SystemExit(f"Unsupported local file input: {path}")
        adapter_result = run_adapter_for_source(
            source_id=source_id,
            input_value=str(path),
            work_dir=input_dir / f"adapter-local-{index}",
            tool_dir=args.tool_dir,
            deps_dir=args.deps_dir,
            options={},
        )
        if adapter_result.get("status") != "ok":
            raise SystemExit(
                f"Adapter failed for {path}: {adapter_result.get('status')} - {adapter_result.get('reason', '')}"
            )
        articles.append(adapter_result_to_article(result=adapter_result, staging_root=staged_root))

    for index, text in enumerate(getattr(args, "text", []) or [], start=len(articles) + 1):
        adapter_result = run_adapter_for_source(
            source_id="plain_text",
            input_value=text,
            work_dir=input_dir / f"adapter-text-{index}",
            tool_dir=args.tool_dir,
            deps_dir=args.deps_dir,
            options={},
        )
        if adapter_result.get("status") != "ok":
            raise SystemExit(
                f"Adapter failed for plain text input: {adapter_result.get('status')} - {adapter_result.get('reason', '')}"
            )
        articles.append(adapter_result_to_article(result=adapter_result, staging_root=staged_root))

    if fallback_urls:
        run_fetch(args, fallback_urls, input_dir)
        articles.extend(load_articles(input_dir))

    return articles