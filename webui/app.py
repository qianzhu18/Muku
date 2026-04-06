import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

try:
    from transcript_pipeline import (
        TranscriptSegment,
        build_plain_text,
        coerce_segments,
        load_segments_from_subtitle_file,
        normalize_segments,
        parse_srt_segments,
        render_markdown_note,
    )
except ImportError:  # pragma: no cover - import style depends on launch mode
    from webui.transcript_pipeline import (
        TranscriptSegment,
        build_plain_text,
        coerce_segments,
        load_segments_from_subtitle_file,
        normalize_segments,
        parse_srt_segments,
        render_markdown_note,
    )

try:
    import yt_dlp
except ImportError as exc:
    raise SystemExit("yt-dlp is not installed.") from exc

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

APP_TITLE = "Downloader by Qianzhu"
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/downloads")
COOKIES_PATH = os.environ.get("COOKIES_PATH", "")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "auto")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "auto").strip().lower()
WHISPER_BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "8"))
WHISPER_BEST_OF = int(os.environ.get("WHISPER_BEST_OF", "8"))
ASR_CONCURRENCY = int(os.environ.get("ASR_CONCURRENCY", "1"))
WHISPER_CACHE_DIR = os.environ.get(
    "WHISPER_CACHE_DIR", str(Path(DOWNLOAD_DIR) / ".whisper-model-cache")
)
TRANSCRIPT_CACHE_DIR = os.environ.get(
    "TRANSCRIPT_CACHE_DIR", str(Path(DOWNLOAD_DIR) / ".transcript-cache")
)
TRANSCRIPT_PARAGRAPH_CHARS = int(os.environ.get("TRANSCRIPT_PARAGRAPH_CHARS", "220"))
TRANSCRIPT_PARAGRAPH_GAP_SECONDS = float(
    os.environ.get("TRANSCRIPT_PARAGRAPH_GAP_SECONDS", "1.6")
)
PREFER_PLATFORM_SUBTITLES = os.environ.get("PREFER_PLATFORM_SUBTITLES", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
SUBTITLE_LANGS = [
    item.strip()
    for item in os.environ.get(
        "SUBTITLE_LANGS", "zh-Hans,zh-CN,zh,zh-Hant,en,en-US,en-GB"
    ).split(",")
    if item.strip()
]
ASR_PREPROCESS_ENABLED = os.environ.get("ASR_PREPROCESS_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
ASR_AUDIO_FILTER = os.environ.get("ASR_AUDIO_FILTER", "highpass=f=80,lowpass=f=7600,afftdn,loudnorm")
ASR_SAMPLE_RATE = int(os.environ.get("ASR_SAMPLE_RATE", "16000"))
TRANSCRIPTION_BACKEND = os.environ.get("TRANSCRIPTION_BACKEND", "auto").strip().lower()
TRANSCRIPTION_FALLBACK_LOCAL = os.environ.get("TRANSCRIPTION_FALLBACK_LOCAL", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
REMOTE_MLX_URL = os.environ.get("REMOTE_MLX_URL", "").rstrip("/")
REMOTE_MLX_TIMEOUT = int(os.environ.get("REMOTE_MLX_TIMEOUT", "1800"))
REMOTE_MLX_MODEL = os.environ.get("REMOTE_MLX_MODEL", "large-v3").strip() or "large-v3"
REMOTE_MLX_BATCH_SIZE = int(os.environ.get("REMOTE_MLX_BATCH_SIZE", "12"))
REMOTE_MLX_QUANT = os.environ.get("REMOTE_MLX_QUANT", "4bit").strip() or None
LOCAL_AUDIO_MAX_MB = int(os.environ.get("LOCAL_AUDIO_MAX_MB", "1024"))
LOCAL_AUDIO_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}
LOCAL_AUDIO_ACCEPT = ",".join(sorted(LOCAL_AUDIO_EXTENSIONS))
KNOWLEDGE_BASE_PRESET = "转 Markdown 知识库（MP3 + 逐字稿）"

TRANSCRIPT_PRESET = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
    "transcribe": True,
}

FORMAT_PRESETS = {
    "Best Video (MP4)": {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    },
    "Best Audio (MP3)": {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    },
    "4K / High Res": {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
    },
    KNOWLEDGE_BASE_PRESET: dict(TRANSCRIPT_PRESET),
    "MP3 + 字幕稿 (Whisper)": dict(TRANSCRIPT_PRESET),
    "转字幕稿（准确率优先·自动识别）": dict(TRANSCRIPT_PRESET),
}
HIDDEN_PRESETS = {"MP3 + 字幕稿 (Whisper)", "转字幕稿（准确率优先·自动识别）"}
DEFAULT_PRESET = os.environ.get("DEFAULT_PRESET", KNOWLEDGE_BASE_PRESET)
if DEFAULT_PRESET not in FORMAT_PRESETS:
    DEFAULT_PRESET = "Best Video (MP4)"


@dataclass
class Job:
    job_id: str
    url: str
    preset: str
    use_cookies: bool
    source_kind: str = "download"
    local_audio_paths: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    title: str = "Fetching info..."
    status: str = "Queued"
    progress: float = 0.0
    done: bool = False
    error: str | None = None
    output_dir: str | None = None
    artifacts: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass(frozen=True)
class TranscriptArtifacts:
    files: list[Path]
    transcript_source: str
    transcript_source_detail: str | None
    transcript_language: str
    transcript_model: str


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = max(1, LOCAL_AUDIO_MAX_MB) * 1024 * 1024
jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
whisper_model_lock = threading.Lock()
whisper_slots = threading.Semaphore(max(1, ASR_CONCURRENCY))
whisper_model = None
active_compute_type = None


def set_job_status(job: Job | None, status: str, progress: float | None = None):
    if job is None:
        return
    with job.lock:
        job.status = status
        if progress is not None:
            job.progress = progress


def progress_hook(job):
    def hook(data):
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes")
            with job.lock:
                if total and downloaded:
                    job.progress = min((downloaded / total) * 100, 95)
                job.status = (
                    data.get("_percent_str", "0%").strip()
                    + " "
                    + data.get("_speed_str", "").strip()
                ).strip()
                if data.get("info_dict"):
                    job.title = data["info_dict"].get("title", job.title)
        elif status == "finished":
            set_job_status(job, "Processing...", 95)

    return hook


def sanitize_filename(name: str, max_length: int = 110) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length]


def ensure_unique_path(target: Path) -> Path:
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def ensure_unique_dir(target: Path) -> Path:
    if not target.exists():
        return target

    index = 1
    while True:
        candidate = target.parent / f"{target.name} ({index})"
        if not candidate.exists():
            return candidate
        index += 1


def move_outputs(temp_dir: Path, final_dir: Path) -> list[Path]:
    moved = []
    for file_path in sorted(temp_dir.rglob("*")):
        if not file_path.is_file():
            continue
        destination = ensure_unique_path(final_dir / file_path.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(destination))
        moved.append(destination)
    return moved


def is_supported_local_audio(filename: str) -> bool:
    return Path(filename or "").suffix.lower() in LOCAL_AUDIO_EXTENSIONS


def save_uploaded_audio(file_storage, target_dir: Path) -> Path:
    original_name = Path(str(file_storage.filename or "")).name
    if not original_name:
        raise ValueError("Uploaded audio file is missing a filename.")
    if not is_supported_local_audio(original_name):
        raise ValueError(
            f"Unsupported audio format: {original_name}. Allowed: {', '.join(sorted(LOCAL_AUDIO_EXTENSIONS))}"
        )

    suffix = Path(original_name).suffix.lower()
    stem = sanitize_filename(Path(original_name).stem, max_length=180)
    destination = ensure_unique_path(target_dir / f"{stem}{suffix}")
    file_storage.save(destination)
    if not destination.exists() or destination.stat().st_size <= 0:
        raise ValueError(f"Uploaded audio is empty: {original_name}")
    return destination


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(path: Path, segments: list) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index, segment in enumerate(segments, start=1):
            handle.write(f"{index}\n")
            handle.write(
                f"{format_srt_timestamp(segment.start)} --> {format_srt_timestamp(segment.end)}\n"
            )
            handle.write(f"{segment.text.strip()}\n\n")


def format_media_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_title_and_id_from_media(audio_file: Path, fallback_title: str, fallback_id: str) -> tuple[str, str]:
    match = re.match(r"^(?P<title>.+?) \[(?P<id>[^\]]+)\]$", audio_file.stem)
    if match:
        return match.group("title"), match.group("id")
    return fallback_title, fallback_id


def infer_source_platform(info: dict | None, fallback_url: str) -> str:
    if isinstance(info, dict):
        platform = (
            info.get("extractor_key")
            or info.get("extractor")
            or info.get("webpage_url_domain")
        )
        if platform:
            mapping = {
                "youtube": "YouTube",
                "youtu": "YouTube",
                "bilibili": "Bilibili",
            }
            normalized = str(platform).strip()
            return mapping.get(normalized.lower(), normalized)

    hostname = urlparse(fallback_url).netloc.lower()
    if "youtube.com" in hostname or "youtu.be" in hostname:
        return "YouTube"
    if "bilibili.com" in hostname or "b23.tv" in hostname:
        return "Bilibili"
    return hostname or "Unknown"


def parse_compute_types() -> list[str]:
    if WHISPER_COMPUTE_TYPE.strip().lower() == "auto":
        return ["float16", "int8_float16", "int8"]
    values = [item.strip() for item in WHISPER_COMPUTE_TYPE.split(",") if item.strip()]
    return values or ["int8"]


def get_whisper_model():
    global whisper_model, active_compute_type

    if WhisperModel is None:
        raise RuntimeError(
            "faster-whisper is not installed. Please install dependencies and retry."
        )

    with whisper_model_lock:
        if whisper_model is not None:
            return whisper_model

        model_cache_root = Path(WHISPER_CACHE_DIR)
        model_cache_root.mkdir(parents=True, exist_ok=True)

        last_error = None
        for compute_type in parse_compute_types():
            try:
                whisper_model = WhisperModel(
                    WHISPER_MODEL,
                    device=WHISPER_DEVICE,
                    compute_type=compute_type,
                    download_root=str(model_cache_root),
                )
                active_compute_type = compute_type
                return whisper_model
            except Exception as exc:  # pragma: no cover - hardware dependent
                last_error = exc

        raise RuntimeError(f"Failed to load Whisper model: {last_error}")


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_cache_key(audio_file: Path, source_key: str | None, backend: str | None = None) -> str:
    if source_key:
        raw = source_key
    else:
        raw = file_sha1(audio_file)

    language_part = "auto" if WHISPER_LANGUAGE in {"", "auto"} else WHISPER_LANGUAGE
    backend_signature = backend or effective_transcription_backend()
    if backend_signature == "remote_mlx":
        backend_signature = (
            f"remote_mlx:model={REMOTE_MLX_MODEL}|quant={REMOTE_MLX_QUANT or 'base'}"
            f"|batch={REMOTE_MLX_BATCH_SIZE}"
        )
    else:
        backend_signature = (
            f"local:model={WHISPER_MODEL}|beam={WHISPER_BEAM_SIZE}|best_of={WHISPER_BEST_OF}"
            f"|preprocess={int(ASR_PREPROCESS_ENABLED)}|filter={ASR_AUDIO_FILTER}|sr={ASR_SAMPLE_RATE}"
        )
    payload = (
        f"{raw}|lang={language_part}|backend={backend_signature}"
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def effective_transcription_backend() -> str:
    if TRANSCRIPTION_BACKEND == "remote_mlx":
        return "remote_mlx"
    if TRANSCRIPTION_BACKEND == "auto" and REMOTE_MLX_URL:
        return "remote_mlx"
    return "local"


def container_relative_audio_path(audio_file: Path) -> str | None:
    try:
        resolved = audio_file.resolve()
        download_root = Path(DOWNLOAD_DIR).resolve()
        return str(resolved.relative_to(download_root)).replace(os.sep, "/")
    except Exception:
        return None


def subtitle_language_preferences() -> list[str]:
    preferred: list[str] = []
    if WHISPER_LANGUAGE not in {"", "auto"}:
        preferred.append(WHISPER_LANGUAGE)
    for item in SUBTITLE_LANGS:
        if item not in preferred:
            preferred.append(item)
    return preferred


def list_subtitle_files(temp_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in temp_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".srt", ".vtt"} and ".raw." not in path.name
    )


def score_subtitle_file(audio_file: Path, subtitle_file: Path) -> int:
    name = subtitle_file.name.lower()
    score = 0
    if name.startswith(audio_file.stem.lower()):
        score += 500

    for index, language in enumerate(subtitle_language_preferences()):
        token = language.lower()
        if f".{token}." in name or name.endswith(f".{token}{subtitle_file.suffix.lower()}"):
            score += 200 - index
            break

    if subtitle_file.suffix.lower() == ".srt":
        score += 20
    if any(token in name for token in ("auto", "automatic")):
        score -= 10
    if "live_chat" in name:
        score -= 1000
    return score


def find_best_subtitle_file(audio_file: Path, subtitle_files: list[Path]) -> Path | None:
    if not subtitle_files:
        return None

    stem = audio_file.stem.lower()
    matching = [
        path
        for path in subtitle_files
        if path.name.lower().startswith(stem) or f"[{stem.split('[')[-1]}" in path.name.lower()
    ]
    if not matching:
        return None
    return max(matching, key=lambda path: score_subtitle_file(audio_file, path), default=None)


def detect_subtitle_language(path: Path) -> str:
    suffixes = [item.lstrip(".") for item in path.suffixes]
    if len(suffixes) >= 2:
        return suffixes[-2]
    return "subtitle"


def prepare_audio_for_asr(audio_file: Path, job: Job | None) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if not ASR_PREPROCESS_ENABLED or not shutil.which("ffmpeg"):
        return audio_file, None

    temp_dir = tempfile.TemporaryDirectory(prefix="asr-prep-")
    prepared_path = Path(temp_dir.name) / f"{audio_file.stem}.asr.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_file),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(ASR_SAMPLE_RATE),
    ]
    if ASR_AUDIO_FILTER.strip():
        command.extend(["-af", ASR_AUDIO_FILTER])
    command.append(str(prepared_path))

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        return prepared_path, temp_dir
    except Exception:
        temp_dir.cleanup()
        set_job_status(job, "ASR preprocessing failed, fallback to original audio", 97)
        return audio_file, None


def build_markdown_file(
    md_path: Path,
    *,
    title: str,
    source_url: str,
    source_id: str,
    source_platform: str,
    preset: str,
    transcript_language: str,
    transcript_model: str,
    transcript_source: str,
    transcript_source_detail: str | None,
    segments: list[TranscriptSegment],
    audio_name: str,
    raw_txt_name: str | None,
    raw_srt_name: str | None,
) -> Path:
    md_path.write_text(
        render_markdown_note(
            title=title,
            source_url=source_url,
            source_id=source_id,
            source_platform=source_platform,
            preset=preset,
            created_at=format_media_timestamp(),
            transcript_language=transcript_language,
            transcript_model=transcript_model,
            transcript_source=transcript_source,
            transcript_source_detail=transcript_source_detail,
            audio_name=audio_name,
            txt_name=md_path.with_suffix(".txt").name,
            srt_name=md_path.with_suffix(".srt").name,
            raw_txt_name=raw_txt_name,
            raw_srt_name=raw_srt_name,
            segments=segments,
            paragraph_chars=TRANSCRIPT_PARAGRAPH_CHARS,
            paragraph_gap_seconds=TRANSCRIPT_PARAGRAPH_GAP_SECONDS,
        ),
        encoding="utf-8",
    )
    return md_path


def write_transcript_outputs(
    target_base: Path,
    *,
    raw_segments: list[TranscriptSegment],
    cleaned_segments: list[TranscriptSegment],
    title: str,
    source_url: str,
    source_id: str,
    source_platform: str,
    preset: str,
    transcript_language: str,
    transcript_model: str,
    transcript_source: str,
    transcript_source_detail: str | None,
    audio_name: str,
) -> TranscriptArtifacts:
    raw_txt_path = target_base.with_suffix(".raw.txt")
    raw_srt_path = target_base.with_suffix(".raw.srt")
    txt_path = target_base.with_suffix(".txt")
    srt_path = target_base.with_suffix(".srt")
    md_path = target_base.with_suffix(".md")

    raw_txt_path.write_text(build_plain_text(raw_segments, clean=False) + "\n", encoding="utf-8")
    write_srt(raw_srt_path, raw_segments)
    txt_path.write_text(build_plain_text(cleaned_segments) + "\n", encoding="utf-8")
    write_srt(srt_path, cleaned_segments)
    build_markdown_file(
        md_path,
        title=title,
        source_url=source_url,
        source_id=source_id,
        source_platform=source_platform,
        preset=preset,
        transcript_language=transcript_language,
        transcript_model=transcript_model,
        transcript_source=transcript_source,
        transcript_source_detail=transcript_source_detail,
        segments=cleaned_segments,
        audio_name=audio_name,
        raw_txt_name=raw_txt_path.name,
        raw_srt_name=raw_srt_path.name,
    )
    return TranscriptArtifacts(
        files=[raw_txt_path, raw_srt_path, txt_path, srt_path, md_path],
        transcript_source=transcript_source,
        transcript_source_detail=transcript_source_detail,
        transcript_language=transcript_language,
        transcript_model=transcript_model,
    )


def load_from_transcript_cache(
    cache_key: str,
    target_base: Path,
    *,
    title: str,
    source_url: str,
    source_id: str,
    source_platform: str,
    preset: str,
    transcript_language: str,
    transcript_model: str,
    transcript_source: str,
    transcript_source_detail: str | None,
) -> TranscriptArtifacts | None:
    cache_dir = Path(TRANSCRIPT_CACHE_DIR)
    cache_txt = cache_dir / f"{cache_key}.txt"
    cache_srt = cache_dir / f"{cache_key}.srt"
    cache_md = cache_dir / f"{cache_key}.md"
    cache_raw_txt = cache_dir / f"{cache_key}.raw.txt"
    cache_raw_srt = cache_dir / f"{cache_key}.raw.srt"
    if not (cache_txt.exists() and cache_srt.exists()):
        return None

    target_raw_txt = target_base.with_suffix(".raw.txt")
    target_raw_srt = target_base.with_suffix(".raw.srt")
    target_txt = target_base.with_suffix(".txt")
    target_srt = target_base.with_suffix(".srt")
    target_md = target_base.with_suffix(".md")
    if cache_raw_txt.exists():
        shutil.copy2(cache_raw_txt, target_raw_txt)
    else:
        shutil.copy2(cache_txt, target_raw_txt)
    if cache_raw_srt.exists():
        shutil.copy2(cache_raw_srt, target_raw_srt)
    else:
        shutil.copy2(cache_srt, target_raw_srt)
    shutil.copy2(cache_txt, target_txt)
    shutil.copy2(cache_srt, target_srt)
    if cache_md.exists():
        shutil.copy2(cache_md, target_md)
    else:
        segments = parse_srt_segments(cache_srt.read_text(encoding="utf-8"))
        build_markdown_file(
            target_md,
            title=title,
            source_url=source_url,
            source_id=source_id,
            source_platform=source_platform,
            preset=preset,
            transcript_language=transcript_language,
            transcript_model=transcript_model,
            transcript_source=transcript_source,
            transcript_source_detail=transcript_source_detail,
            segments=segments,
            audio_name=target_base.name,
            raw_txt_name=target_raw_txt.name,
            raw_srt_name=target_raw_srt.name,
        )
        shutil.copy2(target_md, cache_md)
    return TranscriptArtifacts(
        files=[target_raw_txt, target_raw_srt, target_txt, target_srt, target_md],
        transcript_source=transcript_source,
        transcript_source_detail=transcript_source_detail,
        transcript_language=transcript_language,
        transcript_model=transcript_model,
    )


def save_to_transcript_cache(cache_key: str, artifacts: TranscriptArtifacts) -> None:
    cache_dir = Path(TRANSCRIPT_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)

    raw_txt_path = next((path for path in artifacts.files if path.name.endswith(".raw.txt")), None)
    raw_srt_path = next((path for path in artifacts.files if path.name.endswith(".raw.srt")), None)
    txt_path = next((path for path in artifacts.files if path.suffix == ".txt" and ".raw." not in path.name), None)
    srt_path = next((path for path in artifacts.files if path.suffix == ".srt" and ".raw." not in path.name), None)
    md_path = next((path for path in artifacts.files if path.suffix == ".md"), None)

    if not (txt_path and srt_path and md_path):
        return

    cache_raw_txt = cache_dir / f"{cache_key}.raw.txt"
    cache_raw_srt = cache_dir / f"{cache_key}.raw.srt"
    cache_txt = cache_dir / f"{cache_key}.txt"
    cache_srt = cache_dir / f"{cache_key}.srt"
    cache_md = cache_dir / f"{cache_key}.md"
    if raw_txt_path and not cache_raw_txt.exists():
        shutil.copy2(raw_txt_path, cache_raw_txt)
    if raw_srt_path and not cache_raw_srt.exists():
        shutil.copy2(raw_srt_path, cache_raw_srt)
    if not cache_txt.exists():
        shutil.copy2(txt_path, cache_txt)
    if not cache_srt.exists():
        shutil.copy2(srt_path, cache_srt)
    if not cache_md.exists():
        shutil.copy2(md_path, cache_md)


def whisper_language_arg() -> str | None:
    if WHISPER_LANGUAGE in {"", "auto"}:
        return None
    return WHISPER_LANGUAGE


def remote_mlx_source_detail(payload: dict | None = None) -> str:
    backend = payload.get("backend", {}) if isinstance(payload, dict) else {}
    model = backend.get("model") or REMOTE_MLX_MODEL
    quant = backend.get("quant")
    batch_size = backend.get("batch_size") or REMOTE_MLX_BATCH_SIZE
    quant_label = quant or "base"
    return f"{model} quant={quant_label} batch={batch_size} @ {REMOTE_MLX_URL}"


def transcribe_remote_mlx(
    audio_file: Path,
    *,
    note_title: str,
    source_url: str,
    source_id: str,
    source_platform: str,
    preset: str,
) -> TranscriptArtifacts:
    relative_path = container_relative_audio_path(audio_file)
    payload = {
        "audio_relative_path": relative_path,
        "audio_path": str(audio_file),
        "language": whisper_language_arg(),
        "model": REMOTE_MLX_MODEL,
        "batch_size": REMOTE_MLX_BATCH_SIZE,
        "quant": REMOTE_MLX_QUANT,
    }
    request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{REMOTE_MLX_URL}/api/transcribe",
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REMOTE_MLX_TIMEOUT) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Remote MLX HTTP {exc.code}: {message or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Remote MLX unavailable: {exc.reason}") from exc

    raw_segments = coerce_segments(response_payload.get("segments", []))
    cleaned_segments = normalize_segments(raw_segments)
    if not raw_segments or not cleaned_segments:
        text = str(response_payload.get("text", "") or "").strip()
        if not text:
            raise RuntimeError("Remote MLX returned no transcript segments.")
        raw_segments = [TranscriptSegment(start=0.0, end=0.0, text=text)]
        cleaned_segments = normalize_segments(raw_segments)

    transcript_language = str(response_payload.get("language") or whisper_language_arg() or "auto")
    source_detail = str(response_payload.get("source_detail") or remote_mlx_source_detail(response_payload))
    model_label = str(
        response_payload.get("backend", {}).get("model")
        or response_payload.get("model")
        or REMOTE_MLX_MODEL
    )
    return write_transcript_outputs(
        audio_file,
        raw_segments=raw_segments,
        cleaned_segments=cleaned_segments,
        title=note_title,
        source_url=source_url,
        source_id=source_id,
        source_platform=source_platform,
        preset=preset,
        transcript_language=transcript_language,
        transcript_model=model_label,
        transcript_source="远程 MLX",
        transcript_source_detail=source_detail,
        audio_name=audio_file.name,
    )


def build_transcript_from_subtitle(
    subtitle_file: Path,
    audio_file: Path,
    *,
    note_title: str,
    source_url: str,
    source_id: str,
    source_platform: str,
    preset: str,
) -> TranscriptArtifacts:
    raw_segments = load_segments_from_subtitle_file(subtitle_file, clean=False)
    cleaned_segments = normalize_segments(raw_segments)
    if not raw_segments or not cleaned_segments:
        raise RuntimeError(f"Subtitle file is empty or unreadable: {subtitle_file.name}")

    return write_transcript_outputs(
        audio_file,
        raw_segments=raw_segments,
        cleaned_segments=cleaned_segments,
        title=note_title,
        source_url=source_url,
        source_id=source_id,
        source_platform=source_platform,
        preset=preset,
        transcript_language=detect_subtitle_language(subtitle_file),
        transcript_model="platform-subtitle",
        transcript_source="平台字幕",
        transcript_source_detail=subtitle_file.name,
        audio_name=audio_file.name,
    )


def transcribe_audio(
    audio_file: Path,
    job: Job | None,
    source_key: str | None,
    *,
    note_title: str,
    source_url: str,
    source_id: str,
    source_platform: str,
    preset: str,
    subtitle_file: Path | None = None,
) -> TranscriptArtifacts:
    if subtitle_file is not None:
        set_job_status(job, "Using platform subtitles...", 97)
        return build_transcript_from_subtitle(
            subtitle_file,
            audio_file,
            note_title=note_title,
            source_url=source_url,
            source_id=source_id,
            source_platform=source_platform,
            preset=preset,
        )

    use_remote_mlx = effective_transcription_backend() == "remote_mlx"
    if use_remote_mlx:
        remote_cache_key = build_cache_key(audio_file, source_key, backend="remote_mlx")
        cached = load_from_transcript_cache(
            remote_cache_key,
            audio_file,
            title=note_title,
            source_url=source_url,
            source_id=source_id,
            source_platform=source_platform,
            preset=preset,
            transcript_language=whisper_language_arg() or "auto",
            transcript_model=REMOTE_MLX_MODEL,
            transcript_source="远程 MLX",
            transcript_source_detail=remote_mlx_source_detail(),
        )
        if cached:
            set_job_status(job, "Transcription cache hit", 98)
            return cached

        set_job_status(job, "Transcribing via remote MLX...", 97)
        try:
            artifacts = transcribe_remote_mlx(
                audio_file,
                note_title=note_title,
                source_url=source_url,
                source_id=source_id,
                source_platform=source_platform,
                preset=preset,
            )
            save_to_transcript_cache(remote_cache_key, artifacts)
            return artifacts
        except Exception as exc:
            if not TRANSCRIPTION_FALLBACK_LOCAL:
                raise
            set_job_status(job, f"Remote MLX failed, fallback to local Whisper: {exc}", 97)

    cache_key = build_cache_key(audio_file, source_key, backend="local")
    cached = load_from_transcript_cache(
        cache_key,
        audio_file,
        title=note_title,
        source_url=source_url,
        source_id=source_id,
        source_platform=source_platform,
        preset=preset,
        transcript_language=whisper_language_arg() or "auto",
        transcript_model=WHISPER_MODEL,
        transcript_source="Whisper",
        transcript_source_detail=f"{WHISPER_MODEL} ({active_compute_type or WHISPER_COMPUTE_TYPE})",
    )
    if cached:
        set_job_status(job, "Transcription cache hit", 98)
        return cached

    model = get_whisper_model()
    set_job_status(job, "Transcribing (accuracy first)...", 98)

    asr_input, temp_dir = prepare_audio_for_asr(audio_file, job)
    with whisper_slots:
        try:
            segments, info = model.transcribe(
                str(asr_input),
                language=whisper_language_arg(),
                beam_size=WHISPER_BEAM_SIZE,
                best_of=WHISPER_BEST_OF,
                condition_on_previous_text=True,
                vad_filter=True,
            )
            segment_list = list(segments)
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

    if not segment_list:
        raise RuntimeError(f"No speech detected in audio: {audio_file.name}")

    raw_segments = coerce_segments(segment_list)
    normalized_segments = normalize_segments(raw_segments)
    if not raw_segments or not normalized_segments:
        raise RuntimeError(f"No readable transcript text was produced for audio: {audio_file.name}")

    detected_language = getattr(info, "language", None)
    artifacts = write_transcript_outputs(
        audio_file,
        raw_segments=raw_segments,
        cleaned_segments=normalized_segments,
        title=note_title,
        source_url=source_url,
        source_id=source_id,
        source_platform=source_platform,
        preset=preset,
        transcript_language=detected_language or whisper_language_arg() or "auto",
        transcript_model=WHISPER_MODEL,
        transcript_source="Whisper",
        transcript_source_detail=f"{WHISPER_MODEL} ({active_compute_type or WHISPER_COMPUTE_TYPE})",
        audio_name=audio_file.name,
    )
    save_to_transcript_cache(cache_key, artifacts)

    if detected_language:
        set_job_status(job, f"Transcribed language: {detected_language}", 99)

    return artifacts


def extract_source_meta(info: dict | None, fallback_url: str, fallback_job_id: str) -> tuple[str, str, str]:
    if isinstance(info, dict):
        title = info.get("title")
        source_id = info.get("id")

        if not title and isinstance(info.get("entries"), list) and info["entries"]:
            first = info["entries"][0]
            if isinstance(first, dict):
                title = first.get("title")
        if not source_id and isinstance(info.get("entries"), list) and info["entries"]:
            first = info["entries"][0]
            if isinstance(first, dict):
                source_id = first.get("id")

        platform = infer_source_platform(info, fallback_url)
        if title and source_id:
            return str(title), str(source_id), platform
        if title:
            return str(title), fallback_job_id[:8], platform

    return fallback_url, fallback_job_id[:8], infer_source_platform(info, fallback_url)


def write_manifest(
    final_dir: Path,
    job: Job,
    source_id: str,
    source_platform: str,
    artifacts: list[Path],
    transcript_runs: list[TranscriptArtifacts] | None = None,
) -> Path:
    manifest_path = final_dir / "_meta.json"
    payload = {
        "job_id": job.job_id,
        "url": job.url,
        "preset": job.preset,
        "source_kind": job.source_kind,
        "source_id": source_id,
        "source_platform": source_platform,
        "created_at": int(job.created_at),
        "whisper": {
            "model": WHISPER_MODEL,
            "device": WHISPER_DEVICE,
            "compute_type": active_compute_type or WHISPER_COMPUTE_TYPE,
            "language": WHISPER_LANGUAGE or "auto",
            "beam_size": WHISPER_BEAM_SIZE,
            "best_of": WHISPER_BEST_OF,
        },
        "knowledge_base": {
            "note_format": "markdown",
            "paragraph_chars": TRANSCRIPT_PARAGRAPH_CHARS,
            "paragraph_gap_seconds": TRANSCRIPT_PARAGRAPH_GAP_SECONDS,
            "subtitle_first": PREFER_PLATFORM_SUBTITLES,
            "transcription_backend": TRANSCRIPTION_BACKEND,
            "transcription_fallback_local": TRANSCRIPTION_FALLBACK_LOCAL,
            "remote_mlx_url": REMOTE_MLX_URL if effective_transcription_backend() == "remote_mlx" else "",
            "remote_mlx_model": REMOTE_MLX_MODEL,
            "remote_mlx_batch_size": REMOTE_MLX_BATCH_SIZE,
            "remote_mlx_quant": REMOTE_MLX_QUANT,
            "raw_outputs": True,
            "asr_preprocess_enabled": ASR_PREPROCESS_ENABLED,
            "asr_audio_filter": ASR_AUDIO_FILTER,
            "asr_sample_rate": ASR_SAMPLE_RATE,
            "cleaning": [
                "collapse_whitespace",
                "join_split_digits",
                "normalize_numeric_symbols",
                "merge_short_segments",
            ],
        },
        "artifacts": [p.name for p in artifacts],
    }
    if job.source_kind == "local_audio" and job.local_audio_paths:
        payload["local_audio_inputs"] = [Path(path).name for path in job.local_audio_paths]
    if transcript_runs:
        payload["transcripts"] = [
            {
                "source": item.transcript_source,
                "source_detail": item.transcript_source_detail,
                "language": item.transcript_language,
                "model": item.transcript_model,
            }
            for item in transcript_runs
        ]
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def finalize_job_outputs(
    temp_dir: Path,
    output_root: Path,
    *,
    job: Job,
    source_title: str,
    source_id: str,
    source_platform: str,
    transcript_runs: list[TranscriptArtifacts] | None = None,
) -> None:
    set_job_status(job, "Organizing files...", 99)

    date_bucket = time.strftime("%Y-%m-%d")
    folder_name = f"{sanitize_filename(source_title)} [{sanitize_filename(source_id)}]"
    final_dir = ensure_unique_dir(output_root / date_bucket / folder_name)
    final_dir.mkdir(parents=True, exist_ok=True)

    moved = move_outputs(temp_dir, final_dir)
    manifest_path = write_manifest(
        final_dir,
        job,
        source_id,
        source_platform,
        moved,
        transcript_runs=transcript_runs,
    )
    moved_with_manifest = moved + [manifest_path]

    with job.lock:
        job.output_dir = str(final_dir)
        job.artifacts = sorted(path.name for path in moved_with_manifest)
        job.done = True
        job.status = "Done"
        job.progress = 100


def worker(job_id):
    job = jobs.get(job_id)
    if not job:
        return

    set_job_status(job, "Starting...")

    preset_conf = FORMAT_PRESETS[job.preset]
    output_root = Path(DOWNLOAD_DIR)
    temp_dir = output_root / ".tmp" / job.job_id

    options = {
        "format": preset_conf["format"],
        "outtmpl": str(temp_dir / "%(title).150B [%(id)s].%(ext)s"),
        "progress_hooks": [progress_hook(job)],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "windowsfilenames": True,
    }

    if "merge_output_format" in preset_conf:
        options["merge_output_format"] = preset_conf["merge_output_format"]
    if "postprocessors" in preset_conf:
        options["postprocessors"] = preset_conf["postprocessors"]
    if "keepvideo" in preset_conf:
        options["keepvideo"] = bool(preset_conf["keepvideo"])
    if preset_conf.get("transcribe") and PREFER_PLATFORM_SUBTITLES:
        options["writesubtitles"] = True
        options["writeautomaticsub"] = True
        options["subtitleslangs"] = subtitle_language_preferences()
        options["subtitlesformat"] = "srt/vtt/best"
    if job.use_cookies and COOKIES_PATH:
        options["cookiefile"] = COOKIES_PATH

    info = None
    source_title = job.url
    source_id = job.job_id[:8]
    source_platform = infer_source_platform(None, job.url)

    try:
        output_root.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        with yt_dlp.YoutubeDL(options) as ydl:
            try:
                info = ydl.extract_info(job.url, download=False)
                source_title, source_id, source_platform = extract_source_meta(
                    info, job.url, job.job_id
                )
                with job.lock:
                    job.title = source_title
            except Exception:
                pass

            ydl.download([job.url])

        downloaded_files = [path for path in temp_dir.rglob("*") if path.is_file()]
        if not downloaded_files:
            raise RuntimeError("No downloadable media file was produced for this URL.")

        transcript_runs: list[TranscriptArtifacts] = []
        if preset_conf.get("transcribe"):
            audio_files = sorted(temp_dir.rglob("*.mp3"))
            if not audio_files:
                raise RuntimeError("MP3 file was not generated, transcription skipped.")
            subtitle_files = list_subtitle_files(temp_dir)

            for index, audio_file in enumerate(audio_files, start=1):
                set_job_status(
                    job,
                    f"Transcribing {index}/{len(audio_files)} (accuracy first)...",
                    97,
                )
                key = f"{source_id}:{audio_file.name}"
                note_title, note_source_id = parse_title_and_id_from_media(
                    audio_file, source_title, source_id
                )
                subtitle_file = (
                    find_best_subtitle_file(audio_file, subtitle_files)
                    if PREFER_PLATFORM_SUBTITLES
                    else None
                )
                artifacts = transcribe_audio(
                    audio_file,
                    job,
                    key,
                    note_title=note_title,
                    source_url=job.url,
                    source_id=note_source_id,
                    source_platform=source_platform,
                    preset=job.preset,
                    subtitle_file=subtitle_file,
                )
                transcript_runs.append(artifacts)

        finalize_job_outputs(
            temp_dir,
            output_root,
            job=job,
            source_title=source_title,
            source_id=source_id,
            source_platform=source_platform,
            transcript_runs=transcript_runs,
        )
    except Exception as exc:
        with job.lock:
            job.done = True
            job.status = "Failed"
            job.error = str(exc)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def local_audio_worker(job_id):
    job = jobs.get(job_id)
    if not job:
        return

    set_job_status(job, "Preparing local audio...", 5)
    output_root = Path(DOWNLOAD_DIR)
    temp_dir = output_root / ".tmp" / job.job_id

    try:
        if not job.local_audio_paths:
            raise RuntimeError("No local audio file was queued.")

        audio_files = [Path(path) for path in job.local_audio_paths]
        for audio_file in audio_files:
            if not audio_file.exists() or not audio_file.is_file():
                raise FileNotFoundError(f"Queued audio file not found: {audio_file}")

        transcript_runs: list[TranscriptArtifacts] = []
        source_platform = "Local Audio"
        source_title = sanitize_filename(audio_files[0].stem, max_length=180)
        source_id = file_sha1(audio_files[0])[:12]
        with job.lock:
            job.title = source_title

        for index, audio_file in enumerate(audio_files, start=1):
            note_title = sanitize_filename(audio_file.stem, max_length=180)
            note_source_id = file_sha1(audio_file)[:12]
            set_job_status(
                job,
                f"Transcribing local audio {index}/{len(audio_files)}...",
                97,
            )
            artifacts = transcribe_audio(
                audio_file,
                job,
                f"local:{note_source_id}:{audio_file.name}",
                note_title=note_title,
                source_url=audio_file.name,
                source_id=note_source_id,
                source_platform=source_platform,
                preset=job.preset,
            )
            transcript_runs.append(artifacts)

        if len(audio_files) > 1:
            source_title = f"Local Audio Batch {job.job_id[:8]}"
            source_id = job.job_id[:8]

        finalize_job_outputs(
            temp_dir,
            output_root,
            job=job,
            source_title=source_title,
            source_id=source_id,
            source_platform=source_platform,
            transcript_runs=transcript_runs,
        )
    except Exception as exc:
        with job.lock:
            job.done = True
            job.status = "Failed"
            job.error = str(exc)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route("/")
def index():
    config = {
        "presets": [name for name in FORMAT_PRESETS.keys() if name not in HIDDEN_PRESETS],
        "defaultPreset": DEFAULT_PRESET,
        "knowledgeBasePreset": KNOWLEDGE_BASE_PRESET,
        "localAudioAccept": LOCAL_AUDIO_ACCEPT,
        "localAudioMaxMb": LOCAL_AUDIO_MAX_MB,
    }
    return render_template("index.html", app_title=APP_TITLE, config_json=json.dumps(config))


@app.route("/api/start", methods=["POST"])
def start():
    data = request.json or {}
    urls = [u.strip() for u in data.get("url", "").splitlines() if u.strip()]
    if not urls:
        return jsonify({"error": "No URL"}), 400

    preset = data.get("preset") or DEFAULT_PRESET
    if preset not in FORMAT_PRESETS:
        return jsonify({"error": f"Unsupported preset: {preset}"}), 400

    use_cookies = bool(data.get("use_cookies"))

    added = 0
    with jobs_lock:
        for url in urls:
            job_id = uuid.uuid4().hex
            job = Job(job_id, url, preset, use_cookies)
            jobs[job_id] = job
            executor.submit(worker, job_id)
            added += 1
    return jsonify({"count": added})


@app.route("/api/local-audio", methods=["POST"])
def start_local_audio():
    uploaded_files = [
        file_storage
        for file_storage in request.files.getlist("audio_files")
        if file_storage and str(file_storage.filename or "").strip()
    ]
    if not uploaded_files:
        return jsonify({"error": "No audio file was uploaded."}), 400

    preset = request.form.get("preset") or KNOWLEDGE_BASE_PRESET
    if preset not in FORMAT_PRESETS:
        return jsonify({"error": f"Unsupported preset: {preset}"}), 400
    if not FORMAT_PRESETS[preset].get("transcribe"):
        return jsonify({"error": f"Preset does not support transcription: {preset}"}), 400

    output_root = Path(DOWNLOAD_DIR)
    tmp_root = output_root / ".tmp"
    output_root.mkdir(parents=True, exist_ok=True)
    tmp_root.mkdir(parents=True, exist_ok=True)

    prepared_jobs: list[tuple[Job, str, Path]] = []
    try:
        for file_storage in uploaded_files:
            original_name = str(file_storage.filename or "").strip()
            if not is_supported_local_audio(original_name):
                raise ValueError(
                    f"Unsupported audio format: {original_name}. "
                    f"Allowed: {', '.join(sorted(LOCAL_AUDIO_EXTENSIONS))}"
                )

            job_id = uuid.uuid4().hex
            temp_dir = tmp_root / job_id
            temp_dir.mkdir(parents=True, exist_ok=True)
            try:
                saved_path = save_uploaded_audio(file_storage, temp_dir)
            except Exception:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise

            job = Job(
                job_id=job_id,
                url=f"local://{saved_path.name}",
                preset=preset,
                use_cookies=False,
                source_kind="local_audio",
                local_audio_paths=[str(saved_path)],
                title=sanitize_filename(saved_path.stem, max_length=180),
            )
            prepared_jobs.append((job, saved_path.name, temp_dir))
    except ValueError as exc:
        for _job, _name, temp_dir in prepared_jobs:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        for _job, _name, temp_dir in prepared_jobs:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({"error": f"Failed to queue local audio: {exc}"}), 500

    queued_jobs = []
    with jobs_lock:
        for job, name, _temp_dir in prepared_jobs:
            jobs[job.job_id] = job
            executor.submit(local_audio_worker, job.job_id)
            queued_jobs.append({"id": job.job_id, "name": name})

    return jsonify({"count": len(queued_jobs), "jobs": queued_jobs})


@app.route("/api/tasks")
def tasks():
    with jobs_lock:
        tasks_list = []
        for job in sorted(jobs.values(), key=lambda x: x.created_at, reverse=True)[:20]:
            tasks_list.append(
                {
                    "id": job.job_id,
                    "title": job.title,
                    "source_kind": job.source_kind,
                    "status": job.status,
                    "progress": round(job.progress),
                    "done": job.done,
                    "error": job.error,
                    "output_dir": job.output_dir,
                    "artifacts": job.artifacts,
                }
            )
    return jsonify({"tasks": tasks_list})


def process_local_audio(audio_paths: list[str], output_dir: str | None) -> int:
    resolved_output_dir = Path(output_dir).expanduser().resolve() if output_dir else None
    processed = 0

    for raw_path in audio_paths:
        audio_path = Path(raw_path).expanduser().resolve()
        if not audio_path.exists() or not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        source_id = file_sha1(audio_path)[:12]
        note_title = sanitize_filename(audio_path.stem, max_length=180)
        source_platform = "Local Audio"

        if resolved_output_dir:
            target_dir = resolved_output_dir / time.strftime("%Y-%m-%d") / f"{note_title} [{source_id}]"
            target_dir = ensure_unique_dir(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_audio = target_dir / audio_path.name
            shutil.copy2(audio_path, target_audio)
        else:
            target_audio = audio_path
            target_dir = target_audio.parent

        artifacts = transcribe_audio(
            target_audio,
            None,
            f"local:{source_id}:{audio_path.name}",
            note_title=note_title,
            source_url=str(audio_path),
            source_id=source_id,
            source_platform=source_platform,
            preset=KNOWLEDGE_BASE_PRESET,
        )

        manifest_path = target_audio.with_suffix(".meta.json")
        manifest_path.write_text(
            json.dumps(
                {
                    "source_file": str(audio_path),
                    "preset": KNOWLEDGE_BASE_PRESET,
                    "source_kind": "local_audio",
                    "source_id": source_id,
                    "source_platform": source_platform,
                    "transcript_source": artifacts.transcript_source,
                    "transcript_source_detail": artifacts.transcript_source_detail,
                    "transcript_language": artifacts.transcript_language,
                    "transcript_model": artifacts.transcript_model,
                    "created_at": format_media_timestamp(),
                    "artifacts": [target_audio.name] + [path.name for path in artifacts.files],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        processed += 1

    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", nargs="*", help="Process local audio files into Markdown notes")
    parser.add_argument(
        "--output-dir",
        help="Optional destination for local audio processing; defaults to the audio file directory",
    )
    args = parser.parse_args()

    if args.audio:
        count = process_local_audio(args.audio, args.output_dir)
        print(f"Processed {count} audio file(s) into Markdown transcripts.")
        return

    app.run(host=HOST, port=PORT, threaded=True)


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_exc):
    return (
        jsonify(
            {
                "error": (
                    f"Uploaded audio exceeds the configured limit of {LOCAL_AUDIO_MAX_MB} MB. "
                    "Use the CLI mode for very large local files."
                )
            }
        ),
        413,
    )


if __name__ == "__main__":
    main()
