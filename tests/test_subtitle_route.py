import tempfile
import unittest
from pathlib import Path
from unittest import mock

from webui import app as web_app


class SubtitleParsingTests(unittest.TestCase):
    def test_parse_cookies_from_browser_spec_supports_profile(self) -> None:
        parsed = web_app.parse_cookies_from_browser_spec("chrome:Profile 1")
        self.assertEqual(parsed, ("chrome", "Profile 1", None, None))

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

    def test_resolve_cookie_options_prefers_youtube_specific_browser_auth(self) -> None:
        with mock.patch.object(web_app, "YOUTUBE_COOKIES_FROM_BROWSER", "chrome"), mock.patch.object(
            web_app, "YOUTUBE_COOKIES_PATH", ""
        ), mock.patch.object(web_app, "COOKIES_FROM_BROWSER", ""), mock.patch.object(
            web_app, "COOKIES_PATH", "/tmp/bilibili.cookies.txt"
        ):
            options = web_app.resolve_cookie_options("https://www.youtube.com/watch?v=abcdefghijk")

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


class TranscriptRoutingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
