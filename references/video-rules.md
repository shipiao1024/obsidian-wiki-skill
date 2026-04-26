# Video Processing Rules

Rules for video source handling in the Claude-obsidian-wiki-skill pipeline. Read this file when processing YouTube/Bilibili/Douyin video URLs.

---

## Transcript Rules

- Do not treat Bilibili `danmaku.xml` as the primary transcript body.
- Keep `danmaku.xml` only as a weak-reference asset when no real subtitle is available.
- Prefer transcript sources in this order:
  - `platform_subtitle`
  - `embedded_subtitle`
  - `asr`
- `transcript_source = asr` is allowed to enter the pipeline, but its quality should not be promoted to `high` by default.
- Current ASR uses `faster-whisper`.
- Even when ASR text is long, default maximum quality rating is `acceptable`, avoiding mistaking machine transcription for high-confidence original text.

## Collection Protection Rules

Collection imports now default to a small window and should be treated as low-rate jobs, not bulk crawls.

Current protection knobs on the default supporting script are:

- `--collection-limit`
- `--collection-delay-seconds`
- `--collection-backoff-seconds`
- `--collection-jitter-seconds`
- `--collection-failure-threshold`
- `--collection-platform-cooldown-seconds`

When repeated failures trip the threshold, the corresponding `wiki/import-jobs/*.md` entry is marked `paused`.

Paused jobs record:
- `last_failure_reason`
- `cooldown_until`

During the cooldown window, the collection job should be skipped rather than retried immediately.

Semantics:
- Successes can maintain a fixed interval between items.
- Failures enter backoff with random jitter.
- When consecutive failures hit the threshold, the `import-job` enters `paused`.
- During cooldown, running again will skip the collection rather than continue requesting the platform.

This is basic risk-control + circuit-breaker cooldown, not a full anti-risk-control system. Current gaps include:
- No proxy / IP rotation
- No UA / header rotation
- No global platform-level scheduler

## Cookie Rules

The skill should auto-discover `Claude-obsidian-wiki-skill/cookies.txt` when no explicit video cookie env var is set.

On the first Bilibili request that hits login / 412 / browser-cookie-copy failures, do not stop at "需要 cookie".

For information-security reasons, the default path is user-managed:
- Ask the user to place or update a Netscape-format `cookies.txt` directly under `Claude-obsidian-wiki-skill/`
- Then retry; the skill will read that file by default
- Do not ask the user to paste raw cookie contents into the chat by default.

Secondary path:
- If the user already has a local `cookies.txt` elsewhere and explicitly wants help installing it
- Use `scripts/install_video_cookies.py` with that local file path to copy it into `Claude-obsidian-wiki-skill/cookies.txt`