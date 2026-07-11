import os
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QDialog, QFormLayout, QFrame, QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QStackedLayout, QVBoxLayout, QWidget

from autodub.utils.ffmpeg import get_video_dimensions


class DraggableSubtitleLabel(QLabel):
    position_changed = Signal(int, int)
    font_size_changed = Signal(int)

    def __init__(self, parent: QWidget):
        super().__init__("Subtitle preview", parent)
        self._drag_origin: QPoint | None = None
        self._drag_widget_origin: QPoint | None = None
        self._resize_origin: QPoint | None = None
        self._resize_font_size = 14
        self._is_resizing = False
        self.font_size = 14
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self._apply_style()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setMinimumWidth(180)
        self.resize(240, 54)
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_resize_handle(event.position().toPoint()):
                self._is_resizing = True
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_font_size = self.font_size
            else:
                self._drag_origin = event.globalPosition().toPoint()
                self._drag_widget_origin = self.pos()
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing and self._resize_origin and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_origin
            self.set_font_size(self._resize_font_size + round(delta.y() / 2))
            event.accept()
            return
        if self._drag_origin and event.buttons() & Qt.MouseButton.LeftButton:
            parent = self.parentWidget()
            if parent and self._drag_widget_origin:
                delta = event.globalPosition().toPoint() - self._drag_origin
                x = max(0, min(self._drag_widget_origin.x() + delta.x(), parent.width() - self.width()))
                y = max(0, min(self._drag_widget_origin.y() + delta.y(), parent.height() - self.height()))
                self.move(x, y)
                self._emit_position()
            event.accept()
            return
        super().mouseMoveEvent(event)
        if not event.buttons():
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._is_resize_handle(event.position().toPoint()) else Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event):
        self._drag_origin = None
        self._drag_widget_origin = None
        self._resize_origin = None
        self._is_resizing = False
        self.releaseMouse()
        super().mouseReleaseEvent(event)

    def set_font_size(self, font_size: int):
        self.font_size = max(10, min(72, font_size))
        self._apply_style()
        self.adjustSize()
        self.font_size_changed.emit(self.font_size)

    def _apply_style(self):
        self.setStyleSheet(
            f"background: rgba(0, 0, 0, 190); color: white; border: 2px solid #facc15; "
            f"border-radius: 3px; padding: 5px 9px; font-weight: 700; font-size: {self.font_size}px;"
        )

    def _is_resize_handle(self, point: QPoint) -> bool:
        return point.x() >= self.width() - 18 and point.y() >= self.height() - 18

    def set_normalized_position(self, x_percent: int, y_percent: int):
        parent = self.parentWidget()
        if not parent or parent.width() <= 0 or parent.height() <= 0:
            return
        x = round(parent.width() * x_percent / 100) - self.width() // 2
        y = round(parent.height() * y_percent / 100) - self.height()
        self.move(max(0, min(x, parent.width() - self.width())), max(0, min(y, parent.height() - self.height())))

    def _emit_position(self):
        parent = self.parentWidget()
        if not parent or parent.width() <= 0 or parent.height() <= 0:
            return
        x = round((self.x() + self.width() / 2) * 100 / parent.width())
        y = round((self.y() + self.height()) * 100 / parent.height())
        self.position_changed.emit(max(0, min(100, x)), max(0, min(100, y)))


class SubtitleBox(QWidget):
    """One direct-manipulation box for subtitle position and size."""

    geometry_changed = Signal(int, int, int, int, int)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._mode: str | None = None
        self._drag_origin: QPoint | None = None
        self._geometry_origin: QRect | None = None
        self.x_percent, self.y_percent = 50, 88
        self.width_percent, self.height_percent = 72, 12
        self.font_size = 72
        self.caption = QLabel("Subtitle preview", self)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMouseTracking(True)
        self._apply_style()

    def set_normalized_geometry(self, x_percent: int, y_percent: int, width_percent: int, height_percent: int, font_size: int):
        self.x_percent = max(0, min(100, x_percent))
        self.y_percent = max(0, min(100, y_percent))
        self.width_percent = max(20, min(95, width_percent))
        self.height_percent = max(6, min(35, height_percent))
        self.font_size = max(10, min(160, font_size))
        parent = self.parentWidget()
        if not parent or parent.width() <= 0 or parent.height() <= 0:
            return
        width = round(parent.width() * self.width_percent / 100)
        height = round(parent.height() * self.height_percent / 100)
        x = round(parent.width() * self.x_percent / 100) - width // 2
        y = round(parent.height() * self.y_percent / 100) - height // 2
        x = max(0, min(x, parent.width() - width))
        y = max(0, min(y, parent.height() - height))
        self.setGeometry(x, y, width, height)
        self._apply_style()

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        self._mode = self._edge_at(point) or "move"
        self._drag_origin = event.globalPosition().toPoint()
        self._geometry_origin = self.geometry()
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        if self._mode and event.buttons() & Qt.MouseButton.LeftButton and self._drag_origin and self._geometry_origin:
            delta = event.globalPosition().toPoint() - self._drag_origin
            rect = QRect(self._geometry_origin)
            if self._mode == "move":
                rect.translate(delta)
            elif self._mode == "left":
                rect.setLeft(min(rect.right() - 80, rect.left() + delta.x()))
            elif self._mode == "right":
                rect.setRight(max(rect.left() + 80, rect.right() + delta.x()))
            elif self._mode == "top":
                rect.setTop(min(rect.bottom() - 38, rect.top() + delta.y()))
            elif self._mode == "bottom":
                rect.setBottom(max(rect.top() + 38, rect.bottom() + delta.y()))
            parent = self.parentWidget()
            if parent:
                rect.moveLeft(max(0, min(rect.left(), parent.width() - rect.width())))
                rect.moveTop(max(0, min(rect.top(), parent.height() - rect.height())))
            self.setGeometry(rect)
            self._emit_geometry()
            event.accept()
            return
        self._set_cursor_for_point(point)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.releaseMouse()
        self._mode = None
        self._drag_origin = None
        self._geometry_origin = None
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_style()

    def _edge_at(self, point: QPoint) -> str | None:
        threshold = 12
        if abs(point.x()) <= threshold:
            return "left"
        if abs(point.x() - self.width()) <= threshold:
            return "right"
        if abs(point.y()) <= threshold:
            return "top"
        if abs(point.y() - self.height()) <= threshold:
            return "bottom"
        return None

    def _set_cursor_for_point(self, point: QPoint):
        edge = self._edge_at(point)
        cursor = (
            Qt.CursorShape.SizeHorCursor if edge in {"left", "right"}
            else Qt.CursorShape.SizeVerCursor if edge in {"top", "bottom"}
            else Qt.CursorShape.SizeAllCursor
        )
        self.setCursor(cursor)

    def _apply_style(self):
        # Grow text until it nearly fills the editable box without clipping horizontally.
        preview_font_size = max(14, round(self.height() * 0.78))
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(preview_font_size)
        metrics = QFontMetrics(font)
        available_width = max(1, self.width() - 18)
        measured_width = max(1, metrics.horizontalAdvance(self.caption.text()))
        if measured_width > available_width:
            preview_font_size = max(14, round(preview_font_size * available_width / measured_width))
        self.setStyleSheet("background: rgba(15, 23, 42, 90); border: 0;")
        self.caption.setStyleSheet(
            f"background: transparent; color: white; border: 0; padding: 2px 8px; "
            f"font-weight: 700; font-size: {preview_font_size}px;"
        )
        self.caption.setGeometry(self.rect())

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(QColor("#38bdf8"))
        pen.setWidth(3)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

    def _emit_geometry(self):
        parent = self.parentWidget()
        if not parent or parent.width() <= 0 or parent.height() <= 0:
            return
        self.x_percent = round(self.geometry().center().x() * 100 / parent.width())
        self.y_percent = round(self.geometry().center().y() * 100 / parent.height())
        self.width_percent = round(self.width() * 100 / parent.width())
        self.height_percent = round(self.height() * 100 / parent.height())
        self.font_size = max(10, min(160, round(min(self.height_percent * 6, self.width_percent * 1.5))))
        self.geometry_changed.emit(self.x_percent, self.y_percent, self.width_percent, self.height_percent, self.font_size)


class CropGuide(QWidget):
    crop_changed = Signal(int, int, int, int)
    position_changed = Signal(int, int)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.left_percent = 0
        self.right_percent = 0
        self.top_percent = 0
        self.bottom_percent = 0
        self._active_edge: str | None = None
        self._drag_origin: QPoint | None = None
        self._crop_origin: tuple[int, int, int, int] | None = None
        self.caption_x_percent = 50
        self.caption_y_percent = 88
        self.caption = QLabel("Subtitle preview", self)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.font_size = 14
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._apply_caption_style()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_crop(self, left: int, right: int, top: int, bottom: int):
        self.left_percent = max(0, min(85, left))
        self.right_percent = max(0, min(85 - self.left_percent, right))
        self.top_percent = max(0, min(85, top))
        self.bottom_percent = max(0, min(85 - self.top_percent, bottom))
        self.update()

    def set_caption_font_size(self, font_size: int):
        self.caption.font_size = max(10, min(72, font_size))
        self._apply_caption_style()
        self.update()

    def set_caption_position(self, x_percent: int, y_percent: int):
        self.caption_x_percent = max(0, min(100, x_percent))
        self.caption_y_percent = max(0, min(100, y_percent))
        self.update()

    def _apply_caption_style(self):
        self.caption.setStyleSheet(
            f"background: rgba(0, 0, 0, 175); color: white; border: 0; border-radius: 3px; "
            f"padding: 5px 9px; font-weight: 700; font-size: {self.caption.font_size}px;"
        )

    def _crop_rect(self) -> QRect:
        x = round(self.width() * self.left_percent / 100)
        right = self.width() - round(self.width() * self.right_percent / 100)
        y = round(self.height() * self.top_percent / 100)
        bottom = self.height() - round(self.height() * self.bottom_percent / 100)
        return QRect(x, y, max(1, right - x), max(1, bottom - y))

    def paintEvent(self, _event):
        if self.width() <= 0 or self.height() <= 0:
            return
        crop = self._crop_rect()
        painter = QPainter(self)
        painter.fillRect(QRect(0, 0, self.width(), crop.top()), QColor(0, 0, 0, 100))
        painter.fillRect(QRect(0, crop.bottom() + 1, self.width(), self.height() - crop.bottom() - 1), QColor(0, 0, 0, 100))
        painter.fillRect(QRect(0, crop.top(), crop.left(), crop.height()), QColor(0, 0, 0, 100))
        painter.fillRect(QRect(crop.right() + 1, crop.top(), self.width() - crop.right() - 1, crop.height()), QColor(0, 0, 0, 100))
        pen = QPen(QColor("#38bdf8"))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(crop)
        self._layout_caption(crop)

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        self._active_edge = self._edge_at(point)
        if self._active_edge:
            self._drag_origin = point
            self._crop_origin = (self.left_percent, self.right_percent, self.top_percent, self.bottom_percent)
            self.grabMouse()
            event.accept()
            return
        if self._crop_rect().contains(point):
            self._active_edge = "move"
            self._drag_origin = point
            self._crop_origin = (self.left_percent, self.right_percent, self.top_percent, self.bottom_percent)
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        if self._active_edge and event.buttons() & Qt.MouseButton.LeftButton:
            if self._active_edge == "move":
                self._move_crop(point)
            else:
                self._update_edge(self._active_edge, point)
            event.accept()
            return
        edge = self._edge_at(point)
        self.setCursor(
            Qt.CursorShape.SizeHorCursor if edge in {"left", "right"}
            else Qt.CursorShape.SizeVerCursor if edge in {"top", "bottom"}
            else Qt.CursorShape.SizeAllCursor if self._crop_rect().contains(point) else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._active_edge:
            self.releaseMouse()
            self._active_edge = None
            self._drag_origin = None
            self._crop_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _edge_at(self, point: QPoint) -> str | None:
        crop = self._crop_rect()
        threshold = 14
        if crop.top() - threshold <= point.y() <= crop.bottom() + threshold:
            if abs(point.x() - crop.left()) <= threshold:
                return "left"
            if abs(point.x() - crop.right()) <= threshold:
                return "right"
        if crop.left() - threshold <= point.x() <= crop.right() + threshold:
            if abs(point.y() - crop.top()) <= threshold:
                return "top"
            if abs(point.y() - crop.bottom()) <= threshold:
                return "bottom"
        return None

    def _update_edge(self, edge: str, point: QPoint):
        minimum_size = 15
        if edge == "left":
            self.left_percent = max(0, min(100 - self.right_percent - minimum_size, round(point.x() * 100 / self.width())))
        elif edge == "right":
            self.right_percent = max(0, min(100 - self.left_percent - minimum_size, round((self.width() - point.x()) * 100 / self.width())))
        elif edge == "top":
            self.top_percent = max(0, min(100 - self.bottom_percent - minimum_size, round(point.y() * 100 / self.height())))
        elif edge == "bottom":
            self.bottom_percent = max(0, min(100 - self.top_percent - minimum_size, round((self.height() - point.y()) * 100 / self.height())))
        self.update()
        self.crop_changed.emit(self.left_percent, self.right_percent, self.top_percent, self.bottom_percent)
        self._emit_position()

    def _move_crop(self, point: QPoint):
        if not self._drag_origin or not self._crop_origin:
            return
        left, right, top, bottom = self._crop_origin
        width_percent = 100 - left - right
        height_percent = 100 - top - bottom
        next_left = round(left + (point.x() - self._drag_origin.x()) * 100 / self.width())
        next_top = round(top + (point.y() - self._drag_origin.y()) * 100 / self.height())
        self.left_percent = max(0, min(100 - width_percent, next_left))
        self.right_percent = 100 - width_percent - self.left_percent
        self.top_percent = max(0, min(100 - height_percent, next_top))
        self.bottom_percent = 100 - height_percent - self.top_percent
        self.update()
        self.crop_changed.emit(self.left_percent, self.right_percent, self.top_percent, self.bottom_percent)
        self._emit_position()

    def _layout_caption(self, crop: QRect):
        width = max(140, min(crop.width() - 16, round(crop.width() * 0.72)))
        height = max(38, round(self.caption.font_size * 2.4))
        x = round(self.width() * self.caption_x_percent / 100) - width // 2
        y = round(self.height() * self.caption_y_percent / 100) - height // 2
        x = max(crop.left() + 8, min(x, crop.right() - width - 7))
        y = max(crop.top() + 8, min(y, crop.bottom() - height - 7))
        self.caption.setGeometry(x, y, width, height)
        self.caption.raise_()

    def _emit_position(self):
        crop = self._crop_rect()
        self.caption_x_percent = round(crop.center().x() * 100 / self.width())
        self.caption_y_percent = round(crop.center().y() * 100 / self.height())
        self.position_changed.emit(self.caption_x_percent, self.caption_y_percent)


class VideoPreview(QWidget):
    def __init__(self, interactive: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.interactive = interactive
        self._source_path: str | None = None
        self._subtitle_x = 50
        self._subtitle_y = 88
        self._video_aspect_ratio = 16 / 9
        self.max_video_height = 520
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.6)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        self.video_host = QWidget()
        self.video_host.setStyleSheet("background: #0b1220; border-radius: 4px;")
        stack = QStackedLayout(self.video_host)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.video_scene = QGraphicsScene(self)
        self.video_item = QGraphicsVideoItem()
        self.video_scene.addItem(self.video_item)
        self.video_widget = QGraphicsView(self.video_scene)
        self.video_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.video_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_widget.setStyleSheet("background: #000;")
        self.placeholder = QLabel("Choose a video to preview")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: #94a3b8; background: transparent;")
        stack.addWidget(self.video_widget)
        stack.addWidget(self.placeholder)
        self.player.setVideoOutput(self.video_item)
        self.overlay = QWidget(self.video_host) if interactive else None
        if self.overlay:
            self.overlay.setStyleSheet("background: transparent;")
            self.subtitle_box = SubtitleBox(self.overlay)
            self.crop_guide = None
            self.subtitle = self.subtitle_box.caption
        else:
            self.subtitle_box = None
            self.crop_guide = None
            self.subtitle = None
        if self.subtitle:
            self.subtitle_box.geometry_changed.connect(self._remember_subtitle_geometry)
            self.overlay.raise_()

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_playback)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderMoved.connect(self.player.setPosition)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setMinimumWidth(100)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.metaDataChanged.connect(self._update_video_aspect_ratio)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.play_button)
        controls.addWidget(self.timeline, 1)
        controls.addWidget(self.time_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_host, 1)
        layout.addLayout(controls)
        self.setMinimumHeight(240)

    def set_source(self, path: str | None):
        normalized = str(Path(path)) if path else None
        if normalized == self._source_path:
            return
        self.player.stop()
        self._source_path = normalized
        exists = bool(normalized and os.path.exists(normalized))
        self.placeholder.setVisible(not exists)
        self.player.setSource(QUrl.fromLocalFile(normalized) if exists else QUrl())
        if exists:
            try:
                width, height = get_video_dimensions(normalized)
                if width > 0 and height > 0:
                    self._video_aspect_ratio = width / height
                    self._apply_video_height()
            except RuntimeError:
                pass
            QTimer.singleShot(250, self._update_video_aspect_ratio)
        self.timeline.setValue(0)
        self._set_time_label(0, 0)

    def toggle_playback(self):
        if not self._source_path:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_position_changed(self, position: int):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(position)
        self._set_time_label(position, self.player.duration())

    def _on_duration_changed(self, duration: int):
        self.timeline.setRange(0, max(0, duration))
        self._set_time_label(self.player.position(), duration)

    def _on_playback_state_changed(self, state):
        self.play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    def _set_time_label(self, position: int, duration: int):
        self.time_label.setText(f"{self._format_time(position)} / {self._format_time(duration)}")

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)
        return f"{seconds // 60:02}:{seconds % 60:02}"

    def set_subtitle_box(self, x_percent: int, y_percent: int, width_percent: int, height_percent: int, font_size: int):
        self._subtitle_x = x_percent
        self._subtitle_y = y_percent
        if self.subtitle_box:
            self.subtitle_box.set_normalized_geometry(x_percent, y_percent, width_percent, height_percent, font_size)

    def set_subtitle_font_size(self, font_size: int):
        if self.subtitle_box:
            self.subtitle_box.font_size = font_size
            self.subtitle_box._apply_style()

    def _remember_subtitle_geometry(self, x_percent: int, y_percent: int, _width: int, _height: int, _font_size: int):
        self._subtitle_x = x_percent
        self._subtitle_y = y_percent

    def _update_video_aspect_ratio(self):
        resolution = self.player.metaData().value(QMediaMetaData.Key.Resolution)
        if isinstance(resolution, QSize) and resolution.width() > 0 and resolution.height() > 0:
            self._video_aspect_ratio = resolution.width() / resolution.height()
            self._apply_video_height()
            self._layout_video_content()

    def _apply_video_height(self):
        if self.width() <= 0:
            return
        height = max(180, min(self.max_video_height, round(self.width() / self._video_aspect_ratio)))
        self.video_host.setFixedHeight(height)

    def _layout_video_content(self):
        host_width = self.video_host.width()
        host_height = self.video_host.height()
        if host_width <= 0 or host_height <= 0:
            return
        host_ratio = host_width / host_height
        if host_ratio > self._video_aspect_ratio:
            content_height = host_height
            content_width = round(content_height * self._video_aspect_ratio)
        else:
            content_width = host_width
            content_height = round(content_width / self._video_aspect_ratio)
        x = (host_width - content_width) // 2
        y = (host_height - content_height) // 2
        content_rect = QRect(x, y, content_width, content_height)
        self.video_scene.setSceneRect(QRectF(0, 0, host_width, host_height))
        self.video_item.setSize(content_rect.size())
        self.video_item.setPos(content_rect.topLeft())
        if self.overlay:
            self.overlay.setGeometry(content_rect)
            if self.subtitle_box:
                self.subtitle_box.set_normalized_geometry(
                    self.subtitle_box.x_percent,
                    self.subtitle_box.y_percent,
                    self.subtitle_box.width_percent,
                    self.subtitle_box.height_percent,
                    self.subtitle_box.font_size,
                )
            self.overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_video_height()
        QTimer.singleShot(0, self._layout_video_content)


class PreviewEditorDialog(QDialog):
    """Dedicated editor window that keeps vertical videos out of the main dashboard layout."""

    preview_changed = Signal(int, int, int, int, int)

    def __init__(self, interactive: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.interactive = interactive
        self.setWindowTitle("Input Preview Editor" if interactive else "Output Preview")
        self.resize(1200, 860)
        self.setMinimumSize(900, 650)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        self.preview = VideoPreview(interactive=interactive)
        self.preview.max_video_height = 760
        body.addWidget(self.preview, 1)

        if interactive:
            controls = QGroupBox("Subtitle Box")
            controls.setMinimumWidth(250)
            form = QFormLayout(controls)
            reset = QPushButton("Reset edits")
            reset.clicked.connect(self.reset_edits)
            form.addRow(reset)
            hint = QLabel("Drag inside the blue box to move it. Hover any edge to resize it. The subtitle scales with the box.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #667085; font-size: 12px;")
            form.addRow(hint)
            self.preview.subtitle_box.geometry_changed.connect(self._emit_changes)
            body.addWidget(controls)

        root.addLayout(body, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        footer.addWidget(close)
        root.addLayout(footer)

    def set_source(self, path: str | None):
        self.preview.set_source(path)

    def set_edit_state(self, subtitle_x: int, subtitle_y: int, box_width: int, box_height: int, font_size: int):
        if not self.interactive:
            return
        self.preview.set_subtitle_box(subtitle_x, subtitle_y, box_width, box_height, font_size)

    def reset_edits(self):
        self.set_edit_state(50, 88, 72, 12, 72)
        self._emit_changes()

    def _emit_changes(self, *_args):
        if not self.interactive:
            return
        self.preview_changed.emit(
            self.preview.subtitle_box.x_percent,
            self.preview.subtitle_box.y_percent,
            self.preview.subtitle_box.width_percent,
            self.preview.subtitle_box.height_percent,
            self.preview.subtitle_box.font_size,
        )
