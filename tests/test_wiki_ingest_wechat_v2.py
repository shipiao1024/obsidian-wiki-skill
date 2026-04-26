from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import wiki_ingest_wechat  # noqa: E402
import wiki_ingest as _wi  # noqa: E402


class WikiIngestV2Tests(unittest.TestCase):
    def test_parse_args_accepts_collection_protection_flags(self) -> None:
        argv = [
            "wiki_ingest_wechat.py",
            "--collection-backoff-seconds",
            "5",
            "--collection-jitter-seconds",
            "0.5",
            "--collection-platform-cooldown-seconds",
            "1800",
            "https://www.bilibili.com/list/695894135?sid=3074280",
        ]
        with mock.patch.object(sys, "argv", argv):
            args = wiki_ingest_wechat.parse_args()

        self.assertEqual(args.collection_backoff_seconds, 5.0)
        self.assertEqual(args.collection_jitter_seconds, 0.5)
        self.assertEqual(args.collection_platform_cooldown_seconds, 1800)

    def test_video_id_from_url_preserves_bilibili_page_parameter(self) -> None:
        self.assertEqual(
            wiki_ingest_wechat.video_id_from_url("https://www.bilibili.com/video/BV1xx?p=2"),
            "BV1xx:p2",
        )

    def test_normalize_collection_url_canonicalizes_youtube_playlist(self) -> None:
        self.assertEqual(
            wiki_ingest_wechat.normalize_collection_url(
                "video_playlist_youtube",
                "https://www.youtube.com/playlist?foo=bar&list=PL123",
            ),
            "https://www.youtube.com/playlist?list=PL123",
        )

    def test_create_runtime_input_dir_allows_child_directories(self) -> None:
        runtime_root = ROOT / ".tmp-tests" / "runtime-root"
        runtime_root.mkdir(parents=True, exist_ok=True)

        input_dir, cleanup = wiki_ingest_wechat.create_runtime_input_dir(runtime_root)
        self.addCleanup(cleanup)

        staged_root = input_dir / "staged"
        staged_root.mkdir(parents=True, exist_ok=True)

        self.assertTrue(input_dir.exists())
        self.assertTrue(staged_root.exists())

    def test_collect_urls_accepts_supported_url_kinds(self) -> None:
        args = type(
            "Args",
            (),
            {
                "urls": [
                    "https://mp.weixin.qq.com/s/example",
                    "https://example.com/post",
                    "https://www.youtube.com/watch?v=abc",
                    "https://www.youtube.com/playlist?list=PL123",
                    "not-a-url",
                ],
                "file": None,
            },
        )()

        urls = wiki_ingest_wechat.collect_urls(args)
        self.assertEqual(
            urls,
            [
                "https://mp.weixin.qq.com/s/example",
                "https://example.com/post",
                "https://www.youtube.com/watch?v=abc",
                "https://www.youtube.com/playlist?list=PL123",
            ],
        )

    def test_load_articles_from_urls_prefers_adapter_pipeline_for_wechat(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-adapter-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
            },
        )()

        with mock.patch("source_adapters.run_adapter_for_source", return_value={
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "wechat_url",
            "adapter_name": "wechat-article-to-markdown",
            "metadata": {
                "title": "示例文章",
                "author": "作者",
                "date": "2026-04-24",
                "source_url": "https://mp.weixin.qq.com/s/example",
                "source_id": "wechat_url",
                "source_kind": "wechat",
            },
            "markdown_body": "正文",
            "plain_text_body": "正文",
            "assets": [],
            "extra": {},
        }) as adapter_mock, mock.patch.object(wiki_ingest_wechat, "run_fetch") as run_fetch_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://mp.weixin.qq.com/s/example"],
                input_dir,
            )

        adapter_mock.assert_called_once()
        run_fetch_mock.assert_not_called()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "示例文章")

    def test_load_articles_from_urls_prefers_adapter_pipeline_for_web(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-web-adapter-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
            },
        )()

        with mock.patch("source_adapters.run_adapter_for_source", return_value={
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "web_url",
            "adapter_name": "baoyu-url-to-markdown",
            "metadata": {
                "title": "网页文章",
                "author": "",
                "date": "",
                "source_url": "https://example.com/post",
                "source_id": "web_url",
                "source_kind": "web",
            },
            "markdown_body": "正文",
            "plain_text_body": "正文",
            "assets": [],
            "extra": {},
        }) as adapter_mock, mock.patch.object(wiki_ingest_wechat, "run_fetch") as run_fetch_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://example.com/post"],
                input_dir,
            )

        adapter_mock.assert_called_once()
        run_fetch_mock.assert_not_called()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "网页文章")

    def test_load_articles_from_urls_prefers_adapter_pipeline_for_video(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-video-adapter-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
            },
        )()

        with mock.patch("source_adapters.run_adapter_for_source", return_value={
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=abc",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }) as adapter_mock, mock.patch.object(wiki_ingest_wechat, "run_fetch") as run_fetch_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/watch?v=abc"],
                input_dir,
            )

        adapter_mock.assert_called_once()
        run_fetch_mock.assert_not_called()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "视频文稿")

    def test_load_articles_from_urls_expands_video_playlist(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-adapter-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
            },
        )()

        adapter_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=abc",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/watch?v=def",
        ]) as expand_mock, mock.patch("source_adapters.run_adapter_for_source", return_value=adapter_result) as adapter_mock, mock.patch.object(
            wiki_ingest_wechat, "run_fetch"
        ) as run_fetch_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
            )

        expand_mock.assert_called_once()
        self.assertEqual(adapter_mock.call_count, 2)
        run_fetch_mock.assert_not_called()
        self.assertEqual(len(articles), 2)

    def test_load_articles_from_urls_limits_video_collection_to_20_items(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-limit-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-limit-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
            },
        )()

        expanded = [f"https://www.youtube.com/watch?v={index}" for index in range(120)]
        adapter_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=abc",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=expanded), mock.patch(
            "source_adapters.run_adapter_for_source", return_value=adapter_result
        ) as adapter_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
            )

        self.assertEqual(adapter_mock.call_count, 20)
        self.assertEqual(len(articles), 20)

    def test_load_articles_from_urls_honors_collection_limit_argument(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-arg-limit-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-arg-limit-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
                "collection_limit": 5,
            },
        )()

        expanded = [f"https://www.youtube.com/watch?v={index}" for index in range(20)]
        adapter_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频标题",
                "author": "频道",
                "date": "2026-04-24",
                "source_url": "https://www.youtube.com/watch?v=0",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "视频正文",
            "plain_text_body": "视频正文",
            "assets": [],
            "extra": {},
        }

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=expanded), mock.patch(
            "source_adapters.run_adapter_for_source", return_value=adapter_result
        ) as adapter_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
            )

        self.assertEqual(adapter_mock.call_count, 5)
        self.assertEqual(len(articles), 5)

    def test_load_articles_from_urls_skips_completed_video_collection_items(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-resume-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-resume-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
            },
        )()

        job_path = vault / "wiki" / "import-jobs" / "video-playlist-youtube-test.md"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(
            """---
title: "job"
type: "import-job"
source_kind: "video_playlist_youtube"
source_url: "https://www.youtube.com/playlist?list=PL123"
status: "active"
max_items_per_run: "100"
discovered_count: "2"
completed_count: "1"
remaining_count: "1"
last_run_at: ""
graph_role: "working"
graph_include: "false"
lifecycle: "working"
---

# Import Job

## 已完成视频

- `abc` | [[sources/video-abc]]

## 待处理视频

- `def` | https://www.youtube.com/watch?v=def

## 最近一次结果

- 尚未运行。
""",
            encoding="utf-8",
        )

        adapter_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=def",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/watch?v=def",
        ]), mock.patch("import_jobs.ensure_import_job", return_value=job_path), mock.patch(
            "source_adapters.run_adapter_for_source", return_value=adapter_result
        ) as adapter_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
            )

        adapter_mock.assert_called_once()
        self.assertEqual(len(articles), 1)

    def test_load_articles_from_urls_continues_when_one_video_collection_item_fails(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-continue-on-fail"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-continue-on-fail-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
            },
        )()

        ok_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=def",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }
        failed_result = {
            "status": "empty_result",
            "reason": "Video adapter produced no subtitle/transcript files.",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "assets": [],
            "extra": {},
        }
        collection_contexts: list[dict[str, object]] = []

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/watch?v=def",
        ]), mock.patch("source_adapters.run_adapter_for_source", side_effect=[failed_result, ok_result]), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr_buffer:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
                collection_contexts=collection_contexts,
            )

        self.assertEqual(len(articles), 1)
        self.assertIn("Video adapter failed", stderr_buffer.getvalue())
        self.assertEqual(len(collection_contexts), 1)
        planned_items = collection_contexts[0]["planned_items"]
        self.assertEqual(len(planned_items), 2)
        self.assertEqual(planned_items[0]["video_id"], "abc")
        self.assertEqual(planned_items[1]["video_id"], "def")

    def test_load_articles_from_urls_sleeps_between_video_collection_items(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-delay"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-delay-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
                "collection_delay_seconds": 0.25,
            },
        )()

        adapter_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=abc",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/watch?v=def",
            "https://www.youtube.com/watch?v=ghi",
        ]), mock.patch("source_adapters.run_adapter_for_source", return_value=adapter_result), mock.patch.object(
            wiki_ingest_wechat.time, "sleep"
        ) as sleep_mock:
            wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
            )

        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_any_call(0.25)

    def test_load_articles_from_urls_pauses_after_consecutive_video_collection_failures(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-pause-on-fail"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-pause-on-fail-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
                "collection_failure_threshold": 2,
                "collection_backoff_seconds": 0.0,
                "collection_jitter_seconds": 0.0,
            },
        )()

        failed_result = {
            "status": "network_failed",
            "reason": "socket blocked",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "assets": [],
            "extra": {},
        }
        collection_contexts: list[dict[str, object]] = []

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/watch?v=def",
            "https://www.youtube.com/watch?v=ghi",
        ]), mock.patch("source_adapters.run_adapter_for_source", return_value=failed_result) as adapter_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
                collection_contexts=collection_contexts,
            )

        self.assertEqual(articles, [])
        self.assertEqual(adapter_mock.call_count, 2)
        self.assertEqual(len(collection_contexts), 1)
        self.assertEqual(collection_contexts[0]["forced_status"], "paused")
        self.assertIn("socket blocked", collection_contexts[0]["last_failure_reason"])

    def test_load_articles_from_urls_uses_backoff_and_jitter_on_video_collection_failures(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-backoff"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-backoff-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
                "collection_failure_threshold": 3,
                "collection_backoff_seconds": 2.0,
                "collection_jitter_seconds": 0.5,
            },
        )()

        failed_result = {
            "status": "network_failed",
            "reason": "socket blocked",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "assets": [],
            "extra": {},
        }

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/watch?v=def",
        ]), mock.patch("source_adapters.run_adapter_for_source", return_value=failed_result), mock.patch.object(
            wiki_ingest_wechat.random, "uniform", return_value=0.25
        ) as uniform_mock, mock.patch.object(
            wiki_ingest_wechat.time, "sleep"
        ) as sleep_mock:
            wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
            )

        uniform_mock.assert_called()
        sleep_mock.assert_any_call(2.25)

    def test_load_articles_from_urls_skips_paused_video_collection_during_cooldown(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-cooldown"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-cooldown-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
            },
        )()

        job_path = vault / "wiki" / "import-jobs" / "video-playlist-youtube-cooldown.md"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(
            """---
title: "job"
type: "import-job"
source_kind: "video_playlist_youtube"
source_url: "https://www.youtube.com/playlist?list=PL123"
status: "paused"
max_items_per_run: "20"
discovered_count: "2"
completed_count: "0"
remaining_count: "2"
last_run_at: ""
last_failure_reason: "socket blocked"
cooldown_until: "2999-01-01 00:00:00"
graph_role: "working"
graph_include: "false"
lifecycle: "working"
---

# Import Job

## 已完成视频

- （空）

## 待处理视频

- `abc` | https://www.youtube.com/watch?v=abc
- `def` | https://www.youtube.com/watch?v=def

## 最近一次结果

- 尚未运行。

## 最近失败

- socket blocked
""",
            encoding="utf-8",
        )

        collection_contexts: list[dict[str, object]] = []
        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/watch?v=def",
        ]), mock.patch("import_jobs.ensure_import_job", return_value=job_path), mock.patch(
            "source_adapters.run_adapter_for_source"
        ) as adapter_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
                collection_contexts=collection_contexts,
            )

        self.assertEqual(articles, [])
        adapter_mock.assert_not_called()
        self.assertEqual(collection_contexts[0]["forced_status"], "paused")
        self.assertIn("冷却中", collection_contexts[0]["last_failure_reason"])

    def test_load_articles_from_video_collection_uses_normalized_collection_url_for_context(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-normalized-context"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-normalized-context-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
            },
        )()

        adapter_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=abc",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }
        collection_contexts: list[dict[str, object]] = []

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=[
            "https://www.youtube.com/watch?v=abc",
        ]), mock.patch("source_adapters.run_adapter_for_source", return_value=adapter_result):
            wiki_ingest_wechat.load_articles_from_video_collection(
                args,
                "video_playlist_youtube",
                "https://www.youtube.com/playlist?foo=bar&list=PL123",
                input_dir,
                input_dir / "staged",
                0,
                vault=vault,
                collection_contexts=collection_contexts,
            )

        self.assertEqual(len(collection_contexts), 1)
        self.assertEqual(
            collection_contexts[0]["source_url"],
            "https://www.youtube.com/playlist?list=PL123",
        )

    def test_load_articles_from_urls_clamps_job_limit_to_20(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "url-playlist-clamp-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        vault = ROOT / ".tmp-tests" / "url-playlist-clamp-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        args = type(
            "Args",
            (),
            {
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
                "force": False,
            },
        )()

        job_path = vault / "wiki" / "import-jobs" / "video-playlist-youtube-clamp.md"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(
            """---
title: "job"
type: "import-job"
source_kind: "video_playlist_youtube"
source_url: "https://www.youtube.com/playlist?list=PL123"
status: "active"
max_items_per_run: "250"
discovered_count: "0"
completed_count: "0"
remaining_count: "0"
last_run_at: ""
graph_role: "working"
graph_include: "false"
lifecycle: "working"
---

# Import Job

## 已完成视频

- （空）

## 待处理视频

- （空）

## 最近一次结果

- 尚未运行。
""",
            encoding="utf-8",
        )

        expanded = [f"https://www.youtube.com/watch?v={index}" for index in range(150)]
        adapter_result = {
            "status": "ok",
            "reason": "",
            "input_kind": "url",
            "source_id": "video_url_youtube",
            "adapter_name": "yt-dlp",
            "metadata": {
                "title": "视频文稿",
                "author": "",
                "date": "",
                "source_url": "https://www.youtube.com/watch?v=abc",
                "source_id": "video_url_youtube",
                "source_kind": "youtube",
            },
            "markdown_body": "字幕正文",
            "plain_text_body": "字幕正文",
            "assets": [],
            "extra": {},
        }

        with mock.patch("source_adapters.expand_video_collection_urls", return_value=expanded), mock.patch(
            "import_jobs.ensure_import_job", return_value=job_path
        ), mock.patch("source_adapters.run_adapter_for_source", return_value=adapter_result) as adapter_mock:
            articles = wiki_ingest_wechat.load_articles_from_urls(
                args,
                ["https://www.youtube.com/playlist?list=PL123"],
                input_dir,
                vault=vault,
            )

        self.assertEqual(adapter_mock.call_count, 20)
        self.assertEqual(len(articles), 20)

    def test_update_collection_import_jobs_marks_completed_and_remaining(self) -> None:
        vault = ROOT / ".tmp-tests" / "collection-job-update-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        job_path = vault / "wiki" / "import-jobs" / "video-playlist-youtube-update.md"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(
            """---
title: "job"
type: "import-job"
source_kind: "video_playlist_youtube"
source_url: "https://www.youtube.com/playlist?list=PL123"
status: "active"
max_items_per_run: "100"
discovered_count: "2"
completed_count: "1"
remaining_count: "1"
last_run_at: ""
graph_role: "working"
graph_include: "false"
lifecycle: "working"
---

# Import Job

## 已完成视频

- `abc` | [[sources/video-abc]]

## 待处理视频

- `def` | https://www.youtube.com/watch?v=def
- `ghi` | https://www.youtube.com/watch?v=ghi

## 最近一次结果

- 尚未运行。
""",
            encoding="utf-8",
        )

        context = {
            "source_kind": "video_playlist_youtube",
            "source_url": "https://www.youtube.com/playlist?list=PL123",
            "job_path": job_path,
            "discovered_items": [
                {"video_id": "abc", "video_url": "https://www.youtube.com/watch?v=abc"},
                {"video_id": "def", "video_url": "https://www.youtube.com/watch?v=def"},
                {"video_id": "ghi", "video_url": "https://www.youtube.com/watch?v=ghi"},
            ],
            "existing_completed_items": [
                {"video_id": "abc", "source_slug": "video-abc"},
            ],
            "planned_items": [
                {"video_id": "def", "video_url": "https://www.youtube.com/watch?v=def"},
                {"video_id": "ghi", "video_url": "https://www.youtube.com/watch?v=ghi"},
            ],
        }

        wiki_ingest_wechat.update_collection_import_jobs(
            [context],
            {
                ("video_playlist_youtube", "https://www.youtube.com/playlist?list=PL123"): [
                    {"video_id": "def", "source_slug": "video-def", "status": "ingested"},
                    {"video_id": "ghi", "source_slug": "video-ghi", "status": "skipped"},
                ]
            },
        )

        body = job_path.read_text(encoding="utf-8")
        self.assertIn("`abc` | [[sources/video-abc]]", body)
        self.assertIn("`def` | [[sources/video-def]]", body)
        self.assertIn("`ghi` | [[sources/video-ghi]]", body)
        self.assertIn('status: "completed"', body)

    def test_update_collection_import_jobs_persists_pause_and_failure_reason(self) -> None:
        vault = ROOT / ".tmp-tests" / "collection-job-paused-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        job_path = vault / "wiki" / "import-jobs" / "video-playlist-youtube-paused.md"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(
            """---
title: "job"
type: "import-job"
source_kind: "video_playlist_youtube"
source_url: "https://www.youtube.com/playlist?list=PL123"
status: "active"
max_items_per_run: "20"
discovered_count: "0"
completed_count: "0"
remaining_count: "0"
last_run_at: ""
graph_role: "working"
graph_include: "false"
lifecycle: "working"
---

# Import Job

## 已完成视频

- （空）

## 待处理视频

- （空）

## 最近一次结果

- 尚未运行。
""",
            encoding="utf-8",
        )

        context = {
            "source_kind": "video_playlist_youtube",
            "source_url": "https://www.youtube.com/playlist?list=PL123",
            "job_path": job_path,
            "discovered_items": [
                {"video_id": "abc", "video_url": "https://www.youtube.com/watch?v=abc"},
                {"video_id": "def", "video_url": "https://www.youtube.com/watch?v=def"},
            ],
            "existing_completed_items": [],
            "planned_items": [
                {"video_id": "abc", "video_url": "https://www.youtube.com/watch?v=abc"},
                {"video_id": "def", "video_url": "https://www.youtube.com/watch?v=def"},
            ],
            "failed_items": [
                {"video_id": "abc", "video_url": "https://www.youtube.com/watch?v=abc"},
                {"video_id": "def", "video_url": "https://www.youtube.com/watch?v=def"},
            ],
            "forced_status": "paused",
            "last_failure_reason": "连续失败达到阈值: socket blocked",
        }

        wiki_ingest_wechat.update_collection_import_jobs(
            [context],
            {},
        )

        body = job_path.read_text(encoding="utf-8")
        self.assertIn('status: "paused"', body)
        self.assertIn('last_failure_reason: "连续失败达到阈值: socket blocked"', body)
        self.assertIn("## 最近失败", body)
        self.assertIn("连续失败达到阈值: socket blocked", body)

    def test_main_allows_empty_collection_rerun(self) -> None:
        vault = ROOT / ".tmp-tests" / "main-empty-collection-vault"
        args = type(
            "Args",
            (),
            {
                "vault": vault,
                "input_dir": None,
                "work_dir": ROOT / ".tmp-tests" / "main-empty-collection-work",
                "force": False,
                "no_llm_compile": True,
            },
        )()
        buffer = io.StringIO()

        with mock.patch.object(wiki_ingest_wechat, "parse_args", return_value=args), mock.patch.object(
            wiki_ingest_wechat, "ensure_bootstrap"
        ), mock.patch.object(
            _wi._fetch,
            "load_articles_from_inputs",
            side_effect=lambda *a, **k: k["collection_contexts"].append({"source_kind": "video_playlist_youtube"}) or [],
        ), mock.patch.object(
            _wi._fetch, "update_collection_import_jobs"
        ) as update_jobs_mock, mock.patch.object(
            _wi._apply, "rebuild_index"
        ) as rebuild_mock, mock.patch.object(
            _wi._apply, "append_log"
        ) as append_log_mock, mock.patch(
            "sys.stdout", buffer
        ):
            rc = wiki_ingest_wechat.main()

        self.assertEqual(rc, 0)
        update_jobs_mock.assert_called_once()
        rebuild_mock.assert_not_called()
        append_log_mock.assert_not_called()
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["ingested"], [])
        self.assertEqual(
            payload["collections"],
            [
                {
                    "source_kind": "video_playlist_youtube",
                    "source_url": "",
                    "collection_status": "completed",
                    "collection_reason": "",
                    "job_path": "",
                    "cooldown_until": "",
                }
            ],
        )

    def test_main_outputs_collection_status_summary(self) -> None:
        vault = ROOT / ".tmp-tests" / "main-collection-summary-vault"
        job_path = vault / "wiki" / "import-jobs" / "video-playlist-youtube-example.md"
        args = type(
            "Args",
            (),
            {
                "vault": vault,
                "input_dir": None,
                "work_dir": ROOT / ".tmp-tests" / "main-collection-summary-work",
                "force": False,
                "no_llm_compile": True,
            },
        )()
        buffer = io.StringIO()

        with mock.patch.object(wiki_ingest_wechat, "parse_args", return_value=args), mock.patch.object(
            wiki_ingest_wechat, "ensure_bootstrap"
        ), mock.patch.object(
            _wi._fetch,
            "load_articles_from_inputs",
            side_effect=lambda *a, **k: k["collection_contexts"].append(
                {
                    "source_kind": "video_playlist_youtube",
                    "source_url": "https://www.youtube.com/playlist?list=PL123",
                    "job_path": job_path,
                    "forced_status": "paused",
                    "last_failure_reason": "连续失败达到阈值: socket blocked",
                    "cooldown_until": "2026-04-24 12:34:56",
                }
            )
            or [],
        ), mock.patch.object(
            _wi._fetch, "update_collection_import_jobs"
        ), mock.patch(
            "sys.stdout", buffer
        ):
            rc = wiki_ingest_wechat.main()

        self.assertEqual(rc, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["ingested"], [])
        self.assertEqual(
            payload["collections"],
            [
                {
                    "source_kind": "video_playlist_youtube",
                    "source_url": "https://www.youtube.com/playlist?list=PL123",
                    "collection_status": "paused",
                    "collection_reason": "连续失败达到阈值: socket blocked",
                    "job_path": str(job_path),
                    "cooldown_until": "2026-04-24 12:34:56",
                }
            ],
        )

    def test_load_articles_from_inputs_prefers_adapter_pipeline_for_local_file(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "input-local-adapter-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        local_path = input_dir / "sample.md"
        local_path.write_text("# 标题\n\n正文", encoding="utf-8")
        self.addCleanup(lambda: local_path.unlink(missing_ok=True))
        args = type(
            "Args",
            (),
            {
                "urls": [str(local_path)],
                "file": None,
                "text": [],
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
            },
        )()

        with mock.patch("source_adapters.run_adapter_for_source", return_value={
            "status": "ok",
            "reason": "",
            "input_kind": "file",
            "source_id": "local_file_md",
            "adapter_name": "direct_read",
            "metadata": {
                "title": "本地文件",
                "author": "",
                "date": "",
                "source_id": "local_file_md",
                "source_kind": "markdown",
            },
            "markdown_body": "正文",
            "plain_text_body": "正文",
            "assets": [],
            "extra": {},
        }) as adapter_mock, mock.patch.object(wiki_ingest_wechat, "run_fetch") as run_fetch_mock:
            articles = wiki_ingest_wechat.load_articles_from_inputs(args, input_dir)

        adapter_mock.assert_called_once()
        run_fetch_mock.assert_not_called()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "本地文件")

    def test_load_articles_from_inputs_prefers_adapter_pipeline_for_plain_text(self) -> None:
        input_dir = ROOT / ".tmp-tests" / "input-text-adapter-pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)
        args = type(
            "Args",
            (),
            {
                "urls": [],
                "file": None,
                "text": ["这是直接粘贴的正文"],
                "tool_dir": None,
                "deps_dir": None,
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "python": "python",
            },
        )()

        with mock.patch("source_adapters.run_adapter_for_source", return_value={
            "status": "ok",
            "reason": "",
            "input_kind": "text",
            "source_id": "plain_text",
            "adapter_name": "direct_ingest",
            "metadata": {
                "title": "这是直接粘贴的正文",
                "author": "",
                "date": "",
                "source_id": "plain_text",
                "source_kind": "plain_text",
            },
            "markdown_body": "这是直接粘贴的正文",
            "plain_text_body": "这是直接粘贴的正文",
            "assets": [],
            "extra": {},
        }) as adapter_mock, mock.patch.object(wiki_ingest_wechat, "run_fetch") as run_fetch_mock:
            articles = wiki_ingest_wechat.load_articles_from_inputs(args, input_dir)

        adapter_mock.assert_called_once()
        run_fetch_mock.assert_not_called()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "这是直接粘贴的正文")

    def test_article_output_exists_requires_raw_source_and_brief(self) -> None:
        vault = ROOT / ".tmp-tests" / "skip-check-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        slug = "2026-04-24--example"
        raw_path = vault / "raw" / "articles" / f"{slug}.md"
        source_path = vault / "wiki" / "sources" / f"{slug}.md"
        brief_path = vault / "wiki" / "briefs" / f"{slug}.md"
        raw_path.write_text("raw", encoding="utf-8")
        source_path.write_text("source", encoding="utf-8")
        self.addCleanup(lambda: raw_path.unlink(missing_ok=True))
        self.addCleanup(lambda: source_path.unlink(missing_ok=True))
        self.addCleanup(lambda: brief_path.unlink(missing_ok=True))

        self.assertFalse(wiki_ingest_wechat.article_output_exists(vault, slug))
        brief_path.write_text("brief", encoding="utf-8")
        self.assertTrue(wiki_ingest_wechat.article_output_exists(vault, slug))

    def test_ingest_article_skips_when_raw_source_and_brief_exist(self) -> None:
        vault = ROOT / ".tmp-tests" / "skip-ingest-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        slug = "2026-04-24--example"
        raw_path = vault / "raw" / "articles" / f"{slug}.md"
        source_path = vault / "wiki" / "sources" / f"{slug}.md"
        brief_path = vault / "wiki" / "briefs" / f"{slug}.md"
        raw_path.write_text("raw", encoding="utf-8")
        source_path.write_text("source", encoding="utf-8")
        brief_path.write_text("brief", encoding="utf-8")
        self.addCleanup(lambda: raw_path.unlink(missing_ok=True))
        self.addCleanup(lambda: source_path.unlink(missing_ok=True))
        self.addCleanup(lambda: brief_path.unlink(missing_ok=True))

        article_dir = vault / "source"
        article_dir.mkdir(parents=True, exist_ok=True)
        md_path = article_dir / "article.md"
        md_path.write_text("---\ntitle: \"示例\"\n---\n正文\n", encoding="utf-8")
        article = wiki_ingest_wechat.Article(
            title="example",
            author="作者",
            date="2026-04-24",
            source="https://mp.weixin.qq.com/s/example",
            body="正文",
            src_dir=article_dir,
            md_path=md_path,
        )

        with mock.patch.object(wiki_ingest_wechat, "copy_assets") as copy_assets_mock, mock.patch.object(
            wiki_ingest_wechat, "try_llm_compile"
        ) as try_llm_compile_mock:
            result = wiki_ingest_wechat.ingest_article(vault, article, force=False, no_llm_compile=False)

        copy_assets_mock.assert_not_called()
        try_llm_compile_mock.assert_not_called()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["compile_mode"], "skipped")
        self.assertEqual(result["skip_reason"], "raw/source/brief already exist")

    def test_run_fetch_resolves_relative_tool_dir_before_subprocess(self) -> None:
        tool_dir = ROOT / ".tmp-tests" / "tool-dir"
        tool_dir.mkdir(parents=True, exist_ok=True)
        main_path = tool_dir / "main.py"
        main_path.write_text("print('ok')\n", encoding="utf-8")
        self.addCleanup(lambda: main_path.unlink(missing_ok=True))

        args = type(
            "Args",
            (),
            {
                "tool_dir": Path(".tmp-tests") / "tool-dir",
                "python": "python",
                "no_images": False,
                "no_headless": False,
                "verbose": False,
                "deps_dir": None,
            },
        )()

        with mock.patch.object(wiki_ingest_wechat.subprocess, "run") as run_mock:
            wiki_ingest_wechat.run_fetch(args, ["https://mp.weixin.qq.com/s/example"], ROOT / ".tmp-tests" / "output")

        called_cmd = run_mock.call_args.args[0]
        called_cwd = run_mock.call_args.kwargs["cwd"]
        self.assertEqual(Path(called_cwd), tool_dir.resolve())
        self.assertEqual(Path(called_cmd[1]), main_path.resolve())

    def test_ingest_article_reports_compile_reason_when_llm_compile_falls_back(self) -> None:
        vault = ROOT / ".tmp-tests" / "ingest-reason-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        article_dir = vault / "source"
        article_dir.mkdir(parents=True, exist_ok=True)
        md_path = article_dir / "article.md"
        md_path.write_text("---\ntitle: \"示例\"\n---\n正文\n", encoding="utf-8")
        article = wiki_ingest_wechat.Article(
            title="示例文章",
            author="作者",
            date="2026-04-24",
            source="https://mp.weixin.qq.com/s/example",
            body="正文",
            src_dir=article_dir,
            md_path=md_path,
        )

        with mock.patch.object(
            _wi._apply,
            "try_llm_compile",
            return_value=(None, "LLM compile is not configured."),
        ) as compile_mock:
            result = wiki_ingest_wechat.ingest_article(vault, article, force=True, no_llm_compile=False)

        self.assertEqual(result["compile_mode"], "heuristic")
        self.assertEqual(result["compile_reason"], "LLM compile is not configured.")

    def test_ingest_article_preserves_article_quality_and_log_records_it(self) -> None:
        vault = ROOT / ".tmp-tests" / "ingest-quality-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        article_dir = vault / "source"
        article_dir.mkdir(parents=True, exist_ok=True)
        md_path = article_dir / "article.md"
        md_path.write_text("---\ntitle: \"示例\"\n---\n正文\n", encoding="utf-8")
        article = wiki_ingest_wechat.Article(
            title="质量样例",
            author="作者",
            date="2026-04-24",
            source="https://example.com/post",
            body="正文",
            src_dir=article_dir,
            md_path=md_path,
            quality="acceptable",
        )

        with mock.patch.object(
            wiki_ingest_wechat,
            "try_llm_compile",
            return_value=(None, "LLM compile disabled by test."),
        ):
            result = wiki_ingest_wechat.ingest_article(vault, article, force=True, no_llm_compile=False)

        self.assertEqual(result["quality"], "acceptable")
        source_text = (vault / "wiki" / "sources" / f'{result["slug"]}.md').read_text(encoding="utf-8")
        self.assertIn('quality: "acceptable"', source_text)

        wiki_ingest_wechat.append_log(vault, [(result["title"], result["slug"], result["quality"])])
        log_text = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
        self.assertIn("- quality: acceptable", log_text)

    def test_ingest_article_writes_video_transcript_page_and_raw_article_summary(self) -> None:
        vault = ROOT / ".tmp-tests" / "ingest-video-transcript-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        article_dir = vault / "source"
        article_dir.mkdir(parents=True, exist_ok=True)
        md_path = article_dir / "video.md"
        md_path.write_text("---\ntitle: \"视频标题\"\n---\n\n这是 ASR 文稿\n", encoding="utf-8")
        article = wiki_ingest_wechat.Article(
            title="视频标题",
            author="UP主",
            date="2026-04-24",
            source="https://www.bilibili.com/video/BV1xx",
            body="这是 ASR 文稿",
            src_dir=article_dir,
            md_path=md_path,
            quality="acceptable",
            transcript_stage="asr",
            transcript_source="asr",
            transcript_language="zh",
            transcript_confidence_hint="medium",
            transcript_body="这是 ASR 文稿",
        )

        with mock.patch.object(
            wiki_ingest_wechat,
            "try_llm_compile",
            return_value=(None, "LLM compile disabled by test."),
        ):
            result = wiki_ingest_wechat.ingest_article(vault, article, force=True, no_llm_compile=False)

        slug = result["slug"]
        transcript_path = vault / "raw" / "transcripts" / f"{slug}--asr.md"
        raw_path = vault / "raw" / "articles" / f"{slug}.md"
        self.assertTrue(transcript_path.exists())
        transcript_text = transcript_path.read_text(encoding="utf-8")
        raw_text = raw_path.read_text(encoding="utf-8")
        self.assertIn('type: "raw-transcript"', transcript_text)
        self.assertIn('transcript_source: "asr"', transcript_text)
        self.assertIn("这是 ASR 文稿", transcript_text)
        self.assertIn(f"[[raw/transcripts/{slug}--asr]]", raw_text)
        self.assertIn('transcript_source: "asr"', raw_text)
        self.assertIn("## 来源说明", raw_text)

    def test_emit_update_proposals_from_payload_writes_delta_pages(self) -> None:
        vault = ROOT / ".tmp-tests" / "ingest-v2-vault"
        outputs_dir = vault / "wiki" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: [path.unlink(missing_ok=True) for path in outputs_dir.glob("*.md")])
        paths = wiki_ingest_wechat.emit_update_proposals_from_payload(
            vault=vault,
            compiled_payload={
                "schema_version": "2.0",
                "result": {
                    "update_proposals": [
                        {
                            "target_page": "wiki/syntheses/自动驾驶--综合分析.md",
                            "target_type": "synthesis",
                            "action": "draft_delta",
                            "reason": "补充综合判断",
                            "confidence": "medium",
                            "evidence": ["证据句"],
                            "patch": {
                                "mode": "draft_note",
                                "summary_delta": ["新增判断"],
                                "questions_open": ["待验证问题"],
                            },
                        }
                    ]
                },
            },
            source_slug="2026-04-24--example",
            article_title="示例文章",
        )

        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].exists())
        text = paths[0].read_text(encoding="utf-8")
        self.assertIn('type: "delta-compile"', text)
        self.assertIn("## 建议修改", text)

    def test_emit_update_proposals_from_payload_includes_claim_inventory(self) -> None:
        vault = ROOT / ".tmp-tests" / "ingest-v2-vault"
        outputs_dir = vault / "wiki" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: [path.unlink(missing_ok=True) for path in outputs_dir.glob("*.md")])
        paths = wiki_ingest_wechat.emit_update_proposals_from_payload(
            vault=vault,
            compiled_payload={
                "schema_version": "2.0",
                "result": {
                    "claim_inventory": [
                        {
                            "claim": "本文认为中央计算会加强跨域协同。",
                            "claim_type": "interpretation",
                            "confidence": "medium",
                            "evidence": ["证据句"],
                        }
                    ],
                    "update_proposals": [
                        {
                            "target_page": "wiki/syntheses/自动驾驶--综合分析.md",
                            "target_type": "synthesis",
                            "action": "draft_delta",
                            "reason": "补充综合判断",
                            "confidence": "medium",
                            "evidence": ["证据句"],
                            "patch": {"mode": "draft_note"},
                        }
                    ]
                },
            },
            source_slug="2026-04-24--example",
            article_title="示例文章",
        )

        text = paths[0].read_text(encoding="utf-8")
        self.assertIn("## 关键判断", text)
        self.assertIn("中央计算会加强跨域协同", text)

    def test_ensure_taxonomy_pages_uses_promoted_knowledge_proposals(self) -> None:
        vault = ROOT / ".tmp-tests" / "taxonomy-v2-vault"
        wiki_ingest_wechat.ensure_bootstrap(vault)
        article = wiki_ingest_wechat.Article(
            title="示例文章",
            author="作者",
            date="2026-04-24",
            source="https://mp.weixin.qq.com/s/example",
            body="这是一篇没有明显实体和概念命中的文章。",
            src_dir=vault,
            md_path=vault / "dummy.md",
        )
        concept_path = vault / "wiki" / "concepts" / "跨域编排.md"
        entity_path = vault / "wiki" / "entities" / "样例公司.md"
        self.addCleanup(lambda: concept_path.unlink(missing_ok=True))
        self.addCleanup(lambda: entity_path.unlink(missing_ok=True))

        wiki_ingest_wechat.ensure_taxonomy_pages(
            vault=vault,
            article=article,
            source_slug="2026-04-24--example",
            force=True,
            domains_override=["AI 工程"],
            compiled_payload={
                "schema_version": "2.0",
                "result": {
                    "knowledge_proposals": {
                        "concepts": [
                            {
                                "name": "跨域编排",
                                "action": "promote_to_official_candidate",
                                "reason": "值得独立成页",
                                "confidence": "high",
                                "evidence": ["证据句"],
                            }
                        ],
                        "entities": [
                            {
                                "name": "样例公司",
                                "action": "promote_to_official_candidate",
                                "reason": "值得独立成页",
                                "confidence": "high",
                                "evidence": ["证据句"],
                            }
                        ],
                    }
                },
            },
        )

        self.assertTrue(concept_path.exists())
        self.assertTrue(entity_path.exists())


if __name__ == "__main__":
    unittest.main()

