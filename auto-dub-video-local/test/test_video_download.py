import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.services import video_download


class VideoDownloadTests(unittest.TestCase):
    def test_supported_social_links_are_normalized(self):
        cases = {
            "youtu.be/BaW_jenozKc": "YouTube",
            "https://www.youtube.com/watch?v=BaW_jenozKc": "YouTube",
            "https://vm.tiktok.com/example": "TikTok",
            "https://v.douyin.com/example": "Douyin",
        }
        for value, expected_platform in cases.items():
            with self.subTest(value=value):
                url, platform = video_download.validate_video_url(value)
                self.assertTrue(url.startswith("https://"))
                self.assertEqual(platform, expected_platform)

    def test_lookalike_and_unrelated_hosts_are_rejected(self):
        for value in ("https://youtube.com.evil.example/video", "https://vimeo.com/1", "file:///clip.mp4"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    video_download.validate_video_url(value)

    def test_metadata_is_reduced_to_ui_fields(self):
        downloader = mock.MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.extract_info.return_value = {
            "title": "Demo clip",
            "duration": 42.8,
            "thumbnail": "https://example.com/thumb.jpg",
            "uploader": "Creator",
            "extractor_key": "Youtube",
            "webpage_url": "https://www.youtube.com/watch?v=demo",
        }
        with mock.patch("yt_dlp.YoutubeDL", return_value=downloader):
            metadata = video_download.inspect_video_url("https://youtu.be/demo")

        self.assertEqual(metadata.title, "Demo clip")
        self.assertEqual(metadata.platform, "YouTube")
        self.assertEqual(metadata.duration_seconds, 42)
        self.assertEqual(metadata.uploader, "Creator")

    def test_tiktok_metadata_uses_app_api_and_retries_a_transient_failure(self):
        first_downloader = mock.MagicMock()
        first_downloader.__enter__.return_value = first_downloader
        first_downloader.extract_info.side_effect = RuntimeError(
            "ERROR: [TikTok] Unable to extract universal data for rehydration"
        )
        second_downloader = mock.MagicMock()
        second_downloader.__enter__.return_value = second_downloader
        second_downloader.extract_info.return_value = {
            "title": "TikTok clip",
            "duration": 18,
            "extractor_key": "TikTok",
        }

        with (
            mock.patch("yt_dlp.YoutubeDL", side_effect=[first_downloader, second_downloader]) as youtube_dl,
            mock.patch("autodub.services.video_download._wait_for_retry") as wait_for_retry,
        ):
            metadata = video_download.inspect_video_url("https://www.tiktok.com/@creator/video/123")

        self.assertEqual(metadata.title, "TikTok clip")
        self.assertEqual(youtube_dl.call_count, 2)
        self.assertEqual(wait_for_retry.call_count, 1)
        options = youtube_dl.call_args_list[0].args[0]
        self.assertEqual(options["extractor_args"]["tiktok"]["app_info"], [""])

    def test_non_transient_tiktok_metadata_errors_are_not_retried(self):
        downloader = mock.MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.extract_info.side_effect = RuntimeError("ERROR: [TikTok] Video is private")

        with mock.patch("yt_dlp.YoutubeDL", return_value=downloader) as youtube_dl:
            with self.assertRaisesRegex(RuntimeError, "Video is private"):
                video_download.inspect_video_url("https://www.tiktok.com/@creator/video/123")

        self.assertEqual(youtube_dl.call_count, 1)

    def test_downloader_error_text_removes_ansi_escape_sequences(self):
        self.assertEqual(
            video_download._friendly_error(RuntimeError("\x1b[0;31mERROR:\x1b[0m Link unavailable")),
            "Link unavailable",
        )

    def test_download_reports_progress_and_returns_project_staging_file(self):
        class FakeDownloader:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download):
                self.assert_download(download)
                workspace = os.path.dirname(self.options["outtmpl"])
                output = os.path.join(workspace, "clip.mp4")
                Path(output).write_bytes(b"video")
                for hook in self.options["progress_hooks"]:
                    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
                    hook({"status": "finished"})
                return {"filepath": output, "title": "clip", "ext": "mp4"}

            @staticmethod
            def assert_download(download):
                if download is not True:
                    raise AssertionError("download=True was not used")

            @staticmethod
            def prepare_filename(info):
                return info["filepath"]

        metadata = video_download.VideoMetadata(
            url="https://youtu.be/demo",
            title="Demo",
            platform="YouTube",
            duration_seconds=10,
            thumbnail_url="",
            uploader="",
        )
        progress = []
        with tempfile.TemporaryDirectory() as workspace:
            with mock.patch("yt_dlp.YoutubeDL", FakeDownloader):
                path = video_download.download_video(
                    metadata,
                    workspace,
                    lambda value, detail: progress.append((value, detail)),
                    threading.Event(),
                )
            self.assertTrue(Path(path).is_file())
            self.assertTrue(Path(path).is_relative_to(Path(workspace)))

        self.assertEqual(progress[-1], (100, "Download complete"))
        self.assertTrue(any(value == 50 for value, _detail in progress))

    def test_cancelled_download_stops_before_network_work(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(video_download.DownloadCancelled):
            video_download.inspect_video_url("https://youtu.be/demo", event)


if __name__ == "__main__":
    unittest.main()
