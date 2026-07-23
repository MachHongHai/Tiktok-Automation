"""Catalog projections, thumbnail recovery, and media metadata helpers."""

from __future__ import annotations

import os
import time

from haizflow.desktop.media import thumbnail_source
from haizflow.services import video_store


class CatalogMediaController:
    """Keeps potentially expensive catalog operations out of the QML facade."""

    def __init__(self, host):
        self._host = host

    @staticmethod
    def thumbnail_retry_signature(source_path: str) -> str:
        normalized = os.path.abspath(source_path) if source_path else "<missing-source>"
        try:
            stat = os.stat(normalized)
        except OSError:
            return f"{normalized}:missing"
        return f"{normalized}:{stat.st_mtime_ns}:{stat.st_size}"

    def missing_thumbnail_ids(self, videos) -> list[str]:
        host = self._host
        known_ids = {video.video_id for video in videos}
        with host._thumbnail_retry_lock:
            host._thumbnail_retry_failures = {
                video_id: failure for video_id, failure in host._thumbnail_retry_failures.items()
                if video_id in known_ids
            }
        missing = []
        for video in videos:
            if thumbnail_source(video.files.get("thumbnail") or ""):
                continue
            source = host._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
            signature = self.thumbnail_retry_signature(source)
            with host._thumbnail_retry_lock:
                failure = host._thumbnail_retry_failures.get(video.video_id)
                if failure and failure[0] != signature:
                    host._thumbnail_retry_failures.pop(video.video_id, None)
                    failure = None
                if failure and (
                    failure[1] >= host._THUMBNAIL_RETRY_MAX_ATTEMPTS
                    or time.monotonic() < failure[2]
                ):
                    continue
            missing.append(video.video_id)
        return missing

    def record_thumbnail_failure(self, video_id: str, signature: str) -> None:
        host = self._host
        with host._thumbnail_retry_lock:
            previous = host._thumbnail_retry_failures.get(video_id)
            attempts = previous[1] + 1 if previous and previous[0] == signature else 1
            delay = min(300.0, host._THUMBNAIL_RETRY_INITIAL_DELAY_SECONDS * (2 ** (attempts - 1)))
            host._thumbnail_retry_failures[video_id] = (signature, attempts, time.monotonic() + delay)

    def clear_thumbnail_failure(self, video_id: str) -> None:
        with self._host._thumbnail_retry_lock:
            self._host._thumbnail_retry_failures.pop(video_id, None)

    def create_missing_thumbnails(self, video_ids) -> None:
        host = self._host
        try:
            for video_id in video_ids:
                video = video_store.get_video(video_id)
                if not video or thumbnail_source(video.files.get("thumbnail") or ""):
                    continue
                path = host._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
                signature = self.thumbnail_retry_signature(path)
                thumbnail = host._create_video_thumbnail_path(path, host._video_thumbnail_path(video.video_id))
                if thumbnail:
                    video.files["thumbnail"] = thumbnail
                    video_store.save_video(video)
                    self.clear_thumbnail_failure(video.video_id)
                else:
                    self.record_thumbnail_failure(video.video_id, signature)
        finally:
            host._log_queue.put("__THUMBNAILS_READY__")

    def refresh_batch_model(self) -> None:
        host = self._host
        videos, valid_ids = [], []
        catalog = getattr(host, "_catalog_videos", {})
        for video_id in host._batch_video_ids:
            video = catalog.get(video_id) or video_store.get_video(video_id)
            if video:
                valid_ids.append(video_id)
                videos.append(self.ensure_video_dimensions(video))
        host._batch_video_ids = valid_ids
        host.batch_videos.set_videos(videos)

    def ensure_video_dimensions(self, video):
        if video.video_width > 0 and video.video_height > 0:
            return video
        path = self._host._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
        self._host._dimension_probe.request(video.video_id, path)
        return video

    def on_video_dimensions_ready(self, video_id: str, width: int, height: int) -> None:
        host = self._host
        if host._shutdown_started or video_id in host._deleted_video_ids:
            return
        video_store.update_video(video_id, video_width=width, video_height=height)
        host._log_queue.put("__VIDEO_DIMENSIONS_READY__")

    def batch_dimension_groups(self):
        host = self._host
        grouped = {}
        catalog = getattr(host, "_catalog_videos", {})
        for video_id in host._batch_video_ids:
            video = catalog.get(video_id) or video_store.get_video(video_id)
            if not video:
                continue
            video = self.ensure_video_dimensions(video)
            if video.video_width > 0 and video.video_height > 0:
                size_key = f"{video.video_width}x{video.video_height}"
                label = f"{video.video_width} x {video.video_height}"
            else:
                size_key, label = f"unknown:{video.video_id}", "Unknown size"
            grouped.setdefault(size_key, {"size_key": size_key, "label": label, "videos": []})["videos"].append(video)
        return sorted(
            grouped.values(),
            key=lambda group: (
                -(group["videos"][0].video_width * group["videos"][0].video_height),
                group["label"],
            ),
        )

    def batch_dimension_group(self, size_key):
        return next((group for group in self.batch_dimension_groups() if group["size_key"] == size_key), None)
