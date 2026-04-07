import tempfile
import unittest
from pathlib import Path
from unittest import mock

from webui import app as web_app


class SubtitleParsingTests(unittest.TestCase):
    def test_parse_cookies_from_browser_spec_supports_profile(self) -> None:
        parsed = web_app.parse_cookies_from_browser_spec("chrome:Profile 1")
        self.assertEqual(parsed, ("chrome", "Profile 1", None, None))

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
