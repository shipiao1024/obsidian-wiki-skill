from __future__ import annotations

import os
import re
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .types import AdapterStatus, AdapterResult, AssetItem, make_error_result, build_success_result
from .utils import parse_configured_command
from .quality import assess_video_quality
from env_compat import resolve_env


def resolve_video_adapter_command() -> list[str] | None:
    configured = resolve_env("KWIKI_VIDEO_ADAPTER_BIN")
    if configured:
        return parse_configured_command(configured)
    discovered = shutil.which("yt-dlp")
    if discovered:
        return [discovered]
    return None


def resolve_video_cookie_args() -> list[str]:
    """Return cookie args for yt-dlp: only uses cookies.txt if it exists."""
    cookies_file = resolve_env("KWIKI_VIDEO_COOKIES_FILE")
    if cookies_file:
        return ["--cookies", cookies_file]
    default_cookie_file = default_video_cookie_file()
    if default_cookie_file is not None:
        return ["--cookies", str(default_cookie_file)]
    return []


def _try_cdp_cookie_file(domains: list[str] | None = None) -> Path | None:
    """Extract cookies via Chrome DevTools Protocol and write a temp cookies.txt.

    Bypasses Windows-specific issues:
    1. Chrome/Edge lock the SQLite cookie database while running
    2. Chrome v130+ uses App-Bound Encryption (requires admin to decrypt via file)

    CDP extraction works because the browser itself decrypts cookies in memory.

    Returns the path to the temp file, or None if CDP extraction fails.
    """
    import tempfile
    try:
        from cdp_extract_cookies import try_extract_from_browser, cookies_to_netscape
    except ImportError:
        return None
    for browser in ["chrome", "edge"]:
        try:
            cookies = try_extract_from_browser(browser, domains, launch=False)
        except Exception:
            continue
        if cookies:
            tmp = Path(tempfile.mktemp(suffix=".txt", prefix="kwiki_cdp_cookies_"))
            tmp.write_text(cookies_to_netscape(cookies), encoding="utf-8")
            return tmp
    return None


def resolve_video_cookie_arg_variants(source_id: str | None = None) -> list[list[str]]:
    variants: list[list[str]] = []
    browser = resolve_env("KWIKI_VIDEO_COOKIES_FROM_BROWSER")
    if browser:
        variants.append(["--cookies-from-browser", browser])
    cookie_args = resolve_video_cookie_args()
    if cookie_args:
        variants.append(cookie_args)
    # CDP fallback: extract cookies from running browser via DevTools Protocol
    cdp_domains = ["douyin.com", "bilibili.com"] if source_id and "douyin" in source_id else None
    cdp_cookie_file = _try_cdp_cookie_file(domains=cdp_domains)
    if cdp_cookie_file:
        variants.append(["--cookies", str(cdp_cookie_file)])
    variants.append([])
    return variants


def default_video_cookie_file() -> Path | None:
    candidate = Path(__file__).resolve().parents[2] / "cookies.txt"
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def default_video_cookie_files(source_id: str | None = None) -> list[Path]:
    del source_id
    cookie_file = default_video_cookie_file()
    return [cookie_file] if cookie_file is not None else []


def is_browser_cookie_copy_error(exc: subprocess.CalledProcessError) -> bool:
    message = " ".join(
        part
        for part in [
            str(getattr(exc, "stdout", "") or ""),
            str(getattr(exc, "stderr", "") or ""),
            str(exc),
        ]
        if part
    ).lower()
    return "could not copy" in message and "cookie" in message


def normalize_video_fetch_url(source_id: str, input_value: str) -> str:
    if source_id != "video_url_douyin":
        return input_value
    parsed = urlparse(input_value)
    modal_id = (parse_qs(parsed.query).get("modal_id") or [""])[0].strip()
    if modal_id.isdigit():
        return f"https://www.douyin.com/video/{modal_id}"
    return input_value




def classify_video_adapter_failure(exc: subprocess.CalledProcessError) -> tuple[AdapterStatus, str]:
    parts = [
        str(getattr(exc, "stdout", "") or ""),
        str(getattr(exc, "stderr", "") or ""),
        str(exc),
    ]
    message = " ".join(part for part in parts if part).strip()
    lowered = message.lower()

    if "http error 412" in lowered or "precondition failed" in lowered:
        return "platform_blocked", f"Video adapter was blocked by the platform (likely needs cookies.txt): {message}"
    if "sign in" in lowered or "login" in lowered or "cookie" in lowered:
        return "platform_blocked", f"Video adapter likely requires authenticated cookies.txt: {message}"
    return "runtime_failed", f"Video adapter failed: {message or exc}"


def should_fallback_to_douyin_browser_capture(status: AdapterStatus, reason: str) -> bool:
    lowered = reason.lower()
    return status in {"platform_blocked", "runtime_failed"} and (
        "fresh cookies" in lowered
        or "failed to parse json" in lowered
        or "cookie" in lowered
        or "authenticated" in lowered
        or "login" in lowered
    )


def subtitle_to_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def danmaku_xml_to_text(text: str) -> str:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ""
    items: list[str] = []
    seen: set[str] = set()
    for node in root.findall(".//d"):
        value = (node.text or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        items.append(value)
    return "\n".join(items).strip()


def _split_audio_pyav(audio_path: Path, segment_seconds: int = 1800, work_dir: Path | None = None) -> list[Path]:
    """Split a long audio file into WAV segments using PyAV to avoid OOM during ASR."""
    try:
        import av
    except ImportError:
        return []
    out_dir = work_dir or audio_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        container = av.open(str(audio_path))
        stream = container.streams.audio[0]
        sample_rate = stream.sample_rate or 16000
        channels = stream.codec_context.channels or 1
        # Re-encode to 16kHz mono WAV for whisper
        out_sample_rate = 16000
        out_channels = 1
        chunk_idx = 0
        outputs: list[Path] = []
        current_pts = 0
        segment_pts = segment_seconds * stream.time_base.denominator // stream.time_base.numerator if stream.time_base.denominator else segment_seconds * sample_rate
        # Resampler for 16kHz mono
        resampler = av.AudioResampler(format="s16", layout="mono", rate=out_sample_rate)
        # Collect frames into segments
        frame_buffer: list = []
        buffer_pts_start = 0
        for frame in container.decode(audio=0):
            frame = resampler.resample(frame)
            for f in frame:
                frame_buffer.append(f)
                f_pts = f.pts if f.pts is not None else 0
                f_time = float(f_pts * f.time_base) if f.time_base else 0.0
                if f_time - buffer_pts_start >= segment_seconds:
                    chunk_path = out_dir / f"chunk_{chunk_idx:03d}.wav"
                    out_container = av.open(str(chunk_path), mode="w")
                    out_stream = out_container.add_stream("pcm_s16le", rate=out_sample_rate)
                    out_stream.layout = "mono"
                    for buf_frame in frame_buffer:
                        for packet in out_stream.encode(buf_frame):
                            out_container.mux(packet)
                    for packet in out_stream.encode():
                        out_container.mux(packet)
                    out_container.close()
                    outputs.append(chunk_path)
                    chunk_idx += 1
                    frame_buffer = []
                    buffer_pts_start = f_time
        # Flush remaining
        if frame_buffer:
            chunk_path = out_dir / f"chunk_{chunk_idx:03d}.wav"
            out_container = av.open(str(chunk_path), mode="w")
            out_stream = out_container.add_stream("pcm_s16le", rate=out_sample_rate)
            out_stream.layout = "mono"
            for buf_frame in frame_buffer:
                for packet in out_stream.encode(buf_frame):
                    out_container.mux(packet)
            for packet in out_stream.encode():
                out_container.mux(packet)
            out_container.close()
            outputs.append(chunk_path)
        container.close()
        return outputs
    except Exception:
        return []


def _audio_duration_pyav(audio_path: Path) -> float:
    """Get audio duration in seconds using PyAV."""
    try:
        import av
        container = av.open(str(audio_path))
        duration = 0.0
        stream = container.streams.audio[0]
        if stream.duration and stream.time_base:
            duration = float(stream.duration * stream.time_base)
        if duration <= 0:
            duration = float(container.duration) / 1_000_000 if container.duration else 0.0
        container.close()
        return duration
    except Exception:
        return 0.0


def transcribe_audio_with_asr(audio_path: Path) -> str:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError("ASR dependency missing: faster-whisper") from exc

    # Auto-select model: use tiny for long audio (>10 min) unless explicitly overridden
    duration = _audio_duration_pyav(audio_path)
    env_model = os.environ.get("KWIKI_ASR_MODEL") or os.environ.get("WECHAT_WIKI_ASR_MODEL")
    if env_model:
        model_size = env_model
    elif duration > 600:  # 10 minutes
        model_size = "tiny"
    else:
        model_size = "small"
    compute_type = resolve_env("KWIKI_ASR_COMPUTE_TYPE", "int8")
    model = WhisperModel(model_size, device="cpu", compute_type=compute_type)

    # For long audio (>30 min), split into chunks to avoid OOM
    segment_minutes = int(resolve_env("KWIKI_ASR_CHUNK_MINUTES", "30"))
    chunks: list[Path] = []
    chunk_dir: Path | None = None
    if duration > segment_minutes * 60:
        chunk_dir = audio_path.parent / "_asr_chunks"
        chunks = _split_audio_pyav(audio_path, segment_seconds=segment_minutes * 60, work_dir=chunk_dir)
        if not chunks:
            chunks = [audio_path]
    else:
        chunks = [audio_path]

    parts: list[str] = []
    for chunk in chunks:
        segments_iter, _info = model.transcribe(
            str(chunk),
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )
        for segment in segments_iter:
            text = getattr(segment, "text", "") or ""
            text = text.strip()
            if text:
                parts.append(text)

    # Clean up chunk directory if we created it
    if chunk_dir and chunk_dir.exists():
        shutil.rmtree(chunk_dir, ignore_errors=True)

    return "\n".join(parts).strip()


def node_command() -> list[str] | None:
    configured = resolve_env("KWIKI_NODE_BIN")
    if configured:
        return parse_configured_command(configured)
    discovered = shutil.which("node")
    if discovered:
        return [discovered]
    return None


def run_douyin_browser_capture(*, input_value: str, work_dir: Path, cookies_file: Path | None = None) -> dict[str, object]:
    base_cmd = node_command()
    if not base_cmd:
        return {
            "status": "dependency_missing",
            "reason": "Node.js is required for Douyin browser capture fallback.",
        }
    script_path = Path(__file__).resolve().parents[1] / "douyin_browser_capture.js"
    if not script_path.exists():
        return {
            "status": "dependency_missing",
            "reason": f"Douyin browser capture script not found: {script_path}",
        }
    cmd = [
        *base_cmd,
        str(script_path),
        "--url",
        normalize_video_fetch_url("video_url_douyin", input_value),
        "--output-dir",
        str(work_dir),
    ]
    if cookies_file is not None:
        cmd.extend(["--cookies", str(cookies_file)])
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        return {"status": "dependency_missing", "reason": f"Node.js executable not found: {exc}"}
    except subprocess.CalledProcessError as exc:
        message = " ".join(part for part in [exc.stdout or "", exc.stderr or "", str(exc)] if part).strip()
        return {"status": "runtime_failed", "reason": f"Douyin browser capture failed: {message}"}

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"status": "runtime_failed", "reason": f"Douyin browser capture returned invalid JSON: {exc}"}
    if not isinstance(payload, dict):
        return {"status": "runtime_failed", "reason": "Douyin browser capture returned a non-object payload."}
    return payload


def build_douyin_browser_capture_result(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
) -> AdapterResult:
    cookie_files = default_video_cookie_files(source_id)
    capture = run_douyin_browser_capture(
        input_value=input_value,
        work_dir=work_dir,
        cookies_file=cookie_files[0] if cookie_files else None,
    )
    if capture.get("status") != "ok":
        return make_error_result(
            status=str(capture.get("status", "runtime_failed")),  # type: ignore[arg-type]
            reason=str(capture.get("reason", "Douyin browser capture failed.")),
            input_kind="url",
            source_id=source_id,
            adapter_name="douyin-browser-capture",
        )

    video_path = Path(str(capture.get("video_path", "")))
    if not video_path.exists() or not video_path.is_file():
        return make_error_result(
            status="empty_result",
            reason="Douyin browser capture did not produce a local video file.",
            input_kind="url",
            source_id=source_id,
            adapter_name="douyin-browser-capture",
        )
    try:
        asr_text = transcribe_audio_with_asr(video_path)
    except RuntimeError as exc:
        return make_error_result(
            status="dependency_missing",
            reason=str(exc),
            input_kind="url",
            source_id=source_id,
            adapter_name="douyin-browser-capture",
        )
    except Exception as exc:
        return make_error_result(
            status="runtime_failed",
            reason=f"ASR transcription failed for Douyin browser capture: {exc}",
            input_kind="url",
            source_id=source_id,
            adapter_name="douyin-browser-capture",
        )
    if not asr_text.strip():
        return make_error_result(
            status="empty_result",
            reason="Douyin browser capture succeeded but ASR produced no transcript.",
            input_kind="url",
            source_id=source_id,
            adapter_name="douyin-browser-capture",
        )
    title = str(capture.get("title", "")).strip() or "Douyin video"
    author = str(capture.get("author", "")).strip()
    date = str(capture.get("date", "")).strip()
    return build_success_result(
        input_kind="url",
        source_id=source_id,
        adapter_name="douyin-browser-capture",
        title=title,
        source_kind="douyin",
        markdown_body=asr_text,
        plain_text_body=asr_text,
        source_url=input_value,
        author=author,
        date=date,
        quality=assess_video_quality(
            title=title,
            plain_text_body=asr_text,
            transcript_source="asr",
        ),
        assets=[{"local_path": str(video_path), "media_type": "video"}],
        extra={
            "audio_path": str(video_path),
            "subtitle_source": "asr",
            "browser_capture_video_url": str(capture.get("video_url", "")).strip(),
        },
    )


def download_audio_for_asr(
    *,
    base_cmd: list[str],
    input_value: str,
    work_dir: Path,
) -> tuple[AdapterStatus, str] | None:
    cmd = [
        *base_cmd,
        *resolve_video_cookie_args(),
        "--no-playlist",
        "-f",
        "bestaudio",
        "-o",
        str(work_dir / "video-audio.%(ext)s"),
        input_value,
    ]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        return "dependency_missing", f"Video adapter executable not found: {exc}"
    except subprocess.CalledProcessError as exc:
        return classify_video_adapter_failure(exc)
    return None


def load_video_metadata(work_dir: Path) -> dict[str, str]:
    candidates = sorted([*work_dir.glob("*.info.json"), *work_dir.rglob("*.info.json")])
    if not candidates:
        return {}
    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
    except Exception:
        return {}
    metadata: dict[str, str] = {}
    title = data.get("title")
    uploader = data.get("uploader")
    upload_date = data.get("upload_date")
    if isinstance(title, str) and title.strip():
        metadata["title"] = title.strip()
    if isinstance(uploader, str) and uploader.strip():
        metadata["author"] = uploader.strip()
    if isinstance(upload_date, str) and upload_date.strip():
        metadata["date"] = upload_date.strip()
    return metadata


def extract_embedded_subtitle_text(work_dir: Path) -> tuple[str, str] | None:
    candidates = sorted([*work_dir.glob("*.info.json"), *work_dir.rglob("*.info.json")])
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        subtitles = data.get("subtitles")
        if not isinstance(subtitles, dict):
            continue
        for language, entries in subtitles.items():
            if not isinstance(language, str) or not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                embedded = entry.get("data")
                if not isinstance(embedded, str) or not embedded.strip():
                    continue
                plain_text = subtitle_to_text(embedded)
                if plain_text:
                    return plain_text, language
    return None


def run_video_adapter(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
    options: dict[str, object] | None = None,
) -> AdapterResult:
    del options
    work_dir.mkdir(parents=True, exist_ok=True)
    base_cmd = resolve_video_adapter_command()
    if not base_cmd:
        return make_error_result(
            status="dependency_missing",
            reason="Video adapter is not configured or not on PATH. Set WECHAT_WIKI_VIDEO_ADAPTER_BIN or install yt-dlp.",
            input_kind="url",
            source_id=source_id,
            adapter_name="yt-dlp",
        )
    base_args = [
        "--no-playlist",
        "--write-subs",
        "--write-auto-subs",
        "--write-info-json",
        "--skip-download",
        "-o",
        str(work_dir / "video"),
        normalize_video_fetch_url(source_id, input_value),
    ]
    last_called_process_error: subprocess.CalledProcessError | None = None
    for cookie_args in resolve_video_cookie_arg_variants(source_id):
        cmd = [*base_cmd, *cookie_args, *base_args]
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            last_called_process_error = None
            break
        except FileNotFoundError as exc:
            return make_error_result(
                status="dependency_missing",
                reason=f"Video adapter executable not found: {exc}",
                input_kind="url",
                source_id=source_id,
                adapter_name="yt-dlp",
            )
        except subprocess.CalledProcessError as exc:
            last_called_process_error = exc
            if "--cookies-from-browser" in cmd and is_browser_cookie_copy_error(exc):
                explicit_cookie_file = resolve_env("KWIKI_VIDEO_COOKIES_FILE")
                if explicit_cookie_file:
                    continue
                return make_error_result(
                    status="invalid_input",
                    reason=(
                        "Video adapter could not read browser cookies. Export a Netscape cookies.txt file and set "
                        "WECHAT_WIKI_VIDEO_COOKIES_FILE."
                    ),
                    input_kind="url",
                    source_id=source_id,
                    adapter_name="yt-dlp",
                )
            status, reason = classify_video_adapter_failure(exc)
            if source_id == "video_url_douyin" and should_fallback_to_douyin_browser_capture(status, reason):
                return build_douyin_browser_capture_result(
                    source_id=source_id,
                    input_value=input_value,
                    work_dir=work_dir,
                )
            return make_error_result(
                status=status,
                reason=reason,
                input_kind="url",
                source_id=source_id,
                adapter_name="yt-dlp",
            )
    if last_called_process_error is not None:
        status, reason = classify_video_adapter_failure(last_called_process_error)
        if source_id == "video_url_douyin" and should_fallback_to_douyin_browser_capture(status, reason):
            return build_douyin_browser_capture_result(
                source_id=source_id,
                input_value=input_value,
                work_dir=work_dir,
            )
        return make_error_result(
            status=status,
            reason=reason,
            input_kind="url",
            source_id=source_id,
            adapter_name="yt-dlp",
        )

    subtitle_candidates = sorted(
        [*work_dir.glob("*.srt"), *work_dir.glob("*.vtt"), *work_dir.glob("*.txt"), *work_dir.glob("*.xml")]
    )
    if not subtitle_candidates:
        subtitle_candidates = sorted(path for path in work_dir.rglob("*") if path.suffix.lower() in {".srt", ".vtt", ".txt", ".xml"})
    source_kind = "youtube" if source_id == "video_url_youtube" else ("douyin" if source_id == "video_url_douyin" else "bilibili")
    danmaku_assets: list[AssetItem] = []
    if subtitle_candidates:
        for subtitle_path in subtitle_candidates:
            subtitle_raw = subtitle_path.read_text(encoding="utf-8")
            if subtitle_path.suffix.lower() == ".xml":
                danmaku_assets.append({"local_path": str(subtitle_path), "media_type": "subtitle"})
                continue
            plain_text = subtitle_to_text(subtitle_raw)
            subtitle_source = "platform"
            if plain_text:
                video_meta = load_video_metadata(work_dir)
                title = video_meta.get("title") or subtitle_path.stem.split(".")[0] or "video"
                return build_success_result(
                    input_kind="url",
                    source_id=source_id,
                    adapter_name="yt-dlp",
                    title=title,
                    source_kind=source_kind,
                    markdown_body=plain_text,
                    plain_text_body=plain_text,
                    source_url=input_value,
                    author=video_meta.get("author"),
                    date=video_meta.get("date"),
                    quality=assess_video_quality(
                        title=title,
                        plain_text_body=plain_text,
                        transcript_source=subtitle_source,
                    ),
                    assets=[{"local_path": str(subtitle_path), "media_type": "subtitle"}, *danmaku_assets],
                    extra={"subtitle_path": str(subtitle_path), "subtitle_source": subtitle_source},
                )

    embedded_subtitle = extract_embedded_subtitle_text(work_dir)
    if embedded_subtitle:
        plain_text, language = embedded_subtitle
        video_meta = load_video_metadata(work_dir)
        title = video_meta.get("title") or "video"
        return build_success_result(
            input_kind="url",
            source_id=source_id,
            adapter_name="yt-dlp",
            title=title,
            source_kind=source_kind,
            markdown_body=plain_text,
            plain_text_body=plain_text,
            source_url=input_value,
            author=video_meta.get("author"),
            date=video_meta.get("date"),
            language=language,
            quality=assess_video_quality(
                title=title,
                plain_text_body=plain_text,
                transcript_source="embedded_subtitle",
            ),
            assets=[],
            extra={"subtitle_source": "embedded-metadata", "subtitle_language": language},
        )

    if source_kind in {"bilibili", "douyin"}:
        download_error = download_audio_for_asr(
            base_cmd=base_cmd,
            input_value=input_value,
            work_dir=work_dir,
        )
        if download_error is not None:
            status, reason = download_error
            return make_error_result(
                status=status,
                reason=reason,
                input_kind="url",
                source_id=source_id,
                adapter_name="yt-dlp",
            )

    audio_candidates = sorted(
        [*work_dir.glob("*.mp3"), *work_dir.glob("*.m4a"), *work_dir.glob("*.wav"), *work_dir.glob("*.webm"), *work_dir.glob("*.opus")]
    )
    if not audio_candidates:
        audio_candidates = sorted(path for path in work_dir.rglob("*") if path.suffix.lower() in {".mp3", ".m4a", ".wav", ".webm", ".opus"})
    if audio_candidates:
        audio_path = audio_candidates[0]
        try:
            asr_text = transcribe_audio_with_asr(audio_path)
        except RuntimeError as exc:
            return make_error_result(
                status="dependency_missing",
                reason=str(exc),
                input_kind="url",
                source_id=source_id,
                adapter_name="yt-dlp",
            )
        except Exception as exc:
            return make_error_result(
                status="runtime_failed",
                reason=f"ASR transcription failed: {exc}",
                input_kind="url",
                source_id=source_id,
                adapter_name="yt-dlp",
            )
        if asr_text:
            video_meta = load_video_metadata(work_dir)
            title = video_meta.get("title") or audio_path.stem.split(".")[0] or "video"
            return build_success_result(
                input_kind="url",
                source_id=source_id,
                adapter_name="yt-dlp",
                title=title,
                source_kind=source_kind,
                markdown_body=asr_text,
                plain_text_body=asr_text,
                source_url=input_value,
                author=video_meta.get("author"),
                date=video_meta.get("date"),
                quality=assess_video_quality(
                    title=title,
                    plain_text_body=asr_text,
                    transcript_source="asr",
                ),
                assets=[{"local_path": str(audio_path), "media_type": "audio"}, *danmaku_assets],
                extra={
                    "audio_path": str(audio_path),
                    "subtitle_source": "asr",
                    **({"danmaku_path": danmaku_assets[0]["local_path"]} if danmaku_assets else {}),
                },
            )

    return make_error_result(
        status="empty_result",
        reason="Video adapter produced no subtitle/transcript files.",
        input_kind="url",
        source_id=source_id,
        adapter_name="yt-dlp",
    )