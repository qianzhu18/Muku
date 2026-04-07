from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import click

try:
    from . import app as web_app
except ImportError:
    import app as web_app


PRESET_CHOICES = tuple(web_app.FORMAT_PRESETS.keys())
DEFAULT_AUDIO_PRESET = "Best Audio (MP3)"


def _configure_runtime(output_dir: Path | None, cookies_path: Path | None) -> None:
    if output_dir is not None:
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        web_app.DOWNLOAD_DIR = str(output_dir)

    if cookies_path is not None:
        web_app.COOKIES_PATH = str(cookies_path.expanduser().resolve())


def _job_summary(job: web_app.Job) -> dict:
    return {
        "id": job.job_id,
        "title": job.title,
        "status": job.status,
        "done": job.done,
        "error": job.error,
        "artifact_dir": job.artifact_dir,
        "download_path": job.download_path,
        "transcript_path": job.transcript_path,
        "provider": job.provider,
        "generate_transcript": job.generate_transcript,
        "preset": job.preset,
        "source_url": job.url,
    }


def _emit_results(results: list[dict], as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return

    for result in results:
        click.echo(f"[{result['status']}] {result['title']}")
        if result.get("download_path"):
            click.echo(f"  download: {result['download_path']}")
        if result.get("transcript_path"):
            click.echo(f"  transcript: {result['transcript_path']}")
        if result.get("artifact_dir"):
            click.echo(f"  artifacts: {result['artifact_dir']}")
        if result.get("error"):
            click.echo(f"  error: {result['error']}")


def _exit_for_failures(results: list[dict]) -> None:
    if any(result.get("error") for result in results):
        raise click.exceptions.Exit(1)


def _run_download_jobs(
    *,
    urls: tuple[str, ...],
    preset: str,
    use_cookies: bool,
    generate_transcript: bool,
) -> list[dict]:
    results: list[dict] = []
    for url in urls:
        job = web_app.Job(
            job_id=uuid.uuid4().hex,
            url=url,
            preset=preset,
            use_cookies=use_cookies,
            generate_transcript=generate_transcript,
        )
        web_app.run_job(job)
        results.append(_job_summary(job))
    return results


def _run_local_audio_jobs(
    *,
    audio_files: tuple[Path, ...],
    source_url: str | None,
    title: str | None,
    copy_to_dir: Path | None,
) -> list[dict]:
    if title and len(audio_files) != 1:
        raise click.ClickException("--title 只适用于单个音频文件。")

    results: list[dict] = []
    for audio_file in audio_files:
        resolved = audio_file.expanduser().resolve()
        if not resolved.exists():
            raise click.ClickException(f"音频文件不存在：{resolved}")

        target_audio = resolved
        if copy_to_dir is not None:
            copy_to_dir.mkdir(parents=True, exist_ok=True)
            target_audio = copy_to_dir / resolved.name
            shutil.copy2(resolved, target_audio)

        job = web_app.Job(
            job_id=uuid.uuid4().hex,
            url=source_url or f"file://{resolved}",
            preset=DEFAULT_AUDIO_PRESET,
            use_cookies=False,
            generate_transcript=True,
        )
        job.title = title or target_audio.stem
        job.download_path = str(target_audio)
        job.artifact_dir = str(target_audio.parent)

        try:
            web_app.run_transcription_pipeline(job, target_audio)
            job.done = True
            job.progress = 100
            job.status = "Done · transcript ready"
        except Exception as exc:
            job.done = True
            job.status = "Failed"
            job.error = str(exc)

        results.append(_job_summary(job))

    return results


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Downloader by Qianzhu 的 CLI 入口。"""


@main.command("capture")
@click.argument("urls", nargs=-1, required=True)
@click.option(
    "--cookies/--no-cookies",
    default=False,
    help="使用已配置的 cookies 文件抓取受限内容。",
)
@click.option(
    "--cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 cookies 文件路径。",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="下载和逐字稿输出目录。",
)
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON。")
def capture_command(
    urls: tuple[str, ...],
    cookies: bool,
    cookies_path: Path | None,
    output_dir: Path | None,
    as_json: bool,
) -> None:
    """从 URL 直接生成 MP3 和 Markdown 逐字稿。"""
    _configure_runtime(output_dir, cookies_path)
    results = _run_download_jobs(
        urls=urls,
        preset=DEFAULT_AUDIO_PRESET,
        use_cookies=cookies or cookies_path is not None,
        generate_transcript=True,
    )
    _emit_results(results, as_json)
    _exit_for_failures(results)


@main.command("download")
@click.argument("urls", nargs=-1, required=True)
@click.option(
    "--preset",
    type=click.Choice(PRESET_CHOICES),
    default=DEFAULT_AUDIO_PRESET,
    show_default=True,
    help="下载预设。",
)
@click.option(
    "--transcript/--no-transcript",
    default=False,
    help="仅在 Best Audio (MP3) 预设下生成逐字稿。",
)
@click.option(
    "--cookies/--no-cookies",
    default=False,
    help="使用已配置的 cookies 文件抓取受限内容。",
)
@click.option(
    "--cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 cookies 文件路径。",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="下载输出目录。",
)
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON。")
def download_command(
    urls: tuple[str, ...],
    preset: str,
    transcript: bool,
    cookies: bool,
    cookies_path: Path | None,
    output_dir: Path | None,
    as_json: bool,
) -> None:
    """下载 URL，可选附带逐字稿生成。"""
    if transcript and preset != DEFAULT_AUDIO_PRESET:
        raise click.ClickException("开启逐字稿时，请将 --preset 设为 Best Audio (MP3)。")

    _configure_runtime(output_dir, cookies_path)
    results = _run_download_jobs(
        urls=urls,
        preset=preset,
        use_cookies=cookies or cookies_path is not None,
        generate_transcript=transcript,
    )
    _emit_results(results, as_json)
    _exit_for_failures(results)


@main.command("audio")
@click.argument("audio_files", nargs=-1, required=True, type=click.Path(path_type=Path, dir_okay=False))
@click.option("--source-url", help="为本地音频补充原始来源链接。")
@click.option("--title", help="覆盖默认标题，仅适用于单个音频文件。")
@click.option(
    "--copy-to-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="先复制音频到目标目录，再在该目录输出逐字稿产物。",
)
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON。")
def audio_command(
    audio_files: tuple[Path, ...],
    source_url: str | None,
    title: str | None,
    copy_to_dir: Path | None,
    as_json: bool,
) -> None:
    """把本地音频文件转成逐字稿和解析稿。"""
    results = _run_local_audio_jobs(
        audio_files=audio_files,
        source_url=source_url,
        title=title,
        copy_to_dir=copy_to_dir.expanduser().resolve() if copy_to_dir else None,
    )
    _emit_results(results, as_json)
    _exit_for_failures(results)


@main.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON。")
def doctor_command(as_json: bool) -> None:
    """检查依赖和云端接口配置状态。"""
    report = {
        "download_dir": web_app.DOWNLOAD_DIR,
        "ffmpeg_bin": web_app.FFMPEG_BIN,
        "ffmpeg_found": shutil.which(web_app.FFMPEG_BIN) is not None,
        "yt_dlp_found": shutil.which("yt-dlp") is not None,
        "transcription_enabled": web_app.ENABLE_TRANSCRIPTION,
        "transcription_model": web_app.OPENROUTER_TRANSCRIPTION_MODEL,
        "openrouter_key_configured": bool(web_app.transcribe_audio.__globals__.get("OPENROUTER_API_KEY")),
        "cleanup_enabled": web_app.AI_CLEANUP_ENABLED,
        "cleanup_model": web_app.AI_CLEANUP_MODEL,
        "cleanup_key_configured": bool(web_app.cleanup_transcript.__globals__.get("AI_CLEANUP_API_KEY")),
        "cleanup_prompt_file": web_app.AI_CLEANUP_PROMPT_FILE,
        "cleanup_prompt_exists": Path(web_app.AI_CLEANUP_PROMPT_FILE).exists(),
        "article_enabled": web_app.ENABLE_ARTICLE_DRAFT,
        "article_model": web_app.ARTICLE_DRAFT_MODEL,
        "article_key_configured": bool(
            web_app.generate_ai_article_draft.__globals__.get("ARTICLE_DRAFT_API_KEY")
        ),
        "article_prompt_file": web_app.ARTICLE_DRAFT_PROMPT_FILE,
        "article_prompt_exists": Path(web_app.ARTICLE_DRAFT_PROMPT_FILE).exists(),
        "cookies_path": web_app.COOKIES_PATH or None,
        "cookies_exists": bool(web_app.COOKIES_PATH) and Path(web_app.COOKIES_PATH).exists(),
    }

    if as_json:
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for key, value in report.items():
        click.echo(f"{key}: {value}")


@main.command("serve")
@click.option("--host", default=web_app.HOST, show_default=True, help="Web 服务监听地址。")
@click.option("--port", default=web_app.PORT, show_default=True, type=int, help="Web 服务端口。")
def serve_command(host: str, port: int) -> None:
    """启动现有 Web UI。"""
    web_app.HOST = host
    web_app.PORT = port
    click.echo(f"Serving web UI on http://{host}:{port}")
    web_app.app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main(prog_name="video-downloade")
