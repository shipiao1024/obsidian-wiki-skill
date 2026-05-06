from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import adapter_result_to_article  # noqa: E402
import source_adapters  # noqa: E402
import adapters.web as _web_mod  # noqa: E402
import adapters.video as _video_mod  # noqa: E402
import adapters.collection as _collection_mod  # noqa: E402
import adapters.wechat as _wechat_mod  # noqa: E402
import adapters.local as _local_mod  # noqa: E402
import source_registry  # noqa: E402


class SourceRegistryTests(unittest.TestCase):
    def test_match_source_from_url_prefers_specific_patterns(self) -> None:
        self.assertEqual(
            source_registry.match_source_from_url("https://mp.weixin.qq.com/s/example"),
            "wechat_url",
        )
        self.assertEqual(
            source_registry.match_source_from_url("https://www.youtube.com/playlist?list=PL123"),
            "video_playlist_youtube",
        )
        self.assertEqual(
            source_registry.match_source_from_url("https://www.youtube.com/watch?v=abc"),
            "video_url_youtube",
        )
        self.assertEqual(
            source_registry.match_source_from_url("https://www.youtube.com/@example/videos"),
            "video_playlist_youtube",
        )
        self.assertEqual(
            source_registry.match_source_from_url("https://space.bilibili.com/123/channel/collectiondetail?sid=456"),
            "video_playlist_bilibili",
        )
        self.assertEqual(
            source_registry.match_source_from_url("https://www.bilibili.com/list/123456?sid=7890"),
            "video_playlist_bilibili",
        )
        self.assertEqual(
            source_registry.match_source_from_url("https://www.douyin.com/jingxuan/search/topic?modal_id=7631526521361960243&type=general"),
            "video_url_douyin",
        )
        self.assertEqual(
            source_registry.match_source_from_url("https://example.com/post"),
            "web_url",
        )

    def test_match_source_from_file_matches_extension(self) -> None:
        self.assertEqual(source_registry.match_source_from_file(Path("note.md")), "local_file_md")
        self.assertEqual(source_registry.match_source_from_file(Path("note.pdf")), "local_file_pdf")
        self.assertEqual(source_registry.match_source_from_file(Path("note.docx")), "local_file_docx")
        self.assertEqual(source_registry.match_source_from_file(Path("slides.pptx")), "local_file_pptx")
        self.assertEqual(source_registry.match_source_from_file(Path("data.xlsx")), "local_file_xlsx")
        self.assertEqual(source_registry.match_source_from_file(Path("old.xls")), "local_file_xlsx")
        self.assertEqual(source_registry.match_source_from_file(Path("book.epub")), "local_file_epub")


class SourceAdaptersTests(unittest.TestCase):
    def test_resolve_video_cookie_arg_variants_uses_default_repo_cookie_file(self) -> None:
        with mock.patch.dict(
            _video_mod.os.environ,
            {
                "WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "",
                "WECHAT_WIKI_VIDEO_COOKIES_FILE": "",
            },
            clear=False,
        ), mock.patch.object(
            _video_mod,
            "default_video_cookie_file",
            return_value=Path("D:/repo/Claude-obsidian-wiki-skill/cookies.txt"),
        ):
            variants = source_adapters.resolve_video_cookie_arg_variants()

        self.assertEqual(
            variants,
            [
                ["--cookies", "D:\\repo\\Claude-obsidian-wiki-skill\\cookies.txt"],
                [],
            ],
        )

    def test_normalize_video_fetch_url_extracts_douyin_modal_id(self) -> None:
        self.assertEqual(
            source_adapters.normalize_video_fetch_url(
                "video_url_douyin",
                "https://www.douyin.com/jingxuan/search/topic?aid=abc&modal_id=7631526521361960243&type=general",
            ),
            "https://www.douyin.com/video/7631526521361960243",
        )

    def test_assess_web_quality_returns_acceptable_for_readable_body(self) -> None:
        body = "# 网页标题\n\n" + ("这是正文内容。" * 60)
        self.assertEqual(
            source_adapters.assess_web_quality(title="网页标题", markdown_body=body, plain_text_body=body),
            "acceptable",
        )

    def test_assess_pdf_quality_returns_low_for_short_text(self) -> None:
        body = "这是很短的 PDF 文本。"
        self.assertEqual(
            source_adapters.assess_pdf_quality(title="sample", plain_text_body=body),
            "low",
        )

    def test_assess_video_quality_caps_asr_at_acceptable(self) -> None:
        body = "这是较长的视频文稿内容。" * 200
        self.assertEqual(
            source_adapters.assess_video_quality(
                title="视频标题",
                plain_text_body=body,
                transcript_source="asr",
            ),
            "acceptable",
        )

    def test_assess_video_quality_keeps_low_for_short_asr(self) -> None:
        body = "很短的 ASR 文稿。"
        self.assertEqual(
            source_adapters.assess_video_quality(
                title="视频标题",
                plain_text_body=body,
                transcript_source="asr",
            ),
            "low",
        )

    def test_resolve_web_adapter_command_splits_configured_command(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"WECHAT_WIKI_WEB_ADAPTER_BIN": "bun D:\\tools\\main.ts -o"},
            clear=False,
        ):
            command = source_adapters.resolve_web_adapter_command()

        self.assertEqual(command, ["bun", "D:\\tools\\main.ts", "-o"])

    def test_run_plain_text_adapter_returns_ok_result(self) -> None:
        result = source_adapters.run_plain_text_adapter(
            source_id="plain_text",
            input_value="标题\n\n正文",
            work_dir=ROOT / ".tmp-tests",
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata"]["title"], "标题")
        self.assertEqual(result["plain_text_body"], "标题\n\n正文")

    def test_run_local_file_adapter_reads_markdown(self) -> None:
        path = ROOT / ".tmp-tests" / "local-file.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 标题\n\n正文", encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        result = source_adapters.run_local_file_adapter(
            source_id="local_file_md",
            input_value=str(path),
            work_dir=ROOT / ".tmp-tests",
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata"]["title"], "local-file")
        self.assertIn("正文", result["markdown_body"])

    def test_run_wechat_adapter_returns_ok_result(self) -> None:
        tool_dir = ROOT / ".tmp-tests" / "wechat-tool"
        tool_dir.mkdir(parents=True, exist_ok=True)
        main_path = tool_dir / "main.py"
        main_path.write_text("print('ok')\n", encoding="utf-8")
        self.addCleanup(lambda: main_path.unlink(missing_ok=True))

        work_dir = ROOT / ".tmp-tests" / "wechat-work"
        article_dir = work_dir / "示例文章"
        images_dir = article_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        image_path = images_dir / "cover.png"
        image_path.write_bytes(b"fake-image")
        md_path = article_dir / "示例文章.md"
        md_path.write_text(
            "---\n"
            'title: "示例文章"\n'
            'author: "作者"\n'
            'date: "2026-04-24"\n'
            'source: "https://mp.weixin.qq.com/s/example"\n'
            "---\n\n"
            "正文内容\n",
            encoding="utf-8",
        )
        self.addCleanup(lambda: md_path.unlink(missing_ok=True))
        self.addCleanup(lambda: image_path.unlink(missing_ok=True))

        with mock.patch.object(_wechat_mod, "_camoufox_is_installed", return_value=True), mock.patch.object(_wechat_mod.subprocess, "run") as run_mock:
            result = source_adapters.run_wechat_adapter(
                source_id="wechat_url",
                input_value="https://mp.weixin.qq.com/s/example",
                work_dir=work_dir,
                tool_dir=tool_dir,
            )

        run_mock.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata"]["title"], "示例文章")
        self.assertEqual(result["metadata"]["author"], "作者")
        self.assertEqual(len(result["assets"]), 1)

    def test_run_wechat_adapter_requires_tool_dir(self) -> None:
        result = source_adapters.run_wechat_adapter(
            source_id="wechat_url",
            input_value="https://mp.weixin.qq.com/s/example",
            work_dir=ROOT / ".tmp-tests" / "wechat-missing",
            tool_dir=ROOT / ".tmp-tests" / "missing-tool",
        )

        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("not found", result["reason"].lower())

    def test_run_web_adapter_returns_ok_result(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "web-work"
        output_path = work_dir / "article.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("# 网页标题\n\n" + ("正文内容。" * 60), encoding="utf-8")
        self.addCleanup(lambda: output_path.unlink(missing_ok=True))

        with mock.patch.object(_web_mod, "resolve_web_adapter_command", return_value=["baoyu-url-to-markdown"]) as cmd_mock, mock.patch.object(_web_mod.subprocess, "run") as run_mock:
            result = source_adapters.run_web_adapter(
                source_id="web_url",
                input_value="https://example.com/post",
                work_dir=work_dir,
            )

        cmd_mock.assert_called_once()
        run_mock.assert_called_once()
        called_cmd = run_mock.call_args.args[0]
        called_kwargs = run_mock.call_args.kwargs
        self.assertEqual(
            called_cmd,
            ["baoyu-url-to-markdown", "https://example.com/post", "-o", str(output_path)],
        )
        self.assertTrue(called_kwargs["capture_output"])
        self.assertTrue(called_kwargs["text"])
        self.assertEqual(called_kwargs["encoding"], "utf-8")
        self.assertEqual(called_kwargs["errors"], "replace")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["quality"], "acceptable")
        self.assertEqual(result["metadata"]["title"], "网页标题")
        self.assertIn("正文内容", result["markdown_body"])

    def test_run_web_adapter_prefers_frontmatter_title(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "web-frontmatter-work"
        output_path = work_dir / "article.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\n"
            'title: "Example Domain"\n'
            "---\n\n"
            "# Example Domain\n\n"
            "正文内容",
            encoding="utf-8",
        )
        self.addCleanup(lambda: output_path.unlink(missing_ok=True))

        with mock.patch.object(_web_mod, "resolve_web_adapter_command", return_value=["baoyu-url-to-markdown"]), mock.patch.object(
            _web_mod.subprocess,
            "run",
        ):
            result = source_adapters.run_web_adapter(
                source_id="web_url",
                input_value="https://example.com/post",
                work_dir=work_dir,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata"]["title"], "Example Domain")

    def test_run_web_adapter_reports_dependency_missing_when_command_unavailable(self) -> None:
        result = source_adapters.run_web_adapter(
            source_id="web_url",
            input_value="https://example.com/post",
            work_dir=ROOT / ".tmp-tests" / "web-missing",
        )

        self.assertEqual(result["status"], "dependency_missing")
        self.assertIn("not found", result["reason"].lower())

    def test_run_web_adapter_reports_runtime_failed_on_command_error(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "web-runtime-failed"
        with mock.patch.object(_web_mod, "resolve_web_adapter_command", return_value=["baoyu-url-to-markdown"]), mock.patch.object(
            _web_mod.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["baoyu-url-to-markdown"]),
        ):
            result = source_adapters.run_web_adapter(
                source_id="web_url",
                input_value="https://example.com/post",
                work_dir=work_dir,
            )

        self.assertEqual(result["status"], "runtime_failed")

    def test_run_web_adapter_reports_browser_not_ready(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "web-browser-not-ready"
        error = subprocess.CalledProcessError(
            1,
            ["baoyu-url-to-markdown"],
            stderr="Chrome debug port not ready",
        )
        with mock.patch.object(_web_mod, "resolve_web_adapter_command", return_value=["baoyu-url-to-markdown"]), mock.patch.object(
            _web_mod.subprocess,
            "run",
            side_effect=error,
        ):
            result = source_adapters.run_web_adapter(
                source_id="web_url",
                input_value="https://example.com/post",
                work_dir=work_dir,
            )

        self.assertEqual(result["status"], "browser_not_ready")
        self.assertIn("chrome", result["reason"].lower())

    def test_run_web_adapter_reports_network_failed(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "web-network-failed"
        error = subprocess.CalledProcessError(
            1,
            ["baoyu-url-to-markdown"],
            stderr="Unable to connect. Is the computer able to access the url?",
        )
        with mock.patch.object(_web_mod, "resolve_web_adapter_command", return_value=["baoyu-url-to-markdown"]), mock.patch.object(
            _web_mod.subprocess,
            "run",
            side_effect=error,
        ):
            result = source_adapters.run_web_adapter(
                source_id="web_url",
                input_value="https://example.com/post",
                work_dir=work_dir,
            )

        self.assertEqual(result["status"], "network_failed")
        self.assertIn("connect", result["reason"].lower())

    def test_run_video_adapter_returns_ok_result_from_subtitle(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-work"
        subtitle_path = work_dir / "video.zh.srt"
        subtitle_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_text = "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:02,000",
                "第一句字幕",
                "2",
                "00:00:02,000 --> 00:00:04,000",
                "第二句字幕",
            ]
            + [
                str(index)
                + "\n00:00:04,000 --> 00:00:06,000\n"
                + ("这是较长的视频文稿内容。" * 8)
                for index in range(3, 8)
            ]
        )
        subtitle_path.write_text(subtitle_text, encoding="utf-8")
        info_path = work_dir / "video.info.json"
        info_path.write_text('{"title":"真实视频标题","uploader":"上传者","upload_date":"20260424"}', encoding="utf-8")
        self.addCleanup(lambda: subtitle_path.unlink(missing_ok=True))
        self.addCleanup(lambda: info_path.unlink(missing_ok=True))

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]) as cmd_mock, mock.patch.object(_video_mod.subprocess, "run") as run_mock:
            result = source_adapters.run_video_adapter(
                source_id="video_url_youtube",
                input_value="https://www.youtube.com/watch?v=abc",
                work_dir=work_dir,
            )

        cmd_mock.assert_called_once()
        run_mock.assert_called_once()
        called_cmd = run_mock.call_args.args[0]
        self.assertIn("--no-playlist", called_cmd)
        self.assertIn("--write-info-json", called_cmd)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["quality"], "acceptable")
        self.assertEqual(result["metadata"]["title"], "真实视频标题")
        self.assertEqual(result["metadata"]["author"], "上传者")
        self.assertEqual(result["metadata"]["date"], "20260424")
        self.assertIn("第一句字幕", result["plain_text_body"])
        self.assertEqual(result["assets"][0]["media_type"], "subtitle")

    def test_run_video_adapter_prefers_cookies_from_browser(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-cookie-browser"
        subtitle_path = work_dir / "video.en-GB.vtt"
        subtitle_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n字幕\n", encoding="utf-8")
        self.addCleanup(lambda: subtitle_path.unlink(missing_ok=True))

        with mock.patch.dict(
            _video_mod.os.environ,
            {"WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "chrome"},
            clear=False,
        ), mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod.subprocess, "run"
        ) as run_mock:
            source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=work_dir,
            )

        called_cmd = run_mock.call_args.args[0]
        self.assertIn("--cookies-from-browser", called_cmd)
        self.assertIn("chrome", called_cmd)

    def test_run_video_adapter_uses_cookie_file_when_browser_state_not_set(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-cookie-file"
        subtitle_path = work_dir / "video.en-GB.vtt"
        subtitle_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n字幕\n", encoding="utf-8")
        self.addCleanup(lambda: subtitle_path.unlink(missing_ok=True))

        with mock.patch.dict(
            _video_mod.os.environ,
            {
                "WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "",
                "WECHAT_WIKI_VIDEO_COOKIES_FILE": "D:\\cookies.txt",
            },
            clear=False,
        ), mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod.subprocess, "run"
        ) as run_mock:
            source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=work_dir,
            )

        called_cmd = run_mock.call_args.args[0]
        self.assertIn("--cookies", called_cmd)
        self.assertIn("D:\\cookies.txt", called_cmd)

    def test_run_video_adapter_reports_dependency_missing_when_command_unavailable(self) -> None:
        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=None):
            result = source_adapters.run_video_adapter(
                source_id="video_url_youtube",
                input_value="https://www.youtube.com/watch?v=abc",
                work_dir=ROOT / ".tmp-tests" / "video-missing",
            )

        self.assertEqual(result["status"], "dependency_missing")

    def test_run_video_adapter_reports_platform_blocked_on_http_412(self) -> None:
        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: [BiliBili] Unable to download JSON metadata: HTTP Error 412: Precondition Failed",
        )
        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod.subprocess, "run", side_effect=error
        ):
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=ROOT / ".tmp-tests" / "video-412",
            )

        self.assertEqual(result["status"], "platform_blocked")
        self.assertIn("412", result["reason"])

    def test_run_video_adapter_uses_browser_capture_for_douyin_cookie_failure(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "douyin-browser-capture"
        video_path = work_dir / "douyin-browser-capture.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"0" * 2048)
        self.addCleanup(lambda: video_path.unlink(missing_ok=True))

        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: [douyin] Fresh cookies are needed",
        )
        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod.subprocess, "run", side_effect=error
        ), mock.patch.object(
            _video_mod,
            "run_douyin_browser_capture",
            return_value={
                "status": "ok",
                "title": "抖音标题",
                "video_path": str(video_path),
                "video_url": "https://example.com/video.mp4",
            },
        ) as capture_mock, mock.patch.object(_video_mod, "transcribe_audio_with_asr", return_value="这是抖音 ASR 文稿"):
            result = source_adapters.run_video_adapter(
                source_id="video_url_douyin",
                input_value="https://www.douyin.com/jingxuan/search/topic?modal_id=7631526521361960243",
                work_dir=work_dir,
            )

        capture_mock.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["adapter_name"], "douyin-browser-capture")
        self.assertEqual(result["metadata"]["source_kind"], "douyin")
        self.assertIn("抖音 ASR", result["plain_text_body"])

    def test_run_video_adapter_captures_stderr_for_failure_classification(self) -> None:
        def fake_run(*args, **kwargs):
            self.assertTrue(kwargs["capture_output"])
            self.assertTrue(kwargs["text"])
            self.assertEqual(kwargs["encoding"], "utf-8")
            self.assertEqual(kwargs["errors"], "replace")
            raise subprocess.CalledProcessError(
                1,
                args[0],
                stderr="ERROR: [BiliBili] Unable to download JSON metadata: HTTP Error 412: Precondition Failed",
            )

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod.subprocess, "run", side_effect=fake_run
        ):
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=ROOT / ".tmp-tests" / "video-412-captured",
            )

        self.assertEqual(result["status"], "platform_blocked")
        self.assertIn("412", result["reason"])

    def test_run_video_adapter_reports_browser_cookie_copy_failure_actionably(self) -> None:
        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271 for more info",
        )
        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.dict(
            _video_mod.os.environ,
            {"WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "edge"},
            clear=False,
        ), mock.patch.object(_video_mod.subprocess, "run", side_effect=error):
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=ROOT / ".tmp-tests" / "video-cookie-db-fail",
            )

        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("WECHAT_WIKI_VIDEO_COOKIES_FILE", result["reason"])

    def test_run_video_adapter_falls_back_to_cookie_file_when_browser_cookie_copy_fails(self) -> None:
        browser_cookie_error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271 for more info",
        )
        work_dir = ROOT / ".tmp-tests" / "video-cookie-fallback"
        subtitle_path = work_dir / "video.zh-Hans.srt"
        info_path = work_dir / "video.info.json"

        def fake_run(cmd, **kwargs):
            if "--cookies-from-browser" in cmd:
                raise browser_cookie_error
            subtitle_path.parent.mkdir(parents=True, exist_ok=True)
            subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试字幕\n", encoding="utf-8")
            info_path.write_text('{"title":"B站视频标题","uploader":"UP主","upload_date":"20260424"}', encoding="utf-8")
            return mock.Mock(stdout="", stderr="")

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.dict(
            _video_mod.os.environ,
            {
                "WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "edge",
                "WECHAT_WIKI_VIDEO_COOKIES_FILE": "D:\\cookies.txt",
            },
            clear=False,
        ), mock.patch.object(_video_mod.subprocess, "run", side_effect=fake_run) as run_mock:
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=work_dir,
            )

        self.addCleanup(lambda: subtitle_path.unlink(missing_ok=True))
        self.addCleanup(lambda: info_path.unlink(missing_ok=True))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(run_mock.call_count, 2)
        first_cmd = run_mock.call_args_list[0].args[0]
        second_cmd = run_mock.call_args_list[1].args[0]
        self.assertIn("--cookies-from-browser", first_cmd)
        self.assertIn("--cookies", second_cmd)

    def test_run_video_adapter_reports_empty_result_without_subtitle(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-empty"
        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod, "resolve_video_cookie_arg_variants", return_value=[[]]
        ), mock.patch.object(_video_mod.subprocess, "run") as run_mock:
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=work_dir,
            )

        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(result["status"], "empty_result")

    def test_run_video_adapter_does_not_use_bilibili_danmaku_as_transcript(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-danmaku"
        danmaku_path = work_dir / "video.danmaku.xml"
        danmaku_path.parent.mkdir(parents=True, exist_ok=True)
        danmaku_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?><i><d p="1,1,25,16777215,0,0,0,0">第一条弹幕</d><d p="2,1,25,16777215,0,0,0,0">第二条弹幕</d></i>',
            encoding="utf-8",
        )
        info_path = work_dir / "video.info.json"
        info_path.write_text('{"title":"B站视频标题","uploader":"UP主","upload_date":"20260424"}', encoding="utf-8")
        self.addCleanup(lambda: danmaku_path.unlink(missing_ok=True))
        self.addCleanup(lambda: info_path.unlink(missing_ok=True))

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod, "resolve_video_cookie_arg_variants", return_value=[[]]
        ), mock.patch.object(
            _video_mod.subprocess, "run"
        ) as run_mock:
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=work_dir,
            )

        self.assertEqual(run_mock.call_count, 2)
        first_cmd = run_mock.call_args_list[0].args[0]
        second_cmd = run_mock.call_args_list[1].args[0]
        self.assertIn("--skip-download", first_cmd)
        self.assertIn("-f", second_cmd)
        self.assertIn("bestaudio", second_cmd)
        self.assertEqual(result["status"], "empty_result")

    def test_run_video_adapter_uses_asr_fallback_when_only_bilibili_danmaku_exists(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-danmaku-asr"
        danmaku_path = work_dir / "video.danmaku.xml"
        danmaku_path.parent.mkdir(parents=True, exist_ok=True)
        danmaku_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?><i><d p="1,1,25,16777215,0,0,0,0">第一条弹幕</d></i>',
            encoding="utf-8",
        )
        info_path = work_dir / "video.info.json"
        info_path.write_text('{"title":"B站视频标题","uploader":"UP主","upload_date":"20260424"}', encoding="utf-8")
        self.addCleanup(lambda: danmaku_path.unlink(missing_ok=True))
        self.addCleanup(lambda: info_path.unlink(missing_ok=True))

        def fake_run(cmd: list[str], check: bool = True, **kwargs) -> mock.Mock:
            self.assertTrue(check)
            if "-f" in cmd and "bestaudio" in cmd:
                audio_path = work_dir / "video-audio.m4a"
                audio_path.write_bytes(b"fake-audio")
            return mock.Mock()

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod, "resolve_video_cookie_arg_variants", return_value=[[]]
        ), mock.patch.object(
            _video_mod.subprocess, "run", side_effect=fake_run
        ) as run_mock, mock.patch.object(
            _video_mod, "transcribe_audio_with_asr", return_value="这是 ASR 文稿"
        ) as asr_mock:
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=work_dir,
            )

        self.addCleanup(lambda: (work_dir / "video-audio.m4a").unlink(missing_ok=True))
        self.assertEqual(run_mock.call_count, 2)
        asr_mock.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata"]["title"], "B站视频标题")
        self.assertIn("ASR 文稿", result["plain_text_body"])
        self.assertEqual(result["extra"]["subtitle_source"], "asr")

    def test_run_video_adapter_uses_embedded_metadata_subtitle_fallback(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-embedded-subtitle"
        work_dir.mkdir(parents=True, exist_ok=True)
        info_path = work_dir / "video.info.json"
        info_path.write_text(
            json.dumps(
                {
                    "title": "B站内嵌字幕视频",
                    "uploader": "UP主",
                    "upload_date": "20260424",
                    "subtitles": {
                        "ai-zh": [
                            {
                                "ext": "srt",
                                "data": "1\n00:00:00,000 --> 00:00:02,000\n第一句\n\n2\n00:00:02,000 --> 00:00:04,000\n"
                                + ("这是较长的内嵌字幕内容。" * 20),
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: info_path.unlink(missing_ok=True))

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod.subprocess, "run"
        ):
            result = source_adapters.run_video_adapter(
                source_id="video_url_bilibili",
                input_value="https://www.bilibili.com/video/BV1xx",
                work_dir=work_dir,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata"]["title"], "B站内嵌字幕视频")
        self.assertEqual(result["metadata"]["language"], "ai-zh")
        self.assertIn("第一句", result["plain_text_body"])
        self.assertEqual(result["extra"]["subtitle_source"], "embedded-metadata")
        self.assertEqual(result["extra"]["subtitle_language"], "ai-zh")

    def test_run_video_adapter_uses_asr_fallback_when_no_subtitle(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-asr"
        audio_path = work_dir / "video.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"fake-audio")
        self.addCleanup(lambda: audio_path.unlink(missing_ok=True))

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod, "transcribe_audio_with_asr", return_value="这是 ASR 文稿"
        ) as asr_mock, mock.patch.object(_video_mod.subprocess, "run") as run_mock:
            result = source_adapters.run_video_adapter(
                source_id="video_url_youtube",
                input_value="https://www.youtube.com/watch?v=abc",
                work_dir=work_dir,
            )

        run_mock.assert_called_once()
        asr_mock.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertIn("ASR 文稿", result["plain_text_body"])
        self.assertEqual(result["extra"]["subtitle_source"], "asr")

    def test_run_video_adapter_reports_dependency_missing_when_asr_missing(self) -> None:
        work_dir = ROOT / ".tmp-tests" / "video-asr-missing"
        audio_path = work_dir / "video.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"fake-audio")
        self.addCleanup(lambda: audio_path.unlink(missing_ok=True))

        with mock.patch.object(_video_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _video_mod.subprocess,
            "run",
        ), mock.patch.object(
            _video_mod,
            "transcribe_audio_with_asr",
            side_effect=RuntimeError("ASR dependency missing: faster-whisper"),
        ):
            result = source_adapters.run_video_adapter(
                source_id="video_url_youtube",
                input_value="https://www.youtube.com/watch?v=abc",
                work_dir=work_dir,
            )

        self.assertEqual(result["status"], "dependency_missing")
        self.assertIn("faster-whisper", result["reason"])

    def test_expand_video_collection_urls_for_youtube_playlist(self) -> None:
        payload = '{"entries":[{"id":"abc123"},{"webpage_url":"https://www.youtube.com/watch?v=def456"}]}'
        with mock.patch.object(_collection_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _collection_mod.subprocess,
            "run",
            return_value=mock.Mock(stdout=payload, stderr=""),
        ) as run_mock:
            urls = source_adapters.expand_video_collection_urls(
                source_id="video_playlist_youtube",
                input_value="https://www.youtube.com/playlist?list=PL123",
                work_dir=ROOT / ".tmp-tests" / "playlist-youtube",
            )

        run_mock.assert_called_once()
        self.assertEqual(
            urls,
            [
                "https://www.youtube.com/watch?v=abc123",
                "https://www.youtube.com/watch?v=def456",
            ],
        )

    def test_expand_video_collection_urls_for_youtube_channel_videos_page(self) -> None:
        payload = (
            '{"entries":[{"url":"abc123"},'
            '{"webpage_url":"https://www.youtube.com/watch?v=def456"},'
            '{"id":"abc123"}'
            "]}"
        )
        with mock.patch.object(_collection_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _collection_mod.subprocess,
            "run",
            return_value=mock.Mock(stdout=payload, stderr=""),
        ):
            urls = source_adapters.expand_video_collection_urls(
                source_id="video_playlist_youtube",
                input_value="https://www.youtube.com/@example/videos",
                work_dir=ROOT / ".tmp-tests" / "channel-youtube",
            )

        self.assertEqual(
            urls,
            [
                "https://www.youtube.com/watch?v=abc123",
                "https://www.youtube.com/watch?v=def456",
            ],
        )

    def test_expand_video_collection_urls_for_bilibili_playlist(self) -> None:
        payload = '{"entries":[{"url":"https://www.bilibili.com/video/BV1xx"},{"id":"BV2yy"}]}'
        with mock.patch.object(_collection_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
            _collection_mod.subprocess,
            "run",
            return_value=mock.Mock(stdout=payload, stderr=""),
        ):
            urls = source_adapters.expand_video_collection_urls(
                source_id="video_playlist_bilibili",
                input_value="https://space.bilibili.com/123/channel/seriesdetail?sid=456",
                work_dir=ROOT / ".tmp-tests" / "playlist-bilibili",
            )

        self.assertEqual(
            urls,
            [
                "https://www.bilibili.com/video/BV1xx",
                "https://www.bilibili.com/video/BV2yy",
            ],
        )

    def test_expand_video_collection_urls_uses_video_cookie_args(self) -> None:
        payload = '{"entries":[{"id":"BV1xx"}]}'
        with mock.patch.object(_collection_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.dict(
            _video_mod.os.environ,
            {
                "WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "",
                "WECHAT_WIKI_VIDEO_COOKIES_FILE": "D:\\cookies.txt",
            },
            clear=False,
        ), mock.patch.object(
            _collection_mod.subprocess,
            "run",
            return_value=mock.Mock(stdout=payload, stderr=""),
        ) as run_mock:
            source_adapters.expand_video_collection_urls(
                source_id="video_playlist_bilibili",
                input_value="https://www.bilibili.com/list/example",
                work_dir=ROOT / ".tmp-tests" / "playlist-bilibili-cookies",
            )

        called_cmd = run_mock.call_args.args[0]
        self.assertIn("--cookies", called_cmd)
        self.assertIn("D:\\cookies.txt", called_cmd)

    def test_expand_video_collection_urls_raises_network_error_on_winerror_10013(self) -> None:
        """Collection adapter is single-shot (no retry); WinError 10013 → network_failed."""
        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            output="null",
            stderr="WinError 10013",
        )
        with mock.patch.object(_collection_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.dict(
            _video_mod.os.environ,
            {
                "WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "",
                "WECHAT_WIKI_VIDEO_COOKIES_FILE": "D:\\cookies.txt",
            },
            clear=False,
        ), mock.patch.object(
            _collection_mod.subprocess,
            "run",
            side_effect=error,
        ):
            with self.assertRaisesRegex(RuntimeError, "network/socket error"):
                source_adapters.expand_video_collection_urls(
                    source_id="video_playlist_bilibili",
                    input_value="https://www.bilibili.com/list/example",
                    work_dir=ROOT / ".tmp-tests" / "playlist-bilibili-cookie-retry",
                )

    def test_expand_video_collection_urls_classifies_cookie_error_as_platform_blocked(self) -> None:
        """Cookie-related errors are classified as platform_blocked."""
        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: sign in to confirm you are not a bot",
        )
        with mock.patch.object(_collection_mod, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.dict(
            _video_mod.os.environ,
            {
                "WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER": "",
                "WECHAT_WIKI_VIDEO_COOKIES_FILE": "",
            },
            clear=False,
        ), mock.patch.object(
            _collection_mod.subprocess,
            "run",
            side_effect=error,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires cookies.txt"):
                source_adapters.expand_video_collection_urls(
                    source_id="video_playlist_bilibili",
                    input_value="https://www.bilibili.com/list/example",
                    work_dir=ROOT / ".tmp-tests" / "playlist-bilibili-cookie-classify",
                )

    def test_normalize_collection_entry_url_returns_none_for_invalid_entry(self) -> None:
        self.assertIsNone(
            source_adapters.normalize_collection_entry_url(
                "video_playlist_bilibili",
                {"title": "missing-url-and-id"},
            )
        )


class LocalFormatAdapterTests(unittest.TestCase):
    """Tests for the new format normalization adapters (docx, pptx, xlsx, epub)."""

    def test_run_local_file_adapter_routes_docx(self) -> None:
        path = ROOT / ".tmp-tests" / "test-doc.docx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-docx")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        with mock.patch.object(_local_mod, "run_docx_file_adapter", return_value={
            "status": "ok", "markdown_body": "docx content", "metadata": {"title": "test-doc"},
        }) as mock_adapter:
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_docx",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        mock_adapter.assert_called_once_with(source_id="local_file_docx", path=path)
        self.assertEqual(result["status"], "ok")

    def test_run_local_file_adapter_routes_pptx(self) -> None:
        path = ROOT / ".tmp-tests" / "slides.pptx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-pptx")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        with mock.patch.object(_local_mod, "run_pptx_file_adapter", return_value={
            "status": "ok", "markdown_body": "pptx content", "metadata": {"title": "slides"},
        }) as mock_adapter:
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_pptx",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        mock_adapter.assert_called_once_with(source_id="local_file_pptx", path=path)
        self.assertEqual(result["status"], "ok")

    def test_run_local_file_adapter_routes_xlsx(self) -> None:
        path = ROOT / ".tmp-tests" / "data.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-xlsx")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        with mock.patch.object(_local_mod, "run_xlsx_file_adapter", return_value={
            "status": "ok", "markdown_body": "xlsx content", "metadata": {"title": "data"},
        }) as mock_adapter:
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_xlsx",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        mock_adapter.assert_called_once_with(source_id="local_file_xlsx", path=path)
        self.assertEqual(result["status"], "ok")

    def test_run_local_file_adapter_routes_xls(self) -> None:
        path = ROOT / ".tmp-tests" / "old.xls"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-xls")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        with mock.patch.object(_local_mod, "run_xlsx_file_adapter", return_value={
            "status": "ok", "markdown_body": "xls content", "metadata": {"title": "old"},
        }) as mock_adapter:
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_xlsx",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        mock_adapter.assert_called_once_with(source_id="local_file_xlsx", path=path)
        self.assertEqual(result["status"], "ok")

    def test_run_local_file_adapter_routes_epub(self) -> None:
        path = ROOT / ".tmp-tests" / "book.epub"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-epub")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        with mock.patch.object(_local_mod, "run_epub_file_adapter", return_value={
            "status": "ok", "markdown_body": "epub content", "metadata": {"title": "book"},
        }) as mock_adapter:
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_epub",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        mock_adapter.assert_called_once_with(source_id="local_file_epub", path=path)
        self.assertEqual(result["status"], "ok")

    def test_run_docx_adapter_reports_dependency_missing(self) -> None:
        path = ROOT / ".tmp-tests" / "missing-deps.docx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-docx")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        with mock.patch.object(_local_mod, "_try_markitdown_convert", side_effect=RuntimeError("markitdown is not installed")):
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_docx",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        self.assertEqual(result["status"], "dependency_missing")
        self.assertIn("markitdown", result["reason"])

    def test_run_xlsx_adapter_reports_dependency_missing(self) -> None:
        path = ROOT / ".tmp-tests" / "missing-deps.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-xlsx")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pandas":
                raise ImportError("No module named 'pandas'")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=mock_import):
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_xlsx",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        self.assertEqual(result["status"], "dependency_missing")
        self.assertIn("pandas", result["reason"])

    def test_run_epub_adapter_reports_dependency_missing(self) -> None:
        path = ROOT / ".tmp-tests" / "missing-deps.epub"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-epub")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "ebooklib":
                raise ImportError("No module named 'ebooklib'")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=mock_import):
            result = source_adapters.run_local_file_adapter(
                source_id="local_file_epub",
                input_value=str(path),
                work_dir=ROOT / ".tmp-tests",
            )

        self.assertEqual(result["status"], "dependency_missing")
        self.assertIn("ebooklib", result["reason"])


class AdapterResultToArticleTests(unittest.TestCase):
    def test_adapter_result_to_article_writes_markdown_and_images(self) -> None:
        staging_root = ROOT / ".tmp-tests" / "adapter-staging"
        image_src = ROOT / ".tmp-tests" / "example-image.png"
        image_src.parent.mkdir(parents=True, exist_ok=True)
        image_src.write_bytes(b"fake-image")
        self.addCleanup(lambda: image_src.unlink(missing_ok=True))

        article = adapter_result_to_article.adapter_result_to_article(
            result={
                "status": "ok",
                "reason": "",
                "input_kind": "text",
                "source_id": "plain_text",
                "adapter_name": "direct_ingest",
                "quality": "acceptable",
                "metadata": {
                    "title": "示例文章",
                    "author": "作者",
                    "date": "2026-04-24",
                    "source_id": "plain_text",
                    "source_kind": "plain_text",
                },
                "markdown_body": f"![图]({str(image_src)})\n\n正文",
                "plain_text_body": "正文",
                "assets": [
                    {
                        "local_path": str(image_src),
                        "media_type": "image",
                    }
                ],
                "extra": {},
            },
            staging_root=staging_root,
        )
        self.addCleanup(lambda: article.md_path.unlink(missing_ok=True))
        self.addCleanup(
            lambda: [p.unlink(missing_ok=True) for p in (article.src_dir / "images").glob("*")]
        )

        self.assertTrue(article.md_path.exists())
        self.assertTrue((article.src_dir / "images").exists())
        self.assertIn("正文", article.body)
        self.assertEqual(article.quality, "acceptable")

    def test_adapter_result_to_article_preserves_video_transcript_metadata(self) -> None:
        staging_root = ROOT / ".tmp-tests" / "adapter-video-staging"
        article = adapter_result_to_article.adapter_result_to_article(
            result={
                "status": "ok",
                "reason": "",
                "input_kind": "url",
                "source_id": "video_url_bilibili",
                "adapter_name": "yt-dlp",
                "quality": "acceptable",
                "metadata": {
                    "title": "视频标题",
                    "author": "UP主",
                    "date": "2026-04-24",
                    "source_url": "https://www.bilibili.com/video/BV1xx",
                    "source_id": "video_url_bilibili",
                    "source_kind": "bilibili",
                    "language": "zh",
                },
                "markdown_body": "这是视频文稿",
                "plain_text_body": "这是视频文稿",
                "assets": [],
                "extra": {
                    "subtitle_source": "asr",
                    "subtitle_language": "zh",
                    "confidence_hint": "medium",
                },
            },
            staging_root=staging_root,
        )
        self.addCleanup(lambda: article.md_path.unlink(missing_ok=True))

        self.assertEqual(article.transcript_stage, "asr")
        self.assertEqual(article.transcript_source, "asr")
        self.assertEqual(article.transcript_language, "zh")
        self.assertEqual(article.transcript_confidence_hint, "medium")
        self.assertEqual(article.transcript_body, "这是视频文稿")


if __name__ == "__main__":
    unittest.main()