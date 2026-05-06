from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import import_jobs  # noqa: E402


class ImportJobsTests(unittest.TestCase):
    def test_ensure_import_job_creates_expected_file(self) -> None:
        vault = ROOT / ".tmp-tests" / "import-jobs-vault-create"
        path = import_jobs.ensure_import_job(
            vault=vault,
            source_kind="video_playlist_youtube",
            source_url="https://www.youtube.com/playlist?list=PL123",
            max_items_per_run=100,
        )
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        self.assertTrue(path.exists())
        job = import_jobs.load_import_job(path)
        self.assertEqual(job["meta"]["type"], "import-job")
        self.assertEqual(job["meta"]["source_kind"], "video_playlist_youtube")
        self.assertEqual(job["meta"]["max_items_per_run"], "100")
        self.assertIn("## 已完成视频", job["body"])
        self.assertIn("## 待处理视频", job["body"])

    def test_update_import_job_writes_completed_and_pending_items(self) -> None:
        vault = ROOT / ".tmp-tests" / "import-jobs-vault-update"
        path = import_jobs.ensure_import_job(
            vault=vault,
            source_kind="video_playlist_youtube",
            source_url="https://www.youtube.com/playlist?list=PL123",
            max_items_per_run=100,
        )
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        import_jobs.update_import_job(
            path=path,
            source_kind="video_playlist_youtube",
            source_url="https://www.youtube.com/playlist?list=PL123",
            discovered_items=[
                {"video_id": "abc123", "video_url": "https://www.youtube.com/watch?v=abc123"},
                {"video_id": "def456", "video_url": "https://www.youtube.com/watch?v=def456"},
            ],
            completed_items=[
                {"video_id": "abc123", "source_slug": "video-a"},
            ],
            remaining_items=[
                {"video_id": "def456", "video_url": "https://www.youtube.com/watch?v=def456"},
            ],
            status="active",
            processed_count=1,
            skipped_count=0,
            failed_count=0,
        )

        job = import_jobs.load_import_job(path)
        self.assertEqual(job["meta"]["completed_count"], "1")
        self.assertEqual(job["meta"]["remaining_count"], "1")
        self.assertIn("`abc123` | [[sources/video-a]]", job["body"])
        self.assertIn("`def456` | https://www.youtube.com/watch?v=def456", job["body"])

    def test_completed_video_ids_parses_completed_section(self) -> None:
        vault = ROOT / ".tmp-tests" / "import-jobs-vault-completed"
        path = import_jobs.ensure_import_job(
            vault=vault,
            source_kind="video_playlist_bilibili",
            source_url="https://space.bilibili.com/123/channel/seriesdetail?sid=456",
            max_items_per_run=100,
        )
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        import_jobs.update_import_job(
            path=path,
            source_kind="video_playlist_bilibili",
            source_url="https://space.bilibili.com/123/channel/seriesdetail?sid=456",
            discovered_items=[
                {"video_id": "BV1xx", "video_url": "https://www.bilibili.com/video/BV1xx"},
                {"video_id": "BV2yy", "video_url": "https://www.bilibili.com/video/BV2yy"},
            ],
            completed_items=[
                {"video_id": "BV1xx", "source_slug": "bili-a"},
                {"video_id": "BV2yy", "source_slug": "bili-b"},
            ],
            remaining_items=[],
            status="completed",
            processed_count=2,
            skipped_count=0,
            failed_count=0,
        )

        job = import_jobs.load_import_job(path)
        self.assertEqual(import_jobs.completed_video_ids(job), {"BV1xx", "BV2yy"})
        self.assertEqual(
            import_jobs.completed_video_items(job),
            [
                {"video_id": "BV1xx", "source_slug": "bili-a"},
                {"video_id": "BV2yy", "source_slug": "bili-b"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
