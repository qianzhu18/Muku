import html
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
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:
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

try:
    import yt_dlp
except ImportError as exc:
    raise SystemExit("yt-dlp is not installed.") from exc


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


APP_TITLE = "幕库 Muku"
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(Path.home() / "Downloads"))
DOWNLOAD_ROOT_DIR = os.environ.get("DOWNLOAD_ROOT_DIR", "").strip()
COOKIES_PATH = os.environ.get("COOKIES_PATH", "")
COOKIES_FROM_BROWSER = os.environ.get("COOKIES_FROM_BROWSER", "").strip()
YOUTUBE_COOKIES_PATH = os.environ.get("YOUTUBE_COOKIES_PATH", "").strip()
YOUTUBE_COOKIES_FROM_BROWSER = os.environ.get("YOUTUBE_COOKIES_FROM_BROWSER", "").strip()
BILIBILI_COOKIES_PATH = os.environ.get("BILIBILI_COOKIES_PATH", "").strip()
BILIBILI_COOKIES_FROM_BROWSER = os.environ.get("BILIBILI_COOKIES_FROM_BROWSER", "").strip()
DOUYIN_COOKIES_PATH = os.environ.get("DOUYIN_COOKIES_PATH", "").strip()
DOUYIN_COOKIES_FROM_BROWSER = os.environ.get("DOUYIN_COOKIES_FROM_BROWSER", "").strip()
YTDLP_REMOTE_COMPONENTS = tuple(
    component.strip()
    for component in os.environ.get("YTDLP_REMOTE_COMPONENTS", "ejs:github").split(",")
    if component.strip()
)
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "2"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
ENABLE_TRANSCRIPTION = env_bool("ENABLE_TRANSCRIPTION", True)
TRANSCRIPTION_LANGUAGE = os.environ.get("TRANSCRIPTION_LANGUAGE", "auto")
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
TRANSCRIPTION_AUDIO_BITRATE = os.environ.get("TRANSCRIPTION_AUDIO_BITRATE", "48k")
KEEP_TRANSCRIPTION_INPUT = env_bool("KEEP_TRANSCRIPTION_INPUT", False)
VIDEO_PRESET_NAME = "Highest Video (MP4)"
AUDIO_PRESET_NAME = "Best Audio (MP3)"
TRANSCRIPT_PRESET_NAME = "Markdown 逐字稿（字幕优先）"
SUBTITLE_LANGUAGES = tuple(
    lang.strip()
    for lang in os.environ.get(
        "SUBTITLE_LANGUAGES",
        "zh-Hans,zh-CN,zh-TW,zh-HK,zh,cmn-Hans-CN,en,en-US",
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

ENV_DEFAULTS = {
    "download_dir": DOWNLOAD_DIR,
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
    "ai_cleanup_prompt_text": cleanup_backend.AI_CLEANUP_PROMPT_TEXT,
    "enable_article_draft": ENABLE_ARTICLE_DRAFT,
    "article_draft_base_url": ARTICLE_DRAFT_BASE_URL,
    "article_draft_api_key": cleanup_backend.ARTICLE_DRAFT_API_KEY,
    "article_draft_model": ARTICLE_DRAFT_MODEL,
    "article_draft_prompt_text": cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT,
    "enable_knowledge_draft": ENABLE_KNOWLEDGE_DRAFT,
    "knowledge_draft_base_url": cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL,
    "knowledge_draft_api_key": cleanup_backend.KNOWLEDGE_DRAFT_API_KEY,
    "knowledge_draft_model": cleanup_backend.KNOWLEDGE_DRAFT_MODEL,
    "knowledge_draft_prompt_text": cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT,
}
SECRET_SETTING_KEYS = {
    "openrouter_api_key",
    "ai_cleanup_api_key",
    "article_draft_api_key",
    "knowledge_draft_api_key",
}
LEGACY_APP_TITLES = {"Downloader by Qianzhu"}


@dataclass
class Job:
    job_id: str
    url: str
    preset: str
    use_cookies: bool
    generate_transcript: bool
    output_dir: str | None = None
    created_at: float = field(default_factory=time.time)
    title: str = "Fetching info..."
    status: str = "Queued"
    progress: float = 0.0
    done: bool = False
    error: str | None = None
    artifact_dir: str | None = None
    download_path: str | None = None
    transcript_path: str | None = None
    provider: str | None = None
    transcript_route: str | None = None
    backend_error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


app = Flask(__name__)
jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


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


def download_root_path() -> Path | None:
    if not DOWNLOAD_ROOT_DIR:
        return None
    return Path(DOWNLOAD_ROOT_DIR).expanduser().resolve()


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
    bool_fields = {
        "enable_ai_cleanup",
        "enable_article_draft",
        "enable_knowledge_draft",
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

    for field in string_fields:
        if field in payload:
            normalized[field] = str(payload.get(field) or "").strip()
        elif not partial:
            normalized[field] = ""

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
    cleanup_backend.AI_CLEANUP_MODEL = str(value_for("ai_cleanup_model") or "").strip()
    cleanup_backend.AI_CLEANUP_PROMPT_TEXT = str(value_for("ai_cleanup_prompt_text") or "")

    cleanup_backend.ENABLE_ARTICLE_DRAFT = bool(value_for("enable_article_draft"))
    cleanup_backend.ARTICLE_DRAFT_BASE_URL = str(value_for("article_draft_base_url") or "").rstrip("/")
    cleanup_backend.ARTICLE_DRAFT_API_KEY = str(value_for("article_draft_api_key") or "").strip()
    cleanup_backend.ARTICLE_DRAFT_MODEL = str(value_for("article_draft_model") or "").strip()
    cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT = str(value_for("article_draft_prompt_text") or "")

    cleanup_backend.ENABLE_KNOWLEDGE_DRAFT = bool(value_for("enable_knowledge_draft"))
    cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL = str(value_for("knowledge_draft_base_url") or "").rstrip("/")
    cleanup_backend.KNOWLEDGE_DRAFT_API_KEY = str(value_for("knowledge_draft_api_key") or "").strip()
    cleanup_backend.KNOWLEDGE_DRAFT_MODEL = str(value_for("knowledge_draft_model") or "").strip()
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
        "download_dir": DOWNLOAD_DIR,
        "download_root_dir": str(download_root_path()) if download_root_path() else None,
        "download_root_locked": bool(download_root_path()),
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
        "ai_cleanup_prompt_file": cleanup_backend.AI_CLEANUP_PROMPT_FILE,
        "ai_cleanup_prompt_text": cleanup_backend.AI_CLEANUP_PROMPT_TEXT,
        "ai_cleanup_prompt_source": (
            "inline" if cleanup_backend.AI_CLEANUP_PROMPT_TEXT.strip() else "file"
        ),
        "enable_article_draft": cleanup_backend.ENABLE_ARTICLE_DRAFT,
        "article_draft_base_url": cleanup_backend.ARTICLE_DRAFT_BASE_URL,
        "article_draft_api_key": cleanup_backend.ARTICLE_DRAFT_API_KEY,
        "article_draft_model": cleanup_backend.ARTICLE_DRAFT_MODEL,
        "article_draft_prompt_file": cleanup_backend.ARTICLE_DRAFT_PROMPT_FILE,
        "article_draft_prompt_text": cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT,
        "article_draft_prompt_source": (
            "inline" if cleanup_backend.ARTICLE_DRAFT_PROMPT_TEXT.strip() else "file"
        ),
        "enable_knowledge_draft": cleanup_backend.ENABLE_KNOWLEDGE_DRAFT,
        "knowledge_draft_base_url": cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL,
        "knowledge_draft_api_key": cleanup_backend.KNOWLEDGE_DRAFT_API_KEY,
        "knowledge_draft_model": cleanup_backend.KNOWLEDGE_DRAFT_MODEL,
        "knowledge_draft_prompt_file": cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_FILE,
        "knowledge_draft_prompt_text": cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT,
        "knowledge_draft_prompt_source": (
            "inline" if cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT.strip() else "file"
        ),
    }


def persist_runtime_settings(payload: dict, *, partial: bool = True) -> dict:
    current_settings = load_settings()
    normalized = _normalize_runtime_settings(payload, partial=partial)
    merged = dict(current_settings)
    merged.update(normalized)
    save_settings(merged)
    return apply_runtime_settings(merged)


def masked_runtime_settings() -> dict:
    payload = current_runtime_settings()
    for key in SECRET_SETTING_KEYS:
        secret = str(payload.get(key) or "")
        payload[f"{key}_configured"] = bool(secret)
        if not secret:
            payload[key] = ""
        elif len(secret) <= 8:
            payload[key] = "****"
        else:
            payload[key] = f"{secret[:4]}...{secret[-4:]}"
    return payload


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
        elif data["status"] == "finished":
            with job.lock:
                job.progress = 100
                job.status = (
                    "Download finished. Preparing transcript..."
                    if job.generate_transcript
                    else "Download finished."
                )

    return hook


def output_template(base_dir: str | Path | None = None) -> str:
    target_dir = Path(base_dir) if base_dir is not None else Path(DOWNLOAD_DIR)
    return str(target_dir / "%(title)s [%(id)s]" / "%(title)s [%(id)s].%(ext)s")


def parse_cookies_from_browser_spec(spec: str) -> tuple[str, str | None, str | None, str | None]:
    match = COOKIES_FROM_BROWSER_RE.fullmatch(spec.strip())
    if match is None:
        raise ValueError(f"Invalid COOKIES_FROM_BROWSER value: {spec}")
    browser_name, keyring, profile, container = match.group("name", "keyring", "profile", "container")
    return (browser_name.lower(), profile, keyring.upper() if keyring else None, container)


def platform_auth_configured(platform: str) -> bool:
    if platform == "YouTube":
        return bool(
            YOUTUBE_COOKIES_FROM_BROWSER
            or YOUTUBE_COOKIES_PATH
            or COOKIES_FROM_BROWSER
            or COOKIES_PATH
        )
    if platform == "Bilibili":
        return bool(
            BILIBILI_COOKIES_PATH
            or BILIBILI_COOKIES_FROM_BROWSER
            or COOKIES_PATH
            or COOKIES_FROM_BROWSER
        )
    if platform == "Douyin":
        return bool(
            DOUYIN_COOKIES_PATH
            or DOUYIN_COOKIES_FROM_BROWSER
            or COOKIES_PATH
            or COOKIES_FROM_BROWSER
        )
    return bool(
        COOKIES_PATH
        or COOKIES_FROM_BROWSER
        or YOUTUBE_COOKIES_PATH
        or YOUTUBE_COOKIES_FROM_BROWSER
        or BILIBILI_COOKIES_PATH
        or BILIBILI_COOKIES_FROM_BROWSER
        or DOUYIN_COOKIES_PATH
        or DOUYIN_COOKIES_FROM_BROWSER
    )


def resolve_cookie_options(url: str) -> dict:
    platform = detect_platform(url)

    if platform == "YouTube":
        if YOUTUBE_COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(YOUTUBE_COOKIES_FROM_BROWSER)}
        if YOUTUBE_COOKIES_PATH:
            return {"cookiefile": YOUTUBE_COOKIES_PATH}
        if COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
        if COOKIES_PATH:
            return {"cookiefile": COOKIES_PATH}
        return {}

    if platform == "Bilibili":
        if BILIBILI_COOKIES_PATH:
            return {"cookiefile": BILIBILI_COOKIES_PATH}
        if BILIBILI_COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(BILIBILI_COOKIES_FROM_BROWSER)}
        if COOKIES_PATH:
            return {"cookiefile": COOKIES_PATH}
        if COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
        return {}

    if platform == "Douyin":
        if DOUYIN_COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(DOUYIN_COOKIES_FROM_BROWSER)}
        if DOUYIN_COOKIES_PATH:
            return {"cookiefile": DOUYIN_COOKIES_PATH}
        if COOKIES_FROM_BROWSER:
            return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
        if COOKIES_PATH:
            return {"cookiefile": COOKIES_PATH}
        return {}

    if COOKIES_FROM_BROWSER:
        return {"cookiesfrombrowser": parse_cookies_from_browser_spec(COOKIES_FROM_BROWSER)}
    if COOKIES_PATH:
        return {"cookiefile": COOKIES_PATH}
    return {}


def humanize_ydlp_error(job: Job, error_message: str) -> str:
    platform = detect_platform(job.url)
    normalized = (error_message or "").strip()
    folded = normalized.replace("’", "'")

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


def sanitize_output_component(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', "_", value).strip().rstrip(".")
    return sanitized or "untitled"


def normalize_shared_url(candidate: str) -> str:
    trailing_chars = ".,!?;:)]}>\"'。 ，！？；：、）】」』》".replace(" ", "")
    return candidate.strip().rstrip(trailing_chars)


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


def collect_url_inputs(text: str) -> list[str]:
    urls = extract_urls_from_text(text)
    if urls:
        return urls

    stripped = text.strip()
    return [stripped] if stripped else []


def build_artifact_base_path(info: dict, *, base_dir: str | Path | None = None) -> Path:
    title = info.get("title") or info.get("id") or "Untitled"
    media_id = info.get("id") or uuid.uuid4().hex[:8]
    stem = sanitize_output_component(f"{title} [{media_id}]")
    target_dir = Path(base_dir) if base_dir is not None else Path(DOWNLOAD_DIR)
    return target_dir / stem / stem


def build_subtitle_probe_options(job: Job, *, temp_dir: Path) -> dict:
    options = build_ydl_options(job, preset_name=AUDIO_PRESET_NAME, base_dir=temp_dir)
    options.pop("postprocessors", None)
    options["progress_hooks"] = []
    options["skip_download"] = True
    options["writesubtitles"] = True
    options["writeautomaticsub"] = True
    options["subtitleslangs"] = list(SUBTITLE_LANGUAGES)
    options["subtitlesformat"] = SUBTITLE_FORMATS
    return options


def _subtitle_language_rank(lang: str) -> int:
    lowered = lang.lower()
    for index, preferred in enumerate(SUBTITLE_LANGUAGES):
        if lowered == preferred.lower():
            return index
    return len(SUBTITLE_LANGUAGES)


def _collect_subtitle_candidates(info: dict) -> list[dict]:
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
        with yt_dlp.YoutubeDL(build_subtitle_probe_options(job, temp_dir=temp_dir)) as ydl:
            info = ydl.extract_info(job.url, download=True)

        if not isinstance(info, dict):
            return None

        with job.lock:
            job.title = info.get("title", job.title)

        candidates = _collect_subtitle_candidates(info)
        for candidate in candidates:
            raw_text = normalize_raw_transcript_text(load_subtitle_text(candidate["path"])).strip()
            if not raw_text:
                continue
            return {
                "artifact_base_path": build_artifact_base_path(
                    info,
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
                    "subtitle_language": candidate["lang"],
                    "subtitle_format": candidate["ext"],
                    "subtitle_source": candidate["source"],
                },
            }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return None


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

    article_ready = article_path.exists() or not ENABLE_ARTICLE_DRAFT
    if raw_path.exists() and markdown_path.exists() and meta_path.exists() and article_ready:
        job.artifact_dir = str(artifact_base_path.parent)
        job.transcript_path = str(markdown_path)
        job.provider = transcript_provider
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                job.transcript_route = metadata.get("transcript_route")
            except json.JSONDecodeError:
                job.transcript_route = None
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
            set_job_state(job, status="AI cleanup unavailable. Falling back to local cleanup...")

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
            )
            article_text = article_result["text"].strip()
            article_provider = article_result["provider"]
            article_model = article_result["model"]
            article_response = article_result["raw_response"]
        except Exception as exc:
            article_error = str(exc)
            set_job_state(job, status=f"GLM article unavailable. Falling back to {OPENROUTER_ARTICLE_MODEL}...")
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
            "artifact_dir": str(artifact_base_path.parent),
            "prepared_audio_path": str(prepared_audio_path) if prepared_audio_path else None,
            "cleanup_provider": cleanup_provider,
            "cleanup_model": cleanup_model,
            "cleanup_base_url": AI_CLEANUP_BASE_URL,
            "cleanup_prompt_file": AI_CLEANUP_PROMPT_FILE,
            "cleanup_prompt_source": (
                "inline" if cleanup_backend.AI_CLEANUP_PROMPT_TEXT.strip() else "file"
            ),
            "cleanup_error": cleanup_error,
            "article_provider": article_provider,
            "article_model": article_model,
            "article_base_url": ARTICLE_DRAFT_BASE_URL,
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

    job.artifact_dir = str(artifact_base_path.parent)
    job.transcript_path = str(artifact_paths["markdown_path"])
    job.provider = transcript_provider
    job.transcript_route = metadata.get("transcript_route")


def run_transcription_pipeline(job: Job, audio_path: Path, *, extra_meta: dict | None = None) -> None:
    artifact_paths = build_artifact_paths(audio_path)
    raw_path = artifact_paths["raw_path"]
    prepared_audio = audio_path
    transcript_response = None
    transcript_provider = "openrouter"
    transcript_model = OPENROUTER_TRANSCRIPTION_MODEL

    try:
        if raw_path.exists():
            raw_text = normalize_raw_transcript_text(raw_path.read_text(encoding="utf-8")).strip()
        else:
            set_job_state(job, status="Preparing audio for OpenRouter transcription...")
            prepared_audio = prepare_audio_for_transcription(audio_path)

            set_job_state(job, status=f"Transcribing with {OPENROUTER_TRANSCRIPTION_MODEL}...")
            transcript_result = transcribe_audio(
                prepared_audio,
                title=job.title,
                source_url=job.url,
                language_hint=TRANSCRIPTION_LANGUAGE,
            )
            raw_text = normalize_raw_transcript_text(transcript_result["text"]).strip()
            if not raw_text:
                raise RuntimeError("OpenRouter returned an empty transcript.")
            transcript_provider = transcript_result["provider"]
            transcript_model = transcript_result["model"]
            transcript_response = transcript_result["raw_response"]

        metadata = {"transcript_route": "audio_transcription", **(extra_meta or {})}
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
        except Exception:
            pass

        download_info = primary_info_dict(ydl.extract_info(job.url, download=True))
        if download_info is not None:
            selected_info = download_info
            with job.lock:
                job.title = download_info.get("title", job.title)

        if selected_info is None:
            raise RuntimeError("Unable to determine downloaded media path safely.")

        expected_path = Path(ydl.prepare_filename(selected_info))
    media_path = resolve_media_path(expected_path, preset_name)
    job.download_path = str(media_path)
    job.artifact_dir = str(media_path.parent)
    return media_path


def run_transcript_job(job: Job) -> None:
    if detect_platform(job.url) == "Douyin" and job.use_cookies and resolve_cookie_options(job.url):
        set_job_state(job, status="Douyin detected. Skipping subtitle probe and downloading audio...")
        media_path = download_media(job, AUDIO_PRESET_NAME)
        run_transcription_pipeline(
            job,
            media_path,
            extra_meta={"transcript_route": "douyin_audio_transcription"},
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
            job.status = "Done · transcript ready" if job.transcript_path else "Done"
            job.progress = 100
    except Exception as exc:
        with job.lock:
            job.done = True
            job.status = "Failed"
            raw_error = job.backend_error or str(exc)
            job.error = humanize_ydlp_error(job, raw_error)
    return job


def worker(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return

    run_job(job)


def frontend_config() -> dict:
    settings = current_runtime_settings()
    return {
        "presets": list(FORMAT_PRESETS.keys()),
        "defaultPreset": VIDEO_PRESET_NAME,
        "audioPreset": AUDIO_PRESET_NAME,
        "transcriptPreset": TRANSCRIPT_PRESET_NAME,
        "cookiesConfigured": platform_auth_configured("Unknown"),
        "youtubeAuthConfigured": platform_auth_configured("YouTube"),
        "bilibiliAuthConfigured": platform_auth_configured("Bilibili"),
        "douyinAuthConfigured": platform_auth_configured("Douyin"),
        "transcriptionEnabled": ENABLE_TRANSCRIPTION,
        "transcriptionProvider": "openrouter",
        "transcriptionModel": OPENROUTER_TRANSCRIPTION_MODEL,
        "aiCleanupEnabled": AI_CLEANUP_ENABLED,
        "aiCleanupProvider": AI_CLEANUP_PROVIDER_LABEL,
        "aiCleanupModel": AI_CLEANUP_MODEL,
        "articleDraftEnabled": ENABLE_ARTICLE_DRAFT,
        "articleDraftProvider": ARTICLE_DRAFT_PROVIDER_LABEL,
        "articleDraftModel": ARTICLE_DRAFT_MODEL,
        "settings": settings,
    }


@app.route("/")
def index():
    return render_template(
        "index.html",
        app_title=APP_TITLE,
        config_json=json.dumps(frontend_config()),
    )


@app.route("/api/settings")
def get_settings():
    payload = current_runtime_settings()
    payload.update(
        {
            "youtube_auth_configured": platform_auth_configured("YouTube"),
            "bilibili_auth_configured": platform_auth_configured("Bilibili"),
            "douyin_auth_configured": platform_auth_configured("Douyin"),
        }
    )
    return jsonify(payload)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json or {}
    try:
        settings = persist_runtime_settings(data, partial=False)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    payload = dict(settings)
    payload.update(
        {
            "youtube_auth_configured": platform_auth_configured("YouTube"),
            "bilibili_auth_configured": platform_auth_configured("Bilibili"),
            "douyin_auth_configured": platform_auth_configured("Douyin"),
        }
    )
    return jsonify(payload)


@app.route("/api/start", methods=["POST"])
def start():
    data = request.json or {}
    urls = collect_url_inputs(str(data.get("url", "")))
    if not urls:
        return jsonify({"error": "没有识别到可用链接。支持直接粘贴 URL，或粘贴 Bilibili / YouTube / Douyin 分享文案。"}), 400

    preset = data.get("preset")
    use_cookies = bool(data.get("use_cookies"))
    generate_transcript = bool(data.get("generate_transcript"))
    download_dir_raw = str(data.get("download_dir") or "").strip()

    if preset not in FORMAT_PRESETS:
        return jsonify({"error": "Invalid preset"}), 400
    if preset == TRANSCRIPT_PRESET_NAME:
        generate_transcript = True
    elif generate_transcript and preset != AUDIO_PRESET_NAME:
        return jsonify({"error": "提取 Markdown 逐字稿前，请先选择 Best Audio (MP3)。"}), 400

    try:
        download_dir = str(resolve_download_dir(download_dir_raw)) if download_dir_raw else None
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    added = 0
    with jobs_lock:
        for url in urls:
            job_id = uuid.uuid4().hex
            job = Job(job_id, url, preset, use_cookies, generate_transcript, output_dir=download_dir)
            jobs[job_id] = job
            executor.submit(worker, job_id)
            added += 1
    return jsonify({"count": added})


@app.route("/api/tasks")
def tasks():
    with jobs_lock:
        tasks_list = []
        for job in sorted(jobs.values(), key=lambda x: x.created_at, reverse=True)[:20]:
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
                    "transcript_path": job.transcript_path,
                    "provider": job.provider,
                    "preset": job.preset,
                    "output_dir": job.output_dir,
                    "transcript_route": job.transcript_route,
                    "generate_transcript": job.generate_transcript,
                }
            )
    return jsonify({"tasks": tasks_list})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=True)
