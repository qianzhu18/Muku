from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

import click

try:
    from . import app as web_app
    from . import openai_compatible_cleanup as cleanup_backend
    from . import openrouter_backends as openrouter_backend
    from .transcript_pipeline import detect_platform
except ImportError:
    import app as web_app
    import openai_compatible_cleanup as cleanup_backend
    import openrouter_backends as openrouter_backend
    from transcript_pipeline import detect_platform


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
        raise click.ClickException("没有识别到可用链接。支持直接粘贴 URL，或粘贴 Bilibili / YouTube / Douyin 分享文案。")

    return tuple(deduped)


def _write_result_file(results: list[dict], result_file: Path | None) -> None:
    _write_result_file_with_history(results, result_file)


def _write_result_file_with_history(
    results: list[dict],
    result_file: Path | None,
    *,
    previous_results: list[dict] | None = None,
) -> None:
    if result_file is None:
        return
    result_file = result_file.expanduser().resolve()
    result_file.parent.mkdir(parents=True, exist_ok=True)
    payload_results = _merge_results_for_checkpoint(previous_results or [], results)
    _write_result_payload(result_file, payload_results)


def _write_result_payload(result_file: Path, payload_results: list[dict]) -> None:
    temp_path = result_file.with_name(f".{result_file.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps({"results": payload_results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(result_file)


def _result_identity(record: dict) -> str | None:
    for key in ("input_path", "target", "source_url", "download_path", "transcript_path", "artifact_dir", "id"):
        value = record.get(key)
        if value:
            return str(value)
    return None


def _merge_results_for_checkpoint(previous_results: list[dict], current_results: list[dict]) -> list[dict]:
    merged = [dict(record) for record in previous_results]
    index_by_key: dict[str, int] = {}

    for index, record in enumerate(merged):
        identity = _result_identity(record)
        if identity:
            index_by_key[identity] = index

    for record in current_results:
        identity = _result_identity(record)
        if identity and identity in index_by_key:
            merged[index_by_key[identity]] = dict(record)
            continue
        merged.append(dict(record))
        if identity:
            index_by_key[identity] = len(merged) - 1

    return merged


def _load_result_file_records(result_file: Path | None) -> list[dict]:
    if result_file is None:
        return []

    resolved = result_file.expanduser().resolve()
    if not resolved.exists():
        return []

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"结果文件不是合法 JSON：{resolved}") from exc

    records = payload.get("results")
    if not isinstance(records, list):
        raise click.ClickException(f"结果文件缺少 results 列表：{resolved}")
    return [record for record in records if isinstance(record, dict)]


class _CheckpointWriter:
    def __init__(
        self,
        result_file: Path | None,
        *,
        previous_results: list[dict] | None = None,
    ) -> None:
        self._result_file = result_file.expanduser().resolve() if result_file is not None else None
        self._lock = threading.Lock()
        self._results = _merge_results_for_checkpoint(previous_results or [], [])

    def record(self, record: dict) -> None:
        if self._result_file is None:
            return
        with self._lock:
            self._results = _merge_results_for_checkpoint(self._results, [record])
            _write_result_payload(self._result_file, self._results)

    def flush(self, results: list[dict]) -> None:
        if self._result_file is None:
            return
        with self._lock:
            self._results = _merge_results_for_checkpoint(self._results, results)
            _write_result_payload(self._result_file, self._results)


def _is_successful_checkpoint_record(record: dict) -> bool:
    status = str(record.get("status") or "")
    return not record.get("error") and not status.startswith("Failed")


def _mark_resumed_record(record: dict) -> dict:
    resumed = dict(record)
    resumed["status"] = "Skipped · resumed from checkpoint"
    resumed["resumed"] = True
    resumed["done"] = True
    return resumed


def _mark_existing_record(record: dict) -> dict:
    existing = dict(record)
    existing["status"] = (
        "Skipped · existing knowledge"
        if existing.get("knowledge_path")
        else "Skipped · existing transcript"
    )
    existing["reused_existing"] = True
    existing["done"] = True
    return existing


def _record_satisfies_stage(record: dict, stage: str | None) -> bool:
    if stage is None:
        return True
    if stage == "download":
        return bool(record.get("download_path"))
    if stage == "transcript":
        return bool(record.get("transcript_path") or record.get("markdown_path") or record.get("artifact_dir"))
    if stage == "knowledge":
        return bool(record.get("knowledge_path") or record.get("knowledge_exists"))
    raise ValueError(f"Unsupported checkpoint stage: {stage}")


def _split_pending_inputs(
    items: tuple[str, ...],
    *,
    previous_results: list[dict],
    required_stage: str | None = None,
) -> tuple[tuple[str, ...], list[dict], list[dict]]:
    completed_by_key = {
        identity: record
        for record in previous_results
        if _is_successful_checkpoint_record(record)
        if (identity := _result_identity(record))
    }

    pending: list[str] = []
    resumed_results: list[dict] = []
    reusable_results: list[dict] = []
    for item in items:
        existing = completed_by_key.get(item)
        if existing is not None and _record_satisfies_stage(existing, required_stage):
            resumed_results.append(_mark_resumed_record(existing))
            continue
        if existing is not None and required_stage == "knowledge" and _record_satisfies_stage(existing, "transcript"):
            reusable_results.append(dict(existing))
            continue
        pending.append(item)

    return tuple(pending), resumed_results, reusable_results


def _order_results_by_inputs(items: tuple[str, ...], results: list[dict]) -> list[dict]:
    by_key = {
        identity: dict(record)
        for record in results
        if (identity := _result_identity(record))
    }
    ordered: list[dict] = []
    seen: set[str] = set()

    for item in items:
        record = by_key.get(item)
        if record is None:
            continue
        ordered.append(record)
        seen.add(item)

    for identity, record in by_key.items():
        if identity in seen:
            continue
        ordered.append(record)

    return ordered


def _resolve_job_count(requested_jobs: int, total: int, *, cap: int = 4) -> int:
    if total <= 1:
        return 1
    if requested_jobs > 0:
        return max(1, min(requested_jobs, total))
    auto = os.cpu_count() or 1
    return max(1, min(cap, total, auto))


def _run_parallel_map(items: list, *, jobs: int, worker, on_result=None):
    if jobs <= 1 or len(items) <= 1:
        results = []
        for item in items:
            result = worker(item)
            results.append(result)
            if on_result is not None:
                on_result(result)
        return results

    ordered_results: list[dict | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        future_to_index = {
            executor.submit(worker, item): index for index, item in enumerate(items)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            result = future.result()
            ordered_results[index] = result
            if on_result is not None:
                on_result(result)

    return [result for result in ordered_results if result is not None]


def _load_json_if_exists(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_existing_transcript_record(meta_path: Path) -> dict | None:
    metadata = _load_json_if_exists(meta_path)
    if not metadata:
        return None

    source_url = str(metadata.get("source_url") or "").strip()
    if not source_url:
        return None

    artifact_base = metadata.get("artifact_base_path") or metadata.get("audio_path")
    if artifact_base:
        base_path = Path(artifact_base).expanduser().resolve()
    else:
        suffix = " - 转写信息.json"
        stem = meta_path.name[: -len(suffix)] if meta_path.name.endswith(suffix) else meta_path.stem
        base_path = meta_path.with_name(f"{stem}.mp3").resolve()
    artifact_paths = web_app.build_artifact_paths(base_path)
    markdown_path = artifact_paths["markdown_path"]
    if not markdown_path.exists():
        return None

    knowledge_path = artifact_paths["knowledge_path"] if artifact_paths["knowledge_path"].exists() else None
    download_path = metadata.get("audio_path")
    title = metadata.get("title") or base_path.stem
    return {
        "source_url": source_url,
        "title": title,
        "status": "Done · knowledge ready" if knowledge_path else "Done · transcript ready",
        "done": True,
        "error": None,
        "artifact_dir": str(markdown_path.parent),
        "download_path": download_path,
        "transcript_path": str(markdown_path),
        "knowledge_path": str(knowledge_path) if knowledge_path else None,
        "knowledge_exists": bool(knowledge_path),
        "provider": metadata.get("provider"),
        "transcript_route": metadata.get("transcript_route"),
    }


def _index_existing_transcripts_by_source_url() -> dict[str, dict]:
    download_dir = Path(web_app.DOWNLOAD_DIR).expanduser().resolve()
    if not download_dir.exists():
        return {}

    records: dict[str, dict] = {}
    meta_paths = sorted(
        download_dir.glob("**/* - 转写信息.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for meta_path in meta_paths:
        record = _build_existing_transcript_record(meta_path)
        if record is None:
            continue
        source_url = record["source_url"]
        if source_url in records:
            continue
        records[source_url] = record
    return records


def _split_pending_urls_with_existing_artifacts(
    urls: tuple[str, ...],
    *,
    required_stage: str | None,
) -> tuple[tuple[str, ...], list[dict], list[dict]]:
    existing_records = list(_index_existing_transcripts_by_source_url().values())
    pending_urls, reused_results, reusable_results = _split_pending_inputs(
        urls,
        previous_results=existing_records,
        required_stage=required_stage,
    )
    return (
        pending_urls,
        [_mark_existing_record(record) for record in reused_results],
        [dict(record) for record in reusable_results],
    )


def _build_existing_audio_record(audio_path: Path) -> dict | None:
    resolved = audio_path.expanduser().resolve()
    artifact_paths = web_app.build_artifact_paths(resolved)
    article_ready = artifact_paths["article_path"].exists() or not web_app.ENABLE_ARTICLE_DRAFT
    if not (
        artifact_paths["raw_path"].exists()
        and artifact_paths["markdown_path"].exists()
        and artifact_paths["meta_path"].exists()
        and article_ready
    ):
        return None

    metadata = _load_json_if_exists(artifact_paths["meta_path"]) or {}
    knowledge_path = artifact_paths["knowledge_path"] if artifact_paths["knowledge_path"].exists() else None
    return {
        "input_path": str(resolved),
        "title": metadata.get("title") or resolved.stem,
        "status": "Done · knowledge ready" if knowledge_path else "Done · transcript ready",
        "done": True,
        "error": None,
        "artifact_dir": str(artifact_paths["markdown_path"].parent),
        "download_path": str(resolved),
        "transcript_path": str(artifact_paths["markdown_path"]),
        "knowledge_path": str(knowledge_path) if knowledge_path else None,
        "knowledge_exists": bool(knowledge_path),
        "provider": metadata.get("provider"),
        "transcript_route": metadata.get("transcript_route"),
        "source_url": metadata.get("source_url"),
    }


def _split_pending_audio_paths_with_existing_artifacts(
    audio_paths: tuple[str, ...],
    *,
    required_stage: str | None,
) -> tuple[tuple[str, ...], list[dict], list[dict]]:
    existing_records = [
        record
        for path in audio_paths
        if (record := _build_existing_audio_record(Path(path))) is not None
    ]
    pending_paths, reused_results, reusable_results = _split_pending_inputs(
        audio_paths,
        previous_results=existing_records,
        required_stage=required_stage,
    )
    return (
        pending_paths,
        [_mark_existing_record(record) for record in reused_results],
        [dict(record) for record in reusable_results],
    )


def _emit_results(results: list[dict], output_mode: str) -> None:
    if output_mode == "json":
        click.echo(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return

    if output_mode == "paths":
        for result in results:
            primary_path = (
                result.get("knowledge_path")
                or result.get("transcript_path")
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
        if result.get("knowledge_path"):
            click.echo(f"  knowledge: {result['knowledge_path']}")
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
        "backend_error": job.backend_error,
        "artifact_dir": job.artifact_dir,
        "download_path": job.download_path,
        "transcript_path": job.transcript_path,
        "provider": job.provider,
        "transcript_route": job.transcript_route,
        "generate_transcript": job.generate_transcript,
        "preset": job.preset,
        "source_url": job.url,
        "output_dir": job.output_dir,
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
    douyin_cookies_path: Path | None = None,
    douyin_cookies_from_browser: str | object = _UNSET,
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
    knowledge_model: str | object = _UNSET,
    knowledge_prompt_file: Path | object = _UNSET,
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
    if douyin_cookies_path is not None:
        patch(web_app, "DOUYIN_COOKIES_PATH", str(douyin_cookies_path.expanduser().resolve()))
    patch(web_app, "DOUYIN_COOKIES_FROM_BROWSER", douyin_cookies_from_browser)

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
    patch(cleanup_backend, "KNOWLEDGE_DRAFT_MODEL", knowledge_model)

    if cleanup_prompt_file is not _UNSET:
        prompt_path = Path(cleanup_prompt_file).expanduser().resolve()
        patch(cleanup_backend, "AI_CLEANUP_PROMPT_FILE", str(prompt_path))
        patch(web_app, "AI_CLEANUP_PROMPT_FILE", str(prompt_path))

    if article_prompt_file is not _UNSET:
        prompt_path = Path(article_prompt_file).expanduser().resolve()
        patch(cleanup_backend, "ARTICLE_DRAFT_PROMPT_FILE", str(prompt_path))
        patch(web_app, "ARTICLE_DRAFT_PROMPT_FILE", str(prompt_path))

    if knowledge_prompt_file is not _UNSET:
        prompt_path = Path(knowledge_prompt_file).expanduser().resolve()
        patch(cleanup_backend, "KNOWLEDGE_DRAFT_PROMPT_FILE", str(prompt_path))

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
    jobs: int = 1,
    on_result=None,
) -> list[dict]:
    def run_single(url: str) -> dict:
        job = web_app.Job(
            job_id=uuid.uuid4().hex,
            url=url,
            preset=preset,
            use_cookies=use_cookies,
            generate_transcript=generate_transcript,
        )
        web_app.run_job(job)
        return _job_summary(job)

    return _run_parallel_map(
        list(urls),
        jobs=_resolve_job_count(jobs, len(urls), cap=6),
        worker=run_single,
        on_result=on_result,
    )


def _run_local_audio_jobs(
    *,
    audio_files: tuple[Path, ...],
    source_url: str | None,
    title: str | None,
    copy_to_dir: Path | None,
    jobs: int = 1,
    on_result=None,
) -> list[dict]:
    if title and len(audio_files) != 1:
        raise click.ClickException("--title 只适用于单个音频文件。")

    def run_single(audio_file: Path) -> dict:
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

        result = _job_summary(job)
        result["input_path"] = str(resolved)
        return result

    return _run_parallel_map(
        list(audio_files),
        jobs=_resolve_job_count(jobs, len(audio_files), cap=4),
        worker=run_single,
        on_result=on_result,
    )


def _knowledge_target_from_result(result: dict) -> Path | None:
    for key in ("transcript_path", "markdown_path", "download_path", "artifact_dir"):
        value = result.get(key)
        if value:
            return Path(value).expanduser().resolve()
    return None


def _attach_knowledge_results(
    results: list[dict],
    *,
    overwrite: bool,
    jobs: int = 1,
    on_result=None,
) -> list[dict]:
    targets: list[Path] = []
    seen: set[str] = set()

    for result in results:
        if result.get("error"):
            continue
        target = _knowledge_target_from_result(result)
        if target is None:
            continue
        target_key = str(target)
        if target_key in seen:
            continue
        seen.add(target_key)
        targets.append(target)

    if not targets:
        return results

    knowledge_results = _run_knowledge_jobs(
        targets=tuple(targets),
        overwrite=overwrite,
        jobs=jobs,
        on_result=on_result,
    )
    knowledge_by_target = {record["target"]: record for record in knowledge_results}

    merged_results: list[dict] = []
    for result in results:
        merged = dict(result)
        target = _knowledge_target_from_result(result)
        if target is not None:
            knowledge_record = knowledge_by_target.get(str(target))
            if knowledge_record is not None:
                merged["knowledge_status"] = knowledge_record.get("status")
                merged["knowledge_path"] = knowledge_record.get("knowledge_path")
                merged["knowledge_exists"] = knowledge_record.get("knowledge_exists")
                merged["knowledge_provider"] = knowledge_record.get("provider")
                merged["knowledge_model"] = knowledge_record.get("model")
                merged["knowledge_error"] = knowledge_record.get("error")
                if knowledge_record.get("artifact_dir"):
                    merged["artifact_dir"] = knowledge_record["artifact_dir"]
                if knowledge_record.get("error"):
                    merged["status"] = "Failed"
                    merged["error"] = knowledge_record["error"]
                elif knowledge_record.get("knowledge_path"):
                    merged["status"] = "Done · knowledge ready"
        merged_results.append(merged)

    return merged_results


def _artifact_paths_from_target(target: Path) -> dict[str, Path]:
    target = target.expanduser().resolve()
    if target.is_dir():
        meta_candidates = sorted(target.glob("* - 转写信息.json"))
        if meta_candidates:
            return _artifact_paths_from_target(meta_candidates[0])
        markdown_candidates = sorted(target.glob("* - 逐字稿.md"))
        if markdown_candidates:
            return _artifact_paths_from_target(markdown_candidates[0])
        raise click.ClickException(f"目录里没有找到逐字稿产物：{target}")

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
        " - 知识库.md",
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
        "cleanup_prompt_source",
        "cleanup_error",
        "article_provider",
        "article_model",
        "article_base_url",
        "article_prompt_file",
        "article_prompt_source",
        "article_error",
        "knowledge_provider",
        "knowledge_model",
        "knowledge_base_url",
        "knowledge_prompt_file",
        "knowledge_prompt_source",
        "knowledge_error",
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
        "knowledge_path": str(artifact_paths["knowledge_path"]),
        "markdown_path": str(artifact_paths["markdown_path"]),
        "meta_path": str(meta_path),
        "raw_exists": artifact_paths["raw_path"].exists(),
        "article_exists": artifact_paths["article_path"].exists(),
        "knowledge_exists": artifact_paths["knowledge_path"].exists(),
        "markdown_exists": artifact_paths["markdown_path"].exists(),
        "meta_exists": meta_path.exists(),
        "metadata": metadata if include_full_metadata else _summarize_metadata(metadata),
    }


def _load_artifact_metadata(artifact_paths: dict[str, Path]) -> dict:
    meta_path = artifact_paths["meta_path"]
    if not meta_path.exists():
        raise click.ClickException(f"找不到 metadata 文件：{meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _artifact_base_path_from_paths(artifact_paths: dict[str, Path], metadata: dict) -> Path:
    artifact_base = metadata.get("artifact_base_path")
    if artifact_base:
        return Path(artifact_base).expanduser().resolve()

    markdown_path = artifact_paths["markdown_path"]
    suffix = " - 逐字稿.md"
    stem = markdown_path.name[: -len(suffix)] if markdown_path.name.endswith(suffix) else markdown_path.stem
    return markdown_path.with_name(stem)


def _build_knowledge_source_text(artifact_paths: dict[str, Path]) -> str:
    sections: list[str] = []
    if artifact_paths["markdown_path"].exists():
        sections.append("## 逐字稿\n\n" + artifact_paths["markdown_path"].read_text(encoding="utf-8").strip())
    if artifact_paths["article_path"].exists():
        sections.append("## 解析稿\n\n" + artifact_paths["article_path"].read_text(encoding="utf-8").strip())
    if artifact_paths["raw_path"].exists():
        sections.append("## 原始逐字稿\n\n" + artifact_paths["raw_path"].read_text(encoding="utf-8").strip())
    if not sections:
        raise click.ClickException("该目标还没有可用于整理知识库的逐字稿资产。")
    return "\n\n".join(section for section in sections if section.strip()).strip()


def _run_knowledge_jobs(
    *,
    targets: tuple[Path, ...],
    overwrite: bool,
    jobs: int = 1,
    on_result=None,
) -> list[dict]:
    def run_single(target: Path) -> dict:
        resolved_target = str(target.expanduser().resolve())
        try:
            artifact_paths = _artifact_paths_from_target(target)
            metadata = _load_artifact_metadata(artifact_paths)
            artifact_base_path = _artifact_base_path_from_paths(artifact_paths, metadata)
            knowledge_path = artifact_paths["knowledge_path"]

            if knowledge_path.exists() and not overwrite:
                return {
                    "target": resolved_target,
                    "status": "Skipped",
                    "knowledge_path": str(knowledge_path),
                    "artifact_dir": str(knowledge_path.parent),
                    "title": metadata.get("title") or artifact_base_path.stem,
                    "error": None,
                    "knowledge_exists": True,
                    "provider": metadata.get("knowledge_provider"),
                    "model": metadata.get("knowledge_model"),
                }

            source_text = _build_knowledge_source_text(artifact_paths)
            title = metadata.get("title") or artifact_base_path.stem
            source_url = metadata.get("source_url") or ""
            platform = metadata.get("platform") or detect_platform(source_url)
            knowledge_result = cleanup_backend.generate_knowledge_draft(
                text=source_text,
                title=title,
                source_url=source_url,
                platform=platform,
            )
            knowledge_text = knowledge_result["text"].strip()
            knowledge_path.parent.mkdir(parents=True, exist_ok=True)
            knowledge_path.write_text(knowledge_text + "\n", encoding="utf-8")

            metadata["knowledge_provider"] = knowledge_result["provider"]
            metadata["knowledge_model"] = knowledge_result["model"]
            metadata["knowledge_base_url"] = cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL
            metadata["knowledge_prompt_file"] = cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_FILE
            metadata["knowledge_prompt_source"] = (
                "inline" if cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_TEXT.strip() else "file"
            )
            metadata["knowledge_error"] = None
            metadata["knowledge_response"] = knowledge_result["raw_response"]
            artifact_paths["meta_path"].write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            return {
                "target": resolved_target,
                "status": "Done",
                "knowledge_path": str(knowledge_path),
                "artifact_dir": str(knowledge_path.parent),
                "title": title,
                "error": None,
                "knowledge_exists": True,
                "provider": knowledge_result["provider"],
                "model": knowledge_result["model"],
            }
        except Exception as exc:
            return {
                "target": resolved_target,
                "status": "Failed",
                "knowledge_path": None,
                "artifact_dir": None,
                "title": Path(resolved_target).stem,
                "error": str(exc),
                "knowledge_exists": False,
                "provider": None,
                "model": None,
            }

    return _run_parallel_map(
        list(targets),
        jobs=_resolve_job_count(jobs, len(targets), cap=4),
        worker=run_single,
        on_result=on_result,
    )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Downloader by Qianzhu 的 CLI 入口。"""


@main.command("config")
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON。")
@click.option(
    "--download-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="设置默认下载目录；Docker 模式下必须位于已挂载的下载根目录内。",
)
@click.option("--openrouter-base-url", help="设置 OpenRouter 或兼容转写服务的 Base URL。")
@click.option("--openrouter-api-key", help="设置转写服务 API Key。可传空字符串清空。")
@click.option("--openrouter-site-url", help="设置 OpenRouter HTTP-Referer。")
@click.option("--openrouter-app-name", help="设置 OpenRouter X-Title。")
@click.option("--transcription-model", help="设置默认音频转写模型。")
@click.option("--openrouter-article-model", help="设置 OpenRouter 解析稿兜底模型。")
@click.option(
    "--enable-cleanup/--disable-cleanup",
    "enable_cleanup",
    default=None,
    help="是否启用 AI 清洗。",
)
@click.option("--cleanup-base-url", help="设置清洗服务 Base URL。")
@click.option("--cleanup-api-key", help="设置清洗服务 API Key。可传空字符串清空。")
@click.option("--cleanup-model", help="设置默认清洗模型。")
@click.option("--cleanup-prompt-text", help="设置内联清洗提示词；空字符串表示回退到提示词文件。")
@click.option(
    "--enable-article/--disable-article",
    "enable_article",
    default=None,
    help="是否启用解析稿生成。",
)
@click.option("--article-base-url", help="设置解析稿服务 Base URL。")
@click.option("--article-api-key", help="设置解析稿服务 API Key。可传空字符串清空。")
@click.option("--article-model", help="设置默认解析稿模型。")
@click.option("--article-prompt-text", help="设置内联解析稿提示词；空字符串表示回退到提示词文件。")
@click.option(
    "--enable-knowledge/--disable-knowledge",
    "enable_knowledge",
    default=None,
    help="是否启用知识库整理。",
)
@click.option("--knowledge-base-url", help="设置知识库整理服务 Base URL。")
@click.option("--knowledge-api-key", help="设置知识库整理服务 API Key。可传空字符串清空。")
@click.option("--knowledge-model", help="设置默认知识库整理模型。")
@click.option("--knowledge-prompt-text", help="设置内联知识库提示词；空字符串表示回退到提示词文件。")
def config_command(
    as_json: bool,
    download_dir: Path | None,
    openrouter_base_url: str | None,
    openrouter_api_key: str | None,
    openrouter_site_url: str | None,
    openrouter_app_name: str | None,
    transcription_model: str | None,
    openrouter_article_model: str | None,
    enable_cleanup: bool | None,
    cleanup_base_url: str | None,
    cleanup_api_key: str | None,
    cleanup_model: str | None,
    cleanup_prompt_text: str | None,
    enable_article: bool | None,
    article_base_url: str | None,
    article_api_key: str | None,
    article_model: str | None,
    article_prompt_text: str | None,
    enable_knowledge: bool | None,
    knowledge_base_url: str | None,
    knowledge_api_key: str | None,
    knowledge_model: str | None,
    knowledge_prompt_text: str | None,
) -> None:
    """查看或保存默认运行配置。"""
    updates: dict[str, object] = {}

    if download_dir is not None:
        updates["download_dir"] = str(download_dir)
    if openrouter_base_url is not None:
        updates["openrouter_base_url"] = openrouter_base_url
    if openrouter_api_key is not None:
        updates["openrouter_api_key"] = openrouter_api_key
    if openrouter_site_url is not None:
        updates["openrouter_site_url"] = openrouter_site_url
    if openrouter_app_name is not None:
        updates["openrouter_app_name"] = openrouter_app_name
    if transcription_model is not None:
        updates["openrouter_transcription_model"] = transcription_model
    if openrouter_article_model is not None:
        updates["openrouter_article_model"] = openrouter_article_model
    if enable_cleanup is not None:
        updates["enable_ai_cleanup"] = enable_cleanup
    if cleanup_base_url is not None:
        updates["ai_cleanup_base_url"] = cleanup_base_url
    if cleanup_api_key is not None:
        updates["ai_cleanup_api_key"] = cleanup_api_key
    if cleanup_model is not None:
        updates["ai_cleanup_model"] = cleanup_model
    if cleanup_prompt_text is not None:
        updates["ai_cleanup_prompt_text"] = cleanup_prompt_text
    if enable_article is not None:
        updates["enable_article_draft"] = enable_article
    if article_base_url is not None:
        updates["article_draft_base_url"] = article_base_url
    if article_api_key is not None:
        updates["article_draft_api_key"] = article_api_key
    if article_model is not None:
        updates["article_draft_model"] = article_model
    if article_prompt_text is not None:
        updates["article_draft_prompt_text"] = article_prompt_text
    if enable_knowledge is not None:
        updates["enable_knowledge_draft"] = enable_knowledge
    if knowledge_base_url is not None:
        updates["knowledge_draft_base_url"] = knowledge_base_url
    if knowledge_api_key is not None:
        updates["knowledge_draft_api_key"] = knowledge_api_key
    if knowledge_model is not None:
        updates["knowledge_draft_model"] = knowledge_model
    if knowledge_prompt_text is not None:
        updates["knowledge_draft_prompt_text"] = knowledge_prompt_text

    try:
        if updates:
            web_app.persist_runtime_settings(updates, partial=True)
        report = web_app.masked_runtime_settings()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json or updates:
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for key, value in report.items():
        click.echo(f"{key}: {value}")


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
    "--douyin-cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 Douyin cookies.txt 路径。",
)
@click.option(
    "--douyin-cookies-from-browser",
    help="直接从浏览器读取 Douyin 登录态，例如 chrome、edge:Profile 1。",
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
@click.option("--jobs", type=int, default=0, show_default=True, help="批量并发任务数，0 表示自动。")
@click.option("--resume/--no-resume", default=True, help="优先复用 checkpoint 与已有逐字稿产物，减少重复处理。")
@click.option("--language", help="覆盖本次转写语言提示，例如 zh、en、auto。")
@click.option("--bitrate", help="覆盖本次转写前音频压缩码率，例如 48k。")
@click.option("--transcription-model", help="覆盖本次 OpenRouter 音频模型。")
@click.option("--cleanup-model", help="覆盖本次清洗模型。")
@click.option("--article-model", help="覆盖本次解析稿模型。")
@click.option("--cleanup/--no-cleanup", default=True, help="是否启用 AI 清洗。")
@click.option("--article/--no-article", default=True, help="是否生成解析稿。")
@click.option("--knowledge/--no-knowledge", default=False, help="逐字稿完成后继续生成知识库整理稿。")
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
@click.option("--knowledge-model", help="覆盖本次知识库整理模型。")
@click.option(
    "--knowledge-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖知识库整理提示词文件。",
)
@click.option(
    "--overwrite-knowledge/--skip-existing-knowledge",
    default=False,
    help="是否覆盖已有的知识库文件。",
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
    douyin_cookies_path: Path | None,
    douyin_cookies_from_browser: str | None,
    output_dir: Path | None,
    output_mode: str,
    as_json: bool,
    result_file: Path | None,
    jobs: int,
    resume: bool,
    language: str | None,
    bitrate: str | None,
    transcription_model: str | None,
    cleanup_model: str | None,
    article_model: str | None,
    cleanup: bool,
    article: bool,
    knowledge: bool,
    cleanup_prompt_file: Path | None,
    article_prompt_file: Path | None,
    knowledge_model: str | None,
    knowledge_prompt_file: Path | None,
    overwrite_knowledge: bool,
    keep_transcription_input: bool | None,
) -> None:
    """从 URL 直接生成逐字稿，可选继续整理知识库。"""
    resolved_urls = _collect_url_inputs(
        values=urls,
        input_file=input_file,
        stdin_enabled=stdin_enabled,
    )
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    previous_results = _load_result_file_records(result_file) if resume else []
    required_stage = "knowledge" if knowledge else "transcript"
    pending_urls, resumed_results, reusable_checkpoint_results = _split_pending_inputs(
        resolved_urls,
        previous_results=previous_results,
        required_stage=required_stage,
    )
    checkpoint_writer = _CheckpointWriter(
        result_file,
        previous_results=previous_results if resume else None,
    )
    with _runtime_overrides(
        output_dir=output_dir,
        cookies_path=cookies_path,
        cookies_from_browser=cookies_from_browser if cookies_from_browser else _UNSET,
        youtube_cookies_path=youtube_cookies_path,
        youtube_cookies_from_browser=youtube_cookies_from_browser if youtube_cookies_from_browser else _UNSET,
        bilibili_cookies_path=bilibili_cookies_path,
        bilibili_cookies_from_browser=bilibili_cookies_from_browser if bilibili_cookies_from_browser else _UNSET,
        douyin_cookies_path=douyin_cookies_path,
        douyin_cookies_from_browser=douyin_cookies_from_browser if douyin_cookies_from_browser else _UNSET,
        transcription_model=transcription_model if transcription_model else _UNSET,
        cleanup_model=cleanup_model if cleanup_model else _UNSET,
        article_model=article_model if article_model else _UNSET,
        language=language if language else _UNSET,
        bitrate=bitrate if bitrate else _UNSET,
        cleanup_enabled=cleanup,
        article_enabled=article,
        knowledge_model=knowledge_model if knowledge_model else _UNSET,
        keep_transcription_input=keep_transcription_input
        if keep_transcription_input is not None
        else _UNSET,
        cleanup_prompt_file=cleanup_prompt_file if cleanup_prompt_file else _UNSET,
        article_prompt_file=article_prompt_file if article_prompt_file else _UNSET,
        knowledge_prompt_file=knowledge_prompt_file if knowledge_prompt_file else _UNSET,
    ):
        reused_existing_results: list[dict] = []
        reusable_existing_results: list[dict] = []
        if resume:
            pending_urls, reused_existing_results, reusable_existing_results = _split_pending_urls_with_existing_artifacts(
                pending_urls,
                required_stage=required_stage,
            )
        checkpoint_writer.flush(resumed_results + reused_existing_results)
        fresh_results = (
            _run_download_jobs(
                urls=pending_urls,
                preset=DEFAULT_TRANSCRIPT_PRESET,
                use_cookies=(
                    cookies
                    or cookies_path is not None
                    or bool(cookies_from_browser)
                    or youtube_cookies_path is not None
                    or bool(youtube_cookies_from_browser)
                    or bilibili_cookies_path is not None
                    or bool(bilibili_cookies_from_browser)
                    or douyin_cookies_path is not None
                    or bool(douyin_cookies_from_browser)
                ),
                generate_transcript=True,
                jobs=jobs,
                on_result=checkpoint_writer.record,
            )
            if pending_urls
            else []
        )
        results = _order_results_by_inputs(
            resolved_urls,
            resumed_results
            + reused_existing_results
            + reusable_checkpoint_results
            + reusable_existing_results
            + fresh_results,
        )
        if knowledge:
            results = _attach_knowledge_results(results, overwrite=overwrite_knowledge, jobs=jobs)
    checkpoint_writer.flush(results)
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
    "--douyin-cookies-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="显式指定 Douyin cookies.txt 路径。",
)
@click.option(
    "--douyin-cookies-from-browser",
    help="直接从浏览器读取 Douyin 登录态，例如 chrome、edge:Profile 1。",
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
@click.option("--jobs", type=int, default=0, show_default=True, help="批量并发任务数，0 表示自动。")
@click.option("--resume/--no-resume", default=True, help="优先复用 checkpoint 与已有逐字稿产物，减少重复处理。")
@click.option("--language", help="覆盖本次转写语言提示，例如 zh、en、auto。")
@click.option("--bitrate", help="覆盖本次转写前音频压缩码率，例如 48k。")
@click.option("--transcription-model", help="覆盖本次 OpenRouter 音频模型。")
@click.option("--cleanup-model", help="覆盖本次清洗模型。")
@click.option("--article-model", help="覆盖本次解析稿模型。")
@click.option("--cleanup/--no-cleanup", default=True, help="是否启用 AI 清洗。")
@click.option("--article/--no-article", default=True, help="是否生成解析稿。")
@click.option("--knowledge/--no-knowledge", default=False, help="逐字稿完成后继续生成知识库整理稿。")
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
@click.option("--knowledge-model", help="覆盖本次知识库整理模型。")
@click.option(
    "--knowledge-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖知识库整理提示词文件。",
)
@click.option(
    "--overwrite-knowledge/--skip-existing-knowledge",
    default=False,
    help="是否覆盖已有的知识库文件。",
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
    douyin_cookies_path: Path | None,
    douyin_cookies_from_browser: str | None,
    output_dir: Path | None,
    output_mode: str,
    as_json: bool,
    result_file: Path | None,
    jobs: int,
    resume: bool,
    language: str | None,
    bitrate: str | None,
    transcription_model: str | None,
    cleanup_model: str | None,
    article_model: str | None,
    cleanup: bool,
    article: bool,
    knowledge: bool,
    cleanup_prompt_file: Path | None,
    article_prompt_file: Path | None,
    knowledge_model: str | None,
    knowledge_prompt_file: Path | None,
    overwrite_knowledge: bool,
    keep_transcription_input: bool | None,
) -> None:
    """下载 URL，可选附带逐字稿生成。"""
    if transcript and preset != DEFAULT_AUDIO_PRESET:
        raise click.ClickException("开启逐字稿时，请将 --preset 设为 Best Audio (MP3)。")
    if knowledge and not transcript:
        raise click.ClickException("开启知识库整理时，请同时传 --transcript。")

    resolved_urls = _collect_url_inputs(
        values=urls,
        input_file=input_file,
        stdin_enabled=stdin_enabled,
    )
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    previous_results = _load_result_file_records(result_file) if resume else []
    required_stage = "knowledge" if knowledge else "transcript" if transcript else "download"
    pending_urls, resumed_results, reusable_checkpoint_results = _split_pending_inputs(
        resolved_urls,
        previous_results=previous_results,
        required_stage=required_stage,
    )
    checkpoint_writer = _CheckpointWriter(
        result_file,
        previous_results=previous_results if resume else None,
    )
    with _runtime_overrides(
        output_dir=output_dir,
        cookies_path=cookies_path,
        cookies_from_browser=cookies_from_browser if cookies_from_browser else _UNSET,
        youtube_cookies_path=youtube_cookies_path,
        youtube_cookies_from_browser=youtube_cookies_from_browser if youtube_cookies_from_browser else _UNSET,
        bilibili_cookies_path=bilibili_cookies_path,
        bilibili_cookies_from_browser=bilibili_cookies_from_browser if bilibili_cookies_from_browser else _UNSET,
        douyin_cookies_path=douyin_cookies_path,
        douyin_cookies_from_browser=douyin_cookies_from_browser if douyin_cookies_from_browser else _UNSET,
        transcription_model=transcription_model if transcription_model else _UNSET,
        cleanup_model=cleanup_model if cleanup_model else _UNSET,
        article_model=article_model if article_model else _UNSET,
        language=language if language else _UNSET,
        bitrate=bitrate if bitrate else _UNSET,
        cleanup_enabled=cleanup,
        article_enabled=article,
        knowledge_model=knowledge_model if knowledge_model else _UNSET,
        keep_transcription_input=keep_transcription_input
        if keep_transcription_input is not None
        else _UNSET,
        cleanup_prompt_file=cleanup_prompt_file if cleanup_prompt_file else _UNSET,
        article_prompt_file=article_prompt_file if article_prompt_file else _UNSET,
        knowledge_prompt_file=knowledge_prompt_file if knowledge_prompt_file else _UNSET,
    ):
        reused_existing_results: list[dict] = []
        reusable_existing_results: list[dict] = []
        if resume and transcript:
            pending_urls, reused_existing_results, reusable_existing_results = _split_pending_urls_with_existing_artifacts(
                pending_urls,
                required_stage=required_stage,
            )
        checkpoint_writer.flush(resumed_results + reused_existing_results)
        fresh_results = (
            _run_download_jobs(
                urls=pending_urls,
                preset=preset,
                use_cookies=(
                    cookies
                    or cookies_path is not None
                    or bool(cookies_from_browser)
                    or youtube_cookies_path is not None
                    or bool(youtube_cookies_from_browser)
                    or bilibili_cookies_path is not None
                    or bool(bilibili_cookies_from_browser)
                    or douyin_cookies_path is not None
                    or bool(douyin_cookies_from_browser)
                ),
                generate_transcript=transcript,
                jobs=jobs,
                on_result=checkpoint_writer.record,
            )
            if pending_urls
            else []
        )
        results = _order_results_by_inputs(
            resolved_urls,
            resumed_results
            + reused_existing_results
            + reusable_checkpoint_results
            + reusable_existing_results
            + fresh_results,
        )
        if knowledge:
            results = _attach_knowledge_results(results, overwrite=overwrite_knowledge, jobs=jobs)
    checkpoint_writer.flush(results)
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
@click.option("--jobs", type=int, default=0, show_default=True, help="批量并发任务数，0 表示自动。")
@click.option("--resume/--no-resume", default=True, help="优先复用 checkpoint 与已有逐字稿产物，减少重复处理。")
@click.option("--language", help="覆盖本次转写语言提示，例如 zh、en、auto。")
@click.option("--bitrate", help="覆盖本次转写前音频压缩码率，例如 48k。")
@click.option("--transcription-model", help="覆盖本次 OpenRouter 音频模型。")
@click.option("--cleanup-model", help="覆盖本次清洗模型。")
@click.option("--article-model", help="覆盖本次解析稿模型。")
@click.option("--cleanup/--no-cleanup", default=True, help="是否启用 AI 清洗。")
@click.option("--article/--no-article", default=True, help="是否生成解析稿。")
@click.option("--knowledge/--no-knowledge", default=False, help="逐字稿完成后继续生成知识库整理稿。")
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
@click.option("--knowledge-model", help="覆盖本次知识库整理模型。")
@click.option(
    "--knowledge-prompt-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖知识库整理提示词文件。",
)
@click.option(
    "--overwrite-knowledge/--skip-existing-knowledge",
    default=False,
    help="是否覆盖已有的知识库文件。",
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
    jobs: int,
    resume: bool,
    language: str | None,
    bitrate: str | None,
    transcription_model: str | None,
    cleanup_model: str | None,
    article_model: str | None,
    cleanup: bool,
    article: bool,
    knowledge: bool,
    cleanup_prompt_file: Path | None,
    article_prompt_file: Path | None,
    knowledge_model: str | None,
    knowledge_prompt_file: Path | None,
    overwrite_knowledge: bool,
    keep_transcription_input: bool | None,
) -> None:
    """把本地音频文件转成逐字稿，可选继续整理知识库。"""
    raw_paths = _collect_line_inputs(
        values=tuple(str(path) for path in audio_files),
        input_file=input_file,
        stdin_enabled=stdin_enabled,
        label="音频路径",
    )
    resolved_input_paths = tuple(str(Path(path).expanduser().resolve()) for path in raw_paths)
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    previous_results = _load_result_file_records(result_file) if resume else []
    required_stage = "knowledge" if knowledge else "transcript"
    pending_paths, resumed_results, reusable_checkpoint_results = _split_pending_inputs(
        resolved_input_paths,
        previous_results=previous_results,
        required_stage=required_stage,
    )
    checkpoint_writer = _CheckpointWriter(
        result_file,
        previous_results=previous_results if resume else None,
    )
    with _runtime_overrides(
        transcription_model=transcription_model if transcription_model else _UNSET,
        cleanup_model=cleanup_model if cleanup_model else _UNSET,
        article_model=article_model if article_model else _UNSET,
        language=language if language else _UNSET,
        bitrate=bitrate if bitrate else _UNSET,
        cleanup_enabled=cleanup,
        article_enabled=article,
        knowledge_model=knowledge_model if knowledge_model else _UNSET,
        keep_transcription_input=keep_transcription_input
        if keep_transcription_input is not None
        else _UNSET,
        cleanup_prompt_file=cleanup_prompt_file if cleanup_prompt_file else _UNSET,
        article_prompt_file=article_prompt_file if article_prompt_file else _UNSET,
        knowledge_prompt_file=knowledge_prompt_file if knowledge_prompt_file else _UNSET,
    ):
        reused_existing_results: list[dict] = []
        reusable_existing_results: list[dict] = []
        if resume:
            pending_paths, reused_existing_results, reusable_existing_results = _split_pending_audio_paths_with_existing_artifacts(
                pending_paths,
                required_stage=required_stage,
            )
        checkpoint_writer.flush(resumed_results + reused_existing_results)
        fresh_results = (
            _run_local_audio_jobs(
                audio_files=tuple(Path(path) for path in pending_paths),
                source_url=source_url,
                title=title,
                copy_to_dir=copy_to_dir.expanduser().resolve() if copy_to_dir else None,
                jobs=jobs,
                on_result=checkpoint_writer.record,
            )
            if pending_paths
            else []
        )
        results = _order_results_by_inputs(
            resolved_input_paths,
            resumed_results
            + reused_existing_results
            + reusable_checkpoint_results
            + reusable_existing_results
            + fresh_results,
        )
        if knowledge:
            results = _attach_knowledge_results(results, overwrite=overwrite_knowledge, jobs=jobs)
    checkpoint_writer.flush(results)
    _emit_results(results, final_output_mode)
    _exit_for_failures(results)


@main.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON。")
def doctor_command(as_json: bool) -> None:
    """检查依赖和云端接口配置状态。"""
    subtitle_auth_configured = web_app.platform_auth_configured("Unknown")
    settings = web_app.current_runtime_settings()
    report = {
        "settings_path": settings["settings_path"],
        "settings_dir": settings["settings_dir"],
        "download_dir": web_app.DOWNLOAD_DIR,
        "download_root_dir": settings["download_root_dir"],
        "download_root_locked": settings["download_root_locked"],
        "ffmpeg_bin": web_app.FFMPEG_BIN,
        "ffmpeg_found": shutil.which(web_app.FFMPEG_BIN) is not None,
        "yt_dlp_found": shutil.which("yt-dlp") is not None,
        "transcript_route_strategy": "subtitle_first_then_audio_fallback",
        "subtitle_auth_configured": subtitle_auth_configured,
        "youtube_auth_configured": web_app.platform_auth_configured("YouTube"),
        "bilibili_auth_configured": web_app.platform_auth_configured("Bilibili"),
        "douyin_auth_configured": web_app.platform_auth_configured("Douyin"),
        "ytdlp_remote_components": list(web_app.YTDLP_REMOTE_COMPONENTS),
        "transcription_enabled": web_app.ENABLE_TRANSCRIPTION,
        "openrouter_base_url": web_app.OPENROUTER_BASE_URL,
        "transcription_model": web_app.OPENROUTER_TRANSCRIPTION_MODEL,
        "openrouter_key_configured": bool(web_app.transcribe_audio.__globals__.get("OPENROUTER_API_KEY")),
        "cleanup_enabled": web_app.AI_CLEANUP_ENABLED,
        "cleanup_base_url": web_app.AI_CLEANUP_BASE_URL,
        "cleanup_model": web_app.AI_CLEANUP_MODEL,
        "cleanup_key_configured": bool(web_app.cleanup_transcript.__globals__.get("AI_CLEANUP_API_KEY")),
        "cleanup_prompt_file": web_app.AI_CLEANUP_PROMPT_FILE,
        "cleanup_prompt_source": settings["ai_cleanup_prompt_source"],
        "cleanup_prompt_exists": Path(web_app.AI_CLEANUP_PROMPT_FILE).exists(),
        "article_enabled": web_app.ENABLE_ARTICLE_DRAFT,
        "article_base_url": web_app.ARTICLE_DRAFT_BASE_URL,
        "article_model": web_app.ARTICLE_DRAFT_MODEL,
        "article_key_configured": bool(
            web_app.generate_ai_article_draft.__globals__.get("ARTICLE_DRAFT_API_KEY")
        ),
        "article_prompt_file": web_app.ARTICLE_DRAFT_PROMPT_FILE,
        "article_prompt_source": settings["article_draft_prompt_source"],
        "article_prompt_exists": Path(web_app.ARTICLE_DRAFT_PROMPT_FILE).exists(),
        "knowledge_enabled": cleanup_backend.ENABLE_KNOWLEDGE_DRAFT,
        "knowledge_base_url": cleanup_backend.KNOWLEDGE_DRAFT_BASE_URL,
        "knowledge_model": cleanup_backend.KNOWLEDGE_DRAFT_MODEL,
        "knowledge_key_configured": bool(cleanup_backend.KNOWLEDGE_DRAFT_API_KEY),
        "knowledge_prompt_file": cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_FILE,
        "knowledge_prompt_source": settings["knowledge_draft_prompt_source"],
        "knowledge_prompt_exists": Path(cleanup_backend.KNOWLEDGE_DRAFT_PROMPT_FILE).exists(),
        "cookies_path": web_app.COOKIES_PATH or None,
        "cookies_exists": bool(web_app.COOKIES_PATH) and Path(web_app.COOKIES_PATH).exists(),
        "cookies_from_browser": web_app.COOKIES_FROM_BROWSER or None,
        "youtube_cookies_path": web_app.YOUTUBE_COOKIES_PATH or None,
        "youtube_cookies_exists": bool(web_app.YOUTUBE_COOKIES_PATH) and Path(web_app.YOUTUBE_COOKIES_PATH).exists(),
        "youtube_cookies_from_browser": web_app.YOUTUBE_COOKIES_FROM_BROWSER or None,
        "bilibili_cookies_path": web_app.BILIBILI_COOKIES_PATH or None,
        "bilibili_cookies_exists": bool(web_app.BILIBILI_COOKIES_PATH) and Path(web_app.BILIBILI_COOKIES_PATH).exists(),
        "bilibili_cookies_from_browser": web_app.BILIBILI_COOKIES_FROM_BROWSER or None,
        "douyin_cookies_path": web_app.DOUYIN_COOKIES_PATH or None,
        "douyin_cookies_exists": bool(web_app.DOUYIN_COOKIES_PATH) and Path(web_app.DOUYIN_COOKIES_PATH).exists(),
        "douyin_cookies_from_browser": web_app.DOUYIN_COOKIES_FROM_BROWSER or None,
        "transcript_capture_ready": (
            shutil.which("yt-dlp") is not None
            and web_app.ENABLE_TRANSCRIPTION
            and bool(web_app.transcribe_audio.__globals__.get("OPENROUTER_API_KEY"))
        ),
        "knowledge_capture_ready": (
            shutil.which("yt-dlp") is not None
            and web_app.ENABLE_TRANSCRIPTION
            and bool(web_app.transcribe_audio.__globals__.get("OPENROUTER_API_KEY"))
            and cleanup_backend.ENABLE_KNOWLEDGE_DRAFT
            and bool(cleanup_backend.KNOWLEDGE_DRAFT_API_KEY)
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


@main.command("knowledge")
@click.argument("targets", nargs=-1, type=click.Path(path_type=Path))
@click.option(
    "--input-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="从文本文件读取逐字稿产物路径，每行一个。",
)
@click.option("--stdin", "stdin_enabled", is_flag=True, help="从标准输入读取逐字稿产物路径，每行一个。")
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
@click.option("--jobs", type=int, default=0, show_default=True, help="批量并发任务数，0 表示自动。")
@click.option("--resume/--no-resume", default=True, help="优先复用 checkpoint，避免重复整理知识库。")
@click.option(
    "--model",
    "knowledge_model",
    help="覆盖本次知识库整理模型。",
)
@click.option(
    "--prompt-file",
    "knowledge_prompt_file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="覆盖知识库整理提示词文件。",
)
@click.option(
    "--overwrite/--skip-existing",
    default=False,
    help="是否覆盖已有的知识库文件。",
)
def knowledge_command(
    targets: tuple[Path, ...],
    input_file: Path | None,
    stdin_enabled: bool,
    output_mode: str,
    as_json: bool,
    result_file: Path | None,
    jobs: int,
    resume: bool,
    knowledge_model: str | None,
    knowledge_prompt_file: Path | None,
    overwrite: bool,
) -> None:
    """基于现有逐字稿 sidecar 生成知识库整理稿。"""
    resolved_targets = _collect_line_inputs(
        values=tuple(str(target) for target in targets),
        input_file=input_file,
        stdin_enabled=stdin_enabled,
        label="逐字稿路径",
    )
    final_output_mode = _normalize_output_mode(output_mode, as_json)
    resolved_target_paths = tuple(str(Path(target).expanduser().resolve()) for target in resolved_targets)
    previous_results = _load_result_file_records(result_file) if resume else []
    pending_targets, resumed_results, reusable_results = _split_pending_inputs(
        resolved_target_paths,
        previous_results=previous_results,
        required_stage="knowledge",
    )
    checkpoint_writer = _CheckpointWriter(
        result_file,
        previous_results=previous_results if resume else None,
    )
    with _runtime_overrides(
        knowledge_model=knowledge_model if knowledge_model else _UNSET,
        knowledge_prompt_file=knowledge_prompt_file if knowledge_prompt_file else _UNSET,
    ):
        checkpoint_writer.flush(resumed_results)
        fresh_results = (
            _run_knowledge_jobs(
                targets=tuple(Path(target) for target in pending_targets),
                overwrite=overwrite,
                jobs=jobs,
                on_result=checkpoint_writer.record,
            )
            if pending_targets
            else []
        )
        results = _order_results_by_inputs(resolved_target_paths, resumed_results + reusable_results + fresh_results)

    checkpoint_writer.flush(results)
    _emit_results(results, final_output_mode)
    _exit_for_failures(results)


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
