import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from webui import app as web_app
from webui import cli as web_cli


class SubtitleParsingTests(unittest.TestCase):
    def test_parse_cookies_from_browser_spec_supports_profile(self) -> None:
        parsed = web_app.parse_cookies_from_browser_spec("chrome:Profile 1")
        self.assertEqual(parsed, ("chrome", "Profile 1", None, None))

    def test_detect_platform_supports_douyin_web_and_share_urls(self) -> None:
        self.assertEqual(
            web_app.detect_platform("https://www.douyin.com/video/1234567890"),
            "Douyin",
        )
        self.assertEqual(
            web_app.detect_platform("https://v.douyin.com/iABCDE12/"),
            "Douyin",
        )

    def test_collect_url_inputs_accepts_bilibili_share_text(self) -> None:
        share_text = (
            "【SpaceX冲击史上最大IPO，马斯克想要的真的只是一家“公司”吗？】 "
            "https://www.bilibili.com/video/BV14PXKBbEhy/?share_source=copy_web&vd_source=test"
        )

        urls = web_app.collect_url_inputs(share_text)

        self.assertEqual(
            urls,
            ["https://www.bilibili.com/video/BV14PXKBbEhy/?share_source=copy_web&vd_source=test"],
        )

    def test_collect_url_inputs_extracts_multiple_urls_from_share_blocks(self) -> None:
        shared_text = """
        【视频一】
        https://www.bilibili.com/video/BV1111111111/?share_source=copy_web
        打开看看

        Watch this:
        https://www.youtube.com/watch?v=abcdefghijk
        """.strip()

        urls = web_app.collect_url_inputs(shared_text)

        self.assertEqual(
            urls,
            [
                "https://www.bilibili.com/video/BV1111111111/?share_source=copy_web",
                "https://www.youtube.com/watch?v=abcdefghijk",
            ],
        )

    def test_collect_url_inputs_accepts_douyin_share_text(self) -> None:
        share_text = (
            "4.87 复制打开抖音，看看【千逐的作品】这是一个测试 https://v.douyin.com/iABCDE12/ "
            "打开抖音搜索，直接观看视频！"
        )

        urls = web_app.collect_url_inputs(share_text)

        self.assertEqual(urls, ["https://v.douyin.com/iABCDE12/"])

    def test_resolve_cookie_options_prefers_youtube_specific_browser_auth(self) -> None:
        with mock.patch.object(web_app, "YOUTUBE_COOKIES_FROM_BROWSER", "chrome"), mock.patch.object(
            web_app, "YOUTUBE_COOKIES_PATH", ""
        ), mock.patch.object(web_app, "COOKIES_FROM_BROWSER", ""), mock.patch.object(
            web_app, "COOKIES_PATH", "/tmp/bilibili.cookies.txt"
        ):
            options = web_app.resolve_cookie_options("https://www.youtube.com/watch?v=abcdefghijk")

        self.assertEqual(options["cookiesfrombrowser"], ("chrome", None, None, None))
        self.assertNotIn("cookiefile", options)

    def test_resolve_cookie_options_prefers_douyin_specific_browser_auth(self) -> None:
        with mock.patch.object(web_app, "DOUYIN_COOKIES_FROM_BROWSER", "chrome"), mock.patch.object(
            web_app, "DOUYIN_COOKIES_PATH", ""
        ), mock.patch.object(web_app, "COOKIES_FROM_BROWSER", ""), mock.patch.object(
            web_app, "COOKIES_PATH", "/tmp/global.cookies.txt"
        ):
            options = web_app.resolve_cookie_options("https://www.douyin.com/video/1234567890")

        self.assertEqual(options["cookiesfrombrowser"], ("chrome", None, None, None))
        self.assertNotIn("cookiefile", options)

    def test_humanize_ydlp_error_for_youtube_auth_failure(self) -> None:
        job = web_app.Job(
            job_id="job-youtube-error",
            url="https://www.youtube.com/watch?v=abcdefghijk",
            preset=web_app.AUDIO_PRESET_NAME,
            use_cookies=True,
            generate_transcript=False,
        )

        with mock.patch.object(web_app, "YOUTUBE_COOKIES_FROM_BROWSER", ""), mock.patch.object(
            web_app, "YOUTUBE_COOKIES_PATH", ""
        ), mock.patch.object(web_app, "COOKIES_FROM_BROWSER", ""), mock.patch.object(web_app, "COOKIES_PATH", ""):
            message = web_app.humanize_ydlp_error(job, "ERROR: [youtube] abc: Sign in to confirm you're not a bot")

        self.assertIn("YOUTUBE_COOKIES_FROM_BROWSER", message)

    def test_humanize_ydlp_error_handles_curly_apostrophe_and_format_issue(self) -> None:
        job = web_app.Job(
            job_id="job-youtube-format",
            url="https://www.youtube.com/watch?v=abcdefghijk",
            preset=web_app.AUDIO_PRESET_NAME,
            use_cookies=True,
            generate_transcript=False,
        )

        not_bot = web_app.humanize_ydlp_error(job, "Sign in to confirm you’re not a bot")
        format_issue = web_app.humanize_ydlp_error(job, "Requested format is not available")

        self.assertIn("YOUTUBE_COOKIES_FROM_BROWSER", not_bot)
        self.assertIn("YTDLP_REMOTE_COMPONENTS", format_issue)

    def test_load_subtitle_text_parses_youtube_json3_and_dedupes_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle_path = Path(temp_dir) / "captions.json3"
            subtitle_path.write_text(
                """
                {
                  "events": [
                    {"segs": [{"utf8": "Hello world"}]},
                    {"segs": [{"utf8": "Hello world"}]},
                    {"segs": [{"utf8": "Second line"}]}
                  ]
                }
                """.strip(),
                encoding="utf-8",
            )

            text = web_app.load_subtitle_text(subtitle_path)

        self.assertEqual(text, "Hello world\nSecond line")

    def test_load_subtitle_text_parses_vtt_and_strips_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle_path = Path(temp_dir) / "captions.vtt"
            subtitle_path.write_text(
                """
                WEBVTT

                00:00:00.000 --> 00:00:01.000
                Hello world

                00:00:01.000 --> 00:00:02.000
                Hello world

                00:00:02.000 --> 00:00:03.000
                Second line
                """.strip(),
                encoding="utf-8",
            )

            text = web_app.load_subtitle_text(subtitle_path)

        self.assertEqual(text, "Hello world\nSecond line")

    def test_prepare_audio_for_transcription_uses_temp_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.mp3"
            audio_path.write_text("audio", encoding="utf-8")

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).write_text("prepared", encoding="utf-8")
                return mock.Mock()

            with mock.patch.object(web_app.subprocess, "run", side_effect=fake_run):
                prepared_path = web_app.prepare_audio_for_transcription(audio_path)

        self.assertNotEqual(prepared_path.parent, audio_path.parent)
        self.assertTrue(prepared_path.name.endswith(".transcribe.mp3"))
        prepared_path.unlink(missing_ok=True)


class TranscriptRoutingTests(unittest.TestCase):
    def test_runtime_overrides_patch_platform_cookie_paths(self) -> None:
        original_youtube = web_app.YOUTUBE_COOKIES_PATH
        original_bilibili = web_app.BILIBILI_COOKIES_PATH
        original_douyin = web_app.DOUYIN_COOKIES_PATH

        with tempfile.TemporaryDirectory() as temp_dir:
            youtube_path = Path(temp_dir) / "youtube.cookies.txt"
            bilibili_path = Path(temp_dir) / "bilibili.cookies.txt"
            douyin_path = Path(temp_dir) / "douyin.cookies.txt"
            youtube_path.write_text("youtube", encoding="utf-8")
            bilibili_path.write_text("bilibili", encoding="utf-8")
            douyin_path.write_text("douyin", encoding="utf-8")

            with web_cli._runtime_overrides(
                youtube_cookies_path=youtube_path,
                bilibili_cookies_path=bilibili_path,
                douyin_cookies_path=douyin_path,
            ):
                self.assertEqual(web_app.YOUTUBE_COOKIES_PATH, str(youtube_path.resolve()))
                self.assertEqual(web_app.BILIBILI_COOKIES_PATH, str(bilibili_path.resolve()))
                self.assertEqual(web_app.DOUYIN_COOKIES_PATH, str(douyin_path.resolve()))

        self.assertEqual(web_app.YOUTUBE_COOKIES_PATH, original_youtube)
        self.assertEqual(web_app.BILIBILI_COOKIES_PATH, original_bilibili)
        self.assertEqual(web_app.DOUYIN_COOKIES_PATH, original_douyin)

    def test_artifact_paths_from_directory_resolves_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "Sample [abc]" / "Sample [abc].mp3"
            base_path.parent.mkdir(parents=True)
            artifact_paths = web_app.build_artifact_paths(base_path)
            artifact_paths["meta_path"].write_text(
                '{"artifact_base_path": "' + str(base_path).replace("\\", "\\\\") + '"}\n',
                encoding="utf-8",
            )

            resolved = web_cli._artifact_paths_from_target(base_path.parent)

        self.assertEqual(resolved["markdown_path"].resolve(), artifact_paths["markdown_path"].resolve())

    def test_run_knowledge_jobs_writes_knowledge_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "Sample [abc]" / "Sample [abc].mp3"
            base_path.parent.mkdir(parents=True)
            artifact_paths = web_app.build_artifact_paths(base_path)
            artifact_paths["raw_path"].write_text("raw transcript\n", encoding="utf-8")
            artifact_paths["markdown_path"].write_text("# Sample\n\n## 清洗稿\n\nclean transcript\n", encoding="utf-8")
            artifact_paths["meta_path"].write_text(
                (
                    '{'
                    f'"artifact_base_path": "{str(base_path).replace("\\", "\\\\")}", '
                    '"title": "Sample", '
                    '"source_url": "https://example.com/video", '
                    '"platform": "YouTube"'
                    '}\n'
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                web_cli.cleanup_backend,
                "generate_knowledge_draft",
                return_value={
                    "provider": "zhipu-coding",
                    "model": "GLM-4.5",
                    "text": "# Sample\n\n## 一句话总结\n\nsummary",
                    "raw_response": {"id": "mock"},
                },
            ):
                results = web_cli._run_knowledge_jobs(targets=(base_path,), overwrite=True)

            knowledge_text = artifact_paths["knowledge_path"].read_text(encoding="utf-8")
            metadata = json.loads(artifact_paths["meta_path"].read_text(encoding="utf-8"))

        self.assertEqual(results[0]["status"], "Done")
        self.assertIn("一句话总结", knowledge_text)
        self.assertEqual(metadata["knowledge_provider"], "zhipu-coding")

    def test_run_knowledge_jobs_reports_failures_per_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "Sample [abc]" / "Sample [abc].mp3"
            base_path.parent.mkdir(parents=True)
            artifact_paths = web_app.build_artifact_paths(base_path)
            artifact_paths["markdown_path"].write_text("# Sample\n\ncontent\n", encoding="utf-8")
            artifact_paths["meta_path"].write_text(
                (
                    '{'
                    f'"artifact_base_path": "{str(base_path).replace("\\", "\\\\")}", '
                    '"title": "Sample", '
                    '"source_url": "https://example.com/video"'
                    '}\n'
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                web_cli.cleanup_backend,
                "generate_knowledge_draft",
                side_effect=RuntimeError("knowledge backend offline"),
            ):
                results = web_cli._run_knowledge_jobs(targets=(base_path,), overwrite=True)

        self.assertEqual(results[0]["status"], "Failed")
        self.assertIn("knowledge backend offline", results[0]["error"])

    def test_capture_command_can_chain_knowledge_generation(self) -> None:
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            transcript_path = Path(temp_dir) / "Sample - 逐字稿.md"
            transcript_path.write_text("# Sample\n", encoding="utf-8")
            knowledge_path = Path(temp_dir) / "Sample - 知识库.md"

            with mock.patch.object(
                web_cli,
                "_run_download_jobs",
                return_value=[
                    {
                        "title": "Sample",
                        "status": "Done · transcript ready",
                        "error": None,
                        "artifact_dir": str(transcript_path.parent),
                        "download_path": str(Path(temp_dir) / "Sample.mp3"),
                        "transcript_path": str(transcript_path),
                    }
                ],
            ), mock.patch.object(
                web_cli,
                "_run_knowledge_jobs",
                return_value=[
                    {
                        "target": str(transcript_path.resolve()),
                        "status": "Done",
                        "knowledge_path": str(knowledge_path),
                        "artifact_dir": str(transcript_path.parent),
                        "title": "Sample",
                        "error": None,
                        "knowledge_exists": True,
                        "provider": "zhipu-coding",
                        "model": "GLM-4.5",
                    }
                ],
            ):
                result = runner.invoke(
                    web_cli.main,
                    ["capture", "https://example.com/video", "--knowledge", "--json"],
                )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["results"][0]["status"], "Done · knowledge ready")
        self.assertTrue(payload["results"][0]["knowledge_path"].endswith("Sample - 知识库.md"))

    def test_download_command_requires_transcript_for_knowledge(self) -> None:
        runner = CliRunner()

        result = runner.invoke(
            web_cli.main,
            ["download", "https://example.com/video", "--knowledge"],
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--transcript", result.output)

    def test_doctor_command_includes_knowledge_fields(self) -> None:
        runner = CliRunner()

        result = runner.invoke(web_cli.main, ["doctor", "--json"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        payload = json.loads(result.output)
        self.assertIn("knowledge_enabled", payload)
        self.assertIn("knowledge_capture_ready", payload)
        self.assertIn("douyin_auth_configured", payload)

    def test_start_accepts_share_text_payload(self) -> None:
        share_text = (
            "【SpaceX冲击史上最大IPO，马斯克想要的真的只是一家“公司”吗？】 "
            "https://www.bilibili.com/video/BV14PXKBbEhy/?share_source=copy_web&vd_source=test"
        )

        with web_app.jobs_lock:
            web_app.jobs.clear()

        with web_app.app.test_client() as client, mock.patch.object(web_app.executor, "submit", return_value=None):
            response = client.post(
                "/api/start",
                json={
                    "url": share_text,
                    "preset": web_app.TRANSCRIPT_PRESET_NAME,
                    "use_cookies": True,
                    "generate_transcript": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        with web_app.jobs_lock:
            created_jobs = list(web_app.jobs.values())
            self.assertEqual(len(created_jobs), 1)
            self.assertEqual(
                created_jobs[0].url,
                "https://www.bilibili.com/video/BV14PXKBbEhy/?share_source=copy_web&vd_source=test",
            )
            web_app.jobs.clear()

    def test_download_media_uses_download_info_when_preview_fails(self) -> None:
        job = web_app.Job(
            job_id="job-download",
            url="https://example.com/video",
            preset=web_app.VIDEO_PRESET_NAME,
            use_cookies=False,
            generate_transcript=False,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir) / "Sample [abc]"
            media_dir.mkdir(parents=True)
            media_path = media_dir / "Sample [abc].mp4"
            media_path.write_text("video", encoding="utf-8")

            class FakeYDL:
                def __init__(self, options):
                    self.options = options

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def extract_info(self, url, download=False):
                    if not download:
                        raise RuntimeError("preview failed")
                    return {"id": "abc", "title": "Sample", "ext": "mp4"}

                def prepare_filename(self, info):
                    return str(media_path)

            with mock.patch.object(web_app.yt_dlp, "YoutubeDL", FakeYDL):
                resolved = web_app.download_media(job, web_app.VIDEO_PRESET_NAME)

        self.assertEqual(resolved, media_path)
        self.assertEqual(job.download_path, str(media_path))
        self.assertEqual(job.title, "Sample")

    def test_download_media_uses_douyin_provider_when_cookies_enabled(self) -> None:
        job = web_app.Job(
            job_id="job-douyin-download",
            url="https://www.douyin.com/video/1234567890",
            preset=web_app.VIDEO_PRESET_NAME,
            use_cookies=True,
            generate_transcript=False,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir) / "Sample [1234567890]"
            media_dir.mkdir(parents=True)
            media_path = media_dir / "Sample [1234567890].mp4"
            media_path.write_text("video", encoding="utf-8")

            with mock.patch.object(
                web_app,
                "resolve_cookie_options",
                return_value={"cookiefile": "/tmp/douyin.cookies.txt"},
            ), mock.patch.object(
                web_app,
                "download_douyin_media",
                return_value={
                    "title": "Sample",
                    "download_path": media_path,
                    "artifact_dir": media_dir,
                },
            ) as download_douyin_media, mock.patch.object(web_app.yt_dlp, "YoutubeDL") as youtube_dl:
                resolved = web_app.download_media(job, web_app.VIDEO_PRESET_NAME)

        self.assertEqual(resolved, media_path)
        self.assertEqual(job.download_path, str(media_path))
        self.assertEqual(job.title, "Sample")
        download_douyin_media.assert_called_once()
        youtube_dl.assert_not_called()

    def test_run_transcript_job_prefers_direct_subtitles(self) -> None:
        job = web_app.Job(
            job_id="job-1",
            url="https://example.com/video",
            preset=web_app.TRANSCRIPT_PRESET_NAME,
            use_cookies=False,
            generate_transcript=True,
        )
        subtitle_result = {
            "artifact_base_path": Path("/tmp/example/example"),
            "raw_text": "subtitle text",
            "provider": "yt-dlp subtitles",
            "model": "manual subtitles · zh · json3",
            "response": {"subtitle_language": "zh"},
            "meta": {"transcript_route": "direct_subtitles"},
        }

        with mock.patch.object(web_app, "try_extract_direct_subtitles", return_value=subtitle_result), mock.patch.object(
            web_app, "run_text_pipeline"
        ) as run_text_pipeline, mock.patch.object(web_app, "download_media") as download_media, mock.patch.object(
            web_app, "run_transcription_pipeline"
        ) as run_transcription_pipeline:
            web_app.run_transcript_job(job)

        run_text_pipeline.assert_called_once()
        download_media.assert_not_called()
        run_transcription_pipeline.assert_not_called()

    def test_run_transcript_job_falls_back_to_audio_transcription(self) -> None:
        job = web_app.Job(
            job_id="job-2",
            url="https://example.com/video",
            preset=web_app.TRANSCRIPT_PRESET_NAME,
            use_cookies=False,
            generate_transcript=True,
        )
        audio_path = Path("/tmp/example/audio.mp3")

        with mock.patch.object(web_app, "try_extract_direct_subtitles", return_value=None), mock.patch.object(
            web_app, "download_media", return_value=audio_path
        ) as download_media, mock.patch.object(web_app, "run_transcription_pipeline") as run_transcription_pipeline:
            web_app.run_transcript_job(job)

        download_media.assert_called_once_with(job, web_app.AUDIO_PRESET_NAME)
        run_transcription_pipeline.assert_called_once()
        _, kwargs = run_transcription_pipeline.call_args
        self.assertEqual(kwargs["extra_meta"]["transcript_route"], "subtitle_probe_fallback_to_audio")

    def test_run_transcript_job_skips_subtitle_probe_for_douyin(self) -> None:
        job = web_app.Job(
            job_id="job-douyin-transcript",
            url="https://www.douyin.com/video/1234567890",
            preset=web_app.TRANSCRIPT_PRESET_NAME,
            use_cookies=True,
            generate_transcript=True,
        )
        audio_path = Path("/tmp/example/douyin.mp3")

        with mock.patch.object(
            web_app,
            "resolve_cookie_options",
            return_value={"cookiefile": "/tmp/douyin.cookies.txt"},
        ), mock.patch.object(web_app, "try_extract_direct_subtitles") as try_extract_direct_subtitles, mock.patch.object(
            web_app,
            "download_media",
            return_value=audio_path,
        ) as download_media, mock.patch.object(web_app, "run_transcription_pipeline") as run_transcription_pipeline:
            web_app.run_transcript_job(job)

        try_extract_direct_subtitles.assert_not_called()
        download_media.assert_called_once_with(job, web_app.AUDIO_PRESET_NAME)
        _, kwargs = run_transcription_pipeline.call_args
        self.assertEqual(kwargs["extra_meta"]["transcript_route"], "douyin_audio_transcription")

    def test_tasks_endpoint_includes_source_url_and_backend_error(self) -> None:
        job = web_app.Job(
            job_id="job-task-fields",
            url="https://www.douyin.com/video/1234567890",
            preset=web_app.VIDEO_PRESET_NAME,
            use_cookies=True,
            generate_transcript=False,
        )
        job.status = "Failed"
        job.done = True
        job.error = "friendly error"
        job.backend_error = "raw backend error"

        with web_app.jobs_lock:
            web_app.jobs.clear()
            web_app.jobs[job.job_id] = job

        try:
            with web_app.app.test_client() as client:
                response = client.get("/api/tasks")
        finally:
            with web_app.jobs_lock:
                web_app.jobs.clear()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["tasks"][0]["source_url"], job.url)
        self.assertEqual(payload["tasks"][0]["backend_error"], job.backend_error)


if __name__ == "__main__":
    unittest.main()
