import html
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from flask import Flask, jsonify, render_template, request

try:
    from . import cookie_health
    from . import openai_compatible_cleanup as cleanup_backend
    from . import openrouter_backends as openrouter_backend
    from .douyin_provider import DouyinDownloadError, download_douyin_media
    from .env_config import load_env_file
    from .openai_compatible_cleanup import (
        AI_CLEANUP_BASE_URL,
        AI_CLEANUP_ENABLED,
        AI_CLEANUP_FALLBACK_LOCAL,
        AI_CLEANUP_MODEL,
        AI_CLEANUP_PROMPT_FILE,
        AI_CLEANUP_PROVIDER_LABEL,
        ARTICLE_DRAFT_BASE_URL,
        ARTICLE_DRAFT_MODEL,
        ARTICLE_DRAFT_PROMPT_FILE,
        ARTICLE_DRAFT_PROVIDER_LABEL,
        ENABLE_ARTICLE_DRAFT,
        ENABLE_KNOWLEDGE_DRAFT,
        cleanup_transcript,
        generate_article_draft as generate_ai_article_draft,
        generate_knowledge_draft,
    )
    from .openrouter_backends import (
        OPENROUTER_APP_NAME,
        OPENROUTER_ARTICLE_MODEL,
        OPENROUTER_BASE_URL,
        OPENROUTER_SITE_URL,
        OPENROUTER_TRANSCRIPTION_MODEL,
        generate_article_draft as generate_openrouter_article_draft,
        transcribe_audio,
    )
    from .settings_store import config_dir as settings_config_dir
    from .settings_store import load_settings, save_settings, settings_path
    from .transcript_pipeline import (
        build_artifact_paths,
        clean_transcript_text,
        detect_platform,
        normalize_raw_transcript_text,
        render_markdown,
        write_sidecar_files,
    )
except ImportError:
    import cookie_health
    import openai_compatible_cleanup as cleanup_backend
    import openrouter_backends as openrouter_backend
    from douyin_provider import DouyinDownloadError, download_douyin_media
    from env_config import load_env_file
    from openai_compatible_cleanup import (
        AI_CLEANUP_BASE_URL,
        AI_CLEANUP_ENABLED,
        AI_CLEANUP_FALLBACK_LOCAL,
        AI_CLEANUP_MODEL,
        AI_CLEANUP_PROMPT_FILE,
        AI_CLEANUP_PROVIDER_LABEL,
        ARTICLE_DRAFT_BASE_URL,
        ARTICLE_DRAFT_MODEL,
        ARTICLE_DRAFT_PROMPT_FILE,
        ARTICLE_DRAFT_PROVIDER_LABEL,
        ENABLE_ARTICLE_DRAFT,
        ENABLE_KNOWLEDGE_DRAFT,
        cleanup_transcript,
        generate_article_draft as generate_ai_article_draft,
        generate_knowledge_draft,
    )
    from openrouter_backends import (
        OPENROUTER_APP_NAME,
        OPENROUTER_ARTICLE_MODEL,
        OPENROUTER_BASE_URL,
        OPENROUTER_SITE_URL,
        OPENROUTER_TRANSCRIPTION_MODEL,
        generate_article_draft as generate_openrouter_article_draft,
        transcribe_audio,
    )
    from settings_store import config_dir as settings_config_dir
    from settings_store import load_settings, save_settings, settings_path
    from transcript_pipeline import (
        build_artifact_paths,
        clean_transcript_text,
        detect_platform,
        normalize_raw_transcript_text,
        render_markdown,
        write_sidecar_files,
    )
load_env_file()

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
TEMPLATE_DIR = APP_DIR / "templates"

try:
    import yt_dlp
except ImportError as exc:
    raise SystemExit("yt-dlp is not installed.") from exc


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_cookie_search_roots() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "cookies",
        Path("/cookies"),
    )


def _autodetect_cookie_path(filename: str) -> str:
    for root in _default_cookie_search_roots():
        candidate = (root / filename).expanduser()
        if candidate.exists():
            return str(candidate.resolve())
    return ""


APP_TITLE = "幕库 Muku"
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(Path.home() / "Downloads"))
DOWNLOAD_ROOT_DIR = os.environ.get("DOWNLOAD_ROOT_DIR", "").strip()
HOST_DOWNLOADS_DIR = os.environ.get("HOST_DOWNLOADS_DIR", "").strip()
COOKIES_PATH = os.environ.get("COOKIES_PATH", "").strip() or _autodetect_cookie_path("cookies.txt")
COOKIES_FROM_BROWSER = os.environ.get("COOKIES_FROM_BROWSER", "").strip()
YOUTUBE_COOKIES_PATH = os.environ.get("YOUTUBE_COOKIES_PATH", "").strip() or _autodetect_cookie_path(
    "youtube.cookies.txt"
)
YOUTUBE_COOKIES_FROM_BROWSER = os.environ.get("YOUTUBE_COOKIES_FROM_BROWSER", "").strip()
BILIBILI_COOKIES_PATH = os.environ.get("BILIBILI_COOKIES_PATH", "").strip() or _autodetect_cookie_path(
    "bilibili.cookies.txt"
)
BILIBILI_COOKIES_FROM_BROWSER = os.environ.get("BILIBILI_COOKIES_FROM_BROWSER", "").strip()
DOUYIN_COOKIES_PATH = os.environ.get("DOUYIN_COOKIES_PATH", "").strip() or _autodetect_cookie_path(
    "douyin.cookies.txt"
)
DOUYIN_COOKIES_FROM_BROWSER = os.environ.get("DOUYIN_COOKIES_FROM_BROWSER", "").strip()
YTDLP_REMOTE_COMPONENTS = tuple(
    component.strip()
    for component in os.environ.get("YTDLP_REMOTE_COMPONENTS", "ejs:github").split(",")
    if component.strip()
)
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "2"))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5657"))
RESUME_WEB_JOBS = env_bool("MUKU_RESUME_JOBS", False)
WEB_TOKEN = os.environ.get("MUKU_WEB_TOKEN", "").strip()
WEB_TOKEN_HEADER = "X-Muku-Web-Token"
MAX_START_URLS = max(1, int(os.environ.get("MAX_START_URLS", "50")))
ENABLE_TRANSCRIPTION = env_bool("ENABLE_TRANSCRIPTION", True)
TRANSCRIPTION_LANGUAGE = os.environ.get("TRANSCRIPTION_LANGUAGE", "auto")
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
TRANSCRIPTION_AUDIO_BITRATE = os.environ.get("TRANSCRIPTION_AUDIO_BITRATE", "48k")
ENABLE_TRANSCRIPTION_CHUNKING = env_bool("ENABLE_TRANSCRIPTION_CHUNKING", True)
TRANSCRIPTION_CHUNK_SECONDS = max(60, int(os.environ.get("TRANSCRIPTION_CHUNK_SECONDS", "600")))
KEEP_TRANSCRIPTION_INPUT = env_bool("KEEP_TRANSCRIPTION_INPUT", False)
MAX_OUTPUT_TITLE_CHARS = max(16, int(os.environ.get("MAX_OUTPUT_TITLE_CHARS", "48")))
VIDEO_PRESET_NAME = "Highest Video (MP4)"
AUDIO_PRESET_NAME = "Best Audio (MP3)"
TRANSCRIPT_PRESET_NAME = "Markdown 逐字稿（字幕优先）"
SUBTITLE_LANGUAGES = tuple(
    lang.strip()
    for lang in os.environ.get(
        "SUBTITLE_LANGUAGES",
        "ai-zh,zh-Hans,zh-CN,zh-TW,zh-HK,zh,cmn-Hans-CN,ai-en,en,en-US",
    ).split(",")
    if lang.strip()
)
SUBTITLE_FORMATS = os.environ.get("SUBTITLE_FORMATS", "json3/vtt/srt/ttml/best")
TIMECODE_LINE_RE = re.compile(
    r"^\s*(\d+:)?\d{2}:\d{2}([.,]\d{3})?\s*-->\s*(\d+:)?\d{2}:\d{2}([.,]\d{3})?.*$"
)
NUMERIC_CUE_RE = re.compile(r"^\d+$")
XML_TAG_RE = re.compile(r"<[^>]+>")
URL_CANDIDATE_RE = re.compile(r"https?://[^\s<>'\"“”‘’]+", re.IGNORECASE)
COOKIES_FROM_BROWSER_RE = re.compile(
    r"""(?x)
    (?P<name>[^+:]+)
    (?:\s*\+\s*(?P<keyring>[^:]+))?
    (?:\s*:\s*(?!:)(?P<profile>.+?))?
    (?:\s*::\s*(?P<container>.+))?
    """
)

FORMAT_PRESETS = {
    VIDEO_PRESET_NAME: {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "transcribe": False,
    },
    AUDIO_PRESET_NAME: {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "transcribe": False,
    },
    TRANSCRIPT_PRESET_NAME: {
        "format": "bestaudio/best",
        "transcribe": True,
        "transcript_only": True,
    },
}

PLATFORM_AUTH_ORDER = (
    ("youtube", "YouTube"),
    ("bilibili", "Bilibili"),
    ("douyin", "Douyin"),
)
ARTIFACT_PREVIEW_CHAR_LIMIT = 24000
ARTIFACT_PREVIEW_FIELDS: dict[str, dict[str, str]] = {
    "article": {
        "attr": "article_path",
        "label": "解析稿",
        "suffix": " - 解析稿.md",
        "format": "markdown",
    },
    "transcript": {
        "attr": "transcript_path",
        "label": "逐字稿",
        "suffix": " - 逐字稿.md",
        "format": "markdown",
    },
    "knowledge": {
        "attr": "knowledge_path",
        "label": "知识库稿",
        "suffix": " - 知识库.md",
        "format": "markdown",
    },
    "raw": {
        "attr": "raw_path",
        "label": "原始逐字稿",
        "suffix": " - 原始逐字稿.txt",
        "format": "text",
    },
    "metadata": {
        "attr": "metadata_path",
        "label": "转写信息",
        "suffix": " - 转写信息.json",
        "format": "json",
    },
}

ENV_DEFAULTS = {
    "download_dir": DOWNLOAD_DIR,
    "cookies_path": COOKIES_PATH,
    "cookies_from_browser": COOKIES_FROM_BROWSER,
    "youtube_cookies_path": YOUTUBE_COOKIES_PATH,
    "youtube_cookies_from_browser": YOUTUBE_COOKIES_FROM_BROWSER,
    "bilibili_cookies_path": BILIBILI_COOKIES_PATH,
    "bilibili_cookies_from_browser": BILIBILI_COOKIES_FROM_BROWSER,
    "douyin_cookies_path": DOUYIN_COOKIES_PATH,
    "douyin_cookies_from_browser": DOUYIN_COOKIES_FROM_BROWSER,
    "openrouter_base_url": OPENROUTER_BASE_URL,
    "openrouter_api_key": openrouter_backend.OPENROUTER_API_KEY,
    "openrouter_site_url": OPENROUTER_SITE_URL,
    "openrouter_app_name": OPENROUTER_APP_NAME,
    "openrouter_transcription_model": OPENROUTER_TRANSCRIPTION_MODEL,
    "openrouter_article_model": OPENROUTER_ARTICLE_MODEL,
    "enable_ai_cleanup": AI_CLEANUP_ENABLED,
    "ai_cleanup_base_url": AI_CLEANUP_BASE_URL,
    "ai_cleanup_api_key": cleanup_backend.AI_CLEANUP_API_KEY,
    "ai_cleanup_model": AI_CLEANUP_MODEL,
    "ai_cleanup_timeout_seconds": cleanup_backend.AI_CLEANUP_TIMEOUT_SECONDS,
    "ai_cleanup_max_retries": cleanup_backend.AI_CLEANUP_MAX_RETRIES,
    "ai_cleanup_prompt_text": cleanup_backend.AI_CLEANUP_PROMPT_TEXT,
    "enable_article_draft": ENABLE_ARTICLE_DRAFT,
    "article_draft_base_url": ARTICLE_DRAFT_BASE_URL,
    "article_draft_api_key": cleanup_backend.ARTICLE_DRAFT_API_KEY,
    "article_draft_model": ARTICLE_DRAFT_MODEL,
    "article_draft_timeout_seconds": cleanup_backend.ARTICLE_DRAFT_TIMEOUT_SECONDS,
    "article_draft_max_retries": cleanup_backend.ARTICLE_DRAFT_MAX_RETRIES,
    "article_draft_prompt_text": cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT,
    "enable_knowledge_draft": ENABLE_KNOWLEDGE_DRAFT,
    "knowledge_draft_base_url": cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL,
    "knowledge_draft_api_key": cleanup_backend.KNOWLEDGE_DRAFT_API_KEY,
    "knowledge_draft_model": cleanup_backend.KNOWLEDGE_DRAFT_MODEL,
    "knowledge_draft_timeout_seconds": cleanup_backend.KNOWLEDGE_DRAFT_TIMEOUT_SECONDS,
    "knowledge_draft_max_retries": cleanup_backend.KNOWLEDGE_DRAFT_MAX_RETRIES,
    "knowledge_draft_prompt_text": cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT,
}
SECRET_SETTING_KEYS = {
    "openrouter_api_key",
    "ai_cleanup_api_key",
    "article_draft_api_key",
    "knowledge_draft_api_key",
}
SECRET_BACKED_BASE_URL_FIELDS = {
    "openrouter_base_url": "openrouter_api_key",
    "ai_cleanup_base_url": "ai_cleanup_api_key",
    "article_draft_base_url": "article_draft_api_key",
    "knowledge_draft_base_url": "knowledge_draft_api_key",
}
LEGACY_APP_TITLES = {"Downloader by Qianzhu"}
BARE_URL_CANDIDATE_RE = re.compile(
    r"""(?ix)
    \b(
        (?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\.)+[a-z]{2,63}/[^\s<>"']+
    )
    """
)
UNSAFE_WEB_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "instance-data",
    "instance-data.ec2.internal",
    "metadata",
    "metadata.google.internal",
    "host.docker.internal",
    "gateway.docker.internal",
}
UNSAFE_WEB_HOST_SUFFIXES = (
    ".localhost",
    ".localdomain",
    ".ec2.internal",
)
TRUSTED_WEB_HOST_SUFFIXES = (
    "bilibili.com",
    "b23.tv",
    "youtube.com",
    "youtu.be",
    "douyin.com",
    "v.douyin.com",
    "iesdouyin.com",
)
SUPPORTED_SHARE_HOST_SUFFIXES = TRUSTED_WEB_HOST_SUFFIXES


@dataclass
class Job:
    job_id: str
    url: str
    preset: str
    use_cookies: bool
    generate_transcript: bool
    generate_knowledge: bool = False
    output_dir: str | None = None
    created_at: float = field(default_factory=time.time)
    title: str = "Fetching info..."
    status: str = "Queued"
    progress: float = 0.0
    done: bool = False
    error: str | None = None
    artifact_dir: str | None = None
    download_path: str | None = None
    raw_path: str | None = None
    article_path: str | None = None
    transcript_path: str | None = None
    knowledge_path: str | None = None
    metadata_path: str | None = None
    provider: str | None = None
    transcript_route: str | None = None
    source_author: str | None = None
    knowledge_error: str | None = None
    backend_error: str | None = None
    resumed_from_state: bool = False
    last_persist_at: float = field(default=0.0, repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TEMPLATE_DIR),
)
jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
web_jobs_initialized = False

JOB_STATE_FILENAME = "web-jobs.json"
JOB_PERSIST_FIELDS = (
    "job_id",
    "url",
    "preset",
    "use_cookies",
    "generate_transcript",
    "generate_knowledge",
    "output_dir",
    "created_at",
    "title",
    "status",
    "progress",
    "done",
    "error",
    "artifact_dir",
    "download_path",
    "raw_path",
    "article_path",
    "transcript_path",
    "knowledge_path",
    "metadata_path",
    "provider",
    "transcript_route",
    "source_author",
    "knowledge_error",
    "backend_error",
    "resumed_from_state",
)


def frontend_asset_version() -> int:
    candidates = (
        STATIC_DIR / "style.css",
        STATIC_DIR / "app.js",
        TEMPLATE_DIR / "index.html",
    )
    versions = [int(path.stat().st_mtime) for path in candidates if path.exists()]
    return max(versions, default=1)


def web_jobs_state_path() -> Path:
    return settings_config_dir() / JOB_STATE_FILENAME


def serialize_job(job: Job) -> dict[str, object]:
    return {field_name: getattr(job, field_name) for field_name in JOB_PERSIST_FIELDS}


def deserialize_job(payload: dict[str, object]) -> Job:
    job = Job(
        job_id=str(payload.get("job_id") or uuid.uuid4().hex),
        url=str(payload.get("url") or ""),
        preset=str(payload.get("preset") or VIDEO_PRESET_NAME),
        use_cookies=bool(payload.get("use_cookies")),
        generate_transcript=bool(payload.get("generate_transcript")),
        generate_knowledge=bool(payload.get("generate_knowledge")),
        output_dir=str(payload.get("output_dir") or "").strip() or None,
        created_at=float(payload.get("created_at") or time.time()),
    )
    for field_name in JOB_PERSIST_FIELDS:
        if field_name in {
            "job_id",
            "url",
            "preset",
            "use_cookies",
            "generate_transcript",
            "generate_knowledge",
            "output_dir",
            "created_at",
        }:
            continue
        setattr(job, field_name, payload.get(field_name))
    try:
        job.progress = float(payload.get("progress") or 0.0)
    except (TypeError, ValueError):
        job.progress = 0.0
    job.done = bool(payload.get("done"))
    job.resumed_from_state = bool(payload.get("resumed_from_state"))
    return job


def load_persisted_jobs() -> dict[str, Job]:
    path = web_jobs_state_path()
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        return {}

    restored: dict[str, Job] = {}
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue
        job = deserialize_job(item)
        restored[job.job_id] = job
    return restored


def save_jobs_state() -> Path:
    path = web_jobs_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with jobs_lock:
        payload = {
            "saved_at": time.time(),
            "jobs": [serialize_job(job) for job in sorted(jobs.values(), key=lambda item: item.created_at, reverse=True)[:200]],
        }
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)
    return path


def persist_jobs_state(*, force: bool = False) -> None:
    now = time.time()
    if not force:
        should_save = False
        with jobs_lock:
            for job in jobs.values():
                with job.lock:
                    if now - job.last_persist_at >= 1.0:
                        job.last_persist_at = now
                        should_save = True
        if not should_save:
            return
    else:
        with jobs_lock:
            for job in jobs.values():
                with job.lock:
                    job.last_persist_at = now
    save_jobs_state()


def maybe_resume_job(job: Job) -> None:
    if job.done:
        return
    with job.lock:
        job.status = "Resuming after restart..."
        job.error = None
        job.backend_error = None
        job.resumed_from_state = True
    executor.submit(worker, job.job_id)


def initialize_web_jobs() -> None:
    global web_jobs_initialized
    if web_jobs_initialized:
        return

    restored_jobs = load_persisted_jobs()
    with jobs_lock:
        if restored_jobs:
            jobs.update(restored_jobs)
        web_jobs_initialized = True

    if RESUME_WEB_JOBS:
        for job in restored_jobs.values():
            maybe_resume_job(job)
    if restored_jobs:
        persist_jobs_state(force=True)


def load_inline_frontend_assets() -> dict[str, str]:
    css_text = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
    js_text = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    return {
        "inline_css": css_text,
        # Prevent an accidental closing tag inside inline JS from terminating the script block.
        "inline_js": js_text.replace("</script>", "<\\/script>"),
    }


def _coerce_bool(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field_name} 必须是布尔值。")


def _coerce_positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是正整数。")
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是正整数。") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} 必须是正整数。")
    return parsed


def download_root_path() -> Path | None:
    if not DOWNLOAD_ROOT_DIR:
        return None
    return Path(DOWNLOAD_ROOT_DIR).expanduser().resolve()


def running_in_container() -> bool:
    return Path("/.dockerenv").exists()


def resolve_download_dir(value: str | None = None, *, create: bool = False) -> Path:
    raw_value = (value or "").strip()
    candidate = Path(raw_value) if raw_value else Path(DOWNLOAD_DIR)
    root_dir = download_root_path()

    if root_dir is not None and not candidate.is_absolute():
        candidate = root_dir / candidate

    resolved = candidate.expanduser().resolve()
    if root_dir is not None:
        try:
            resolved.relative_to(root_dir)
        except ValueError as exc:
            raise ValueError(f"下载目录必须位于 {root_dir} 内。") from exc

    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _normalize_runtime_settings(payload: dict, *, partial: bool) -> dict:
    normalized: dict[str, object] = {}

    string_fields = {
        "openrouter_base_url",
        "openrouter_api_key",
        "openrouter_site_url",
        "openrouter_app_name",
        "openrouter_transcription_model",
        "openrouter_article_model",
        "ai_cleanup_base_url",
        "ai_cleanup_api_key",
        "ai_cleanup_model",
        "article_draft_base_url",
        "article_draft_api_key",
        "article_draft_model",
        "knowledge_draft_base_url",
        "knowledge_draft_api_key",
        "knowledge_draft_model",
    }
    path_fields = {
        "cookies_path",
        "youtube_cookies_path",
        "bilibili_cookies_path",
        "douyin_cookies_path",
    }
    browser_spec_fields = {
        "cookies_from_browser",
        "youtube_cookies_from_browser",
        "bilibili_cookies_from_browser",
        "douyin_cookies_from_browser",
    }
    bool_fields = {
        "enable_ai_cleanup",
        "enable_article_draft",
        "enable_knowledge_draft",
    }
    int_fields = {
        "ai_cleanup_timeout_seconds",
        "ai_cleanup_max_retries",
        "article_draft_timeout_seconds",
        "article_draft_max_retries",
        "knowledge_draft_timeout_seconds",
        "knowledge_draft_max_retries",
    }
    prompt_fields = {
        "ai_cleanup_prompt_text",
        "article_draft_prompt_text",
        "knowledge_draft_prompt_text",
    }

    if "download_dir" in payload:
        raw_value = str(payload.get("download_dir") or "").strip()
        normalized["download_dir"] = str(resolve_download_dir(raw_value)) if raw_value else ""
    elif not partial:
        normalized["download_dir"] = ""

    for field in path_fields:
        if field in payload:
            raw_value = str(payload.get(field) or "").strip()
            normalized[field] = str(Path(raw_value).expanduser().resolve()) if raw_value else ""
        elif not partial:
            normalized[field] = ""

    for field in browser_spec_fields:
        if field in payload:
            normalized[field] = str(payload.get(field) or "").strip()
        elif not partial:
            normalized[field] = ""

    for field in string_fields:
        if field in payload:
            normalized[field] = str(payload.get(field) or "").strip()
        elif not partial:
            normalized[field] = ""

    for field in ("ai_cleanup_model", "article_draft_model", "knowledge_draft_model"):
        if field in normalized:
            normalized[field] = cleanup_backend.normalize_text_backend_model(str(normalized[field]))

    for field in int_fields:
        if field in payload:
            normalized[field] = _coerce_positive_int(payload.get(field), field_name=field)
        elif not partial:
            normalized[field] = int(ENV_DEFAULTS[field])

    for field in prompt_fields:
        if field in payload:
            normalized[field] = str(payload.get(field) or "").strip()
        elif not partial:
            normalized[field] = ""

    for field in bool_fields:
        if field in payload:
            normalized[field] = _coerce_bool(payload.get(field), field_name=field)
        elif not partial:
            normalized[field] = bool(ENV_DEFAULTS[field])

    return normalized


def apply_runtime_settings(saved_settings: dict | None = None) -> dict:
    global DOWNLOAD_DIR
    global COOKIES_PATH, COOKIES_FROM_BROWSER
    global YOUTUBE_COOKIES_PATH, YOUTUBE_COOKIES_FROM_BROWSER
    global BILIBILI_COOKIES_PATH, BILIBILI_COOKIES_FROM_BROWSER
    global DOUYIN_COOKIES_PATH, DOUYIN_COOKIES_FROM_BROWSER
    global OPENROUTER_BASE_URL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME
    global OPENROUTER_TRANSCRIPTION_MODEL, OPENROUTER_ARTICLE_MODEL
    global AI_CLEANUP_ENABLED, AI_CLEANUP_BASE_URL, AI_CLEANUP_MODEL
    global ENABLE_ARTICLE_DRAFT, ARTICLE_DRAFT_BASE_URL, ARTICLE_DRAFT_MODEL
    global ENABLE_KNOWLEDGE_DRAFT

    settings = saved_settings if saved_settings is not None else load_settings()

    def value_for(key: str) -> object:
        if key in settings:
            return settings[key]
        return ENV_DEFAULTS[key]

    download_value = str(value_for("download_dir") or "").strip()
    DOWNLOAD_DIR = str(resolve_download_dir(download_value)) if download_value else str(
        resolve_download_dir(str(ENV_DEFAULTS["download_dir"]))
    )
    COOKIES_PATH = str(value_for("cookies_path") or "").strip()
    COOKIES_FROM_BROWSER = str(value_for("cookies_from_browser") or "").strip()
    YOUTUBE_COOKIES_PATH = str(value_for("youtube_cookies_path") or "").strip()
    YOUTUBE_COOKIES_FROM_BROWSER = str(value_for("youtube_cookies_from_browser") or "").strip()
    BILIBILI_COOKIES_PATH = str(value_for("bilibili_cookies_path") or "").strip()
    BILIBILI_COOKIES_FROM_BROWSER = str(value_for("bilibili_cookies_from_browser") or "").strip()
    DOUYIN_COOKIES_PATH = str(value_for("douyin_cookies_path") or "").strip()
    DOUYIN_COOKIES_FROM_BROWSER = str(value_for("douyin_cookies_from_browser") or "").strip()

    openrouter_backend.OPENROUTER_BASE_URL = str(value_for("openrouter_base_url") or "").strip()
    openrouter_backend.OPENROUTER_API_KEY = str(value_for("openrouter_api_key") or "").strip()
    openrouter_backend.OPENROUTER_SITE_URL = str(value_for("openrouter_site_url") or "").strip()
    openrouter_app_name = str(value_for("openrouter_app_name") or "").strip()
    if openrouter_app_name in LEGACY_APP_TITLES:
        openrouter_app_name = APP_TITLE
    openrouter_backend.OPENROUTER_APP_NAME = openrouter_app_name
    openrouter_backend.OPENROUTER_TRANSCRIPTION_MODEL = str(
        value_for("openrouter_transcription_model") or ""
    ).strip()
    openrouter_backend.OPENROUTER_ARTICLE_MODEL = str(
        value_for("openrouter_article_model") or ""
    ).strip()

    OPENROUTER_BASE_URL = openrouter_backend.OPENROUTER_BASE_URL
    OPENROUTER_SITE_URL = openrouter_backend.OPENROUTER_SITE_URL
    OPENROUTER_APP_NAME = openrouter_backend.OPENROUTER_APP_NAME
    OPENROUTER_TRANSCRIPTION_MODEL = openrouter_backend.OPENROUTER_TRANSCRIPTION_MODEL
    OPENROUTER_ARTICLE_MODEL = openrouter_backend.OPENROUTER_ARTICLE_MODEL

    cleanup_backend.AI_CLEANUP_ENABLED = bool(value_for("enable_ai_cleanup"))
    cleanup_backend.AI_CLEANUP_BASE_URL = str(value_for("ai_cleanup_base_url") or "").rstrip("/")
    cleanup_backend.AI_CLEANUP_API_KEY = str(value_for("ai_cleanup_api_key") or "").strip()
    cleanup_backend.AI_CLEANUP_MODEL = cleanup_backend.normalize_text_backend_model(
        str(value_for("ai_cleanup_model") or "").strip()
    )
    cleanup_backend.AI_CLEANUP_TIMEOUT_SECONDS = int(value_for("ai_cleanup_timeout_seconds") or 1)
    cleanup_backend.AI_CLEANUP_MAX_RETRIES = int(value_for("ai_cleanup_max_retries") or 1)
    cleanup_backend.AI_CLEANUP_PROMPT_TEXT = str(value_for("ai_cleanup_prompt_text") or "")

    cleanup_backend.ENABLE_ARTICLE_DRAFT = bool(value_for("enable_article_draft"))
    cleanup_backend.ARTICLE_DRAFT_BASE_URL = str(value_for("article_draft_base_url") or "").rstrip("/")
    cleanup_backend.ARTICLE_DRAFT_API_KEY = str(value_for("article_draft_api_key") or "").strip()
    cleanup_backend.ARTICLE_DRAFT_MODEL = cleanup_backend.normalize_text_backend_model(
        str(value_for("article_draft_model") or "").strip()
    )
    cleanup_backend.ARTICLE_DRAFT_TIMEOUT_SECONDS = int(value_for("article_draft_timeout_seconds") or 1)
    cleanup_backend.ARTICLE_DRAFT_MAX_RETRIES = int(value_for("article_draft_max_retries") or 1)
    cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT = str(value_for("article_draft_prompt_text") or "")

    cleanup_backend.ENABLE_KNOWLEDGE_DRAFT = bool(value_for("enable_knowledge_draft"))
    cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL = str(value_for("knowledge_draft_base_url") or "").rstrip("/")
    cleanup_backend.KNOWLEDGE_DRAFT_API_KEY = str(value_for("knowledge_draft_api_key") or "").strip()
    cleanup_backend.KNOWLEDGE_DRAFT_MODEL = cleanup_backend.normalize_text_backend_model(
        str(value_for("knowledge_draft_model") or "").strip()
    )
    cleanup_backend.KNOWLEDGE_DRAFT_TIMEOUT_SECONDS = int(value_for("knowledge_draft_timeout_seconds") or 1)
    cleanup_backend.KNOWLEDGE_DRAFT_MAX_RETRIES = int(value_for("knowledge_draft_max_retries") or 1)
    cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT = str(value_for("knowledge_draft_prompt_text") or "")

    AI_CLEANUP_ENABLED = cleanup_backend.AI_CLEANUP_ENABLED
    AI_CLEANUP_BASE_URL = cleanup_backend.AI_CLEANUP_BASE_URL
    AI_CLEANUP_MODEL = cleanup_backend.AI_CLEANUP_MODEL
    ENABLE_ARTICLE_DRAFT = cleanup_backend.ENABLE_ARTICLE_DRAFT
    ARTICLE_DRAFT_BASE_URL = cleanup_backend.ARTICLE_DRAFT_BASE_URL
    ARTICLE_DRAFT_MODEL = cleanup_backend.ARTICLE_DRAFT_MODEL
    ENABLE_KNOWLEDGE_DRAFT = cleanup_backend.ENABLE_KNOWLEDGE_DRAFT

    return current_runtime_settings()


def current_runtime_settings() -> dict:
    return {
        "settings_path": str(settings_path()),
        "settings_dir": str(settings_config_dir()),
        "web_jobs_state_path": str(web_jobs_state_path()),
        "runtime_environment": "container" if running_in_container() else "local",
        "download_dir": DOWNLOAD_DIR,
        "download_root_dir": str(download_root_path()) if download_root_path() else None,
        "download_root_locked": bool(download_root_path()),
        "host_downloads_dir": HOST_DOWNLOADS_DIR or None,
        "resume_web_jobs": RESUME_WEB_JOBS,
        "cookies_path": COOKIES_PATH,
        "cookies_from_browser": COOKIES_FROM_BROWSER,
        "youtube_cookies_path": YOUTUBE_COOKIES_PATH,
        "youtube_cookies_from_browser": YOUTUBE_COOKIES_FROM_BROWSER,
        "bilibili_cookies_path": BILIBILI_COOKIES_PATH,
        "bilibili_cookies_from_browser": BILIBILI_COOKIES_FROM_BROWSER,
        "douyin_cookies_path": DOUYIN_COOKIES_PATH,
        "douyin_cookies_from_browser": DOUYIN_COOKIES_FROM_BROWSER,
        "openrouter_base_url": openrouter_backend.OPENROUTER_BASE_URL,
        "openrouter_api_key": openrouter_backend.OPENROUTER_API_KEY,
        "openrouter_site_url": openrouter_backend.OPENROUTER_SITE_URL,
        "openrouter_app_name": openrouter_backend.OPENROUTER_APP_NAME,
        "openrouter_transcription_model": openrouter_backend.OPENROUTER_TRANSCRIPTION_MODEL,
        "openrouter_article_model": openrouter_backend.OPENROUTER_ARTICLE_MODEL,
        "enable_ai_cleanup": cleanup_backend.AI_CLEANUP_ENABLED,
        "ai_cleanup_base_url": cleanup_backend.AI_CLEANUP_BASE_URL,
        "ai_cleanup_api_key": cleanup_backend.AI_CLEANUP_API_KEY,
        "ai_cleanup_model": cleanup_backend.AI_CLEANUP_MODEL,
        "ai_cleanup_timeout_seconds": cleanup_backend.AI_CLEANUP_TIMEOUT_SECONDS,
        "ai_cleanup_max_retries": cleanup_backend.AI_CLEANUP_MAX_RETRIES,
        "ai_cleanup_prompt_file": cleanup_backend.AI_CLEANUP_PROMPT_FILE,
        "ai_cleanup_prompt_text": cleanup_backend.AI_CLEANUP_PROMPT_TEXT,
        "ai_cleanup_prompt_source": (
            "inline" if cleanup_backend.AI_CLEANUP_PROMPT_TEXT.strip() else "file"
        ),
        "enable_article_draft": cleanup_backend.ENABLE_ARTICLE_DRAFT,
        "article_draft_base_url": cleanup_backend.ARTICLE_DRAFT_BASE_URL,
        "article_draft_api_key": cleanup_backend.ARTICLE_DRAFT_API_KEY,
        "article_draft_model": cleanup_backend.ARTICLE_DRAFT_MODEL,
        "article_draft_timeout_seconds": cleanup_backend.ARTICLE_DRAFT_TIMEOUT_SECONDS,
        "article_draft_max_retries": cleanup_backend.ARTICLE_DRAFT_MAX_RETRIES,
        "article_draft_prompt_file": cleanup_backend.ARTICLE_DRAFT_PROMPT_FILE,
        "article_draft_prompt_text": cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT,
        "article_draft_prompt_source": (
            "inline" if cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT.strip() else "file"
        ),
        "enable_knowledge_draft": cleanup_backend.ENABLE_KNOWLEDGE_DRAFT,
        "knowledge_draft_base_url": cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL,
        "knowledge_draft_api_key": cleanup_backend.KNOWLEDGE_DRAFT_API_KEY,
        "knowledge_draft_model": cleanup_backend.KNOWLEDGE_DRAFT_MODEL,
        "knowledge_draft_timeout_seconds": cleanup_backend.KNOWLEDGE_DRAFT_TIMEOUT_SECONDS,
        "knowledge_draft_max_retries": cleanup_backend.KNOWLEDGE_DRAFT_MAX_RETRIES,
        "knowledge_draft_prompt_file": cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_FILE,
        "knowledge_draft_prompt_text": cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT,
        "knowledge_draft_prompt_source": (
            "inline" if cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT.strip() else "file"
        ),
    }


def map_runtime_path_to_host(path_value: str | None) -> str | None:
    normalized = str(path_value or "").strip()
    if not normalized:
        return None

    if not running_in_container():
        return normalized

    host_root = HOST_DOWNLOADS_DIR.strip()
    download_root = DOWNLOAD_ROOT_DIR.strip().rstrip("/")
    if not host_root or not download_root:
        return None

    if normalized == download_root:
        return host_root

    prefix = f"{download_root}/"
    if not normalized.startswith(prefix):
        return None

    suffix = normalized[len(prefix) :].lstrip("/")
    host_root = host_root.rstrip("/\\")
    return f"{host_root}/{suffix}" if suffix else host_root


def persist_runtime_settings(payload: dict, *, partial: bool = True) -> dict:
    current_settings = load_settings()
    normalized = _normalize_runtime_settings(payload, partial=partial)
    merged = dict(current_settings)
    merged.update(normalized)
    save_settings(merged)
    return apply_runtime_settings(merged)


def mask_secret_value(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"


def masked_runtime_settings() -> dict:
    payload = current_runtime_settings()
    for key in SECRET_SETTING_KEYS:
        secret = str(payload.get(key) or "")
        payload[f"{key}_configured"] = bool(secret)
        payload[key] = mask_secret_value(secret)
    return payload


def sanitize_settings_update_payload(payload: dict) -> dict:
    validate_secret_rotation_for_base_url_change(payload)
    sanitized = dict(payload)
    current = current_runtime_settings()

    for key in SECRET_SETTING_KEYS:
        if key not in sanitized:
            continue
        value = str(sanitized.get(key) or "").strip()
        if value and value == mask_secret_value(str(current.get(key) or "")):
            sanitized.pop(key)
            continue
        sanitized[key] = value

    return sanitized


def normalize_base_url_for_compare(value: object) -> str:
    return str(value or "").strip().rstrip("/")


def validate_secret_rotation_for_base_url_change(payload: dict) -> None:
    current = current_runtime_settings()

    for base_key, secret_key in SECRET_BACKED_BASE_URL_FIELDS.items():
        if base_key not in payload:
            continue

        previous_base_url = normalize_base_url_for_compare(current.get(base_key))
        next_base_url = normalize_base_url_for_compare(payload.get(base_key))
        if next_base_url == previous_base_url:
            continue

        current_secret = str(current.get(secret_key) or "").strip()
        if not current_secret:
            continue

        if secret_key not in payload:
            raise ValueError(f"变更 {base_key} 时请重新输入对应 API Key，或显式清空。")

        submitted_secret = str(payload.get(secret_key) or "").strip()
        if submitted_secret and submitted_secret == mask_secret_value(current_secret):
            raise ValueError(f"变更 {base_key} 时不能复用脱敏 API Key，请重新输入或显式清空。")


def request_web_token() -> str:
    header_token = request.headers.get(WEB_TOKEN_HEADER, "").strip()
    if header_token:
        return header_token

    authorization = request.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return ""


def require_web_token(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not WEB_TOKEN:
            return view_func(*args, **kwargs)

        if hmac.compare_digest(request_web_token(), WEB_TOKEN):
            return view_func(*args, **kwargs)

        response = jsonify({"error": "需要有效的 MUKU_WEB_TOKEN。", "token_required": True})
        response.status_code = 401
        response.headers["WWW-Authenticate"] = 'Bearer realm="Muku"'
        return response

    return wrapper


apply_runtime_settings()


class YtdlpLogger:
    def __init__(self, job: Job):
        self.job = job

    def debug(self, msg: str) -> None:
        return

    def info(self, msg: str) -> None:
        return

    def warning(self, msg: str) -> None:
        self._remember(msg)

    def error(self, msg: str) -> None:
        self._remember(msg)

    def _remember(self, msg: str) -> None:
        message = msg.strip()
        if not message:
            return
        with self.job.lock:
            self.job.backend_error = message


def set_job_state(job: Job, *, status: str | None = None, progress: float | None = None) -> None:
    with job.lock:
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
    persist_jobs_state()


def progress_hook(job: Job):
    def hook(data):
        if data["status"] == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes")
            with job.lock:
                if total and downloaded:
                    job.progress = (downloaded / total) * 100
                job.status = data.get("_percent_str", "0%").strip() + " " + data.get(
                    "_speed_str", ""
                ).strip()
                if data.get("info_dict"):
                    job.title = data["info_dict"].get("title", job.title)
            persist_jobs_state()
        elif data["status"] == "finished":
            with job.lock:
                job.progress = 100
                job.status = (
                    "Download finished. Preparing transcript..."
                    if job.generate_transcript
                    else "Download finished."
                )
            persist_jobs_state(force=True)

    return hook


def output_template(base_dir: str | Path | None = None) -> str:
    target_dir = Path(base_dir) if base_dir is not None else Path(DOWNLOAD_DIR)
    title_token = f"%(title).{MAX_OUTPUT_TITLE_CHARS}s"
    stem = f"{title_token} [%(id)s]"
    return str(target_dir / stem / f"{stem}.%(ext)s")


def parse_cookies_from_browser_spec(spec: str) -> tuple[str, str | None, str | None, str | None]:
    match = COOKIES_FROM_BROWSER_RE.fullmatch(spec.strip())
    if match is None:
        raise ValueError(f"Invalid COOKIES_FROM_BROWSER value: {spec}")
    browser_name, keyring, profile, container = match.group("name", "keyring", "profile", "container")
    return (browser_name.lower(), profile, keyring.upper() if keyring else None, container)


def _cookie_source_candidates(platform: str) -> tuple[dict[str, str], ...]:
    if platform == "YouTube":
        return (
            {
                "kind": "file",
                "scope": "platform",
                "config_key": "YOUTUBE_COOKIES_PATH",
                "value": YOUTUBE_COOKIES_PATH,
            },
            {
                "kind": "browser",
                "scope": "platform",
                "config_key": "YOUTUBE_COOKIES_FROM_BROWSER",
                "value": YOUTUBE_COOKIES_FROM_BROWSER,
            },
            {
                "kind": "file",
                "scope": "global",
                "config_key": "COOKIES_PATH",
                "value": COOKIES_PATH,
            },
            {
                "kind": "browser",
                "scope": "global",
                "config_key": "COOKIES_FROM_BROWSER",
                "value": COOKIES_FROM_BROWSER,
            },
        )
    if platform == "Bilibili":
        return (
            {
                "kind": "file",
                "scope": "platform",
                "config_key": "BILIBILI_COOKIES_PATH",
                "value": BILIBILI_COOKIES_PATH,
            },
            {
                "kind": "browser",
                "scope": "platform",
                "config_key": "BILIBILI_COOKIES_FROM_BROWSER",
                "value": BILIBILI_COOKIES_FROM_BROWSER,
            },
            {
                "kind": "file",
                "scope": "global",
                "config_key": "COOKIES_PATH",
                "value": COOKIES_PATH,
            },
            {
                "kind": "browser",
                "scope": "global",
                "config_key": "COOKIES_FROM_BROWSER",
                "value": COOKIES_FROM_BROWSER,
            },
        )
    if platform == "Douyin":
        return (
            {
                "kind": "file",
                "scope": "platform",
                "config_key": "DOUYIN_COOKIES_PATH",
                "value": DOUYIN_COOKIES_PATH,
            },
            {
                "kind": "browser",
                "scope": "platform",
                "config_key": "DOUYIN_COOKIES_FROM_BROWSER",
                "value": DOUYIN_COOKIES_FROM_BROWSER,
            },
            {
                "kind": "file",
                "scope": "global",
                "config_key": "COOKIES_PATH",
                "value": COOKIES_PATH,
            },
            {
                "kind": "browser",
                "scope": "global",
                "config_key": "COOKIES_FROM_BROWSER",
                "value": COOKIES_FROM_BROWSER,
            },
        )
    return (
        {
            "kind": "file",
            "scope": "global",
            "config_key": "COOKIES_PATH",
            "value": COOKIES_PATH,
        },
        {
            "kind": "browser",
            "scope": "global",
            "config_key": "COOKIES_FROM_BROWSER",
            "value": COOKIES_FROM_BROWSER,
        },
    )


def _format_browser_cookie_source(spec: str) -> str:
    browser_name, profile, keyring, container = parse_cookies_from_browser_spec(spec)
    parts = [browser_name]
    if profile:
        parts.append(f"profile={profile}")
    if keyring:
        parts.append(f"keyring={keyring}")
    if container:
        parts.append(f"container={container}")
    return ", ".join(parts)


def platform_auth_state(platform: str) -> dict[str, object]:
    selected = next(
        (candidate for candidate in _cookie_source_candidates(platform) if str(candidate["value"]).strip()),
        None,
    )
    state: dict[str, object] = {
        "platform": platform,
        "configured": False,
        "verified": False,
        "status": "missing",
        "source_kind": "none",
        "source_scope": None,
        "source_config_key": None,
        "source_path": None,
        "source_browser": None,
        "source_spec_valid": None,
        "source_display": "not configured",
        "runtime_environment": "container" if running_in_container() else "local",
        "docker_risky": False,
    }
    if selected is None:
        return state

    state.update(
        {
            "configured": True,
            "source_kind": selected["kind"],
            "source_scope": selected["scope"],
            "source_config_key": selected["config_key"],
        }
    )

    if selected["kind"] == "file":
        source_path = Path(str(selected["value"])).expanduser()
        path_exists = source_path.exists()
        verified = path_exists
        status = "verified" if path_exists else "missing_file"
        health_detail = ""
        health_suggestion = ""
        health_skipped = False
        if path_exists:
            try:
                health = cookie_health.check_platform(platform, source_path)
                health_detail = health.detail
                health_suggestion = health.suggestion
                health_skipped = health.skipped
                if not health.skipped:
                    verified = health.ok
                    status = "verified" if health.ok else "invalid"
            except Exception as exc:
                verified = False
                status = "check_failed"
                health_detail = f"cookies 预检失败：{exc}"
        state.update(
            {
                "verified": verified,
                "status": status,
                "source_path": str(source_path),
                "source_display": f"{selected['config_key']}={source_path}",
                "health_detail": health_detail,
                "health_suggestion": health_suggestion,
                "health_skipped": health_skipped,
            }
        )
        return state

    try:
        browser_label = _format_browser_cookie_source(str(selected["value"]))
    except ValueError:
        state.update(
            {
                "status": "invalid",
                "source_spec_valid": False,
                "source_display": f"{selected['config_key']}={selected['value']}",
            }
        )
        return state

    state.update(
        {
            "status": "configured_only",
            "source_browser": browser_label,
            "source_spec_valid": True,
            "source_display": f"{selected['config_key']}={browser_label}",
            "docker_risky": running_in_container(),
        }
    )
    return state


def platform_auth_configured(platform: str) -> bool:
    return bool(platform_auth_state(platform)["configured"])


def platform_auth_verified(platform: str) -> bool:
    return bool(platform_auth_state(platform)["verified"])


def prepare_cookiefile_for_ytdlp(cookiefile: str) -> str:
    source_path = Path(cookiefile).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        return str(source_path)

    stat = source_path.stat()
    fingerprint = hashlib.sha1(
        f"{source_path}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:12]
    prepared_dir = Path(tempfile.gettempdir()) / "video-downloade-cookies"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = prepared_dir / f"{sanitize_output_component(source_path.stem)}.{fingerprint}{source_path.suffix}"

    if (
        not prepared_path.exists()
        or prepared_path.stat().st_size != stat.st_size
        or prepared_path.stat().st_mtime_ns < stat.st_mtime_ns
    ):
        shutil.copy2(source_path, prepared_path)
        try:
            prepared_path.chmod(0o600)
        except OSError:
            pass

    return str(prepared_path)


def resolve_cookie_options(url: str) -> dict:
    platform = detect_platform(url)

    if platform == "YouTube":
        if YOUTUBE_COOKIES_PATH:
            return {"cookiefile": prepare_cookiefile_for_ytdlp(YOUTUBE_COOKIES_PATH)}
        if YOUTUBE_COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(YOUTUBE_COOKIES_FROM_BROWSER)}
        if COOKIES_PATH:
            return {"cookiefile": prepare_cookiefile_for_ytdlp(COOKIES_PATH)}
        if COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
        return {}

    if platform == "Bilibili":
        if BILIBILI_COOKIES_PATH:
            return {"cookiefile": prepare_cookiefile_for_ytdlp(BILIBILI_COOKIES_PATH)}
        if BILIBILI_COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(BILIBILI_COOKIES_FROM_BROWSER)}
        if COOKIES_PATH:
            return {"cookiefile": prepare_cookiefile_for_ytdlp(COOKIES_PATH)}
        if COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
        return {}

    if platform == "Douyin":
        if DOUYIN_COOKIES_PATH:
            return {"cookiefile": prepare_cookiefile_for_ytdlp(DOUYIN_COOKIES_PATH)}
        if DOUYIN_COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(DOUYIN_COOKIES_FROM_BROWSER)}
        if COOKIES_PATH:
            return {"cookiefile": prepare_cookiefile_for_ytdlp(COOKIES_PATH)}
        if COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
        return {}

    if COOKIES_FROM_BROWSER:
        return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
    if COOKIES_PATH:
        return {"cookiefile": prepare_cookiefile_for_ytdlp(COOKIES_PATH)}
    return {}


def humanize_ydlp_error(job: Job, error_message: str) -> str:
    platform = detect_platform(job.url)
    normalized = (error_message or "").strip()
    folded = normalized.replace("’", "'")

    if platform == "Kuaishou" and (
        "Unsupported URL" in folded or "UNEXPECTED_EOF_WHILE_READING" in folded
    ):
        return (
            "当前内置下载后端还不支持快手链接解析。要把快手做成稳定可用，需要补一个专用 provider，"
            "或接入已经验证支持快手的下载能力。"
        )

    if platform == "WeChat Channels" and "Unsupported URL" in folded:
        return (
            "视频号当前不适合直接走这个 Docker / Web 后端链路。更现实的路径是桌面端 bridge："
            "先在用户本机桌面环境导出可下载资源，再接入当前逐字稿和知识库流程。"
        )

    if platform == "YouTube" and "Sign in to confirm you're not a bot" in folded:
        if platform_auth_configured("YouTube"):
            return (
                "YouTube 当前拒绝了这次下载请求。通常是登录态失效、浏览器没有登录 YouTube，"
                "或导出的 Cookies 已过期。建议重新登录 YouTube 后，优先在 .env 配置 "
                "`YOUTUBE_COOKIES_FROM_BROWSER=chrome`，或者重新导出 YouTube 专用 cookies.txt。"
            )
        return (
            "YouTube 现在经常会对 yt-dlp 请求做 bot 校验。当前没有检测到可用于 YouTube 的登录态，"
            "请在 .env 里配置 `YOUTUBE_COOKIES_FROM_BROWSER=chrome`，或填写 "
            "`YOUTUBE_COOKIES_PATH=/absolute/path/to/youtube.cookies.txt` 后重试。"
        )

    if platform == "YouTube" and "Requested format is not available" in normalized:
        return (
            "这条 YouTube 视频当前返回的是受挑战保护的格式集合。通常需要启用 JS challenge 远程组件，"
            "并优先使用浏览器登录态。项目现在建议在 .env 配置 "
            "`YOUTUBE_COOKIES_FROM_BROWSER=chrome`，并保留默认 `YTDLP_REMOTE_COMPONENTS=ejs:github`。"
        )

    if platform == "Douyin" and any(
        marker in folded.lower()
        for marker in (
            "login",
            "cookies",
            "verify",
            "captcha",
        )
    ):
        if platform_auth_configured("Douyin"):
            return (
                "抖音当前拒绝了这次请求。通常是平台登录态失效、需要重新验证，"
                "或导出的 Cookies 已过期。建议重新登录抖音后，优先在 .env 配置 "
                "`DOUYIN_COOKIES_FROM_BROWSER=chrome`，或更新 `DOUYIN_COOKIES_PATH`。"
            )
        return (
            "抖音当前对这次请求做了额外校验。若后续出现登录或验证报错，"
            "请在 .env 配置 `DOUYIN_COOKIES_FROM_BROWSER=chrome`，"
            "或填写 `DOUYIN_COOKIES_PATH=/absolute/path/to/douyin.cookies.txt` 后重试。"
        )

    return normalized


def build_ydl_options(job: Job, *, preset_name: str | None = None, base_dir: str | Path | None = None) -> dict:
    target_preset = preset_name or job.preset
    preset_conf = FORMAT_PRESETS[target_preset]
    if preset_conf.get("transcript_only"):
        preset_conf = FORMAT_PRESETS[AUDIO_PRESET_NAME]
    options = {
        "format": preset_conf["format"],
        "outtmpl": output_template(base_dir),
        "progress_hooks": [progress_hook(job)],
        "logger": YtdlpLogger(job),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "continuedl": True,
    }

    if "merge_output_format" in preset_conf:
        options["merge_output_format"] = preset_conf["merge_output_format"]
    if "postprocessors" in preset_conf:
        options["postprocessors"] = preset_conf["postprocessors"]
    if detect_platform(job.url) == "YouTube" and YTDLP_REMOTE_COMPONENTS:
        options["remote_components"] = list(YTDLP_REMOTE_COMPONENTS)
    if job.use_cookies:
        options.update(resolve_cookie_options(job.url))
    return options


def resolve_media_path(expected_path: Path, preset: str) -> Path:
    artifact_dir = expected_path.parent
    if preset == AUDIO_PRESET_NAME:
        candidate = expected_path.with_suffix(".mp3")
        if candidate.exists():
            return candidate
        matches = sorted(artifact_dir.glob("*.mp3"))
        if matches:
            return matches[0]
        raise RuntimeError("Downloaded MP3 file was not found.")

    if expected_path.exists():
        return expected_path

    matches = sorted(
        path
        for path in artifact_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4a"}
    )
    if matches:
        return matches[0]
    raise RuntimeError("Downloaded media file was not found.")


def primary_info_dict(info: dict | None) -> dict | None:
    if not isinstance(info, dict):
        return None

    if info.get("_type") in {"playlist", "multi_video"}:
        for entry in info.get("entries") or []:
            primary_entry = primary_info_dict(entry)
            if primary_entry:
                return primary_entry
        return None

    return info


def extract_source_author(info: dict | None) -> str | None:
    if not isinstance(info, dict):
        return None
    for key in ("uploader", "channel", "creator", "artist", "uploader_id"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def format_duration_label(total_seconds: int | float | None) -> str | None:
    if total_seconds is None:
        return None
    try:
        seconds = max(0, int(total_seconds))
    except (TypeError, ValueError):
        return None

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def prepare_audio_for_transcription(audio_path: Path) -> Path:
    source_path = audio_path.expanduser().resolve()
    stat = source_path.stat()
    fingerprint = hashlib.sha1(
        f"{source_path}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:12]
    prepared_dir = Path(tempfile.gettempdir()) / "video-downloade-transcription"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = prepared_dir / f"{audio_path.stem}.{fingerprint}.transcribe.mp3"
    if prepared_path.exists() and prepared_path.stat().st_mtime >= audio_path.stat().st_mtime:
        return prepared_path

    command = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        TRANSCRIPTION_AUDIO_BITRATE,
        str(prepared_path),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        return prepared_path
    except (FileNotFoundError, subprocess.CalledProcessError):
        return audio_path


def _parse_bitrate_bits_per_second(value: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*", str(value or ""))
    if match is None:
        return None

    amount = float(match.group(1))
    suffix = match.group(2).lower()
    multiplier = 1
    if suffix == "k":
        multiplier = 1000
    elif suffix == "m":
        multiplier = 1000 * 1000
    return max(1, int(amount * multiplier))


def estimate_audio_duration_seconds(audio_path: Path) -> float | None:
    bitrate_bps = _parse_bitrate_bits_per_second(TRANSCRIPTION_AUDIO_BITRATE)
    if bitrate_bps is None:
        return None
    try:
        size_bytes = audio_path.expanduser().resolve().stat().st_size
    except OSError:
        return None
    if size_bytes <= 0:
        return 0.0
    return (size_bytes * 8) / bitrate_bps


def should_chunk_audio_for_transcription(audio_path: Path) -> bool:
    if not ENABLE_TRANSCRIPTION_CHUNKING:
        return False
    estimated_duration = estimate_audio_duration_seconds(audio_path)
    if estimated_duration is None:
        return False
    return estimated_duration > TRANSCRIPTION_CHUNK_SECONDS


def split_audio_for_transcription(audio_path: Path) -> list[Path]:
    source_path = audio_path.expanduser().resolve()
    if not ENABLE_TRANSCRIPTION_CHUNKING:
        return [source_path]

    stat = source_path.stat()
    fingerprint = hashlib.sha1(
        f"{source_path}:{stat.st_size}:{stat.st_mtime_ns}:{TRANSCRIPTION_CHUNK_SECONDS}".encode("utf-8")
    ).hexdigest()[:12]
    prepared_dir = Path(tempfile.gettempdir()) / "video-downloade-transcription"
    chunk_dir = prepared_dir / f"{audio_path.stem}.{fingerprint}.chunks"
    manifest_path = chunk_dir / ".complete"

    existing_segments = sorted(chunk_dir.glob("chunk-*.mp3"))
    if existing_segments and manifest_path.exists() and manifest_path.stat().st_mtime >= source_path.stat().st_mtime:
        return existing_segments

    if chunk_dir.exists():
        shutil.rmtree(chunk_dir, ignore_errors=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = chunk_dir / "chunk-%03d.mp3"
    command = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(source_path),
        "-f",
        "segment",
        "-segment_time",
        str(TRANSCRIPTION_CHUNK_SECONDS),
        "-reset_timestamps",
        "1",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        TRANSCRIPTION_AUDIO_BITRATE,
        str(output_pattern),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [source_path]

    segments = sorted(chunk_dir.glob("chunk-*.mp3"))
    if not segments:
        return [source_path]
    manifest_path.write_text(json.dumps({"chunk_seconds": TRANSCRIPTION_CHUNK_SECONDS}) + "\n", encoding="utf-8")
    return segments


def cleanup_transcription_chunks(chunk_paths: list[Path]) -> None:
    if not chunk_paths:
        return
    chunk_dir = chunk_paths[0].parent
    if chunk_dir.name.endswith(".chunks"):
        shutil.rmtree(chunk_dir, ignore_errors=True)


def merge_transcript_chunks(chunks: list[str]) -> str:
    merged_parts: list[str] = []
    for chunk in chunks:
        normalized = normalize_raw_transcript_text(chunk).strip()
        if not normalized:
            continue
        if merged_parts:
            previous_lines = [line.strip() for line in merged_parts[-1].splitlines() if line.strip()]
            current_lines = [line.strip() for line in normalized.splitlines() if line.strip()]
            if previous_lines and current_lines and previous_lines[-1] == current_lines[0]:
                current_lines = current_lines[1:]
                normalized = "\n".join(current_lines).strip()
        if normalized:
            merged_parts.append(normalized)
    return "\n\n".join(merged_parts).strip()


def build_chunked_transcript_route(base_route: str) -> str:
    route = str(base_route or "audio_transcription").strip() or "audio_transcription"
    if route.endswith("_chunked"):
        return route
    return f"{route}_chunked"


def should_retry_transcription_with_chunks(exc: Exception) -> bool:
    if not ENABLE_TRANSCRIPTION_CHUNKING:
        return False
    message = str(exc).strip().lower()
    if not message:
        return False
    return "truncated before completion" in message


def transcribe_audio_in_chunks(job: Job, audio_path: Path, *, fallback_error: Exception | None = None) -> dict:
    chunk_paths = split_audio_for_transcription(audio_path)
    if len(chunk_paths) <= 1:
        if fallback_error is not None:
            raise fallback_error
        result = transcribe_audio(
            chunk_paths[0],
            title=job.title,
            source_url=job.url,
            language_hint=TRANSCRIPTION_LANGUAGE,
        )
        return {
            **result,
            "chunked": False,
            "chunk_count": 1,
            "chunk_paths": [str(chunk_paths[0])],
        }

    chunk_texts: list[str] = []
    chunk_responses: list[dict[str, object]] = []
    for index, chunk_path in enumerate(chunk_paths, start=1):
        set_job_state(
            job,
            status=f"Transcribing chunk {index}/{len(chunk_paths)} with {OPENROUTER_TRANSCRIPTION_MODEL}...",
        )
        result = transcribe_audio(
            chunk_path,
            title=f"{job.title} [chunk {index}/{len(chunk_paths)}]",
            source_url=job.url,
            language_hint=TRANSCRIPTION_LANGUAGE,
        )
        chunk_text = normalize_raw_transcript_text(result["text"]).strip()
        if not chunk_text:
            raise RuntimeError(f"Chunk {index}/{len(chunk_paths)} returned an empty transcript.")
        chunk_texts.append(chunk_text)
        chunk_responses.append(
            {
                "index": index,
                "path": str(chunk_path),
                "response": result["raw_response"],
            }
        )

    merged_text = merge_transcript_chunks(chunk_texts)
    if not merged_text:
        raise RuntimeError("Chunked transcription returned an empty transcript.")

    return {
        "provider": "openrouter",
        "model": OPENROUTER_TRANSCRIPTION_MODEL,
        "text": merged_text,
        "raw_response": {
            "chunked": True,
            "chunk_count": len(chunk_paths),
            "fallback_error": str(fallback_error) if fallback_error else None,
            "chunks": chunk_responses,
        },
        "chunked": True,
        "chunk_count": len(chunk_paths),
        "chunk_paths": [str(path) for path in chunk_paths],
    }


def sanitize_output_component(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', "_", value).strip().rstrip(".")
    return sanitized or "untitled"


def truncate_output_title(title: str) -> str:
    sanitized = sanitize_output_component(title)
    if len(sanitized) <= MAX_OUTPUT_TITLE_CHARS:
        return sanitized
    return sanitized[:MAX_OUTPUT_TITLE_CHARS].rstrip() or sanitized[:MAX_OUTPUT_TITLE_CHARS]


def build_output_stem(title: str, media_id: str) -> str:
    safe_title = truncate_output_title(title)
    return sanitize_output_component(f"{safe_title} [{media_id}]")


def normalize_shared_url(candidate: str) -> str:
    trailing_chars = ".,!?;:)]}>\"'。 ，！？；：、）】」』》".replace(" ", "")
    return candidate.strip().rstrip(trailing_chars)


def is_supported_share_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip().rstrip(".").lower()
    if not hostname:
        return False
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in SUPPORTED_SHARE_HOST_SUFFIXES)


def _hostname_platform_label(hostname: str) -> str:
    normalized = hostname.strip().rstrip(".").lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if not normalized:
        return "Other"
    if normalized in {"x.com", "twitter.com"}:
        return "X"
    return normalized


def platform_label_for_url(url: str, info: dict | None = None) -> str:
    detected = detect_platform(url)
    if detected != "Unknown":
        return detected

    if isinstance(info, dict):
        for key in ("extractor_key", "extractor"):
            raw_value = info.get(key)
            if not isinstance(raw_value, str):
                continue
            candidate = raw_value.strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered in {"generic", "unknown"}:
                continue
            if lowered.startswith("twitter"):
                return "X"
            if lowered.startswith("youtube"):
                return "YouTube"
            if lowered.startswith("bilibili"):
                return "Bilibili"
            if lowered.startswith("douyin"):
                return "Douyin"
            if lowered.startswith("tiktok"):
                return "TikTok"
            if lowered.startswith("ted"):
                return "TED"
            if lowered.startswith("archiveorg") or lowered.startswith("archive.org"):
                return "Archive.org"
            return candidate.replace("_", " ").replace("-", " ")

    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return _hostname_platform_label(hostname)


def _remember_preferred_url(urls: list[str], seen: set[str], candidate: str) -> None:
    cleaned = normalize_shared_url(candidate)
    if not cleaned:
        return
    if cleaned in seen:
        return

    for index, existing in enumerate(urls):
        if cleaned.startswith(existing) and len(cleaned) > len(existing) and cleaned[len(existing)] in {"&", "#"}:
            seen.discard(existing)
            urls[index] = cleaned
            seen.add(cleaned)
            return
        if existing.startswith(cleaned) and len(existing) > len(cleaned) and existing[len(cleaned)] in {"&", "#"}:
            return

    urls.append(cleaned)
    seen.add(cleaned)


def _extract_supported_urls_from_candidate(candidate: str, *, max_depth: int = 2) -> list[str]:
    normalized = normalize_shared_url(candidate)
    if not normalized or max_depth < 0:
        return []

    supported: list[str] = []
    seen: set[str] = set()

    def remember(url: str) -> None:
        _remember_preferred_url(supported, seen, url)

    if is_supported_share_url(normalized):
        remember(normalized)

    if max_depth == 0:
        return supported

    decoded_candidate = unquote(normalized)
    if decoded_candidate != normalized:
        for extracted in extract_supported_urls_from_text(decoded_candidate, max_depth=max_depth - 1):
            remember(extracted)

    parsed = urlparse(normalized)
    for _key, value in parse_qsl(parsed.query, keep_blank_values=True):
        nested_value = normalize_shared_url(unquote(value))
        if not nested_value:
            continue
        for extracted in extract_supported_urls_from_text(nested_value, max_depth=max_depth - 1):
            remember(extracted)

    return supported


def extract_supported_urls_from_text(text: str, *, max_depth: int = 2) -> list[str]:
    supported: list[str] = []
    seen: set[str] = set()

    def remember(url: str) -> None:
        _remember_preferred_url(supported, seen, url)

    for match in URL_CANDIDATE_RE.finditer(text):
        for extracted in _extract_supported_urls_from_candidate(match.group(0), max_depth=max_depth):
            remember(extracted)

    for match in BARE_URL_CANDIDATE_RE.finditer(text):
        candidate = normalize_shared_url(match.group(0))
        if candidate and not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        for extracted in _extract_supported_urls_from_candidate(candidate, max_depth=max_depth):
            remember(extracted)

    return supported


def extract_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for match in URL_CANDIDATE_RE.finditer(text):
        normalized = normalize_shared_url(match.group(0))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)

    return urls


def extract_bare_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for match in BARE_URL_CANDIDATE_RE.finditer(text):
        normalized = normalize_shared_url(match.group(0))
        if normalized and not normalized.startswith(("http://", "https://")):
            normalized = f"https://{normalized}"
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)

    return urls


def collect_url_inputs(text: str) -> list[str]:
    supported_urls = extract_supported_urls_from_text(text)
    if supported_urls:
        return supported_urls

    urls = extract_urls_from_text(text)
    if urls:
        return urls

    bare_urls = extract_bare_urls_from_text(text)
    if bare_urls:
        return bare_urls

    stripped = text.strip()
    return [stripped] if stripped else []


def has_url_like_input(text: str) -> bool:
    return bool(extract_urls_from_text(text) or BARE_URL_CANDIDATE_RE.search(text))


def is_unsafe_ip_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            address.is_loopback,
            address.is_link_local,
            address.is_private,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def parse_relaxed_ip_address(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass

    try:
        return ipaddress.IPv4Address(socket.inet_aton(hostname))
    except (ipaddress.AddressValueError, OSError):
        return None


def hostname_resolves_to_unsafe_ip(hostname: str) -> bool:
    try:
        addrinfo = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return False

    saw_parseable_address = False
    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        candidate = str(sockaddr[0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        saw_parseable_address = True
        if not is_unsafe_ip_address(address):
            return False
    return saw_parseable_address


def hostname_matches_trusted_web_suffix(hostname: str) -> bool:
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in TRUSTED_WEB_HOST_SUFFIXES
    )


def is_unsafe_web_url_target(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return True

    hostname = (parsed.hostname or "").strip().rstrip(".").lower()
    if not hostname:
        return True

    if hostname in UNSAFE_WEB_HOSTNAMES or any(hostname.endswith(suffix) for suffix in UNSAFE_WEB_HOST_SUFFIXES):
        return True

    address = parse_relaxed_ip_address(hostname)
    if address is not None:
        return is_unsafe_ip_address(address)

    if hostname_matches_trusted_web_suffix(hostname):
        return False

    return hostname_resolves_to_unsafe_ip(hostname)


def validate_web_start_urls(urls: list[str]) -> None:
    if len(urls) > MAX_START_URLS:
        raise ValueError(f"单次最多提交 {MAX_START_URLS} 个链接，请分批提交。")

    for url in urls:
        if is_unsafe_web_url_target(url):
            raise ValueError("Web 面板不允许访问本机、内网、保留网段或云元数据地址。")


def build_artifact_base_path(info: dict, *, base_dir: str | Path | None = None) -> Path:
    title = info.get("title") or info.get("id") or "Untitled"
    media_id = info.get("id") or uuid.uuid4().hex[:8]
    stem = build_output_stem(str(title), str(media_id))
    target_dir = Path(base_dir) if base_dir is not None else Path(DOWNLOAD_DIR)
    return target_dir / stem / stem


def build_subtitle_probe_options(
    job: Job,
    *,
    temp_dir: Path,
    subtitle_languages: list[str] | None = None,
) -> dict:
    options = build_ydl_options(job, preset_name=AUDIO_PRESET_NAME, base_dir=temp_dir)
    options.pop("format", None)
    options.pop("postprocessors", None)
    options["progress_hooks"] = []
    options["skip_download"] = True
    options["outtmpl"] = str(temp_dir / "subtitle-probe.%(ext)s")
    options["writesubtitles"] = True
    options["writeautomaticsub"] = True
    requested_languages = [str(lang).strip() for lang in (subtitle_languages or SUBTITLE_LANGUAGES) if str(lang).strip()]
    options["subtitleslangs"] = requested_languages or ["all"]
    options["subtitlesformat"] = SUBTITLE_FORMATS
    return options


def _subtitle_language_rank(lang: str) -> int:
    lowered = lang.lower()
    for index, preferred in enumerate(SUBTITLE_LANGUAGES):
        if lowered == preferred.lower():
            return index
    return len(SUBTITLE_LANGUAGES)


def summarize_subtitle_availability(info: dict | None) -> dict[str, object]:
    if not isinstance(info, dict):
        return {
            "available": False,
            "manual_languages": [],
            "automatic_languages": [],
            "preferred_language": None,
            "preferred_source": None,
        }

    manual_languages = sorted(
        {
            str(lang).strip()
            for lang in (info.get("subtitles") or {}).keys()
            if str(lang).strip()
        },
        key=_subtitle_language_rank,
    )
    automatic_languages = sorted(
        {
            str(lang).strip()
            for lang in (info.get("automatic_captions") or {}).keys()
            if str(lang).strip()
        },
        key=_subtitle_language_rank,
    )

    preferred_language = (
        manual_languages[0]
        if manual_languages
        else automatic_languages[0]
        if automatic_languages
        else None
    )
    preferred_source = "manual" if manual_languages else "automatic" if automatic_languages else None
    return {
        "available": bool(manual_languages or automatic_languages),
        "manual_languages": manual_languages,
        "automatic_languages": automatic_languages,
        "preferred_language": preferred_language,
        "preferred_source": preferred_source,
    }


def select_subtitle_probe_languages(info: dict | None) -> list[str]:
    summary = summarize_subtitle_availability(info)
    preferred_language = summary.get("preferred_language")
    if isinstance(preferred_language, str) and preferred_language.strip():
        return [preferred_language.strip()]
    return list(SUBTITLE_LANGUAGES)


def build_transcript_recommendation(
    *,
    url: str,
    use_cookies: bool,
    auth_state: dict[str, object],
    subtitle_summary: dict[str, object],
) -> dict[str, object]:
    platform = detect_platform(url)
    subtitles_available = bool(subtitle_summary.get("available"))
    if platform == "Douyin":
        if use_cookies and bool(auth_state.get("configured")):
            return {
                "preset": TRANSCRIPT_PRESET_NAME,
                "transcript_route": "douyin_audio_transcription",
                "use_cookies_recommended": True,
                "reason": "抖音更适合走专用 provider：先取音频，再进入逐字稿链路。",
            }
        return {
            "preset": TRANSCRIPT_PRESET_NAME,
            "transcript_route": "douyin_audio_transcription",
            "use_cookies_recommended": True,
            "reason": "抖音要想稳定处理，通常需要有效登录态；建议启用抖音 cookies 后再发起任务。",
        }

    if subtitles_available:
        return {
            "preset": TRANSCRIPT_PRESET_NAME,
            "transcript_route": "direct_subtitles",
            "use_cookies_recommended": bool(auth_state.get("configured")),
            "reason": "当前信息显示平台可能提供字幕，优先直提字幕会更快也更稳。",
        }

    return {
        "preset": TRANSCRIPT_PRESET_NAME,
        "transcript_route": "subtitle_probe_fallback_to_audio",
        "use_cookies_recommended": bool(auth_state.get("configured")),
        "reason": "预计会先探测字幕；若没有可用字幕，再回退到音频转写。",
    }


def build_parse_preview_options(url: str, *, use_cookies: bool) -> dict:
    preview_job = Job(
        job_id="preview",
        url=url,
        preset=AUDIO_PRESET_NAME,
        use_cookies=use_cookies,
        generate_transcript=False,
    )
    options = build_ydl_options(
        preview_job,
        preset_name=AUDIO_PRESET_NAME,
        base_dir=Path(tempfile.gettempdir()),
    )
    options["skip_download"] = True
    options["progress_hooks"] = []
    options["quiet"] = True
    options["no_warnings"] = True
    return options


def select_thumbnail_url(info: dict | None) -> str | None:
    if not isinstance(info, dict):
        return None
    thumbnail = info.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail.strip():
        return thumbnail.strip()
    thumbnails = info.get("thumbnails") or []
    for item in reversed(thumbnails):
        url = item.get("url") if isinstance(item, dict) else None
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def preview_source_url(url: str, *, use_cookies: bool) -> dict[str, object]:
    platform = platform_label_for_url(url)
    auth_state = platform_auth_state(platform)
    preview_job = Job(
        job_id="preview",
        url=url,
        preset=AUDIO_PRESET_NAME,
        use_cookies=use_cookies,
        generate_transcript=False,
    )

    try:
        with yt_dlp.YoutubeDL(build_parse_preview_options(url, use_cookies=use_cookies)) as ydl:
            info = primary_info_dict(ydl.extract_info(url, download=False))
    except Exception as exc:
        subtitle_summary = summarize_subtitle_availability(None)
        return {
            "ok": False,
            "source_url": url,
            "resolved_url": url,
            "platform": platform,
            "title": None,
            "source_author": None,
            "duration_seconds": None,
            "duration_label": None,
            "thumbnail": None,
            "media_id": None,
            "extractor": None,
            "subtitles": subtitle_summary,
            "auth": auth_state,
            "recommended": build_transcript_recommendation(
                url=url,
                use_cookies=use_cookies,
                auth_state=auth_state,
                subtitle_summary=subtitle_summary,
            ),
            "error": humanize_ydlp_error(preview_job, str(exc)),
        }

    subtitle_summary = summarize_subtitle_availability(info)
    duration_seconds = info.get("duration")
    platform = platform_label_for_url(url, info)
    return {
        "ok": True,
        "source_url": url,
        "resolved_url": info.get("webpage_url") or info.get("original_url") or url,
        "platform": platform,
        "title": info.get("title") or url,
        "source_author": extract_source_author(info),
        "duration_seconds": duration_seconds,
        "duration_label": format_duration_label(duration_seconds),
        "thumbnail": select_thumbnail_url(info),
        "media_id": info.get("id"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "subtitles": subtitle_summary,
        "auth": auth_state,
        "recommended": build_transcript_recommendation(
            url=url,
            use_cookies=use_cookies,
            auth_state=auth_state,
            subtitle_summary=subtitle_summary,
        ),
        "error": None,
    }


def _collect_downloaded_subtitle_candidates(temp_dir: Path) -> list[dict]:
    candidates: list[dict] = []
    for path in temp_dir.rglob("*"):
        if not path.is_file():
            continue
        suffixes = path.suffixes
        if len(suffixes) < 2:
            continue
        lang = suffixes[-2].lstrip(".").strip()
        ext = suffixes[-1].lstrip(".").strip() or "unknown"
        if not lang or lang == "danmaku":
            continue
        candidates.append(
            {
                "path": path,
                "lang": lang,
                "ext": ext,
                "source": "automatic captions" if lang.startswith("ai-") else "manual subtitles",
            }
        )
    return candidates


def _collect_subtitle_candidates(info: dict, *, temp_dir: Path | None = None) -> list[dict]:
    requested_subtitles = info.get("requested_subtitles") or {}
    manual_languages = set((info.get("subtitles") or {}).keys())
    candidates: list[dict] = []
    for lang, subtitle_info in requested_subtitles.items():
        filepath = subtitle_info.get("filepath")
        if not filepath:
            continue
        path = Path(filepath)
        if not path.exists():
            continue
        source = "manual subtitles" if lang in manual_languages else "automatic captions"
        candidates.append(
            {
                "path": path,
                "lang": lang,
                "ext": subtitle_info.get("ext") or path.suffix.lstrip(".") or "unknown",
                "source": source,
            }
        )
    if not candidates and temp_dir is not None:
        candidates.extend(_collect_downloaded_subtitle_candidates(temp_dir))
    candidates.sort(
        key=lambda item: (
            item["source"] != "manual subtitles",
            _subtitle_language_rank(item["lang"]),
            item["ext"],
        )
    )
    return candidates


def _subtitle_text_from_json(payload: object) -> str:
    fragments: list[str] = []

    def append_text(value: object) -> None:
        if not isinstance(value, str):
            return
        normalized = value.replace("\n", " ").strip()
        if normalized:
            fragments.append(normalized)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key in ("utf8", "content", "text"):
                if key in node:
                    append_text(node.get(key))
                    return
            for key in ("segs", "body", "events", "lines", "paragraphs", "results", "segments", "items"):
                if key in node:
                    walk(node[key])
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return "\n".join(_dedupe_caption_lines(fragments))


def _dedupe_caption_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    previous = None
    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        if not normalized or normalized == previous:
            continue
        deduped.append(normalized)
        previous = normalized
    return deduped


def _subtitle_text_from_timed_text(raw_text: str) -> str:
    lines: list[str] = []
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"WEBVTT", "NOTE"} or stripped.startswith(("Kind:", "Language:")):
            continue
        if NUMERIC_CUE_RE.match(stripped) or TIMECODE_LINE_RE.match(stripped):
            continue
        cleaned = html.unescape(XML_TAG_RE.sub("", stripped)).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(_dedupe_caption_lines(lines))


def _subtitle_text_from_ttml(raw_text: str) -> str:
    try:
        root = ET.fromstring(raw_text)
    except ET.ParseError:
        return _subtitle_text_from_timed_text(raw_text)

    fragments: list[str] = []
    for elem in root.iter():
        tag_name = elem.tag.rsplit("}", 1)[-1]
        if tag_name not in {"p", "span"}:
            continue
        text = "".join(elem.itertext()).strip()
        text = html.unescape(text)
        if text:
            fragments.append(text)
    return "\n".join(_dedupe_caption_lines(fragments))


def load_subtitle_text(path: Path) -> str:
    raw_text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix in {".json", ".json3"}:
        try:
            return _subtitle_text_from_json(json.loads(raw_text))
        except json.JSONDecodeError:
            return raw_text
    if suffix in {".ttml", ".xml", ".srv3"}:
        return _subtitle_text_from_ttml(raw_text)
    return _subtitle_text_from_timed_text(raw_text)


def try_extract_direct_subtitles(job: Job) -> dict | None:
    set_job_state(job, status="Checking platform subtitles...")
    temp_dir = Path(tempfile.mkdtemp(prefix="qianzhu-subs-"))
    try:
        preview_info = None
        try:
            with yt_dlp.YoutubeDL(build_parse_preview_options(job.url, use_cookies=job.use_cookies)) as preview_ydl:
                preview_info = primary_info_dict(preview_ydl.extract_info(job.url, download=False))
        except Exception:
            preview_info = None

        if preview_info is not None:
            with job.lock:
                job.title = preview_info.get("title", job.title)
                job.source_author = extract_source_author(preview_info)
            if not summarize_subtitle_availability(preview_info)["available"]:
                return None

        subtitle_languages = select_subtitle_probe_languages(preview_info)
        with yt_dlp.YoutubeDL(
            build_subtitle_probe_options(job, temp_dir=temp_dir, subtitle_languages=subtitle_languages)
        ) as ydl:
            info = ydl.extract_info(job.url, download=True)

        if not isinstance(info, dict):
            return None

        primary_info = primary_info_dict(info) or info

        with job.lock:
            job.title = primary_info.get("title", job.title)
            job.source_author = extract_source_author(primary_info)

        candidates = _collect_subtitle_candidates(primary_info, temp_dir=temp_dir)
        for candidate in candidates:
            raw_text = normalize_raw_transcript_text(load_subtitle_text(candidate["path"])).strip()
            if not raw_text:
                continue
            return {
                "artifact_base_path": build_artifact_base_path(
                    primary_info,
                    base_dir=job.output_dir or DOWNLOAD_DIR,
                ),
                "raw_text": raw_text,
                "provider": "yt-dlp subtitles",
                "model": f'{candidate["source"]} · {candidate["lang"]} · {candidate["ext"]}',
                "response": {
                    "subtitle_language": candidate["lang"],
                    "subtitle_format": candidate["ext"],
                    "subtitle_source": candidate["source"],
                },
                "meta": {
                    "transcript_route": "direct_subtitles",
                    "source_author": job.source_author,
                    "subtitle_language": candidate["lang"],
                    "subtitle_format": candidate["ext"],
                    "subtitle_source": candidate["source"],
                },
            }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return None


def write_metadata_file(meta_path: Path, metadata: dict) -> None:
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def attach_artifact_paths_to_job(job: Job, artifact_paths: dict[str, Path]) -> None:
    job.raw_path = str(artifact_paths["raw_path"]) if artifact_paths["raw_path"].exists() else None
    job.article_path = (
        str(artifact_paths["article_path"]) if artifact_paths["article_path"].exists() else None
    )
    job.transcript_path = (
        str(artifact_paths["markdown_path"]) if artifact_paths["markdown_path"].exists() else None
    )
    job.knowledge_path = (
        str(artifact_paths["knowledge_path"]) if artifact_paths["knowledge_path"].exists() else None
    )
    job.metadata_path = (
        str(artifact_paths["meta_path"]) if artifact_paths["meta_path"].exists() else None
    )


def infer_artifact_base_path_from_known_path(path: Path) -> Path:
    name = path.name
    for config in ARTIFACT_PREVIEW_FIELDS.values():
        suffix = config["suffix"]
        if name.endswith(suffix):
            return path.with_name(name[: -len(suffix)])
    return path


def infer_artifact_paths_for_job(job: Job) -> dict[str, Path] | None:
    candidates = (
        job.metadata_path,
        job.transcript_path,
        job.article_path,
        job.knowledge_path,
        job.raw_path,
        job.download_path,
    )
    for candidate in candidates:
        if not candidate:
            continue
        return build_artifact_paths(infer_artifact_base_path_from_known_path(Path(candidate)))
    return None


def path_within_directory(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def resolve_job_artifact_path(job: Job, artifact_kind: str) -> Path | None:
    config = ARTIFACT_PREVIEW_FIELDS.get(artifact_kind)
    if config is None:
        return None

    configured_path = getattr(job, config["attr"], None)
    candidate = Path(configured_path).expanduser().resolve() if configured_path else None

    if candidate is None:
        inferred_paths = infer_artifact_paths_for_job(job)
        if inferred_paths is None:
            return None
        inferred_key = {
            "raw": "raw_path",
            "article": "article_path",
            "transcript": "markdown_path",
            "knowledge": "knowledge_path",
            "metadata": "meta_path",
        }[artifact_kind]
        candidate = inferred_paths[inferred_key].expanduser().resolve()

    artifact_dir = Path(job.artifact_dir).expanduser().resolve() if job.artifact_dir else None
    if artifact_dir is not None and not path_within_directory(candidate, artifact_dir):
        return None
    return candidate


def read_text_preview(path: Path, *, limit: int = ARTIFACT_PREVIEW_CHAR_LIMIT) -> tuple[str, bool]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        content = handle.read(limit + 1)
    truncated = len(content) > limit
    if truncated:
        content = content[:limit]
    return content, truncated


def build_knowledge_source_text(
    *,
    markdown_text: str,
    article_text: str | None,
    raw_text: str,
) -> str:
    sections: list[str] = []
    if markdown_text.strip():
        sections.append("## 逐字稿\n\n" + markdown_text.strip())
    if article_text and article_text.strip():
        sections.append("## 解析稿\n\n" + article_text.strip())
    if raw_text.strip():
        sections.append("## 原始逐字稿\n\n" + raw_text.strip())
    return "\n\n".join(section for section in sections if section.strip()).strip()


def run_knowledge_pipeline(
    job: Job,
    *,
    artifact_paths: dict[str, Path],
    metadata: dict,
    raw_text: str,
    markdown_text: str,
    article_text: str | None,
    platform: str,
) -> None:
    knowledge_path = artifact_paths["knowledge_path"]
    if knowledge_path.exists():
        job.knowledge_path = str(knowledge_path)
        job.knowledge_error = None
        persist_jobs_state(force=True)
        return

    set_job_state(job, status=f"Generating knowledge with {cleanup_backend.KNOWLEDGE_DRAFT_MODEL}...")
    try:
        source_text = build_knowledge_source_text(
            markdown_text=markdown_text,
            article_text=article_text,
            raw_text=raw_text,
        )
        knowledge_result = generate_knowledge_draft(
            text=source_text,
            title=job.title,
            source_url=job.url,
            platform=platform,
        )
        knowledge_text = knowledge_result["text"].strip()
        knowledge_path.parent.mkdir(parents=True, exist_ok=True)
        knowledge_path.write_text(knowledge_text + "\n", encoding="utf-8")

        metadata["knowledge_provider"] = knowledge_result["provider"]
        metadata["knowledge_model"] = knowledge_result["model"]
        metadata["knowledge_base_url"] = cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL
        metadata["knowledge_timeout_seconds"] = cleanup_backend.KNOWLEDGE_DRAFT_TIMEOUT_SECONDS
        metadata["knowledge_max_retries"] = cleanup_backend.KNOWLEDGE_DRAFT_MAX_RETRIES
        metadata["knowledge_prompt_file"] = cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_FILE
        metadata["knowledge_prompt_source"] = (
            "inline" if cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT.strip() else "file"
        )
        metadata["knowledge_error"] = None
        metadata["knowledge_response"] = knowledge_result["raw_response"]
        write_metadata_file(artifact_paths["meta_path"], metadata)

        job.knowledge_path = str(knowledge_path)
        job.knowledge_error = None
        persist_jobs_state(force=True)
    except Exception as exc:
        metadata["knowledge_base_url"] = cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL
        metadata["knowledge_prompt_file"] = cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_FILE
        metadata["knowledge_prompt_source"] = (
            "inline" if cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT.strip() else "file"
        )
        metadata["knowledge_error"] = str(exc)
        write_metadata_file(artifact_paths["meta_path"], metadata)
        job.knowledge_error = str(exc)
        persist_jobs_state(force=True)


def run_text_pipeline(
    job: Job,
    *,
    artifact_base_path: Path,
    raw_text: str,
    transcript_provider: str,
    transcript_model: str,
    transcript_response: dict | None = None,
    source_media_path: Path | None = None,
    prepared_audio_path: Path | None = None,
    extra_meta: dict | None = None,
) -> None:
    artifact_paths = build_artifact_paths(artifact_base_path)
    raw_path = artifact_paths["raw_path"]
    article_path = artifact_paths["article_path"]
    markdown_path = artifact_paths["markdown_path"]
    meta_path = artifact_paths["meta_path"]
    knowledge_path = artifact_paths["knowledge_path"]

    article_ready = article_path.exists() or not ENABLE_ARTICLE_DRAFT
    if raw_path.exists() and markdown_path.exists() and meta_path.exists() and article_ready:
        job.artifact_dir = str(artifact_base_path.parent)
        attach_artifact_paths_to_job(job, artifact_paths)
        job.provider = transcript_provider

        try:
            existing_metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_metadata = {}
        job.transcript_route = existing_metadata.get("transcript_route")
        job.knowledge_error = existing_metadata.get("knowledge_error")

        if not job.generate_knowledge or knowledge_path.exists():
            persist_jobs_state(force=True)
            return

        existing_article_text = article_path.read_text(encoding="utf-8").strip() if article_path.exists() else None
        run_knowledge_pipeline(
            job,
            artifact_paths=artifact_paths,
            metadata=existing_metadata,
            raw_text=raw_path.read_text(encoding="utf-8").strip(),
            markdown_text=markdown_path.read_text(encoding="utf-8").strip(),
            article_text=existing_article_text,
            platform=existing_metadata.get("platform") or detect_platform(job.url),
        )
        return

    cleanup_provider = None
    cleanup_model = None
    cleanup_response = None
    cleanup_error = None
    article_text = None
    article_provider = None
    article_model = None
    article_response = None
    article_error = None
    platform = detect_platform(job.url)
    metadata = dict(extra_meta or {})
    source_author = str(metadata.get("source_author") or job.source_author or "").strip() or None

    set_job_state(job, status="Cleaning transcript...")
    clean_text = clean_transcript_text(raw_text) or raw_text

    if AI_CLEANUP_ENABLED:
        try:
            set_job_state(job, status=f"Cleaning with {AI_CLEANUP_MODEL}...")
            cleanup_result = cleanup_transcript(
                clean_text,
                title=job.title,
                source_url=job.url,
            )
            candidate_text = clean_transcript_text(cleanup_result["text"]).strip()
            if candidate_text:
                clean_text = candidate_text
            cleanup_provider = cleanup_result["provider"]
            cleanup_model = cleanup_result["model"]
            cleanup_response = cleanup_result["raw_response"]
        except Exception as exc:
            cleanup_error = str(exc)
            if not AI_CLEANUP_FALLBACK_LOCAL:
                raise
            if isinstance(exc, cleanup_backend.AITextRequestError):
                fallback_message = exc.fallback_status("local cleanup")
            else:
                fallback_message = "AI cleanup unavailable. Falling back to local cleanup..."
            set_job_state(job, status=fallback_message)

    if article_path.exists():
        article_text = article_path.read_text(encoding="utf-8").strip()
    elif ENABLE_ARTICLE_DRAFT:
        try:
            set_job_state(job, status=f"Generating article with {ARTICLE_DRAFT_MODEL}...")
            article_result = generate_ai_article_draft(
                text=clean_text,
                title=job.title,
                source_url=job.url,
                platform=platform,
                source_author=source_author,
            )
            article_text = article_result["text"].strip()
            article_provider = article_result["provider"]
            article_model = article_result["model"]
            article_response = article_result["raw_response"]
        except Exception as exc:
            article_error = str(exc)
            if isinstance(exc, cleanup_backend.AITextRequestError):
                fallback_message = exc.fallback_status(f"OpenRouter {OPENROUTER_ARTICLE_MODEL}")
            else:
                fallback_message = f"Article draft unavailable. Falling back to OpenRouter {OPENROUTER_ARTICLE_MODEL}..."
            set_job_state(job, status=fallback_message)
            try:
                system_prompt = cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT.strip()
                if not system_prompt:
                    system_prompt = Path(ARTICLE_DRAFT_PROMPT_FILE).read_text(encoding="utf-8").strip()
                article_result = generate_openrouter_article_draft(
                    transcript_text=clean_text,
                    system_prompt=system_prompt,
                    title=job.title,
                    source_url=job.url,
                    platform=platform,
                    source_author=source_author,
                )
                article_text = article_result["text"].strip()
                article_provider = article_result["provider"]
                article_model = article_result["model"]
                article_response = article_result["raw_response"]
            except Exception as fallback_exc:
                article_error = f"{article_error} | OpenRouter fallback failed: {fallback_exc}"

    markdown_text = render_markdown(
        title=job.title,
        raw_text=raw_text,
        clean_text=clean_text,
        article_text=article_text,
    )

    metadata.update(
        {
            "title": job.title,
            "platform": platform,
            "source_author": source_author,
            "artifact_dir": str(artifact_base_path.parent),
            "prepared_audio_path": str(prepared_audio_path) if prepared_audio_path else None,
            "cleanup_provider": cleanup_provider,
            "cleanup_model": cleanup_model,
            "cleanup_base_url": AI_CLEANUP_BASE_URL,
            "cleanup_timeout_seconds": cleanup_backend.AI_CLEANUP_TIMEOUT_SECONDS,
            "cleanup_max_retries": cleanup_backend.AI_CLEANUP_MAX_RETRIES,
            "cleanup_fallback_local": AI_CLEANUP_FALLBACK_LOCAL,
            "cleanup_prompt_file": AI_CLEANUP_PROMPT_FILE,
            "cleanup_prompt_source": (
                "inline" if cleanup_backend.AI_CLEANUP_PROMPT_TEXT.strip() else "file"
            ),
            "cleanup_error": cleanup_error,
            "article_provider": article_provider,
            "article_model": article_model,
            "article_base_url": ARTICLE_DRAFT_BASE_URL,
            "article_timeout_seconds": cleanup_backend.ARTICLE_DRAFT_TIMEOUT_SECONDS,
            "article_max_retries": cleanup_backend.ARTICLE_DRAFT_MAX_RETRIES,
            "article_prompt_file": ARTICLE_DRAFT_PROMPT_FILE,
            "article_prompt_source": (
                "inline" if cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT.strip() else "file"
            ),
            "article_error": article_error,
            "transcription_response": transcript_response,
            "cleanup_response": cleanup_response,
            "article_response": article_response,
        }
    )

    artifact_paths = write_sidecar_files(
        artifact_base_path=artifact_base_path,
        source_url=job.url,
        source_media_path=source_media_path,
        provider=transcript_provider,
        model=transcript_model,
        raw_text=raw_text,
        clean_text=clean_text,
        article_text=article_text,
        markdown_text=markdown_text,
        extra_meta=metadata,
    )

    if job.generate_knowledge:
        run_knowledge_pipeline(
            job,
            artifact_paths=artifact_paths,
            metadata=metadata,
            raw_text=raw_text,
            markdown_text=markdown_text,
            article_text=article_text,
            platform=platform,
        )

    job.artifact_dir = str(artifact_base_path.parent)
    attach_artifact_paths_to_job(job, artifact_paths)
    job.provider = transcript_provider
    job.transcript_route = metadata.get("transcript_route")
    persist_jobs_state(force=True)


def run_transcription_pipeline(job: Job, audio_path: Path, *, extra_meta: dict | None = None) -> None:
    artifact_paths = build_artifact_paths(audio_path)
    raw_path = artifact_paths["raw_path"]
    prepared_audio = audio_path
    chunk_paths: list[Path] = []
    transcript_response = None
    transcript_provider = "openrouter"
    transcript_model = OPENROUTER_TRANSCRIPTION_MODEL
    base_transcript_route = str((extra_meta or {}).get("transcript_route") or "audio_transcription")
    transcription_route = base_transcript_route

    try:
        if raw_path.exists():
            raw_text = normalize_raw_transcript_text(raw_path.read_text(encoding="utf-8")).strip()
        else:
            set_job_state(job, status="Preparing audio for OpenRouter transcription...")
            prepared_audio = prepare_audio_for_transcription(audio_path)

            if should_chunk_audio_for_transcription(prepared_audio):
                set_job_state(job, status="Audio looks long. Splitting into chunks before transcription...")
                transcript_result = transcribe_audio_in_chunks(job, prepared_audio)
                transcription_route = build_chunked_transcript_route(base_transcript_route)
                chunk_paths = [Path(path) for path in transcript_result.get("chunk_paths", [])]
            else:
                set_job_state(job, status=f"Transcribing with {OPENROUTER_TRANSCRIPTION_MODEL}...")
                try:
                    transcript_result = transcribe_audio(
                        prepared_audio,
                        title=job.title,
                        source_url=job.url,
                        language_hint=TRANSCRIPTION_LANGUAGE,
                    )
                except Exception as exc:
                    if not should_retry_transcription_with_chunks(exc):
                        raise
                    set_job_state(job, status="Transcription truncated. Retrying with audio chunks...")
                    transcript_result = transcribe_audio_in_chunks(job, prepared_audio, fallback_error=exc)
                    transcription_route = build_chunked_transcript_route(base_transcript_route)
                    chunk_paths = [Path(path) for path in transcript_result.get("chunk_paths", [])]

            raw_text = normalize_raw_transcript_text(transcript_result["text"]).strip()
            if not raw_text:
                raise RuntimeError("OpenRouter returned an empty transcript.")
            transcript_provider = transcript_result["provider"]
            transcript_model = transcript_result["model"]
            transcript_response = transcript_result["raw_response"]

        metadata = {
            **(extra_meta or {}),
            "transcript_route": transcription_route,
            "transcription_chunked": bool(chunk_paths),
            "transcription_chunk_count": len(chunk_paths) if chunk_paths else None,
            "transcription_chunk_seconds": TRANSCRIPTION_CHUNK_SECONDS if chunk_paths else None,
        }
        run_text_pipeline(
            job,
            artifact_base_path=audio_path,
            raw_text=raw_text,
            transcript_provider=transcript_provider,
            transcript_model=transcript_model,
            transcript_response=transcript_response,
            source_media_path=audio_path,
            prepared_audio_path=prepared_audio,
            extra_meta=metadata,
        )
    finally:
        if chunk_paths and not KEEP_TRANSCRIPTION_INPUT:
            cleanup_transcription_chunks(chunk_paths)
        if (
            prepared_audio != audio_path
            and prepared_audio.exists()
            and not KEEP_TRANSCRIPTION_INPUT
        ):
            prepared_audio.unlink(missing_ok=True)


def download_media(job: Job, preset_name: str) -> Path:
    output_dir = Path(job.output_dir) if job.output_dir else resolve_download_dir()
    if detect_platform(job.url) == "Douyin" and job.use_cookies:
        cookie_options = resolve_cookie_options(job.url)
        if cookie_options:
            set_job_state(job, status="Fetching Douyin media with dedicated provider...")
            try:
                result = download_douyin_media(
                    url=job.url,
                    preset_name=preset_name,
                    output_dir=output_dir,
                    cookie_options=cookie_options,
                    ffmpeg_bin=FFMPEG_BIN,
                    audio_bitrate="192k",
                )
            except DouyinDownloadError as exc:
                with job.lock:
                    job.backend_error = str(exc)
                raise

            media_path = Path(result["download_path"])
            with job.lock:
                job.title = result["title"]
                job.download_path = str(media_path)
                job.artifact_dir = str(result["artifact_dir"])
                job.progress = 100
            persist_jobs_state(force=True)
            return media_path

    options = build_ydl_options(job, preset_name=preset_name, base_dir=output_dir)
    selected_info: dict | None = None
    with yt_dlp.YoutubeDL(options) as ydl:
        try:
            preview_info = primary_info_dict(ydl.extract_info(job.url, download=False))
            if preview_info is not None:
                selected_info = preview_info
                with job.lock:
                    job.title = preview_info.get("title", job.url)
                    job.source_author = extract_source_author(preview_info)
        except Exception:
            pass

        download_info = primary_info_dict(ydl.extract_info(job.url, download=True))
        if download_info is not None:
            selected_info = download_info
            with job.lock:
                job.title = download_info.get("title", job.title)
                job.source_author = extract_source_author(download_info)

        if selected_info is None:
            raise RuntimeError("Unable to determine downloaded media path safely.")

        expected_path = Path(ydl.prepare_filename(selected_info))
    media_path = resolve_media_path(expected_path, preset_name)
    job.download_path = str(media_path)
    job.artifact_dir = str(media_path.parent)
    persist_jobs_state(force=True)
    return media_path


def run_transcript_job(job: Job) -> None:
    if detect_platform(job.url) == "Douyin" and job.use_cookies and resolve_cookie_options(job.url):
        set_job_state(job, status="Douyin detected. Skipping subtitle probe and downloading audio...")
        media_path = download_media(job, AUDIO_PRESET_NAME)
        run_transcription_pipeline(
            job,
            media_path,
            extra_meta={
                "transcript_route": "douyin_audio_transcription",
                "source_author": job.source_author,
            },
        )
        return

    subtitle_probe_error = None
    subtitle_result = None

    try:
        subtitle_result = try_extract_direct_subtitles(job)
    except Exception as exc:
        subtitle_probe_error = str(exc)

    if subtitle_result:
        set_job_state(job, status="Subtitles found. Building Markdown transcript...")
        run_text_pipeline(
            job,
            artifact_base_path=subtitle_result["artifact_base_path"],
            raw_text=subtitle_result["raw_text"],
            transcript_provider=subtitle_result["provider"],
            transcript_model=subtitle_result["model"],
            transcript_response=subtitle_result["response"],
            extra_meta=subtitle_result["meta"],
        )
        return

    fallback_message = (
        "Subtitle lookup unavailable. Falling back to MP3 transcription..."
        if subtitle_probe_error
        else "No usable subtitles found. Falling back to MP3 transcription..."
    )
    set_job_state(job, status=fallback_message)
    media_path = download_media(job, AUDIO_PRESET_NAME)
    run_transcription_pipeline(
        job,
        media_path,
        extra_meta={
            "transcript_route": "subtitle_probe_fallback_to_audio",
            "subtitle_probe_error": subtitle_probe_error,
            "source_author": job.source_author,
        },
    )


def run_job(job: Job) -> Job:
    try:
        set_job_state(job, status="Starting...")
        resolve_download_dir(job.output_dir, create=True)
        if job.preset == TRANSCRIPT_PRESET_NAME:
            run_transcript_job(job)
        else:
            media_path = download_media(job, job.preset)
            if job.generate_transcript and ENABLE_TRANSCRIPTION:
                run_transcription_pipeline(job, media_path)

        with job.lock:
            job.done = True
            if job.generate_knowledge:
                if job.knowledge_path:
                    job.status = "Done · knowledge ready"
                elif job.transcript_path:
                    job.status = (
                        "Done · transcript ready · knowledge failed"
                        if job.knowledge_error
                        else "Done · transcript ready"
                    )
                else:
                    job.status = "Done"
            else:
                job.status = "Done · transcript ready" if job.transcript_path else "Done"
            job.progress = 100
            job.backend_error = None
        persist_jobs_state(force=True)
    except Exception as exc:
        with job.lock:
            job.done = True
            job.status = "Failed"
            raw_error = job.backend_error or str(exc)
            job.error = humanize_ydlp_error(job, raw_error)
        persist_jobs_state(force=True)
    return job


def worker(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return

    run_job(job)


def build_platform_auth_payload() -> dict[str, object]:
    states = {
        key: platform_auth_state(platform_name)
        for key, platform_name in PLATFORM_AUTH_ORDER
    }
    states["generic"] = platform_auth_state("Unknown")
    payload: dict[str, object] = {
        "runtime_environment": "container" if running_in_container() else "local",
        "cookiesConfigured": any(bool(state["configured"]) for state in states.values()),
        "cookiesVerified": any(bool(state["verified"]) for state in states.values()),
        "platformAuth": states,
    }
    for key, _platform_name in PLATFORM_AUTH_ORDER:
        payload[f"{key}AuthConfigured"] = bool(states[key]["configured"])
        payload[f"{key}AuthVerified"] = bool(states[key]["verified"])
    payload["genericAuthConfigured"] = bool(states["generic"]["configured"])
    payload["genericAuthVerified"] = bool(states["generic"]["verified"])
    return payload


def frontend_config() -> dict:
    initialize_web_jobs()
    settings = masked_runtime_settings()
    auth_payload = build_platform_auth_payload()
    return {
        "presets": list(FORMAT_PRESETS.keys()),
        "defaultPreset": VIDEO_PRESET_NAME,
        "videoPreset": VIDEO_PRESET_NAME,
        "audioPreset": AUDIO_PRESET_NAME,
        "transcriptPreset": TRANSCRIPT_PRESET_NAME,
        "transcriptionEnabled": ENABLE_TRANSCRIPTION,
        "transcriptionProvider": "openrouter",
        "transcriptionModel": OPENROUTER_TRANSCRIPTION_MODEL,
        "aiCleanupEnabled": AI_CLEANUP_ENABLED,
        "aiCleanupProvider": AI_CLEANUP_PROVIDER_LABEL,
        "aiCleanupModel": AI_CLEANUP_MODEL,
        "articleDraftEnabled": ENABLE_ARTICLE_DRAFT,
        "articleDraftProvider": ARTICLE_DRAFT_PROVIDER_LABEL,
        "articleDraftModel": ARTICLE_DRAFT_MODEL,
        "webTokenRequired": bool(WEB_TOKEN),
        "settings": settings,
        **auth_payload,
    }


@app.route("/")
def index():
    asset_bundle = load_inline_frontend_assets()
    return render_template(
        "index.html",
        app_title=APP_TITLE,
        config_json=json.dumps(frontend_config()),
        asset_version=frontend_asset_version(),
        inline_css=asset_bundle["inline_css"],
        inline_js=asset_bundle["inline_js"],
    )


@app.route("/api/settings")
@require_web_token
def get_settings():
    initialize_web_jobs()
    payload = masked_runtime_settings()
    auth_payload = build_platform_auth_payload()
    payload.update(auth_payload)
    payload.update(
        {
            "generic_auth_configured": auth_payload["genericAuthConfigured"],
            "generic_auth_verified": auth_payload["genericAuthVerified"],
            "youtube_auth_configured": auth_payload["youtubeAuthConfigured"],
            "youtube_auth_verified": auth_payload["youtubeAuthVerified"],
            "bilibili_auth_configured": auth_payload["bilibiliAuthConfigured"],
            "bilibili_auth_verified": auth_payload["bilibiliAuthVerified"],
            "douyin_auth_configured": auth_payload["douyinAuthConfigured"],
            "douyin_auth_verified": auth_payload["douyinAuthVerified"],
            "platform_auth": auth_payload["platformAuth"],
        }
    )
    return jsonify(payload)


@app.route("/api/settings", methods=["POST"])
@require_web_token
def update_settings():
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid settings payload"}), 400
    try:
        persist_runtime_settings(sanitize_settings_update_payload(data), partial=True)
        settings = masked_runtime_settings()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    payload = dict(settings)
    auth_payload = build_platform_auth_payload()
    payload.update(auth_payload)
    payload.update(
        {
            "generic_auth_configured": auth_payload["genericAuthConfigured"],
            "generic_auth_verified": auth_payload["genericAuthVerified"],
            "youtube_auth_configured": auth_payload["youtubeAuthConfigured"],
            "youtube_auth_verified": auth_payload["youtubeAuthVerified"],
            "bilibili_auth_configured": auth_payload["bilibiliAuthConfigured"],
            "bilibili_auth_verified": auth_payload["bilibiliAuthVerified"],
            "douyin_auth_configured": auth_payload["douyinAuthConfigured"],
            "douyin_auth_verified": auth_payload["douyinAuthVerified"],
            "platform_auth": auth_payload["platformAuth"],
        }
    )
    return jsonify(payload)


@app.route("/api/parse", methods=["POST"])
@require_web_token
def parse_sources():
    data = request.json or {}
    raw_input = str(data.get("url", ""))
    if raw_input.strip() and not has_url_like_input(raw_input):
        return jsonify({"error": "请输入有效的视频链接，或包含链接的分享文案。主打 Bilibili / YouTube / Douyin，也支持其他 yt-dlp 可解析平台的直链。"}), 400

    urls = collect_url_inputs(raw_input)
    if not urls:
        return jsonify({"error": "没有识别到可用链接。支持直接粘贴 URL，或粘贴 Bilibili / YouTube / Douyin 分享文案；其他平台建议直接粘贴完整链接。"}), 400
    try:
        validate_web_start_urls(urls)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    use_cookies = bool(data.get("use_cookies"))
    items = [preview_source_url(url, use_cookies=use_cookies) for url in urls]
    return jsonify(
        {
            "count": len(items),
            "urls": urls,
            "items": items,
        }
    )


@app.route("/api/start", methods=["POST"])
@require_web_token
def start():
    initialize_web_jobs()
    data = request.json or {}
    raw_input = str(data.get("url", ""))
    if raw_input.strip() and not has_url_like_input(raw_input):
        return jsonify({"error": "请输入有效的视频链接，或包含链接的分享文案。主打 Bilibili / YouTube / Douyin，也支持其他 yt-dlp 可解析平台的直链。"}), 400

    urls = collect_url_inputs(raw_input)
    if not urls:
        return jsonify({"error": "没有识别到可用链接。支持直接粘贴 URL，或粘贴 Bilibili / YouTube / Douyin 分享文案；其他平台建议直接粘贴完整链接。"}), 400
    try:
        validate_web_start_urls(urls)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    preset = data.get("preset")
    use_cookies = bool(data.get("use_cookies"))
    generate_transcript = bool(data.get("generate_transcript"))
    generate_knowledge = bool(data.get("generate_knowledge"))
    download_dir_raw = str(data.get("download_dir") or "").strip()

    if preset not in FORMAT_PRESETS:
        return jsonify({"error": "Invalid preset"}), 400
    if preset == TRANSCRIPT_PRESET_NAME:
        generate_transcript = True
    elif generate_transcript and preset != AUDIO_PRESET_NAME:
        return jsonify({"error": "提取 Markdown 逐字稿前，请先选择 Best Audio (MP3)。"}), 400
    if generate_knowledge and not generate_transcript:
        return jsonify({"error": "生成知识库稿前，请先选择 Markdown 逐字稿模式。"}), 400
    if generate_knowledge and not ENABLE_KNOWLEDGE_DRAFT:
        return jsonify({"error": "当前还没有启用知识库整理配置，请先在设置里开启。"}), 400
    if generate_knowledge and not cleanup_backend.KNOWLEDGE_DRAFT_API_KEY:
        return jsonify({"error": "当前还没有配置知识库 API Key，请先在设置里补齐。"}), 400

    try:
        download_dir = str(resolve_download_dir(download_dir_raw)) if download_dir_raw else None
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    added = 0
    job_ids: list[str] = []
    with jobs_lock:
        for url in urls:
            job_id = uuid.uuid4().hex
            job = Job(
                job_id=job_id,
                url=url,
                preset=preset,
                use_cookies=use_cookies,
                generate_transcript=generate_transcript,
                generate_knowledge=generate_knowledge,
                output_dir=download_dir,
            )
            jobs[job_id] = job
            executor.submit(worker, job_id)
            added += 1
            job_ids.append(job_id)
    if job_ids:
        persist_jobs_state(force=True)
    return jsonify({"count": added, "job_ids": job_ids})


@app.route("/api/tasks")
@require_web_token
def tasks():
    initialize_web_jobs()
    with jobs_lock:
        tasks_list = []
        for job in sorted(jobs.values(), key=lambda x: x.created_at, reverse=True)[:20]:
            effective_output_dir = job.output_dir or DOWNLOAD_DIR
            host_output_dir = map_runtime_path_to_host(effective_output_dir)
            host_download_path = map_runtime_path_to_host(job.download_path)
            host_raw_path = map_runtime_path_to_host(job.raw_path)
            host_article_path = map_runtime_path_to_host(job.article_path)
            host_transcript_path = map_runtime_path_to_host(job.transcript_path)
            host_knowledge_path = map_runtime_path_to_host(job.knowledge_path)
            host_metadata_path = map_runtime_path_to_host(job.metadata_path)
            host_artifact_dir = map_runtime_path_to_host(job.artifact_dir)
            tasks_list.append(
                {
                    "id": job.job_id,
                    "title": job.title,
                    "source_url": job.url,
                    "status": job.status,
                    "progress": round(job.progress),
                    "done": job.done,
                    "error": job.error,
                    "backend_error": job.backend_error,
                    "artifact_dir": job.artifact_dir,
                    "download_path": job.download_path,
                    "raw_path": job.raw_path,
                    "article_path": job.article_path,
                    "transcript_path": job.transcript_path,
                    "knowledge_path": job.knowledge_path,
                    "metadata_path": job.metadata_path,
                    "provider": job.provider,
                    "preset": job.preset,
                    "output_dir": job.output_dir,
                    "transcript_route": job.transcript_route,
                    "generate_transcript": job.generate_transcript,
                    "generate_knowledge": job.generate_knowledge,
                    "knowledge_error": job.knowledge_error,
                    "resumed_from_state": job.resumed_from_state,
                    "host_output_dir": host_output_dir,
                    "host_download_path": host_download_path,
                    "host_raw_path": host_raw_path,
                    "host_article_path": host_article_path,
                    "host_transcript_path": host_transcript_path,
                    "host_knowledge_path": host_knowledge_path,
                    "host_metadata_path": host_metadata_path,
                    "host_artifact_dir": host_artifact_dir,
                }
            )
    return jsonify({"tasks": tasks_list})


@app.route("/api/tasks/<job_id>/artifacts/<artifact_kind>")
@require_web_token
def task_artifact_preview(job_id: str, artifact_kind: str):
    config = ARTIFACT_PREVIEW_FIELDS.get(artifact_kind)
    if config is None:
        return jsonify({"error": "Unknown artifact kind"}), 404

    with jobs_lock:
        job = jobs.get(job_id)

    if job is None:
        return jsonify({"error": "Task not found"}), 404

    path = resolve_job_artifact_path(job, artifact_kind)
    if path is None:
        return jsonify({"error": "Artifact not available"}), 404
    if not path.exists():
        return jsonify({"error": "Artifact file not found"}), 404

    content, truncated = read_text_preview(path)
    return jsonify(
        {
            "job_id": job_id,
            "artifact_kind": artifact_kind,
            "label": config["label"],
            "path": str(path),
            "format": config["format"],
            "content": content,
            "truncated": truncated,
        }
    )


if __name__ == "__main__":
    initialize_web_jobs()
    app.run(host=HOST, port=PORT, threaded=True)
