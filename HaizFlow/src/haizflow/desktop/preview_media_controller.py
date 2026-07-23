"""Preview and thumbnail state kept outside the QML singleton facade."""

from __future__ import annotations

import os
import shutil

from PySide6.QtCore import QUrl

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.desktop.media import thumbnail_source
from haizflow.schemas.video import SubtitleStyle
from haizflow.services import video_store


class PreviewMediaController:
    """Own the mutable subtitle-preview session for one desktop controller."""

    def __init__(self, host):
        self._host = host

    def load_video_preview(self, video) -> None:
        host = self._host
        host._subtitle_position_x = video.subtitle_style.position_x_percent
        host._subtitle_position_y = video.subtitle_style.position_y_percent
        host._caption_font_size = video.subtitle_style.font_size
        host._subtitle_box_width = video.subtitle_style.box_width_percent
        host._subtitle_box_height = video.subtitle_style.box_height_percent
        host.previewChanged.emit()

    @staticmethod
    def copy_subtitle_style(style):
        data = style.model_dump() if hasattr(style, "model_dump") else style.dict()
        return SubtitleStyle(**data)

    def current_subtitle_style(self, base=None):
        host = self._host
        base = base or SubtitleStyle()
        return SubtitleStyle(
            font_size=host._caption_font_size,
            margin_bottom=base.margin_bottom,
            outline=base.outline,
            max_chars_per_line=base.max_chars_per_line,
            position_x_percent=host._subtitle_position_x,
            position_y_percent=host._subtitle_position_y,
            box_width_percent=host._subtitle_box_width,
            box_height_percent=host._subtitle_box_height,
        )

    def set_preview_style(self, style) -> None:
        host = self._host
        host._subtitle_position_x = style.position_x_percent
        host._subtitle_position_y = style.position_y_percent
        host._caption_font_size = style.font_size
        host._subtitle_box_width = style.box_width_percent
        host._subtitle_box_height = style.box_height_percent

    def open_batch_group_preview(self, size_key: str) -> None:
        host = self._host
        group = host._batch_dimension_group(size_key)
        if not group:
            self.clear_preview_edit_session()
            return
        representative = group["videos"][0]
        video_path = host._resolve_video_file(representative, ("video_input", "input_video"), ("input", "video.mp4"))
        host._preview_edit_scope = "size_group"
        host._preview_target_video_ids = [video.video_id for video in group["videos"]]
        host._preview_original_style = self.copy_subtitle_style(representative.subtitle_style)
        self.set_preview_style(representative.subtitle_style)
        index_label = f"{host._preview_group_index + 1}/{len(host._preview_group_keys)}"
        self.open_preview(video_path, f"{group['label']} | {index_label}", True)

    def clear_preview_edit_session(self) -> None:
        host = self._host
        host._preview_edit_scope = "draft"
        host._preview_target_video_ids = []
        host._preview_group_keys = []
        host._preview_group_index = -1
        host._preview_original_style = None

    def apply_preview_edits(self, subtitle_x, subtitle_y, box_width, box_height, font_size) -> None:
        host = self._host
        host._subtitle_position_x = max(0, min(100, int(subtitle_x)))
        host._subtitle_position_y = max(0, min(100, int(subtitle_y)))
        host._subtitle_box_width = max(20, min(95, int(box_width)))
        host._subtitle_box_height = max(6, min(35, int(box_height)))
        host._caption_font_size = max(10, min(160, int(font_size)))

    def open_preview(self, path: str, title: str, interactive: bool) -> None:
        host = self._host
        host._preview_title = title
        host._preview_interactive = interactive
        host._preview_source = QUrl.fromLocalFile(path).toString()
        selected_video = host._selected_video()
        thumbnail_path = (selected_video.files or {}).get("thumbnail", "") if selected_video else ""
        if not os.path.exists(thumbnail_path):
            thumbnail_path = host._video_thumbnail_path(selected_video.video_id) if selected_video else self.draft_thumbnail_path()
            thumbnail_path = host._create_video_thumbnail_path(path, thumbnail_path)
            if selected_video and thumbnail_path:
                selected_video.files["thumbnail"] = thumbnail_path
                video_store.save_video(selected_video)
        host._preview_poster_source = thumbnail_source(thumbnail_path) or host._video_thumbnail_source
        host._preview_aspect_ratio = 16 / 9
        if selected_video and selected_video.video_width > 0 and selected_video.video_height > 0:
            host._preview_aspect_ratio = selected_video.video_width / selected_video.video_height
        host.previewChanged.emit()
        host.previewOpenRequested.emit()

    def draft_thumbnail_path(self) -> str:
        host = self._host
        if not host.hasOpenProject:
            return ""
        return os.path.join(host._selected_project_root(), ".input-thumbnail.jpg")

    def assign_project_thumbnail(self, video) -> None:
        host = self._host
        thumbnail_path = host._create_video_thumbnail_path(
            video.files["video_input"],
            host._video_thumbnail_path(video.video_id),
        )
        if thumbnail_path:
            video.files["thumbnail"] = thumbnail_path
            video_store.save_video(video)
        draft_thumbnail = self.draft_thumbnail_path()
        if draft_thumbnail and os.path.isfile(draft_thumbnail):
            try:
                os.remove(draft_thumbnail)
            except OSError:
                pass

    def migrate_legacy_project_thumbnails(self) -> None:
        host = self._host
        legacy_directory = os.path.join(RUNTIME_DATA_DIR, "cache", "thumbnails")
        video_store.migrate_legacy_thumbnails(legacy_directory)
        for video in video_store.list_videos():
            expected_path = host._video_thumbnail_path(video.video_id)
            changed = False
            if not os.path.exists(expected_path):
                source_path = host._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
                created_path = host._create_video_thumbnail_path(source_path, expected_path)
                if created_path:
                    video.files["thumbnail"] = created_path
                    changed = True
            if changed:
                video_store.save_video(video)
        if os.path.isdir(legacy_directory):
            try:
                shutil.rmtree(legacy_directory)
            except OSError:
                pass
