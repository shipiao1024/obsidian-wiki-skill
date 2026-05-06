# Video Collection Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持 YouTube playlist/channel videos 页与 Bilibili 合集/系列 URL 的批量视频导入，单次最多 20 条，支持断点续跑且不重复下载。

**Architecture:** 在现有单视频主链外增加一层“集合展开 + import-job 状态管理”。集合 URL 先用 `yt-dlp --flat-playlist --dump-single-json` 展开成多个单视频 URL，再逐条复用当前 `run_video_adapter() -> AdapterResult -> Article -> ingest_article()` 链路。任务状态单独保存在 `wiki/import-jobs/`，不混入知识层。

**Tech Stack:** Python、yt-dlp、Markdown frontmatter、现有 `wiki_ingest_wechat.py` / `source_registry.py` / `source_adapters.py`

---

## File Structure

- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/source_registry.py`
  - 新增 `video_playlist_youtube` 与 `video_playlist_bilibili` 来源类型
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/source_adapters.py`
  - 新增集合展开函数，负责把 playlist/channel/list URL 解析成标准化视频子项
- Create: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/import_jobs.py`
  - 负责 `wiki/import-jobs/*.md` 的读写、已完成项解析、状态回写
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/wiki_ingest_wechat.py`
  - 新增集合主控逻辑，处理单次 20 条限制、断点续跑和去重
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_source_adapters.py`
  - 覆盖来源匹配和集合展开
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_wiki_ingest_wechat_v2.py`
  - 覆盖主入口 playlist/channel 行为
- Create: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_import_jobs.py`
  - 覆盖 job 文件读写、已完成项解析、状态更新

### Task 1: Extend Source Registry For Collection URLs

**Files:**
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/source_registry.py`
- Test: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_source_adapters.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_match_source_from_url_prefers_specific_patterns(self) -> None:
    self.assertEqual(
        source_registry.match_source_from_url("https://www.youtube.com/playlist?list=PL123"),
        "video_playlist_youtube",
    )
    self.assertEqual(
        source_registry.match_source_from_url("https://space.bilibili.com/123/channel/collectiondetail?sid=456"),
        "video_playlist_bilibili",
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_source_adapters.SourceRegistryTests.test_match_source_from_url_prefers_specific_patterns
```

Expected:

```text
FAIL: expected video_playlist_youtube / video_playlist_bilibili, got web_url
```

- [ ] **Step 3: Write minimal implementation**

```python
"video_playlist_youtube": {
    "label": "YouTube 播放列表",
    "kind": "url",
    "subtype": "youtube_playlist",
    "priority": 95,
    "match": {
        "url_patterns": [
            r"^https?://(www\.)?youtube\.com/playlist\?list=",
            r"^https?://(www\.)?youtube\.com/@[^/]+/videos",
            r"^https?://(www\.)?youtube\.com/channel/[^/]+/videos",
            r"^https?://(www\.)?youtube\.com/c/[^/]+/videos",
        ]
    },
    "adapter": {"name": "yt-dlp", "mode": "playlist_expand"},
},
"video_playlist_bilibili": {
    "label": "Bilibili 合集/系列",
    "kind": "url",
    "subtype": "bilibili_playlist",
    "priority": 95,
    "match": {
        "url_patterns": [
            r"^https?://space\.bilibili\.com/\d+/channel/(?:collectiondetail|seriesdetail)\?sid=",
            r"^https?://(www\.)?bilibili\.com/list/",
        ]
    },
    "adapter": {"name": "yt-dlp", "mode": "playlist_expand"},
},
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_source_adapters.SourceRegistryTests.test_match_source_from_url_prefers_specific_patterns
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```powershell
git add Claude-obsidian-wiki-skill/scripts/source_registry.py Claude-obsidian-wiki-skill/tests/test_source_adapters.py
git commit -m "feat: add video collection source types"
```

### Task 2: Add Collection Expansion In Source Adapters

**Files:**
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/source_adapters.py`
- Test: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_source_adapters.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_expand_video_collection_urls_for_youtube_playlist(self) -> None:
    payload = '{"entries":[{"id":"abc123"},{"webpage_url":"https://www.youtube.com/watch?v=def456"}]}'
    with mock.patch.object(source_adapters, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
        source_adapters.subprocess,
        "run",
        return_value=mock.Mock(stdout=payload, stderr=""),
    ):
        urls = source_adapters.expand_video_collection_urls(
            source_id="video_playlist_youtube",
            input_value="https://www.youtube.com/playlist?list=PL123",
            work_dir=ROOT / ".tmp-tests" / "playlist-youtube",
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
    with mock.patch.object(source_adapters, "resolve_video_adapter_command", return_value=["yt-dlp"]), mock.patch.object(
        source_adapters.subprocess,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_source_adapters.SourceAdaptersTests.test_expand_video_collection_urls_for_youtube_playlist Claude-obsidian-wiki-skill.tests.test_source_adapters.SourceAdaptersTests.test_expand_video_collection_urls_for_bilibili_playlist
```

Expected:

```text
AttributeError: module 'source_adapters' has no attribute 'expand_video_collection_urls'
```

- [ ] **Step 3: Write minimal implementation**

```python
def normalize_collection_entry_url(source_id: str, entry: dict[str, object]) -> str | None:
    webpage_url = entry.get("webpage_url")
    if isinstance(webpage_url, str) and webpage_url.strip():
        return webpage_url.strip()
    url = entry.get("url")
    if isinstance(url, str) and url.strip():
        value = url.strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if source_id == "video_playlist_youtube":
            return f"https://www.youtube.com/watch?v={value}"
        if source_id == "video_playlist_bilibili" and value.startswith("BV"):
            return f"https://www.bilibili.com/video/{value}"
    item_id = entry.get("id")
    if isinstance(item_id, str) and item_id.strip():
        value = item_id.strip()
        if source_id == "video_playlist_youtube":
            return f"https://www.youtube.com/watch?v={value}"
        if source_id == "video_playlist_bilibili" and value.startswith("BV"):
            return f"https://www.bilibili.com/video/{value}"
    return None


def expand_video_collection_urls(*, source_id: str, input_value: str, work_dir: Path) -> list[str]:
    base_cmd = resolve_video_adapter_command()
    if not base_cmd:
        raise RuntimeError("Video adapter is not configured or not on PATH. Set WECHAT_WIKI_VIDEO_ADAPTER_BIN or install yt-dlp.")
    work_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [*base_cmd, "--flat-playlist", "--dump-single-json", input_value],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.loads(completed.stdout or "{}")
    entries = payload.get("entries", [])
    urls: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = normalize_collection_entry_url(source_id, entry)
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_source_adapters.SourceAdaptersTests.test_expand_video_collection_urls_for_youtube_playlist Claude-obsidian-wiki-skill.tests.test_source_adapters.SourceAdaptersTests.test_expand_video_collection_urls_for_bilibili_playlist
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```powershell
git add Claude-obsidian-wiki-skill/scripts/source_adapters.py Claude-obsidian-wiki-skill/tests/test_source_adapters.py
git commit -m "feat: add video collection expansion"
```

### Task 3: Add Import Job State File Support

**Files:**
- Create: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/import_jobs.py`
- Test: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_import_jobs.py`

- [ ] **Step 1: Write the failing test**

```python
def test_update_import_job_writes_completed_and_pending_items(self) -> None:
    vault = ROOT / ".tmp-tests" / "import-jobs-vault"
    path = import_jobs.ensure_import_job(
        vault=vault,
        source_kind="video_playlist_youtube",
        source_url="https://www.youtube.com/playlist?list=PL123",
        max_items_per_run=20,
    )

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
    self.assertIn("`abc123` | [[sources/video-a]]", job["body"])
    self.assertIn("`def456` | https://www.youtube.com/watch?v=def456", job["body"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_import_jobs
```

Expected:

```text
ModuleNotFoundError: No module named 'import_jobs'
```

- [ ] **Step 3: Write minimal implementation**

```python
def ensure_import_job(vault: Path, source_kind: str, source_url: str, max_items_per_run: int = 100) -> Path:
    jobs_dir = vault / "wiki" / "import-jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    slug = sanitize_job_slug(source_kind, source_url)
    path = jobs_dir / f"{slug}.md"
    if not path.exists():
        path.write_text(
            "---\n"
            f'title: "{source_kind} import job"\n'
            'type: "import-job"\n'
            f'source_kind: "{source_kind}"\n'
            f'source_url: "{source_url}"\n'
            'status: "active"\n'
            f'max_items_per_run: "{max_items_per_run}"\n'
            'discovered_count: "0"\n'
            'completed_count: "0"\n'
            'remaining_count: "0"\n'
            'last_run_at: ""\n'
            'graph_role: "working"\n'
            'graph_include: "false"\n'
            'lifecycle: "working"\n'
            "---\n\n"
            "# Import Job\n\n"
            "## 已完成视频\n\n"
            "- （空）\n\n"
            "## 待处理视频\n\n"
            "- （空）\n\n"
            "## 最近一次结果\n\n"
            "- 尚未运行。\n",
            encoding="utf-8",
        )
    return path
```

```python
def update_import_job(
    *,
    path: Path,
    source_kind: str,
    source_url: str,
    discovered_items: list[dict[str, str]],
    completed_items: list[dict[str, str]],
    remaining_items: list[dict[str, str]],
    status: str,
    processed_count: int,
    skipped_count: int,
    failed_count: int,
) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "---",
        f'title: "{source_kind} import job"',
        'type: "import-job"',
        f'source_kind: "{source_kind}"',
        f'source_url: "{source_url}"',
        f'status: "{status}"',
        'max_items_per_run: "100"',
        f'discovered_count: "{len(discovered_items)}"',
        f'completed_count: "{len(completed_items)}"',
        f'remaining_count: "{len(remaining_items)}"',
        f'last_run_at: "{timestamp}"',
        'graph_role: "working"',
        'graph_include: "false"',
        'lifecycle: "working"',
        "---",
        "",
        "# Import Job",
        "",
        "## 已完成视频",
        "",
    ]
    lines.extend(
        f"- `{item['video_id']}` | [[sources/{item['source_slug']}]]"
        for item in completed_items
    )
    if not completed_items:
        lines.append("- （空）")
    lines.extend(["", "## 待处理视频", ""])
    lines.extend(
        f"- `{item['video_id']}` | {item['video_url']}"
        for item in remaining_items
    )
    if not remaining_items:
        lines.append("- （空）")
    lines.extend(
        [
            "",
            "## 最近一次结果",
            "",
            f"- {timestamp} | processed={processed_count} | skipped={skipped_count} | failed={failed_count}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_import_jobs
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```powershell
git add Claude-obsidian-wiki-skill/scripts/import_jobs.py Claude-obsidian-wiki-skill/tests/test_import_jobs.py
git commit -m "feat: add import job state files"
```

### Task 4: Process Collection URLs In Main Entrypoint

**Files:**
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/wiki_ingest_wechat.py`
- Test: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_wiki_ingest_wechat_v2.py`

- [ ] **Step 1: Write the failing test**

```python
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
    ]) as expand_mock, mock.patch("source_adapters.run_adapter_for_source", return_value=adapter_result) as adapter_mock:
        articles = wiki_ingest_wechat.load_articles_from_urls(
            args,
            ["https://www.youtube.com/playlist?list=PL123"],
            input_dir,
        )

    expand_mock.assert_called_once()
    self.assertEqual(adapter_mock.call_count, 2)
    self.assertEqual(len(articles), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_wiki_ingest_wechat_v2.WikiIngestV2Tests.test_load_articles_from_urls_expands_video_playlist
```

Expected:

```text
FAIL or ERROR because playlist URLs are not expanded
```

- [ ] **Step 3: Write minimal implementation**

```python
def process_video_collection(
    *,
    args: argparse.Namespace,
    source_id: str,
    collection_url: str,
    input_dir: Path,
    staged_root: Path,
) -> list[Article]:
    expanded_urls = expand_video_collection_urls(
        source_id=source_id,
        input_value=collection_url,
        work_dir=input_dir / f"playlist-{uuid.uuid4().hex[:8]}",
    )
    articles: list[Article] = []
    for index, expanded_url in enumerate(expanded_urls[:100], start=1):
        expanded_source_id = match_source_from_url(expanded_url)
        if expanded_source_id not in {"video_url_youtube", "video_url_bilibili"}:
            continue
        adapter_result = run_adapter_for_source(
            source_id=expanded_source_id,
            input_value=expanded_url,
            work_dir=input_dir / f"adapter-{index}",
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
                f"Video adapter failed for {expanded_url}: {adapter_result.get('status')} - {adapter_result.get('reason', '')}"
            )
        articles.append(adapter_result_to_article(result=adapter_result, staging_root=staged_root))
    return articles
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_wiki_ingest_wechat_v2.WikiIngestV2Tests.test_load_articles_from_urls_expands_video_playlist
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```powershell
git add Claude-obsidian-wiki-skill/scripts/wiki_ingest_wechat.py Claude-obsidian-wiki-skill/tests/test_wiki_ingest_wechat_v2.py
git commit -m "feat: route video collections through main ingest"
```

### Task 5: Integrate Import Jobs With Max-100 Limit And Resume

**Files:**
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/wiki_ingest_wechat.py`
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/scripts/import_jobs.py`
- Test: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_import_jobs.py`
- Test: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/tests/test_wiki_ingest_wechat_v2.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_process_video_collection_limits_to_100_items(self) -> None:
    expanded = [f"https://www.youtube.com/watch?v={index}" for index in range(120)]
    with mock.patch("source_adapters.expand_video_collection_urls", return_value=expanded), mock.patch(
        "source_adapters.run_adapter_for_source",
        return_value=adapter_result,
    ) as adapter_mock:
        articles = wiki_ingest_wechat.process_video_collection(
            args=args,
            source_id="video_playlist_youtube",
            collection_url="https://www.youtube.com/playlist?list=PL123",
            input_dir=input_dir,
            staged_root=staged_root,
        )

    self.assertEqual(adapter_mock.call_count, 100)
    self.assertEqual(len(articles), 100)
```

```python
def test_process_video_collection_skips_completed_job_items(self) -> None:
    # prepare import job with completed video_id abc123
    # expanded URLs include abc123 and def456
    # expect only def456 to be processed
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_import_jobs Claude-obsidian-wiki-skill.tests.test_wiki_ingest_wechat_v2
```

Expected:

```text
FAIL because no import-job resume/max-20 logic exists yet
```

- [ ] **Step 3: Write minimal implementation**

```python
def process_video_collection(...):
    job_path = import_jobs.ensure_import_job(
        vault=vault,
        source_kind=source_id,
        source_url=collection_url,
        max_items_per_run=20,
    )
    job = import_jobs.load_import_job(job_path)
    completed_ids = import_jobs.completed_video_ids(job)
    expanded_urls = expand_video_collection_urls(...)
    deduped_urls = []
    seen: set[str] = set()
    for expanded_url in expanded_urls:
        video_id = extract_video_id_from_url(expanded_url)
        if not video_id or video_id in seen or video_id in completed_ids:
            continue
        seen.add(video_id)
        deduped_urls.append((video_id, expanded_url))
    batch = deduped_urls[:100]
    completed_items = list(import_jobs.completed_items(job))
    remaining_items = [{"video_id": video_id, "video_url": url} for video_id, url in deduped_urls[100:]]
    processed_count = 0
    skipped_count = 0
    failed_count = 0
    for video_id, expanded_url in batch:
        # reuse existing single-video adapter + ingest
        # append {"video_id": video_id, "source_slug": slug} on success
    import_jobs.update_import_job(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest Claude-obsidian-wiki-skill.tests.test_import_jobs Claude-obsidian-wiki-skill.tests.test_wiki_ingest_wechat_v2
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```powershell
git add Claude-obsidian-wiki-skill/scripts/import_jobs.py Claude-obsidian-wiki-skill/scripts/wiki_ingest_wechat.py Claude-obsidian-wiki-skill/tests/test_import_jobs.py Claude-obsidian-wiki-skill/tests/test_wiki_ingest_wechat_v2.py
git commit -m "feat: add resumable video collection imports"
```

### Task 6: Update Docs And Verify End-To-End

**Files:**
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/SKILL.md`
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/references/workflow.md`
- Modify: `D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/references/acceptance-baseline.md`

- [ ] **Step 1: Write the failing doc/test expectations**

```text
- SKILL.md must mention playlist/channel collection support and max 20 items per run.
- workflow.md must mention wiki/import-jobs and resume semantics.
- acceptance-baseline.md should reserve a slot for video-bi-01 once validated.
```

- [ ] **Step 2: Run code verification before doc edits**

Run:

```powershell
python -m unittest discover Claude-obsidian-wiki-skill\tests
```

Expected:

```text
OK
```

- [ ] **Step 3: Write minimal documentation updates**

```markdown
- 新增 `video_playlist_youtube`
- 新增 `video_playlist_bilibili`
- `wiki/import-jobs/` 保存批量导入状态
- 单次最多处理 20 条
- 已完成项不会重复下载
```

- [ ] **Step 4: Run final verification**

Run:

```powershell
python -m unittest discover Claude-obsidian-wiki-skill\tests
python -m py_compile Claude-obsidian-wiki-skill\scripts\source_registry.py Claude-obsidian-wiki-skill\scripts\source_adapters.py Claude-obsidian-wiki-skill\scripts\import_jobs.py Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py
```

Expected:

```text
All tests pass
No syntax errors
```

- [ ] **Step 5: Commit**

```powershell
git add Claude-obsidian-wiki-skill/SKILL.md Claude-obsidian-wiki-skill/references/workflow.md Claude-obsidian-wiki-skill/references/acceptance-baseline.md
git commit -m "docs: describe video collection import jobs"
```

## Spec Coverage Check

- 集合入口来源类型：Task 1
- `yt-dlp --flat-playlist --dump-single-json` 展开：Task 2
- `wiki/import-jobs/`：Task 3
- 主入口复用单视频链路：Task 4
- 单次最多 20 条：Task 5
- 已完成项不重复下载：Task 5
- 文档同步：Task 6

## Plan Self-Review

- Placeholder scan:
  - 唯一保留的注释性占位只出现在测试说明示例中，代码步骤没有 `TODO/TBD`
- Internal consistency:
  - 全部任务都围绕 `playlist/channel/list -> expand -> import-job -> single-video ingest`
- Scope check:
  - 只覆盖第一版集合导入，不包含“UP 主全部历史作品无限抓全”

