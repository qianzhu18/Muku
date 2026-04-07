from __future__ import annotations

from contextlib import contextmanager
import json
import shutil
import uuid
from pathlib import Path

import click

try:
    from . import app as web_app
    from . import openai_compatible_cleanup as cleanup_backend
    from . import openrouter_backends as openrouter_backend
except ImportError:
    import app as web_app
    import openai_compatible_cleanup as cleanup_backend
    import openrouter_backends as openrouter_backend


DEFAULT_VIDEO_PRESET = web_app.VIDEO_PRESET_NAME
DEFAULT_AUDIO_PRESET = web_app.AUDIO_PRESET_NAME
DEFAULT_TRANSCRIPT_PRESET = web_app.TRANSCRIPT_PRESET_NAME
PRESET_CHOICES = (DEFAULT_VIDEO_PRESET, DEFAULT_AUDIO_PRESET)
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".opus", ".aac", ".ogg", ".wma"}
OUTPUT_CHOICES = ("text", "json", "paths")
_UNSET = object()


def _normalize_output_mode(output: str, as_json: bool) -> str:
    return "json" if as_json else output


def _collect_line_inputs(
    *,
    values: tuple[str, ...],
    input_file: Path | None,
    stdin_enabled: bool,
    label: str,
) -> tuple[str, ...]:
    items = [value.strip() for value in values if value.strip()]

    if input_file is not None:
        file_lines = input_file.expanduser().read_text(encoding="utf-8").splitlines()
        items.extend(line.strip() for line in file_lines if line.strip())

    if stdin_enabled:
        stdin_lines = click.get_text_stream("stdin").read().splitlines()
        items.extend(line.strip() for line in stdin_lines if line.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)

    if not deduped:
        raise click.ClickException(f"没有收到任何{label}。请传参数、--input-file 或 --stdin。")

    return tuple(deduped)


def _collect_url_inputs(
    *,
    values: tuple[str, ...],
    input_file: Path | None,
    stdin_enabled: bool,
) -> tuple[str, ...]:
    raw_blocks = [value for value in values if value.strip()]

    if input_file is not None:
        raw_blocks.append(input_file.expanduser().read_text(encoding="utf-8"))

    if stdin_enabled:
        raw_blocks.append(click.get_text_stream("stdin").read())

    merged_text = "\n".join(block for block in raw_blocks if block.strip())
    normalized = web_app.collect_url_inputs(merged_text)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in normalized:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)

    if not deduped:
        raise click.ClickException("没有识别到可用链接。支持直接粘贴 URL，或粘贴 Bilibili / YouTube 分享文案。")

    return tuple(deduped)


def _write_result_file(results: list[dict], result_file: Path | None) -> None:
    if result_file is None:
        return
    result_file = result_file.expanduser().resolve()
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _emit_results(results: list[dict], output_mode: str) -> None:
    if output_mode == "json":
        click.echo(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return

    if output_mode == "paths":
        for result in results:
            primary_path = (
                result.get("transcript_path")
                or result.get("markdown_path")
                or result.get("download_path")
                or result.get("artifact_dir")
            )
            if primary_path:
                click.echo(primary_path)
        return

    for result in results:
        title = result.get("title") or result.get("target") or result.get("markdown_path") or "result"
        status = result.get("status") or ("Ready" if result.get("meta_exists") else "Info")
        click.echo(f"[{status}] {title}")
        if result.get("download_path"):
            click.echo(f"  download: {result['download_path']}")
        if result.get("transcript_path"):
            click.echo(f"  transcript: {result['transcript_path']}")
        if result.get("markdown_path"):
            click.echo(f"  markdown: {result['markdown_path']}")
        if result.get("raw_path"):
            click.echo(f"  raw: {result['raw_path']}")
        if result.get("article_path"):
            click.echo(f"  article: {result['article_path']}")
        if result.get("meta_path"):
            click.echo(f"  meta: {result['meta_path']}")
        if result.get("artifact_dir"):
            click.echo(f"  artifacts: {result['artifact_dir']}")
        if result.get("error"):
            click.echo(f"  error: {result['error']}")


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
        "transcript_route": job.transcript_route,
        "generate_transcript": job.generate_transcript,
        "preset": job.preset,
        "source_url": job.url,
    }


def _exit_for_failures(results: list[dict]) -> None:
    if any(result.get("error") for result in results):
        raise click.exceptions.Exit(1)


@contextmanager
def _runtime_overrides(
    *,
    output_dir: Path | None = None,
    cookies_path: Path | None = None,
    cookies_from_browser: str | object = _UNSET,
    youtube_cookies_path: Path | None = None,
    youtube_cookies_from_browser: str | object = _UNSET,
    bilibili_cookies_path: Path | None = None,
    bilibili_cookies_from_browser: str | object = _UNSET,
    transcription_model: str | object = _UNSET,
    cleanup_model: str | object = _UNSET,
    article_model: str | object = _UNSET,
    language: str | object = _UNSET,
    bitrate: str | object = _UNSET,
    cleanup_enabled: bool | object = _UNSET,
    article_enabled: bool | object = _UNSET,
    keep_transcription_input: bool | object = _UNSET,
    cleanup_prompt_file: Path | object = _UNSET,
    article_prompt_file: Path | object = _UNSET,
):
    snapshots: list[tuple[object, str, object]] = []

    def patch(module: object, name: str, value: object) -> None:
        if value is _UNSET:
            return
        snapshots.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    if output_dir is not None:
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        patch(web_app, "DOWNLOAD_DIR", str(output_dir))

    if cookies_path is not None:
        patch(web_app, "COOKIES_PATH", str(cookies_path.expanduser().resolve()))
    patch(web_app, "COOKIES_FROM_BROWSER", cookies_from_browser)
    if youtube_cookies_path is not None:
        patch(web_app, "YOUTUBE_COOKIES_PATH", str(youtube_cookies_path.expanduser().resolve()))
    patch(web_app, "YOUTUBE_COOKIES_FROM_BROWSER", youtube_cookies_from_browser)
    if bilibili_cookies_path is not None:
        patch(web_app, "BILIBILI_COOKIES_PATH", str(bilibili_cookies_path.expanduser().resolve()))
    patch(web_app, "BILIBILI_COOKIES_FROM_BROWSER", bilibili_cookies_from_browser)

    patch(web_app, "TRANSCRIPTION_LANGUAGE", language)
    patch(web_app, "TRANSCRIPTION_AUDIO_BITRATE", bitrate)
    patch(web_app, "KEEP_TRANSCRIPTION_INPUT", keep_transcription_input)

    patch(openrouter_backend, "OPENROUTER_TRANSCRIPTION_MODEL", transcription_model)
    patch(web_app, "OPENROUTER_TRANSCRIPTION_MODEL", transcription_model)

    patch(cleanup_backend, "AI_CLEANUP_ENABLED", cleanup_enabled)
    patch(web_app, "AI_CLEANUP_ENABLED", cleanup_enabled)
    patch(cleanup_backend, "ENABLE_ARTICLE_DRAFT", article_enabled)
    patch(web_app, "ENABLE_ARTICLE_DRAFT", article_enabled)

    patch(cleanup_backend, "AI_CLEANUP_MODEL", cleanup_model)
    patch(web_app, "AI_CLEANUP_MODEL", cleanup_model)
    patch(cleanup_backend, "ARTICLE_DRAFT_MODEL", article_model)
    patch(web_app, "ARTICLE_DRAFT_MODEL", article_model)

    if cleanup_prompt_file is not _UNSET:
        prompt_path = Path(cleanup_prompt_file).expanduser().resolve()
        patch(cleanup_backend, "AI_CLEANUP_PROMPT_FILE", str(prompt_path))
        patch(web_app, "AI_CLEANUP_PROMPT_FILE", str(prompt_path))

    if article_prompt_file is not _UNSET:
        prompt_path = Path(article_prompt_file).expanduser().resolve()
        patch(cleanup_backend, "ARTICLE_DRAFT_PROMPT_FILE", str(prompt_path))
        patch(web_app, "ARTICLE_DRAFT_PROMPT_FILE", str(prompt_path))

    try:
        yield
    finally:
        for module, name, value in reversed(snapshots):
            setattr(module, name, value)


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


def _artifact_paths_from_target(target: Path) -> dict[str, Path]:
    target = target.expanduser().resolve()
    if target.name.endswith(" - 转写信息.json") and target.exists():
        meta = json.loads(target.read_text(encoding="utf-8"))
        artifact_base = meta.get("artifact_base_path") or meta.get("audio_path")
        if not artifact_base:
            raise click.ClickException(f"该 metadata 缺少 artifact_base_path/audio_path：{target}")
        base_path = Path(artifact_base).expanduser().resolve()
        return web_app.build_artifact_paths(base_path)

    if target.suffix.lower() in AUDIO_EXTENSIONS:
        return web_app.build_artifact_paths(target)

    known_suffixes = (
        " - 原始逐字稿.txt",
        " - 解析稿.md",
        " - 逐字稿.md",
        " - 转写信息.json",
    )
    for suffix in known_suffixes:
        if target.name.endswith(suffix):
            stem = target.name[: -len(suffix)]
            for extension in AUDIO_EXTENSIONS:
                audio_candidate = target.with_name(f"{stem}{extension}")
                if audio_candidate.exists():
                    return web_app.build_artifact_paths(audio_candidate)
            return web_app.build_artifact_paths(target.with_name(f"{stem}.mp3"))

    raise click.ClickException(f"无法从该路径推断逐字稿产物：{target}")


def _summarize_metadata(metadata: dict) -> dict:
    if not metadata:
        return {}

    keys = [
        "audio_path",
        "source_url",
        "provider",
        "model",
        "title",
        "platform",
        "artifact_dir",
        "artifact_base_path",
        "prepared_audio_path",
        "source_media_path",
        "transcript_route",
        "subtitle_source",
        "subtitle_language",
        "subtitle_format",
        "cleanup_provider",
        "cleanup_model",
        "cleanup_base_url",
        "cleanup_prompt_file",
        "cleanup_error",
        "article_provider",
        "article_model",
        "article_base_url",
        "article_prompt_file",
        "article_error",
    ]
    return {key: metadata.get(key) for key in keys if key in metadata}


def _artifact_record_with_metadata(target: Path, *, include_full_metadata: bool) -> dict:
    artifact_paths = _artifact_paths_from_target(target)
    meta_path = artifact_paths["meta_path"]
    metadata = {}
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    return {
        "target": str(target.expanduser().resolve()),
        "artifact_dir": str(artifact_paths["markdown_path"].parent),
        "raw_path": str(artifact_paths["raw_path"]),
        "article_path": str(artifact_paths["article_path"]),
        "markdown_path": str(artifact_paths["markdown_path"]),
        "meta_path": str(meta_path),
        "raw_exists": artifact_paths["raw_path"].exists(),
        "article_exists": artifact_paths["article_path"].exists(),
        "markdown_exists": artifact_paths["markdown_path"].exists(),
        "meta_exists": meta_path.exists(),
        "metadata": metadata if include_full_metadata else _summarize_metadata(metadata),
    }


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Downloader by Qianzhu 的 CLI 入口。"""


@main.command("capture")
@click.argument("urls", nargs=-1)
@click.option(
    "--input-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="从文本文件读取 URL，每行一个。",
)
@click.option("--stdin", "stdin_enabled", is_flag=True, help="从标准输入读取 URL，每行一个。")
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
    "--cookies-from-browser",
    help="直接从浏览器读取 cookies，例如 chrome、edge:Profile 1、firefox::default。",
)
@click.option(
    "--youtube-cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 YouTube cookies.txt 路径。",
)
@click.option(
    "--youtube-cookies-from-browser",
    help="直接从浏览器读取 YouTube 登录态，例如 chrome、edge:Profile 1。",
)
@click.option(
    "--bilibili-cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 Bilibili cookies.txt 路径。",
)
@click.option(
    "--bilibili-cookies-from-browser",
    help="直接从浏览器读取 Bilibili 登录态，例如 chrome、edge:Profile 1。",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="下载和逐字稿输出目录。",
)
@click.option(
    "--output",
    "output_mode",
    type=click.Choice(OUTPUT_CHOICES),
    default="text",
    show_default=True,
    help="结果输出格式。",
)
@click.option("--json", "as_json", is_flag=True, help="兼容旧用法，等同于 --output json。")
@click.option(
    "--result-file",
    type=click.Path(path_type=Path, dir_okay=False),
    help="把结果 JSON 额外写入文件。",
)
@click.option("--language", help="覆盖本次转写语言提示，例如 zh、en、auto。")
@click.option("--bitrate", help="覆盖本次转写前音频压缩码率，例如 48k。")
@click.option("--transcription-model", help="覆盖本次 OpenRouter 音频模型。")
@click.option("--cleanup-model", help="覆盖本次清洗模型。")
@click.option("--article-model", help="覆盖本次解析稿模型。")
@click.option("--cleanup/--no-cleanup", default=True, help="是否启用 AI 清洗。")
@click.option("--article/--no-article", default=True, help="是否生成解析稿。")
@click.option(
    "--cleanup-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖清洗提示词文件。",
)
@click.option(
    "--article-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖解析稿提示词文件。",
)
@click.option(
    "--keep-transcription-input/--no-keep-transcription-input",
    default=None,
    help="是否保留转写前预处理音频。",
)
def capture_command(
    urls: tuple[str, ...],
    input_file: Path | None,
    stdin_enabled: bool,
    cookies: bool,
    cookies_path: Path | None,
    cookies_from_browser: str | None,
    youtube_cookies_path: Path | None,
    youtube_cookies_from_browser: str | None,
    bilibili_cookies_path: Path | None,
    bilibili_cookies_from_browser: str | None,
    output_dir: Path | None,
    output_mode: str,
    as_json: bool,
    result_file: Path | None,
    language: str | None,
    bitrate: str | None,
    transcription_model: str | None,
    cleanup_model: str | None,
    article_model: str | None,
    cleanup: bool,
    article: bool,
    cleanup_prompt_file: Path | None,
    article_prompt_file: Path | None,
    keep_transcription_input: bool | None,
) -> None:
    """从 URL 直接生成 Markdown 逐字稿，优先提取字幕，失败回退到 MP3 转写。"""
    resolved_urls = _collect_url_inputs(
        values=urls,
        input_file=input_file,
        stdin_enabled=stdin_enabled,
    )
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    with _runtime_overrides(
        output_dir=output_dir,
        cookies_path=cookies_path,
        cookies_from_browser=cookies_from_browser if cookies_from_browser else _UNSET,
        youtube_cookies_path=youtube_cookies_path,
        youtube_cookies_from_browser=youtube_cookies_from_browser if youtube_cookies_from_browser else _UNSET,
        bilibili_cookies_path=bilibili_cookies_path,
        bilibili_cookies_from_browser=bilibili_cookies_from_browser if bilibili_cookies_from_browser else _UNSET,
        transcription_model=transcription_model if transcription_model else _UNSET,
        cleanup_model=cleanup_model if cleanup_model else _UNSET,
        article_model=article_model if article_model else _UNSET,
        language=language if language else _UNSET,
        bitrate=bitrate if bitrate else _UNSET,
        cleanup_enabled=cleanup,
        article_enabled=article,
        keep_transcription_input=keep_transcription_input
        if keep_transcription_input is not None
        else _UNSET,
        cleanup_prompt_file=cleanup_prompt_file if cleanup_prompt_file else _UNSET,
        article_prompt_file=article_prompt_file if article_prompt_file else _UNSET,
    ):
        results = _run_download_jobs(
            urls=resolved_urls,
            preset=DEFAULT_TRANSCRIPT_PRESET,
            use_cookies=(
                cookies
                or cookies_path is not None
                or bool(cookies_from_browser)
                or youtube_cookies_path is not None
                or bool(youtube_cookies_from_browser)
                or bilibili_cookies_path is not None
                or bool(bilibili_cookies_from_browser)
            ),
            generate_transcript=True,
        )
    _write_result_file(results, result_file)
    _emit_results(results, final_output_mode)
    _exit_for_failures(results)


@main.command("download")
@click.argument("urls", nargs=-1)
@click.option(
    "--input-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="从文本文件读取 URL，每行一个。",
)
@click.option("--stdin", "stdin_enabled", is_flag=True, help="从标准输入读取 URL，每行一个。")
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
    help="仅在 Best Audio (MP3) 预设下生成逐字稿（兼容旧链路）。",
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
    "--cookies-from-browser",
    help="直接从浏览器读取 cookies，例如 chrome、edge:Profile 1、firefox::default。",
)
@click.option(
    "--youtube-cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 YouTube cookies.txt 路径。",
)
@click.option(
    "--youtube-cookies-from-browser",
    help="直接从浏览器读取 YouTube 登录态，例如 chrome、edge:Profile 1。",
)
@click.option(
    "--bilibili-cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 Bilibili cookies.txt 路径。",
)
@click.option(
    "--bilibili-cookies-from-browser",
    help="直接从浏览器读取 Bilibili 登录态，例如 chrome、edge:Profile 1。",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="下载输出目录。",
)
@click.option(
    "--output",
    "output_mode",
    type=click.Choice(OUTPUT_CHOICES),
    default="text",
    show_default=True,
    help="结果输出格式。",
)
@click.option("--json", "as_json", is_flag=True, help="兼容旧用法，等同于 --output json。")
@click.option(
    "--result-file",
    type=click.Path(path_type=Path, dir_okay=False),
    help="把结果 JSON 额外写入文件。",
)
@click.option("--language", help="覆盖本次转写语言提示，例如 zh、en、auto。")
@click.option("--bitrate", help="覆盖本次转写前音频压缩码率，例如 48k。")
@click.option("--transcription-model", help="覆盖本次 OpenRouter 音频模型。")
@click.option("--cleanup-model", help="覆盖本次清洗模型。")
@click.option("--article-model", help="覆盖本次解析稿模型。")
@click.option("--cleanup/--no-cleanup", default=True, help="是否启用 AI 清洗。")
@click.option("--article/--no-article", default=True, help="是否生成解析稿。")
@click.option(
    "--cleanup-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖清洗提示词文件。",
)
@click.option(
    "--article-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖解析稿提示词文件。",
)
@click.option(
    "--keep-transcription-input/--no-keep-transcription-input",
    default=None,
    help="是否保留转写前预处理音频。",
)
def download_command(
    urls: tuple[str, ...],
    input_file: Path | None,
    stdin_enabled: bool,
    preset: str,
    transcript: bool,
    cookies: bool,
    cookies_path: Path | None,
    cookies_from_browser: str | None,
    youtube_cookies_path: Path | None,
    youtube_cookies_from_browser: str | None,
    bilibili_cookies_path: Path | None,
    bilibili_cookies_from_browser: str | None,
    output_dir: Path | None,
    output_mode: str,
    as_json: bool,
    result_file: Path | None,
    language: str | None,
    bitrate: str | None,
    transcription_model: str | None,
    cleanup_model: str | None,
    article_model: str | None,
    cleanup: bool,
    article: bool,
    cleanup_prompt_file: Path | None,
    article_prompt_file: Path | None,
    keep_transcription_input: bool | None,
) -> None:
    """下载 URL，可选附带逐字稿生成。"""
    if transcript and preset != DEFAULT_AUDIO_PRESET:
        raise click.ClickException("开启逐字稿时，请将 --preset 设为 Best Audio (MP3)。")

    resolved_urls = _collect_url_inputs(
        values=urls,
        input_file=input_file,
        stdin_enabled=stdin_enabled,
    )
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    with _runtime_overrides(
        output_dir=output_dir,
        cookies_path=cookies_path,
        cookies_from_browser=cookies_from_browser if cookies_from_browser else _UNSET,
        youtube_cookies_path=youtube_cookies_path,
        youtube_cookies_from_browser=youtube_cookies_from_browser if youtube_cookies_from_browser else _UNSET,
        bilibili_cookies_path=bilibili_cookies_path,
        bilibili_cookies_from_browser=bilibili_cookies_from_browser if bilibili_cookies_from_browser else _UNSET,
        transcription_model=transcription_model if transcription_model else _UNSET,
        cleanup_model=cleanup_model if cleanup_model else _UNSET,
        article_model=article_model if article_model else _UNSET,
        language=language if language else _UNSET,
        bitrate=bitrate if bitrate else _UNSET,
        cleanup_enabled=cleanup,
        article_enabled=article,
        keep_transcription_input=keep_transcription_input
        if keep_transcription_input is not None
        else _UNSET,
        cleanup_prompt_file=cleanup_prompt_file if cleanup_prompt_file else _UNSET,
        article_prompt_file=article_prompt_file if article_prompt_file else _UNSET,
    ):
        results = _run_download_jobs(
            urls=resolved_urls,
            preset=preset,
            use_cookies=(
                cookies
                or cookies_path is not None
                or bool(cookies_from_browser)
                or youtube_cookies_path is not None
                or bool(youtube_cookies_from_browser)
                or bilibili_cookies_path is not None
                or bool(bilibili_cookies_from_browser)
            ),
            generate_transcript=transcript,
        )
    _write_result_file(results, result_file)
    _emit_results(results, final_output_mode)
    _exit_for_failures(results)


@main.command("audio")
@click.argument("audio_files", nargs=-1, type=click.Path(path_type=Path, dir_okay=False))
@click.option(
    "--input-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="从文本文件读取本地音频路径，每行一个。",
)
@click.option("--stdin", "stdin_enabled", is_flag=True, help="从标准输入读取本地音频路径，每行一个。")
@click.option("--source-url", help="为本地音频补充原始来源链接。")
@click.option("--title", help="覆盖默认标题，仅适用于单个音频文件。")
@click.option(
    "--copy-to-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="先复制音频到目标目录，再在该目录输出逐字稿产物。",
)
@click.option(
    "--output",
    "output_mode",
    type=click.Choice(OUTPUT_CHOICES),
    default="text",
    show_default=True,
    help="结果输出格式。",
)
@click.option("--json", "as_json", is_flag=True, help="兼容旧用法，等同于 --output json。")
@click.option(
    "--result-file",
    type=click.Path(path_type=Path, dir_okay=False),
    help="把结果 JSON 额外写入文件。",
)
@click.option("--language", help="覆盖本次转写语言提示，例如 zh、en、auto。")
@click.option("--bitrate", help="覆盖本次转写前音频压缩码率，例如 48k。")
@click.option("--transcription-model", help="覆盖本次 OpenRouter 音频模型。")
@click.option("--cleanup-model", help="覆盖本次清洗模型。")
@click.option("--article-model", help="覆盖本次解析稿模型。")
@click.option("--cleanup/--no-cleanup", default=True, help="是否启用 AI 清洗。")
@click.option("--article/--no-article", default=True, help="是否生成解析稿。")
@click.option(
    "--cleanup-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖清洗提示词文件。",
)
@click.option(
    "--article-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖解析稿提示词文件。",
)
@click.option(
    "--keep-transcription-input/--no-keep-transcription-input",
    default=None,
    help="是否保留转写前预处理音频。",
)
def audio_command(
    audio_files: tuple[Path, ...],
    input_file: Path | None,
    stdin_enabled: bool,
    source_url: str | None,
    title: str | None,
    copy_to_dir: Path | None,
    output_mode: str,
    as_json: bool,
    result_file: Path | None,
    language: str | None,
    bitrate: str | None,
    transcription_model: str | None,
    cleanup_model: str | None,
    article_model: str | None,
    cleanup: bool,
    article: bool,
    cleanup_prompt_file: Path | None,
    article_prompt_file: Path | None,
    keep_transcription_input: bool | None,
) -> None:
    """把本地音频文件转成逐字稿和解析稿。"""
    raw_paths = _collect_line_inputs(
        values=tuple(str(path) for path in audio_files),
        input_file=input_file,
        stdin_enabled=stdin_enabled,
        label="音频路径",
    )
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    with _runtime_overrides(
        transcription_model=transcription_model if transcription_model else _UNSET,
        cleanup_model=cleanup_model if cleanup_model else _UNSET,
        article_model=article_model if article_model else _UNSET,
        language=language if language else _UNSET,
        bitrate=bitrate if bitrate else _UNSET,
        cleanup_enabled=cleanup,
        article_enabled=article,
        keep_transcription_input=keep_transcription_input
        if keep_transcription_input is not None
        else _UNSET,
        cleanup_prompt_file=cleanup_prompt_file if cleanup_prompt_file else _UNSET,
        article_prompt_file=article_prompt_file if article_prompt_file else _UNSET,
    ):
        results = _run_local_audio_jobs(
            audio_files=tuple(Path(path) for path in raw_paths),
            source_url=source_url,
            title=title,
            copy_to_dir=copy_to_dir.expanduser().resolve() if copy_to_dir else None,
        )
    _write_result_file(results, result_file)
    _emit_results(results, final_output_mode)
    _exit_for_failures(results)


@main.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON。")
def doctor_command(as_json: bool) -> None:
    """检查依赖和云端接口配置状态。"""
    subtitle_auth_configured = web_app.platform_auth_configured("Unknown")
    report = {
        "download_dir": web_app.DOWNLOAD_DIR,
        "ffmpeg_bin": web_app.FFMPEG_BIN,
        "ffmpeg_found": shutil.which(web_app.FFMPEG_BIN) is not None,
        "yt_dlp_found": shutil.which("yt-dlp") is not None,
        "transcript_route_strategy": "subtitle_first_then_audio_fallback",
        "subtitle_auth_configured": subtitle_auth_configured,
        "youtube_auth_configured": web_app.platform_auth_configured("YouTube"),
        "bilibili_auth_configured": web_app.platform_auth_configured("Bilibili"),
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
        "cookies_from_browser": web_app.COOKIES_FROM_BROWSER or None,
        "youtube_cookies_path": web_app.YOUTUBE_COOKIES_PATH or None,
        "youtube_cookies_exists": bool(web_app.YOUTUBE_COOKIES_PATH) and Path(web_app.YOUTUBE_COOKIES_PATH).exists(),
        "youtube_cookies_from_browser": web_app.YOUTUBE_COOKIES_FROM_BROWSER or None,
        "bilibili_cookies_path": web_app.BILIBILI_COOKIES_PATH or None,
        "bilibili_cookies_exists": bool(web_app.BILIBILI_COOKIES_PATH) and Path(web_app.BILIBILI_COOKIES_PATH).exists(),
        "bilibili_cookies_from_browser": web_app.BILIBILI_COOKIES_FROM_BROWSER or None,
        "transcript_capture_ready": (
            shutil.which("yt-dlp") is not None
            and web_app.ENABLE_TRANSCRIPTION
            and bool(web_app.transcribe_audio.__globals__.get("OPENROUTER_API_KEY"))
        ),
    }

    if as_json:
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for key, value in report.items():
        click.echo(f"{key}: {value}")


@main.command("artifacts")
@click.argument("targets", nargs=-1, type=click.Path(path_type=Path))
@click.option(
    "--input-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="从文本文件读取目标路径，每行一个。",
)
@click.option("--stdin", "stdin_enabled", is_flag=True, help="从标准输入读取目标路径，每行一个。")
@click.option(
    "--output",
    "output_mode",
    type=click.Choice(OUTPUT_CHOICES),
    default="json",
    show_default=True,
    help="结果输出格式。",
)
@click.option("--json", "as_json", is_flag=True, help="兼容旧用法，等同于 --output json。")
@click.option(
    "--result-file",
    type=click.Path(path_type=Path, dir_okay=False),
    help="把结果 JSON 额外写入文件。",
)
@click.option(
    "--full-metadata/--summary-metadata",
    default=False,
    help="是否返回转写信息.json 的完整 metadata。",
)
def artifacts_command(
    targets: tuple[Path, ...],
    input_file: Path | None,
    stdin_enabled: bool,
    output_mode: str,
    as_json: bool,
    result_file: Path | None,
    full_metadata: bool,
) -> None:
    """从任意产物路径反查整组逐字稿 sidecar。"""
    resolved_targets = _collect_line_inputs(
        values=tuple(str(path) for path in targets),
        input_file=input_file,
        stdin_enabled=stdin_enabled,
        label="目标路径",
    )
    results = [
        _artifact_record_with_metadata(Path(target), include_full_metadata=full_metadata)
        for target in resolved_targets
    ]
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    _write_result_file(results, result_file)
    _emit_results(results, final_output_mode)


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
