import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from env_config import load_env_file
load_env_file()

from openai_compatible_cleanup import (
    AI_CLEANUP_BASE_URL,
    AI_CLEANUP_ENABLED,
    AI_CLEANUP_FALLBACK_LOCAL,
    AI_CLEANUP_MODEL,
    AI_CLEANUP_PROMPT_FILE,
    AI_CLEANUP_PROVIDER_LABEL,
    cleanup_transcript,
)
from openrouter_backends import (
    OPENROUTER_TRANSCRIPTION_MODEL,
    transcribe_audio,
)
from transcript_pipeline import clean_transcript_text, render_markdown, write_sidecar_files

try:
    import yt_dlp
except ImportError as exc:
    raise SystemExit("yt-dlp is not installed.") from exc


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


APP_TITLE = "Downloader by Qianzhu"
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/downloads")
COOKIES_PATH = os.environ.get("COOKIES_PATH", "")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "2"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
ENABLE_TRANSCRIPTION = env_bool("ENABLE_TRANSCRIPTION", True)
TRANSCRIPTION_LANGUAGE = os.environ.get("TRANSCRIPTION_LANGUAGE", "auto")
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
TRANSCRIPTION_AUDIO_BITRATE = os.environ.get("TRANSCRIPTION_AUDIO_BITRATE", "48k")
KEEP_TRANSCRIPTION_INPUT = env_bool("KEEP_TRANSCRIPTION_INPUT", False)

FORMAT_PRESETS = {
    "Best Video (MP4)": {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "transcribe": False,
    },
    "Best Audio (MP3)": {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "transcribe": True,
    },
    "4K / High Res": {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "transcribe": False,
    },
}


@dataclass
class Job:
    job_id: str
    url: str
    preset: str
    use_cookies: bool
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
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


app = Flask(__name__)
jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


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
                job.status = "Download finished. Preparing transcript..."

    return hook


def output_template() -> str:
    return str(Path(DOWNLOAD_DIR) / "%(title)s [%(id)s]" / "%(title)s [%(id)s].%(ext)s")


def build_ydl_options(job: Job) -> dict:
    preset_conf = FORMAT_PRESETS[job.preset]
    options = {
        "format": preset_conf["format"],
        "outtmpl": output_template(),
        "progress_hooks": [progress_hook(job)],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    if "merge_output_format" in preset_conf:
        options["merge_output_format"] = preset_conf["merge_output_format"]
    if "postprocessors" in preset_conf:
        options["postprocessors"] = preset_conf["postprocessors"]
    if job.use_cookies and COOKIES_PATH:
        options["cookiefile"] = COOKIES_PATH
    return options


def resolve_media_path(expected_path: Path, preset: str) -> Path:
    artifact_dir = expected_path.parent
    if preset == "Best Audio (MP3)":
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


def prepare_audio_for_transcription(audio_path: Path) -> Path:
    prepared_path = audio_path.with_name(f"{audio_path.stem}.transcribe.mp3")
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


def run_transcription_pipeline(job: Job, audio_path: Path) -> None:
    raw_path = audio_path.with_suffix(".raw.txt")
    clean_path = audio_path.with_suffix(".clean.txt")
    markdown_path = audio_path.with_suffix(".md")
    meta_path = audio_path.with_suffix(".transcript.json")

    if raw_path.exists() and clean_path.exists() and markdown_path.exists() and meta_path.exists():
        job.artifact_dir = str(audio_path.parent)
        job.transcript_path = str(markdown_path)
        job.provider = "openrouter"
        return

    prepared_audio = audio_path
    cleanup_provider = None
    cleanup_model = None
    cleanup_response = None
    cleanup_error = None
    transcript_response = None
    transcript_provider = "openrouter"
    transcript_model = OPENROUTER_TRANSCRIPTION_MODEL

    try:
        if raw_path.exists():
            raw_text = raw_path.read_text(encoding="utf-8").strip()
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
            raw_text = transcript_result["text"].strip()
            if not raw_text:
                raise RuntimeError("OpenRouter returned an empty transcript.")
            transcript_provider = transcript_result["provider"]
            transcript_model = transcript_result["model"]
            transcript_response = transcript_result["raw_response"]

        if clean_path.exists():
            clean_text = clean_path.read_text(encoding="utf-8").strip()
        else:
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
                candidate_text = cleanup_result["text"].strip()
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

        markdown_text = render_markdown(
            title=job.title,
            source_url=job.url,
            provider=transcript_provider,
            model=transcript_model,
            raw_text=raw_text,
            clean_text=clean_text,
        )

        artifact_paths = write_sidecar_files(
            audio_path=audio_path,
            source_url=job.url,
            provider=transcript_provider,
            model=transcript_model,
            raw_text=raw_text,
            clean_text=clean_text,
            markdown_text=markdown_text,
            extra_meta={
                "title": job.title,
                "artifact_dir": str(audio_path.parent),
                "prepared_audio_path": str(prepared_audio),
                "cleanup_provider": cleanup_provider,
                "cleanup_model": cleanup_model,
                "cleanup_base_url": AI_CLEANUP_BASE_URL,
                "cleanup_prompt_file": AI_CLEANUP_PROMPT_FILE,
                "cleanup_error": cleanup_error,
                "transcription_response": transcript_response,
                "cleanup_response": cleanup_response,
            },
        )

        job.artifact_dir = str(audio_path.parent)
        job.transcript_path = str(artifact_paths["markdown_path"])
        job.provider = transcript_provider
    finally:
        if (
            prepared_audio != audio_path
            and prepared_audio.exists()
            and not KEEP_TRANSCRIPTION_INPUT
        ):
            prepared_audio.unlink(missing_ok=True)


def worker(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return

    set_job_state(job, status="Starting...")
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    options = build_ydl_options(job)
    preset_conf = FORMAT_PRESETS[job.preset]

    try:
        expected_path: Path | None = None
        with yt_dlp.YoutubeDL(options) as ydl:
            preview_info = None
            try:
                preview_info = ydl.extract_info(job.url, download=False)
                if isinstance(preview_info, dict):
                    expected_path = Path(ydl.prepare_filename(preview_info))
                    with job.lock:
                        job.title = preview_info.get("title", job.url)
            except Exception:
                pass

            download_info = ydl.extract_info(job.url, download=True)
            if expected_path is None and isinstance(download_info, dict):
                expected_path = Path(ydl.prepare_filename(download_info))
                with job.lock:
                    job.title = download_info.get("title", job.title)

        if expected_path is None:
            raise RuntimeError("Unable to resolve download output path.")

        media_path = resolve_media_path(expected_path, job.preset)
        job.download_path = str(media_path)
        job.artifact_dir = str(media_path.parent)

        if preset_conf.get("transcribe") and ENABLE_TRANSCRIPTION:
            run_transcription_pipeline(job, media_path)

        with job.lock:
            job.done = True
            job.status = (
                "Done · transcript ready"
                if preset_conf.get("transcribe") and ENABLE_TRANSCRIPTION
                else "Done"
            )
            job.progress = 100
    except Exception as exc:
        with job.lock:
            job.done = True
            job.status = "Failed"
            job.error = str(exc)


@app.route("/")
def index():
    config = {
        "presets": list(FORMAT_PRESETS.keys()),
        "defaultPreset": "Best Video (MP4)",
        "transcriptionEnabled": ENABLE_TRANSCRIPTION,
        "transcriptionProvider": "openrouter",
        "transcriptionModel": OPENROUTER_TRANSCRIPTION_MODEL,
        "aiCleanupEnabled": AI_CLEANUP_ENABLED,
        "aiCleanupProvider": AI_CLEANUP_PROVIDER_LABEL,
        "aiCleanupModel": AI_CLEANUP_MODEL,
    }
    return render_template("index.html", app_title=APP_TITLE, config_json=json.dumps(config))


@app.route("/api/start", methods=["POST"])
def start():
    data = request.json or {}
    urls = [u.strip() for u in data.get("url", "").splitlines() if u.strip()]
    if not urls:
        return jsonify({"error": "No URL"}), 400

    preset = data.get("preset")
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


@app.route("/api/tasks")
def tasks():
    with jobs_lock:
        tasks_list = []
        for job in sorted(jobs.values(), key=lambda x: x.created_at, reverse=True)[:20]:
            tasks_list.append(
                {
                    "id": job.job_id,
                    "title": job.title,
                    "status": job.status,
                    "progress": round(job.progress),
                    "done": job.done,
                    "error": job.error,
                    "artifact_dir": job.artifact_dir,
                    "download_path": job.download_path,
                    "transcript_path": job.transcript_path,
                    "provider": job.provider,
                }
            )
    return jsonify({"tasks": tasks_list})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=True)
