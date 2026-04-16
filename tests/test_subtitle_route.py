import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from webui import app as web_app
from webui import cli as web_cli
from webui import openai_compatible_cleanup as cleanup_backend
from webui import openrouter_backends as openrouter_backend
from webui import transcript_pipeline


class SubtitleParsingTests(unittest.TestCase):
    def test_web_app_uses_repo_static_and_template_directories(self) -> None:
        app_dir = Path(web_app.__file__).resolve().parent

        self.assertEqual(Path(web_app.app.static_folder), app_dir / "static")
        self.assertEqual(Path(web_app.app.template_folder), app_dir / "templates")

    def test_index_inlines_frontend_assets(self) -> None:
        with web_app.app.test_client() as client:
            response = client.get("/")

        html = response.get_data(as_text=True)
        asset_bundle = web_app.load_inline_frontend_assets()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<style>", html)
        self.assertIn(":root {", html)
        self.assertIn(asset_bundle["inline_css"][:64], html)
        self.assertIn(asset_bundle["inline_js"][:64], html)
        self.assertNotIn('/static/style.css?v=', html)
        self.assertNotIn('/static/app.js?v=', html)

    def test_render_markdown_outputs_clean_transcript_only(self) -> None:
        rendered = transcript_pipeline.render_markdown(
            title="Sample",
            clean_text="第一段。\n\n第二段。",
            raw_text="原始逐字稿",
            article_text="# 解析稿",
        )

        self.assertEqual(rendered, "第一段。\n\n第二段。\n")

    def test_build_article_payload_includes_source_author(self) -> None:
        payload = cleanup_backend.build_article_payload(
            text="逐字稿正文",
            title="标题",
            source_url="https://example.com/video",
            platform="Bilibili",
            source_author="酸老师",
        )

        user_message = payload["messages"][1]["content"]
        self.assertIn("- 作者：酸老师", user_message)
        self.assertIn("【逐字稿全文】", user_message)

    def test_openrouter_headers_fall_back_to_ascii_title(self) -> None:
        with mock.patch.object(openrouter_backend, "OPENROUTER_API_KEY", "sk-test"), mock.patch.object(
            openrouter_backend, "OPENROUTER_APP_NAME", "幕库 Muku"
        ), mock.patch.object(openrouter_backend, "OPENROUTER_SITE_URL", ""):
            headers = openrouter_backend._headers()

        self.assertEqual(headers["X-Title"], "Muku")

    def test_parse_cookies_from_browser_spec_supports_profile(self) -> None:
        parsed = web_app.parse_cookies_from_browser_spec("chrome:Profile 1")
        self.assertEqual(parsed, ("chrome", "Profile 1", None, None))

    def test_platform_auth_state_marks_cookie_file_source_as_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cookies_path = Path(temp_dir) / "youtube.cookies.txt"
            cookies_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

            with mock.patch.object(web_app, "YOUTUBE_COOKIES_PATH", str(cookies_path)), mock.patch.object(
                web_app, "YOUTUBE_COOKIES_FROM_BROWSER", ""
            ), mock.patch.object(web_app, "COOKIES_PATH", ""), mock.patch.object(
                web_app, "COOKIES_FROM_BROWSER", ""
            ):
                state = web_app.platform_auth_state("YouTube")

        self.assertTrue(state["configured"])
        self.assertTrue(state["verified"])
        self.assertEqual(state["status"], "verified")
        self.assertEqual(state["source_kind"], "file")

    def test_platform_auth_state_marks_browser_source_as_configured_only_in_container(self) -> None:
        with mock.patch.object(web_app, "YOUTUBE_COOKIES_PATH", ""), mock.patch.object(
            web_app, "YOUTUBE_COOKIES_FROM_BROWSER", "chrome"
        ), mock.patch.object(web_app, "COOKIES_PATH", ""), mock.patch.object(
            web_app, "COOKIES_FROM_BROWSER", ""
        ), mock.patch.object(web_app, "running_in_container", return_value=True):
            state = web_app.platform_auth_state("YouTube")

        self.assertTrue(state["configured"])
        self.assertFalse(state["verified"])
        self.assertEqual(state["status"], "configured_only")
        self.assertTrue(state["docker_risky"])

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

    def test_subtitle_language_rank_prioritizes_bilibili_ai_zh(self) -> None:
        self.assertIn("ai-zh", web_app.SUBTITLE_LANGUAGES)
        self.assertLess(
            web_app._subtitle_language_rank("ai-zh"),
            web_app._subtitle_language_rank("zh-Hans"),
        )

    def test_extract_source_author_prefers_uploader(self) -> None:
        self.assertEqual(
            web_app.extract_source_author(
                {"uploader": "酸老师", "channel": "频道名", "creator": "创作者"}
            ),
            "酸老师",
        )

    def test_collect_subtitle_candidates_falls_back_to_downloaded_ai_subtitles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            nested = temp_path / "Sample [BV-test]"
            nested.mkdir()
            (nested / "sample.ai-zh.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n你好\n", encoding="utf-8")
            (nested / "sample.danmaku.xml").write_text("<i></i>", encoding="utf-8")

            candidates = web_app._collect_subtitle_candidates({}, temp_dir=temp_path)

        self.assertEqual([candidate["lang"] for candidate in candidates], ["ai-zh"])
        self.assertEqual(candidates[0]["ext"], "srt")
        self.assertEqual(candidates[0]["source"], "automatic captions")

    def test_start_rejects_obvious_non_url_input(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()

        with web_app.app.test_client() as client, mock.patch.object(web_app.executor, "submit") as submit:
            response = client.post(
                "/api/start",
                json={
                    "url": "not-a-url",
                    "preset": web_app.AUDIO_PRESET_NAME,
                    "use_cookies": False,
                    "generate_transcript": False,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("有效的视频链接", response.get_json()["error"])
        submit.assert_not_called()
        with web_app.jobs_lock:
            self.assertEqual(web_app.jobs, {})

    def test_start_rejects_cloud_metadata_and_loopback_variants(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()

        blocked_urls = (
            "http://169.254.169.254/latest/meta-data/",
            "http://127.1/",
            "http://2130706433/",
            "http://0x7f000001/",
            "http://0177.0.0.1/",
            "http://metadata/computeMetadata/v1/",
            "http://instance-data.ec2.internal/",
        )
        with web_app.app.test_client() as client, mock.patch.object(web_app.executor, "submit") as submit:
            for blocked_url in blocked_urls:
                response = client.post(
                    "/api/start",
                    json={
                        "url": blocked_url,
                        "preset": web_app.AUDIO_PRESET_NAME,
                        "use_cookies": False,
                        "generate_transcript": False,
                    },
                )
                self.assertEqual(response.status_code, 400, msg=blocked_url)
                self.assertIn("云元数据", response.get_json()["error"])

        submit.assert_not_called()
        with web_app.jobs_lock:
            self.assertEqual(web_app.jobs, {})

    def test_start_rejects_too_many_urls(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()

        urls = "\n".join(
            f"https://www.youtube.com/watch?v=abcdefghij{index}"
            for index in range(3)
        )
        with web_app.app.test_client() as client, mock.patch.object(
            web_app,
            "MAX_START_URLS",
            2,
        ), mock.patch.object(web_app.executor, "submit") as submit:
            response = client.post(
                "/api/start",
                json={
                    "url": urls,
                    "preset": web_app.AUDIO_PRESET_NAME,
                    "use_cookies": False,
                    "generate_transcript": False,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("最多提交 2 个链接", response.get_json()["error"])
        submit.assert_not_called()
        with web_app.jobs_lock:
            self.assertEqual(web_app.jobs, {})

    def test_start_accepts_bare_supported_url(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()

        with web_app.app.test_client() as client, mock.patch.object(web_app.executor, "submit", return_value=None):
            response = client.post(
                "/api/start",
                json={
                    "url": "youtube.com/watch?v=abcdefghijk",
                    "preset": web_app.AUDIO_PRESET_NAME,
                    "use_cookies": False,
                    "generate_transcript": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["job_ids"]), 1)
        with web_app.jobs_lock:
            created_jobs = list(web_app.jobs.values())
            self.assertEqual(created_jobs[0].job_id, payload["job_ids"][0])
            self.assertEqual(created_jobs[0].url, "https://youtube.com/watch?v=abcdefghijk")
            web_app.jobs.clear()

    def test_start_rejects_generate_knowledge_without_transcript(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()

        with web_app.app.test_client() as client, mock.patch.object(web_app.executor, "submit") as submit:
            response = client.post(
                "/api/start",
                json={
                    "url": "https://www.youtube.com/watch?v=abcdefghijk",
                    "preset": web_app.AUDIO_PRESET_NAME,
                    "use_cookies": False,
                    "generate_transcript": False,
                    "generate_knowledge": True,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Markdown 逐字稿模式", response.get_json()["error"])
        submit.assert_not_called()
        with web_app.jobs_lock:
            self.assertEqual(web_app.jobs, {})

    def test_start_accepts_generate_knowledge_in_transcript_mode(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()

        with web_app.app.test_client() as client, mock.patch.object(
            web_app.executor, "submit", return_value=None
        ), mock.patch.object(web_app, "ENABLE_KNOWLEDGE_DRAFT", True), mock.patch.object(
            cleanup_backend, "KNOWLEDGE_DRAFT_API_KEY", "sk-knowledge"
        ):
            response = client.post(
                "/api/start",
                json={
                    "url": "https://www.youtube.com/watch?v=abcdefghijk",
                    "preset": web_app.TRANSCRIPT_PRESET_NAME,
                    "use_cookies": False,
                    "generate_transcript": True,
                    "generate_knowledge": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        with web_app.jobs_lock:
            created_jobs = list(web_app.jobs.values())
            self.assertTrue(created_jobs[0].generate_knowledge)
            web_app.jobs.clear()

    def test_run_text_pipeline_generates_knowledge_sidecar_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_base_path = Path(temp_dir) / "Sample [demo]" / "Sample [demo]"
            job = web_app.Job(
                job_id="job-knowledge",
                url="https://www.youtube.com/watch?v=abcdefghijk",
                preset=web_app.TRANSCRIPT_PRESET_NAME,
                use_cookies=False,
                generate_transcript=True,
                generate_knowledge=True,
            )
            job.title = "Sample"

            with mock.patch.object(web_app, "AI_CLEANUP_ENABLED", False), mock.patch.object(
                web_app, "ENABLE_ARTICLE_DRAFT", False
            ), mock.patch.object(
                web_app,
                "generate_knowledge_draft",
                return_value={
                    "provider": "knowledge-test",
                    "model": "knowledge-model",
                    "text": "# 知识库稿",
                    "raw_response": {"id": "knowledge-response"},
                },
            ):
                web_app.run_text_pipeline(
                    job,
                    artifact_base_path=artifact_base_path,
                    raw_text="原始逐字稿",
                    transcript_provider="yt-dlp subtitles",
                    transcript_model="manual subtitles · zh · vtt",
                    transcript_response={"subtitle_language": "zh"},
                    extra_meta={"transcript_route": "direct_subtitles"},
                )

            artifact_paths = web_app.build_artifact_paths(artifact_base_path)
            metadata = json.loads(artifact_paths["meta_path"].read_text(encoding="utf-8"))

            self.assertTrue(artifact_paths["knowledge_path"].exists())
            self.assertEqual(
                artifact_paths["knowledge_path"].read_text(encoding="utf-8").strip(),
                "# 知识库稿",
            )
            self.assertEqual(metadata["knowledge_model"], "knowledge-model")
            self.assertEqual(job.knowledge_path, str(artifact_paths["knowledge_path"]))
            self.assertIsNone(job.knowledge_error)

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

    def test_transcribe_audio_rejects_truncated_openrouter_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.mp3"
            audio_path.write_text("audio", encoding="utf-8")

            with mock.patch.object(
                openrouter_backend,
                "_post_chat",
                return_value={
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": "partial transcript"},
                        }
                    ]
                },
            ):
                with self.assertRaisesRegex(RuntimeError, "truncated before completion"):
                    openrouter_backend.transcribe_audio(
                        audio_path,
                        title="Sample",
                        source_url="https://example.com/video",
                        language_hint="zh",
                    )

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

    def test_split_audio_for_transcription_creates_chunk_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.transcribe.mp3"
            audio_path.write_text("audio", encoding="utf-8")

            def fake_run(command, check, capture_output, text):
                pattern = Path(command[-1])
                pattern.parent.mkdir(parents=True, exist_ok=True)
                (pattern.parent / "chunk-000.mp3").write_text("chunk-1", encoding="utf-8")
                (pattern.parent / "chunk-001.mp3").write_text("chunk-2", encoding="utf-8")
                return mock.Mock()

            with mock.patch.object(web_app.subprocess, "run", side_effect=fake_run):
                chunk_paths = web_app.split_audio_for_transcription(audio_path)

        self.assertEqual(len(chunk_paths), 2)
        self.assertTrue(chunk_paths[0].name.endswith("chunk-000.mp3"))
        web_app.cleanup_transcription_chunks(chunk_paths)

    def test_merge_transcript_chunks_dedupes_boundary_line(self) -> None:
        merged = web_app.merge_transcript_chunks(
            [
                "第一段\n重复边界",
                "重复边界\n第二段",
            ]
        )

        self.assertEqual(merged, "第一段\n重复边界\n\n第二段")

    def test_run_transcription_pipeline_retries_with_chunked_transcription_after_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.mp3"
            prepared_audio = Path(temp_dir) / "sample.transcribe.mp3"
            chunk_one = Path(temp_dir) / "chunk-000.mp3"
            chunk_two = Path(temp_dir) / "chunk-001.mp3"
            for path in (audio_path, prepared_audio, chunk_one, chunk_two):
                path.write_text("audio", encoding="utf-8")

            job = web_app.Job(
                job_id="job-chunked-transcription",
                url="https://example.com/video",
                preset=web_app.TRANSCRIPT_PRESET_NAME,
                use_cookies=False,
                generate_transcript=True,
            )
            job.title = "Sample"

            truncated_error = RuntimeError(
                "OpenRouter transcription response was truncated before completion. Try a shorter clip."
            )

            with mock.patch.object(web_app, "prepare_audio_for_transcription", return_value=prepared_audio), mock.patch.object(
                web_app, "should_chunk_audio_for_transcription", return_value=False
            ), mock.patch.object(
                web_app,
                "split_audio_for_transcription",
                return_value=[chunk_one, chunk_two],
            ), mock.patch.object(
                web_app,
                "transcribe_audio",
                side_effect=[
                    truncated_error,
                    {
                        "provider": "openrouter",
                        "model": "openai/gpt-audio-mini",
                        "text": "第一段",
                        "raw_response": {"id": "chunk-1"},
                    },
                    {
                        "provider": "openrouter",
                        "model": "openai/gpt-audio-mini",
                        "text": "第二段",
                        "raw_response": {"id": "chunk-2"},
                    },
                ],
            ) as transcribe_audio, mock.patch.object(
                web_app, "run_text_pipeline"
            ) as run_text_pipeline, mock.patch.object(
                web_app, "cleanup_transcription_chunks"
            ) as cleanup_chunks:
                web_app.run_transcription_pipeline(job, audio_path)

        self.assertEqual(transcribe_audio.call_count, 3)
        run_text_pipeline.assert_called_once()
        kwargs = run_text_pipeline.call_args.kwargs
        self.assertEqual(kwargs["raw_text"], "第一段\n\n第二段")
        self.assertEqual(kwargs["extra_meta"]["transcript_route"], "audio_transcription_chunked")
        self.assertTrue(kwargs["extra_meta"]["transcription_chunked"])
        self.assertEqual(kwargs["extra_meta"]["transcription_chunk_count"], 2)
        cleanup_chunks.assert_called_once()

    def test_build_artifact_base_path_truncates_long_titles(self) -> None:
        long_title = (
            "B站强推！这才是2026年最全最细的AI产品经理教程，从零到精通，字节大佬整理的内部版，"
            "通俗易懂，学完即就业！！！ 大模型｜LLM p07【基础篇】07. 如何从0开始做一款软硬协同型AI产品？"
        )

        artifact_base = web_app.build_artifact_base_path(
            {"title": long_title, "id": "BV1KzDYBYED6_p7"},
            base_dir="/tmp/muku-tests",
        )

        component = artifact_base.name
        self.assertLess(len(component.encode("utf-8")), 255)
        self.assertIn("[BV1KzDYBYED6_p7]", component)
        self.assertEqual(artifact_base.parent.name, component)

    def test_output_template_truncates_long_title_components(self) -> None:
        info = {
            "title": (
                "B站强推！这才是2026年最全最细的AI产品经理教程，从零到精通，字节大佬整理的内部版，"
                "通俗易懂，学完即就业！！！ 大模型｜LLM p07【基础篇】07. 如何从0开始做一款软硬协同型AI产品？"
            ),
            "id": "BV1KzDYBYED6_p7",
            "ext": "mp4",
        }
        ydl = web_app.yt_dlp.YoutubeDL({"quiet": True})

        rendered = ydl.evaluate_outtmpl(web_app.output_template("/tmp/muku-tests"), info)

        relative = Path(rendered).relative_to("/tmp/muku-tests")
        for component in relative.parts:
            self.assertLess(len(component.encode("utf-8")), 255)
        self.assertIn("[BV1KzDYBYED6_p7]", relative.parts[0])

    def test_resolve_download_dir_respects_root_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir) / "downloads"
            root_dir.mkdir()

            with mock.patch.object(web_app, "DOWNLOAD_ROOT_DIR", str(root_dir)), mock.patch.object(
                web_app, "DOWNLOAD_DIR", str(root_dir)
            ):
                resolved = web_app.resolve_download_dir("creator-series")

                self.assertEqual(resolved, (root_dir / "creator-series").resolve())
                with self.assertRaises(ValueError):
                    web_app.resolve_download_dir(str(root_dir.parent / "outside"))


class TranscriptRoutingTests(unittest.TestCase):
    def test_split_pending_inputs_skips_only_successful_checkpoint_records(self) -> None:
        previous_results = [
            {
                "source_url": "https://example.com/a",
                "status": "Done",
                "error": None,
            },
            {
                "source_url": "https://example.com/b",
                "status": "Failed",
                "error": "network error",
            },
        ]

        pending, resumed, reusable = web_cli._split_pending_inputs(
            ("https://example.com/a", "https://example.com/b", "https://example.com/c"),
            previous_results=previous_results,
        )

        self.assertEqual(pending, ("https://example.com/b", "https://example.com/c"))
        self.assertEqual(resumed[0]["source_url"], "https://example.com/a")
        self.assertTrue(resumed[0]["resumed"])
        self.assertEqual(reusable, [])

    def test_split_pending_inputs_reuses_transcript_for_knowledge_stage(self) -> None:
        previous_results = [
            {
                "source_url": "https://example.com/a",
                "status": "Done · transcript ready",
                "error": None,
                "transcript_path": "/tmp/a - 逐字稿.md",
                "artifact_dir": "/tmp/a",
            }
        ]

        pending, resumed, reusable = web_cli._split_pending_inputs(
            ("https://example.com/a",),
            previous_results=previous_results,
            required_stage="knowledge",
        )

        self.assertEqual(pending, ())
        self.assertEqual(resumed, [])
        self.assertEqual(reusable[0]["source_url"], "https://example.com/a")
        self.assertEqual(reusable[0]["transcript_path"], "/tmp/a - 逐字稿.md")

    def test_order_results_by_inputs_preserves_original_order(self) -> None:
        ordered = web_cli._order_results_by_inputs(
            ("b", "a"),
            [
                {"source_url": "a", "status": "Done"},
                {"source_url": "b", "status": "Done"},
            ],
        )

        self.assertEqual([record["source_url"] for record in ordered], ["b", "a"])

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

    def test_artifacts_paths_output_prefers_existing_markdown_over_missing_knowledge(self) -> None:
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "Sample [abc]" / "Sample [abc].mp3"
            base_path.parent.mkdir(parents=True)
            base_path.write_text("audio", encoding="utf-8")
            artifact_paths = web_app.build_artifact_paths(base_path)
            artifact_paths["markdown_path"].write_text("# Sample\n", encoding="utf-8")

            result = runner.invoke(
                web_cli.main,
                ["artifacts", str(artifact_paths["markdown_path"]), "--output", "paths"],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual(result.output.strip(), str(artifact_paths["markdown_path"].resolve()))
        self.assertFalse(artifact_paths["knowledge_path"].exists())

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

    def test_capture_command_resumes_from_result_file(self) -> None:
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            result_file = Path(temp_dir) / "capture.json"
            result_file.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "source_url": "https://example.com/a",
                                "status": "Done",
                                "error": None,
                                "artifact_dir": "/tmp/a",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(
                web_cli,
                "_run_download_jobs",
                return_value=[
                    {
                        "source_url": "https://example.com/b",
                        "status": "Done · transcript ready",
                        "error": None,
                        "artifact_dir": "/tmp/b",
                    }
                ],
            ) as run_download_jobs:
                result = runner.invoke(
                    web_cli.main,
                    [
                        "capture",
                        "https://example.com/a",
                        "https://example.com/b",
                        "--json",
                        "--result-file",
                        str(result_file),
                    ],
                )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        run_download_jobs.assert_called_once()
        self.assertEqual(run_download_jobs.call_args.kwargs["urls"], ("https://example.com/b",))
        payload = json.loads(result.output)
        self.assertEqual(payload["results"][0]["status"], "Skipped · resumed from checkpoint")
        self.assertEqual(payload["results"][1]["source_url"], "https://example.com/b")

    def test_capture_command_reuses_existing_artifacts_before_redownload(self) -> None:
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "Sample [abc]" / "Sample [abc].mp3"
            base_path.parent.mkdir(parents=True)
            artifact_paths = web_app.build_artifact_paths(base_path)
            artifact_paths["raw_path"].write_text("raw transcript\n", encoding="utf-8")
            artifact_paths["markdown_path"].write_text("# Sample\n\n## 清洗稿\n\nclean transcript\n", encoding="utf-8")
            artifact_paths["meta_path"].write_text(
                json.dumps(
                    {
                        "artifact_base_path": str(base_path),
                        "title": "Sample",
                        "source_url": "https://example.com/video",
                        "provider": "openrouter",
                        "transcript_route": "audio_transcription",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(web_cli, "_run_download_jobs") as run_download_jobs:
                result = runner.invoke(
                    web_cli.main,
                    [
                        "capture",
                        "https://example.com/video",
                        "--output-dir",
                        temp_dir,
                        "--json",
                    ],
                )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        run_download_jobs.assert_not_called()
        payload = json.loads(result.output)
        self.assertEqual(payload["results"][0]["status"], "Skipped · existing transcript")
        self.assertEqual(
            Path(payload["results"][0]["transcript_path"]).resolve(),
            artifact_paths["markdown_path"].resolve(),
        )

    def test_capture_command_records_output_dir_override_in_json_result(self) -> None:
        runner = CliRunner()

        def fake_run_job(job: web_app.Job) -> web_app.Job:
            job.done = True
            job.status = "Failed"
            job.error = "mock failure"
            return job

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(web_cli.web_app, "run_job", side_effect=fake_run_job):
                result = runner.invoke(
                    web_cli.main,
                    [
                        "capture",
                        "https://example.com/video",
                        "--output-dir",
                        temp_dir,
                        "--json",
                        "--no-resume",
                    ],
                )

        self.assertNotEqual(result.exit_code, 0)
        payload = json.loads(result.output)
        self.assertEqual(payload["results"][0]["output_dir"], str(Path(temp_dir).resolve()))

    def test_capture_command_resumes_knowledge_from_checkpoint_without_redownload(self) -> None:
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            transcript_path = Path(temp_dir) / "Sample - 逐字稿.md"
            transcript_path.write_text("# Sample\n", encoding="utf-8")
            result_file = Path(temp_dir) / "capture.json"
            result_file.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "source_url": "https://example.com/video",
                                "status": "Done · transcript ready",
                                "error": None,
                                "artifact_dir": temp_dir,
                                "transcript_path": str(transcript_path),
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(web_cli, "_run_download_jobs") as run_download_jobs, mock.patch.object(
                web_cli,
                "_run_knowledge_jobs",
                return_value=[
                    {
                        "target": str(transcript_path.resolve()),
                        "status": "Done",
                        "knowledge_path": str(Path(temp_dir) / "Sample - 知识库.md"),
                        "artifact_dir": temp_dir,
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
                    [
                        "capture",
                        "https://example.com/video",
                        "--knowledge",
                        "--json",
                        "--result-file",
                        str(result_file),
                    ],
                )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        run_download_jobs.assert_not_called()
        payload = json.loads(result.output)
        self.assertEqual(payload["results"][0]["status"], "Done · knowledge ready")

    def test_checkpoint_writer_records_partial_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result_file = Path(temp_dir) / "capture.json"
            writer = web_cli._CheckpointWriter(result_file)

            writer.record(
                {
                    "source_url": "https://example.com/video",
                    "status": "Done · transcript ready",
                    "error": None,
                    "transcript_path": "/tmp/video - 逐字稿.md",
                }
            )

            payload = json.loads(result_file.read_text(encoding="utf-8"))

        self.assertEqual(payload["results"][0]["source_url"], "https://example.com/video")

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
        self.assertIn("settings_path", payload)
        self.assertIn("download_root_locked", payload)
        self.assertIn("knowledge_enabled", payload)
        self.assertIn("knowledge_capture_ready", payload)
        self.assertIn("douyin_auth_configured", payload)
        self.assertIn("youtube_auth_verified", payload)
        self.assertIn("runtime_environment", payload)

    def test_doctor_command_default_output_is_human_readable(self) -> None:
        runner = CliRunner()

        result = runner.invoke(web_cli.main, ["doctor"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Muku doctor", result.output)
        self.assertIn("Readiness", result.output)
        self.assertIn("Dependencies", result.output)
        self.assertIn("verified:", result.output)
        self.assertIn("Next steps", result.output)

    def test_config_command_persists_runtime_settings(self) -> None:
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            output_dir = Path(temp_dir) / "downloads"

            with mock.patch.dict(
                web_cli.os.environ,
                {"VIDEO_DOWNLOADE_CONFIG_DIR": str(config_dir)},
                clear=False,
            ):
                result = runner.invoke(
                    web_cli.main,
                    [
                        "config",
                        "--json",
                        "--download-dir",
                        str(output_dir),
                        "--transcription-model",
                        "openai/mock-transcribe",
                        "--disable-knowledge",
                    ],
                )

                payload = json.loads(result.output)
                saved = json.loads((config_dir / "settings.json").read_text(encoding="utf-8"))
                web_app.apply_runtime_settings({})

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual(payload["download_dir"], str(output_dir.resolve()))
        self.assertEqual(payload["openrouter_transcription_model"], "openai/mock-transcribe")
        self.assertFalse(payload["enable_knowledge_draft"])
        self.assertEqual(saved["download_dir"], str(output_dir.resolve()))

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

    def test_start_accepts_download_dir_override(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()

        with tempfile.TemporaryDirectory() as temp_dir:
            with web_app.app.test_client() as client, mock.patch.object(
                web_app.executor, "submit", return_value=None
            ):
                response = client.post(
                    "/api/start",
                    json={
                        "url": "https://www.youtube.com/watch?v=abcdefghijk",
                        "preset": web_app.AUDIO_PRESET_NAME,
                        "use_cookies": False,
                        "generate_transcript": False,
                        "download_dir": temp_dir,
                    },
                )

        self.assertEqual(response.status_code, 200)
        with web_app.jobs_lock:
            created_jobs = list(web_app.jobs.values())
            self.assertEqual(created_jobs[0].output_dir, str(Path(temp_dir).resolve()))

    def test_update_settings_api_persists_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            download_dir = Path(temp_dir) / "downloads"

            with mock.patch.dict(
                web_app.os.environ,
                {"VIDEO_DOWNLOADE_CONFIG_DIR": str(config_dir)},
                clear=False,
            ):
                with web_app.app.test_client() as client:
                    response = client.post(
                        "/api/settings",
                        json={
                            "download_dir": str(download_dir),
                            "openrouter_transcription_model": "openai/mock-transcribe",
                            "enable_ai_cleanup": True,
                            "ai_cleanup_prompt_text": "清洗提示词",
                            "enable_article_draft": True,
                            "article_draft_prompt_text": "解析提示词",
                            "enable_knowledge_draft": True,
                            "knowledge_draft_prompt_text": "知识库提示词",
                        },
                    )

                payload = response.get_json()
                saved = json.loads((config_dir / "settings.json").read_text(encoding="utf-8"))
                web_app.apply_runtime_settings({})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["download_dir"], str(download_dir.resolve()))
        self.assertEqual(payload["ai_cleanup_prompt_source"], "inline")
        self.assertEqual(saved["knowledge_draft_prompt_text"], "知识库提示词")

    def test_settings_api_masks_secrets_and_preserves_omitted_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"

            with mock.patch.dict(
                web_app.os.environ,
                {"VIDEO_DOWNLOADE_CONFIG_DIR": str(config_dir)},
                clear=False,
            ):
                with web_app.app.test_client() as client:
                    create_response = client.post(
                        "/api/settings",
                        json={
                            "openrouter_api_key": "sk-test-secret-value",
                            "openrouter_transcription_model": "openai/mock-transcribe",
                            "enable_ai_cleanup": False,
                            "enable_article_draft": False,
                            "enable_knowledge_draft": False,
                        },
                    )
                    masked_response = client.get("/api/settings")
                    frontend_settings = web_app.frontend_config()["settings"]
                    update_response = client.post(
                        "/api/settings",
                        json={
                            "openrouter_transcription_model": "openai/changed-transcribe",
                            "enable_ai_cleanup": False,
                            "enable_article_draft": False,
                            "enable_knowledge_draft": False,
                        },
                    )
                    saved_after_update = json.loads((config_dir / "settings.json").read_text(encoding="utf-8"))
                    clear_response = client.post(
                        "/api/settings",
                        json={
                            "openrouter_api_key": "",
                            "enable_ai_cleanup": False,
                            "enable_article_draft": False,
                            "enable_knowledge_draft": False,
                        },
                    )

                saved_after_clear = json.loads((config_dir / "settings.json").read_text(encoding="utf-8"))
                web_app.apply_runtime_settings({})

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(masked_response.status_code, 200)
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(clear_response.status_code, 200)
        self.assertNotEqual(create_response.get_json()["openrouter_api_key"], "sk-test-secret-value")
        self.assertNotEqual(masked_response.get_json()["openrouter_api_key"], "sk-test-secret-value")
        self.assertNotEqual(frontend_settings["openrouter_api_key"], "sk-test-secret-value")
        self.assertTrue(masked_response.get_json()["openrouter_api_key_configured"])
        self.assertEqual(saved_after_update["openrouter_api_key"], "sk-test-secret-value")
        self.assertEqual(saved_after_clear["openrouter_api_key"], "")

    def test_settings_api_exposes_platform_auth_verification_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cookies_path = Path(temp_dir) / "youtube.cookies.txt"
            cookies_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

            with mock.patch.object(web_app, "YOUTUBE_COOKIES_PATH", str(cookies_path)), mock.patch.object(
                web_app, "YOUTUBE_COOKIES_FROM_BROWSER", ""
            ), mock.patch.object(web_app, "COOKIES_PATH", ""), mock.patch.object(
                web_app, "COOKIES_FROM_BROWSER", ""
            ):
                with web_app.app.test_client() as client:
                    response = client.get("/api/settings")

                payload = response.get_json()
                frontend_payload = web_app.frontend_config()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["youtube_auth_configured"])
        self.assertTrue(payload["youtube_auth_verified"])
        self.assertEqual(payload["platform_auth"]["youtube"]["status"], "verified")
        self.assertTrue(frontend_payload["platformAuth"]["youtube"]["verified"])

    def test_frontend_config_exposes_primary_presets(self) -> None:
        payload = web_app.frontend_config()

        self.assertEqual(payload["defaultPreset"], web_app.VIDEO_PRESET_NAME)
        self.assertEqual(payload["videoPreset"], web_app.VIDEO_PRESET_NAME)
        self.assertEqual(payload["audioPreset"], web_app.AUDIO_PRESET_NAME)
        self.assertEqual(payload["transcriptPreset"], web_app.TRANSCRIPT_PRESET_NAME)

    def test_api_requires_web_token_when_configured(self) -> None:
        with web_app.app.test_client() as client, mock.patch.object(web_app, "WEB_TOKEN", "secret-token"):
            missing_response = client.get("/api/tasks")
            wrong_response = client.get("/api/tasks", headers={web_app.WEB_TOKEN_HEADER: "wrong"})
            query_response = client.get("/api/tasks?token=secret-token")
            valid_response = client.get("/api/tasks", headers={web_app.WEB_TOKEN_HEADER: "secret-token"})

        self.assertEqual(missing_response.status_code, 401)
        self.assertEqual(wrong_response.status_code, 401)
        self.assertEqual(query_response.status_code, 401)
        self.assertEqual(valid_response.status_code, 200)

    def test_settings_base_url_change_requires_secret_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"

            with mock.patch.dict(
                web_app.os.environ,
                {"VIDEO_DOWNLOADE_CONFIG_DIR": str(config_dir)},
                clear=False,
            ):
                with web_app.app.test_client() as client:
                    create_response = client.post(
                        "/api/settings",
                        json={
                            "openrouter_base_url": "https://openrouter.ai/api/v1",
                            "openrouter_api_key": "sk-test-secret-value",
                            "enable_ai_cleanup": False,
                            "enable_article_draft": False,
                            "enable_knowledge_draft": False,
                        },
                    )
                    blocked_response = client.post(
                        "/api/settings",
                        json={
                            "openrouter_base_url": "https://attacker.example/v1",
                            "enable_ai_cleanup": False,
                            "enable_article_draft": False,
                            "enable_knowledge_draft": False,
                        },
                    )
                    cleared_response = client.post(
                        "/api/settings",
                        json={
                            "openrouter_base_url": "https://attacker.example/v1",
                            "openrouter_api_key": "",
                            "enable_ai_cleanup": False,
                            "enable_article_draft": False,
                            "enable_knowledge_draft": False,
                        },
                    )

                saved_after_clear = json.loads((config_dir / "settings.json").read_text(encoding="utf-8"))
                web_app.apply_runtime_settings({})

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(blocked_response.status_code, 400)
        self.assertIn("重新输入对应 API Key", blocked_response.get_json()["error"])
        self.assertEqual(cleared_response.status_code, 200)
        self.assertEqual(saved_after_clear["openrouter_base_url"], "https://attacker.example/v1")
        self.assertEqual(saved_after_clear["openrouter_api_key"], "")

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

    def test_run_job_clears_non_fatal_backend_warning_on_success(self) -> None:
        job = web_app.Job(
            job_id="job-success-warning",
            url="https://www.youtube.com/watch?v=abcdefghijk",
            preset=web_app.TRANSCRIPT_PRESET_NAME,
            use_cookies=False,
            generate_transcript=True,
        )
        job.backend_error = "WARNING: impersonation target unavailable"

        def fake_run_transcript_job(active_job: web_app.Job) -> None:
            active_job.transcript_path = "/tmp/Sample - 逐字稿.md"

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(web_app, "DOWNLOAD_DIR", temp_dir), mock.patch.object(
                web_app,
                "run_transcript_job",
                side_effect=fake_run_transcript_job,
            ):
                web_app.run_job(job)

        self.assertTrue(job.done)
        self.assertEqual(job.status, "Done · transcript ready")
        self.assertIsNone(job.backend_error)

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
        job.raw_path = "/tmp/sample - 原始逐字稿.txt"
        job.article_path = "/tmp/sample - 解析稿.md"
        job.transcript_path = "/tmp/sample - 逐字稿.md"
        job.metadata_path = "/tmp/sample - 转写信息.json"

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
        self.assertEqual(payload["tasks"][0]["raw_path"], job.raw_path)
        self.assertEqual(payload["tasks"][0]["article_path"], job.article_path)
        self.assertEqual(payload["tasks"][0]["metadata_path"], job.metadata_path)

    def test_task_artifact_preview_endpoint_returns_transcript_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            transcript_path = artifact_dir / "Sample - 逐字稿.md"
            article_path = artifact_dir / "Sample - 解析稿.md"
            metadata_path = artifact_dir / "Sample - 转写信息.json"
            transcript_path.write_text("# Sample\n\nTranscript body\n", encoding="utf-8")
            article_path.write_text("# 解析稿\n\nArticle body\n", encoding="utf-8")
            metadata_path.write_text('{"source_url":"https://example.com/video"}\n', encoding="utf-8")

            job = web_app.Job(
                job_id="job-preview",
                url="https://example.com/video",
                preset=web_app.TRANSCRIPT_PRESET_NAME,
                use_cookies=False,
                generate_transcript=True,
            )
            job.artifact_dir = str(artifact_dir)
            job.transcript_path = str(transcript_path)
            job.article_path = str(article_path)
            job.metadata_path = str(metadata_path)

            with web_app.jobs_lock:
                web_app.jobs.clear()
                web_app.jobs[job.job_id] = job

            try:
                with web_app.app.test_client() as client:
                    response = client.get(f"/api/tasks/{job.job_id}/artifacts/transcript")
            finally:
                with web_app.jobs_lock:
                    web_app.jobs.clear()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["artifact_kind"], "transcript")
        self.assertEqual(payload["label"], "逐字稿")
        self.assertIn("Transcript body", payload["content"])
        self.assertFalse(payload["truncated"])

    def test_task_artifact_preview_endpoint_can_infer_metadata_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            transcript_path = artifact_dir / "Sample - 逐字稿.md"
            metadata_path = artifact_dir / "Sample - 转写信息.json"
            transcript_path.write_text("# Sample\n", encoding="utf-8")
            metadata_path.write_text('{"provider":"yt-dlp"}\n', encoding="utf-8")

            job = web_app.Job(
                job_id="job-preview-infer",
                url="https://example.com/video",
                preset=web_app.TRANSCRIPT_PRESET_NAME,
                use_cookies=False,
                generate_transcript=True,
            )
            job.artifact_dir = str(artifact_dir)
            job.transcript_path = str(transcript_path)

            with web_app.jobs_lock:
                web_app.jobs.clear()
                web_app.jobs[job.job_id] = job

            try:
                with web_app.app.test_client() as client:
                    response = client.get(f"/api/tasks/{job.job_id}/artifacts/metadata")
            finally:
                with web_app.jobs_lock:
                    web_app.jobs.clear()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["artifact_kind"], "metadata")
        self.assertIn('"provider":"yt-dlp"', payload["content"])


if __name__ == "__main__":
    unittest.main()
