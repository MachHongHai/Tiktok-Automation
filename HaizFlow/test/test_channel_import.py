import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.services.channel_import import (
    _extract_info_with_platform_retry,
    _hydrate_candidate,
    _is_non_video_metadata,
    _needs_hydration,
    _scan_with_ytdlp,
    _youtube_collection_urls,
    load_latest_session,
    new_session,
    normalize_remote_url,
    save_session,
    scan_channel,
    validate_channel_url,
)
from haizflow.services.douyin_channel_worker import (
    _candidate as douyin_candidate,
    inspect_profile as inspect_douyin_profile,
)
from haizflow.services import project_store


class ChannelUrlTests(unittest.TestCase):
    def test_supported_channel_urls_are_normalized(self):
        youtube, youtube_platform = validate_channel_url("youtube.com/@creator")
        tiktok, tiktok_platform = validate_channel_url("https://www.tiktok.com/@creator/")
        douyin, douyin_platform = validate_channel_url("https://www.douyin.com/user/example")

        self.assertEqual(youtube, "https://youtube.com/@creator")
        self.assertEqual(youtube_platform, "YouTube")
        self.assertEqual(tiktok, "https://www.tiktok.com/@creator")
        self.assertEqual(tiktok_platform, "TikTok")
        self.assertEqual(douyin, "https://www.douyin.com/user/example")
        self.assertEqual(douyin_platform, "Douyin")

    def test_video_urls_and_unknown_hosts_are_rejected(self):
        invalid = (
            "https://www.youtube.com/watch?v=abc",
            "https://www.tiktok.com/@creator/video/123",
            "https://www.douyin.com/video/123",
            "https://example.com/@creator",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_channel_url(url)

    def test_selected_platform_must_match_channel_link(self):
        with self.assertRaisesRegex(ValueError, "selected platform"):
            validate_channel_url("https://www.youtube.com/@creator", "tiktok")

        normalized, platform = validate_channel_url(
            "https://www.youtube.com/@creator",
            "youtube",
        )
        self.assertEqual(normalized, "https://www.youtube.com/@creator")
        self.assertEqual(platform, "YouTube")

    def test_remote_url_normalization_removes_tracking_data(self):
        self.assertEqual(
            normalize_remote_url("https://www.tiktok.com/@name/video/123/?lang=en#player"),
            "https://www.tiktok.com/@name/video/123",
        )
        self.assertEqual(
            normalize_remote_url("https://www.youtube.com/watch?v=abc&utm_source=test"),
            "https://www.youtube.com/watch?v=abc",
        )

    def test_youtube_collection_matches_duration_filter(self):
        channel = "https://www.youtube.com/@creator/videos"

        self.assertEqual(
            _youtube_collection_urls(channel, "short"),
            ["https://www.youtube.com/@creator/shorts"],
        )
        self.assertEqual(
            _youtube_collection_urls(channel, "long"),
            ["https://www.youtube.com/@creator/videos"],
        )
        self.assertEqual(
            _youtube_collection_urls(channel, "all"),
            [
                "https://www.youtube.com/@creator/videos",
                "https://www.youtube.com/@creator/shorts",
            ],
        )

    def test_audio_only_slideshow_metadata_is_not_treated_as_video(self):
        self.assertTrue(
            _is_non_video_metadata(
                {
                    "formats": [
                        {"ext": "m4a", "acodec": "aac", "vcodec": "none"},
                    ]
                }
            )
        )
        self.assertFalse(
            _is_non_video_metadata(
                {
                    "formats": [
                        {"ext": "mp4", "acodec": "aac", "vcodec": "h264"},
                    ]
                }
            )
        )

    def test_tiktok_image_metadata_is_not_treated_as_video(self):
        candidate = ChannelVideoCandidate(
            remote_video_id="photo-post",
            source_url="https://www.tiktok.com/@creator/video/photo-post",
            title="Photo post",
            platform="TikTok",
        )
        with patch(
            "haizflow.services.channel_import._extract_info_with_platform_retry",
            return_value={
                "images": [{"url": "https://example.com/photo.jpg"}],
                "formats": [{"vcodec": "h264", "ext": "mp4"}],
            },
        ):
            self.assertIsNone(_hydrate_candidate(candidate, {}, threading.Event()))

    def test_tiktok_transient_hydration_error_is_retried_once(self):
        first = Mock()
        first.__enter__ = Mock(return_value=first)
        first.__exit__ = Mock(return_value=False)
        first.extract_info.side_effect = RuntimeError("Unable to extract universal data for rehydration")
        second = Mock()
        second.__enter__ = Mock(return_value=second)
        second.__exit__ = Mock(return_value=False)
        second.extract_info.return_value = {"id": "123"}
        fake_ytdlp = SimpleNamespace(YoutubeDL=Mock(side_effect=[first, second]))

        with (
            patch("haizflow.services.channel_import._load_yt_dlp", return_value=fake_ytdlp),
            patch("haizflow.services.channel_import._wait_for_retry") as wait_for_retry,
        ):
            info = _extract_info_with_platform_retry(
                "TikTok",
                {"noplaylist": True},
                "https://www.tiktok.com/@creator/video/123",
                threading.Event(),
            )

        self.assertEqual(info, {"id": "123"})
        self.assertEqual(fake_ytdlp.YoutubeDL.call_count, 2)
        wait_for_retry.assert_called_once()

    def test_tiktok_candidates_are_hydrated_to_reject_slideshows(self):
        candidate = ChannelVideoCandidate(
            remote_video_id="123",
            source_url="https://www.tiktok.com/@creator/video/123",
            title="Post",
            platform="TikTok",
            duration_seconds=30,
            published_at="20260718",
            view_count=100,
        )
        request = ChannelImportRequest(
            url="https://www.tiktok.com/@creator",
            platform="tiktok",
            ranking="popular",
            duration_filter="all",
        )

        self.assertTrue(_needs_hydration(candidate, request))

    def test_douyin_photo_posts_are_excluded(self):
        self.assertIsNone(
            douyin_candidate(
                {
                    "aweme_id": "photo-1",
                    "images": [{"url_list": ["https://example.com/image.jpg"]}],
                    "video": {"play_addr": {"url_list": ["https://example.com/fallback.mp4"]}},
                }
            )
        )

    def test_douyin_post_without_playable_video_url_is_excluded(self):
        self.assertIsNone(
            douyin_candidate(
                {
                    "aweme_id": "broken-video",
                    "video": {"play_addr": {"url_list": []}},
                }
            )
        )

    def test_douyin_newest_scan_uses_the_requested_count(self):
        with (
            patch("haizflow.services.douyin_channel_worker._cookie_header", return_value=""),
            patch(
                "haizflow.services.douyin_channel_worker._resolve_profile_url",
                return_value="https://www.douyin.com/user/creator-id",
            ),
            patch("haizflow.services.douyin_channel_worker._extract_sec_uid", return_value="creator-id"),
            patch(
                "haizflow.services.douyin_channel_worker._api_page",
                return_value={
                    "aweme_list": [],
                    "has_more": False,
                },
            ) as api_page,
        ):
            with self.assertRaisesRegex(RuntimeError, "no public videos"):
                inspect_douyin_profile({"url": "https://www.douyin.com/user/creator-id", "limit": 20})

        self.assertEqual(api_page.call_args.args[2], 20)


class ChannelScanTests(unittest.TestCase):
    @staticmethod
    def candidate(video_id, *, views, duration, published, content_type=""):
        return ChannelVideoCandidate(
            remote_video_id=video_id,
            source_url=f"https://www.youtube.com/watch?v={video_id}",
            title=f"Video {video_id}",
            platform="YouTube",
            content_type=content_type,
            duration_seconds=duration,
            published_at=published,
            view_count=views,
        )

    def test_popular_scan_filters_duration_sorts_and_marks_duplicates(self):
        candidates = [
            self.candidate("known", views=5000, duration=60, published="20260101"),
            self.candidate("duplicate", views=9000, duration=90, published="20260102"),
            self.candidate("unknown", views=None, duration=45, published="20260103"),
            self.candidate("long", views=20000, duration=181, published="20260104"),
        ]
        request = ChannelImportRequest(
            url="https://www.youtube.com/@creator",
            ranking="popular",
            limit=10,
            duration_filter="short",
            scan_scope=300,
        )

        with patch(
            "haizflow.services.channel_import._scan_with_ytdlp",
            return_value=("Creator", candidates),
        ):
            platform, channel, result = scan_channel(
                request,
                {"youtube:duplicate"},
                cancel_event=threading.Event(),
            )

        self.assertEqual(platform, "YouTube")
        self.assertEqual(channel, "Creator")
        self.assertEqual([candidate.remote_video_id for candidate in result], ["duplicate", "known", "unknown"])
        self.assertTrue(result[0].duplicate)
        self.assertFalse(result[0].selected)
        self.assertEqual(result[0].status, "duplicate")

    def test_newest_scan_uses_normalized_url_fallback(self):
        candidates = [
            self.candidate("older", views=100, duration=30, published="20250101"),
            self.candidate("newer", views=10, duration=30, published="20260101"),
        ]
        request = ChannelImportRequest(
            url="https://www.youtube.com/@creator/videos",
            ranking="newest",
            limit=2,
            duration_filter="all",
        )

        with patch(
            "haizflow.services.channel_import._scan_with_ytdlp",
            return_value=("Creator", candidates),
        ):
            _platform, _channel, result = scan_channel(
                request,
                {"https://www.youtube.com/watch?v=newer&utm_source=old"},
            )

        self.assertEqual([candidate.remote_video_id for candidate in result], ["newer", "older"])
        self.assertTrue(result[0].duplicate)

    def test_newest_scan_preserves_provider_order_when_dates_are_missing(self):
        candidates = [
            self.candidate("latest-source-item", views=10, duration=30, published="20260717"),
            self.candidate("older-source-item", views=100, duration=30, published=""),
            self.candidate("oldest-source-item", views=1000, duration=30, published="20260715"),
        ]
        request = ChannelImportRequest(
            url="https://www.youtube.com/@creator/shorts",
            platform="youtube",
            ranking="newest",
            limit=3,
            duration_filter="short",
        )

        with patch(
            "haizflow.services.channel_import._scan_with_ytdlp",
            return_value=("Creator", candidates),
        ):
            _platform, _channel, result = scan_channel(request)

        self.assertEqual(
            [candidate.remote_video_id for candidate in result],
            ["latest-source-item", "older-source-item", "oldest-source-item"],
        )

    def test_specific_duration_filter_excludes_unknown_duration(self):
        candidates = [
            self.candidate("unknown", views=100, duration=0, published="20260101"),
            self.candidate("short", views=90, duration=180, published="20260102"),
        ]
        request = ChannelImportRequest(
            url="https://www.youtube.com/@creator",
            ranking="newest",
            limit=10,
            duration_filter="short",
        )

        with patch(
            "haizflow.services.channel_import._scan_with_ytdlp",
            return_value=("Creator", candidates),
        ):
            _platform, _channel, result = scan_channel(request)

        self.assertEqual([candidate.remote_video_id for candidate in result], ["short"])

    def test_youtube_regular_video_filter_uses_channel_tab_not_duration(self):
        candidates = [
            self.candidate(
                "short-music-video",
                views=100,
                duration=120,
                published="20260718",
                content_type="long",
            ),
            self.candidate(
                "long-short",
                views=200,
                duration=240,
                published="20260717",
                content_type="short",
            ),
        ]
        request = ChannelImportRequest(
            url="https://www.youtube.com/@artist",
            platform="youtube",
            ranking="newest",
            limit=10,
            duration_filter="long",
        )

        with patch(
            "haizflow.services.channel_import._scan_with_ytdlp",
            return_value=("Artist", candidates),
        ):
            _platform, _channel, result = scan_channel(request)

        self.assertEqual([candidate.remote_video_id for candidate in result], ["short-music-video"])

    def test_ytdlp_tags_regular_youtube_tab_even_for_a_short_music_video(self):
        requested_urls = []

        class FakeDownloader:
            def __init__(self, _options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, url, download=False):
                requested_urls.append((url, download))
                return {
                    "channel": "Artist",
                    "entries": [
                        {
                            "id": "music-video",
                            "title": "Two-minute music video",
                            "duration": 120,
                            "upload_date": "20260718",
                        }
                    ],
                }

        request = ChannelImportRequest(
            url="https://www.youtube.com/@artist",
            platform="youtube",
            limit=1,
            duration_filter="long",
        )
        fake_ytdlp = type("FakeYtDlp", (), {"YoutubeDL": FakeDownloader})
        with patch("haizflow.services.channel_import._load_yt_dlp", return_value=fake_ytdlp):
            _channel, candidates = _scan_with_ytdlp(request, "YouTube", None, threading.Event())

        self.assertEqual(requested_urls, [("https://www.youtube.com/@artist/videos", False)])
        self.assertEqual(candidates[0].content_type, "long")
        self.assertEqual(candidates[0].duration_seconds, 120)

    def test_newest_tiktok_scan_uses_the_requested_count(self):
        options_used = []

        class FakeDownloader:
            def __init__(self, options):
                options_used.append(options)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download=False):
                self.assert_download(download)
                return {
                    "uploader": "Creator",
                    "entries": [
                        {
                            "id": "123",
                            "uploader_id": "creator",
                            "title": "Video",
                            "duration": 30,
                            "upload_date": "20260718",
                        }
                    ],
                }

            @staticmethod
            def assert_download(download):
                if download:
                    raise AssertionError("Channel inspection must not download media")

        request = ChannelImportRequest(
            url="https://www.tiktok.com/@creator",
            platform="tiktok",
            ranking="newest",
            limit=20,
            duration_filter="all",
        )
        fake_ytdlp = type("FakeYtDlp", (), {"YoutubeDL": FakeDownloader})
        with (
            patch("haizflow.services.channel_import._load_yt_dlp", return_value=fake_ytdlp),
            patch("haizflow.services.channel_import._needs_hydration", return_value=False),
        ):
            _channel, candidates = _scan_with_ytdlp(request, "TikTok", None, threading.Event())

        self.assertEqual(options_used[0]["playlistend"], 20)
        self.assertEqual([candidate.remote_video_id for candidate in candidates], ["123"])


class ChannelSessionTests(unittest.TestCase):
    def test_session_is_project_owned_and_does_not_persist_cookie_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            request = ChannelImportRequest(
                url="https://www.youtube.com/@creator/videos",
                cookie_browser="edge",
                cookie_file="C:/secret/cookies.txt",
            )
            session = new_session("batch:key", str(project_root), request)
            session.candidates = [
                ChannelVideoCandidate(
                    remote_video_id="abc",
                    source_url="https://www.youtube.com/watch?v=abc",
                    title="Example",
                    platform="YouTube",
                )
            ]
            save_session(session)

            restored = load_latest_session(str(project_root))
            raw = json.loads(
                (project_root / "imports" / "channel" / session.session_id / "session.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertIsNotNone(restored)
        self.assertEqual(restored.session_id, session.session_id)
        self.assertEqual(restored.candidates[0].remote_video_id, "abc")
        self.assertNotIn("cookie_browser", raw["request"])
        self.assertNotIn("cookie_file", raw["request"])
        self.assertNotIn("secret", json.dumps(raw).lower())

    def test_deleting_project_removes_import_sessions_and_partial_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                record = project_store.ensure_project("Campaign", str(root / "projects"), "batch")
                request = ChannelImportRequest(url="https://www.youtube.com/@creator/videos")
                session = new_session(record["key"], record["project_root"], request)
                save_session(session)
                partial = (
                    Path(record["project_root"])
                    / "imports"
                    / "channel"
                    / session.session_id
                    / "downloads"
                    / "abc"
                    / "video.mp4.part"
                )
                partial.parent.mkdir(parents=True)
                partial.write_bytes(b"partial")

                deleted = project_store.delete_project("Campaign", str(root / "projects"), "batch")
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertTrue(deleted)
        self.assertFalse(Path(record["project_root"]).exists())

    def test_switching_projects_restores_each_projects_own_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            request = ChannelImportRequest(url="https://www.youtube.com/@creator")
            first = new_session("batch:first", str(root / "first"), request)
            first.candidates = [
                ChannelVideoCandidate(
                    remote_video_id="first-video",
                    source_url="https://www.youtube.com/watch?v=first-video",
                    title="First",
                    platform="YouTube",
                )
            ]
            second = new_session("batch:second", str(root / "second"), request)
            second.candidates = [
                ChannelVideoCandidate(
                    remote_video_id="second-video",
                    source_url="https://www.youtube.com/watch?v=second-video",
                    title="Second",
                    platform="YouTube",
                )
            ]
            save_session(first)
            save_session(second)

            coordinator = ChannelImportCoordinator()
            coordinator.attach_project(first.project_key, first.project_root, set())
            first_id = coordinator.candidates.candidate_at(0).remote_video_id
            coordinator.attach_project(second.project_key, second.project_root, set())
            second_id = coordinator.candidates.candidate_at(0).remote_video_id
            coordinator.attach_project(first.project_key, first.project_root, set())
            restored_first_id = coordinator.candidates.candidate_at(0).remote_video_id

        self.assertEqual(first_id, "first-video")
        self.assertEqual(second_id, "second-video")
        self.assertEqual(restored_first_id, "first-video")

    def test_interrupted_download_is_restored_as_retryable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            request = ChannelImportRequest(url="https://www.youtube.com/@creator")
            session = new_session("batch:key", str(root), request)
            session.state = "downloading"
            session.candidates = [
                ChannelVideoCandidate(
                    remote_video_id="abc",
                    source_url="https://www.youtube.com/watch?v=abc",
                    title="Example",
                    platform="YouTube",
                    status="downloading",
                )
            ]
            save_session(session)

            coordinator = ChannelImportCoordinator()
            coordinator.attach_project(session.project_key, session.project_root, set())
            restored = coordinator.candidates.candidate_at(0)

        self.assertEqual(coordinator.state, "ready")
        self.assertEqual(restored.status, "failed")
        self.assertIn("Retry", restored.error)

    def test_project_session_is_not_forgotten_until_worker_has_stopped(self):
        class WorkerState:
            running = True

            def is_alive(self):
                return self.running

            def join(self, timeout=None):
                return None

        coordinator = ChannelImportCoordinator()
        request = ChannelImportRequest(url="https://www.youtube.com/@creator")
        session = new_session("batch:key", "D:/projects/example", request)
        worker = WorkerState()
        coordinator._sessions[session.session_id] = session
        coordinator._project_sessions[session.project_key] = session.session_id
        coordinator._runner_threads[session.session_id] = worker
        coordinator._cancel_events[session.session_id] = threading.Event()

        self.assertFalse(coordinator.cancel_project(session.project_key))
        self.assertIn(session.session_id, coordinator._sessions)

        worker.running = False
        self.assertTrue(coordinator.cancel_project(session.project_key))
        self.assertNotIn(session.session_id, coordinator._sessions)


if __name__ == "__main__":
    unittest.main()
