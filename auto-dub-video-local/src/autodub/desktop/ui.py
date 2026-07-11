import os
import queue
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QScrollArea, QSlider, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from autodub.config import APP_DATA_DIR, BIN_DIR, CACHE_DIR, LOGS_DIR, STORAGE_DIR, TRANSLATOR_PROVIDER, WHISPER_MODEL
from autodub.core.events import subscribe_log, unsubscribe_log
from autodub.desktop.video_preview import PreviewEditorDialog
from autodub.pipeline.job_manager import cancel_job
from autodub.schemas.job import CropSettings, JobConfig, SubtitleStyle
from autodub.services import job_store
from autodub.services.desktop_jobs import create_desktop_job
from autodub.services.ollama_runtime import ensure_ollama_running
from autodub.utils.ffmpeg import get_ffmpeg_version, is_ffmpeg_available


APP_STYLESHEET = """
QMainWindow, QWidget { background: #f5f7fb; color: #172033; font-family: 'Segoe UI'; font-size: 13px; }
QGroupBox { background: #fff; border: 1px solid #dce2ec; border-radius: 6px; margin-top: 12px; padding: 13px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QLineEdit, QComboBox, QSpinBox { background: #fff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 8px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #2563eb; }
QPushButton { background: #fff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 7px 11px; min-height: 20px; }
QPushButton:hover { background: #eff6ff; border-color: #93c5fd; }
QPushButton#primaryButton { background: #2563eb; border-color: #2563eb; color: #fff; font-weight: 600; }
QPushButton#primaryButton:hover { background: #1d4ed8; }
QPushButton#dangerButton { color: #b42318; border-color: #f0b8b2; }
QPushButton#dangerButton:hover { background: #fff1f0; }
QProgressBar { border: 0; border-radius: 5px; background: #e6eaf2; height: 12px; }
QProgressBar::chunk { background: #2563eb; border-radius: 5px; }
QPlainTextEdit { background: #0f172a; color: #dbeafe; border: 0; border-radius: 4px; font-family: Consolas; font-size: 12px; }
QTableWidget { background: #fff; border: 1px solid #dce2ec; gridline-color: #edf1f7; selection-background-color: #dbeafe; selection-color: #172033; }
QHeaderView::section { background: #f8fafc; border: 0; border-bottom: 1px solid #dce2ec; padding: 7px; font-weight: 600; }
QScrollArea { border: 0; }
"""


class AutoDubDesktopApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Dub Video Local")
        self.resize(1280, 820)
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(APP_STYLESHEET)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.processing_job_id: str | None = None
        self.selected_job_id: str | None = None
        self.worker_thread: threading.Thread | None = None
        self.is_processing = False
        self.deleted_job_ids: set[str] = set()
        self.subtitle_position_x = 50
        self.subtitle_position_y = 88
        self.caption_font_size = 72
        self.subtitle_box_width = 72
        self.subtitle_box_height = 12
        self.input_preview_editor: PreviewEditorDialog | None = None
        self.output_preview_editor: PreviewEditorDialog | None = None
        self._build_layout()
        self._refresh_jobs()
        subscribe_log(self._on_job_log)
        threading.Thread(target=lambda: ensure_ollama_running(warm_model=True), daemon=True).start()
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._drain_log_queue)
        self.log_timer.start(250)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_jobs)
        self.status_timer.start(1000)

    def _build_layout(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        header = QHBoxLayout()
        labels = QVBoxLayout()
        title = QLabel("Auto Dub Video Local")
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #101828;")
        labels.addWidget(title)
        subtitle = QLabel(f"Desktop mode | Translator: {TRANSLATOR_PROVIDER} | Whisper: {WHISPER_MODEL}")
        subtitle.setStyleSheet("color: #667085;")
        labels.addWidget(subtitle)
        header.addLayout(labels)
        header.addStretch()
        for text, callback in (("Open App Data", lambda: self._open_path(APP_DATA_DIR)), ("Diagnostics", self._show_diagnostics)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            header.addWidget(button)
        root.addLayout(header)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_input_panel())
        splitter.addWidget(self._build_workspace())
        splitter.setSizes([440, 820])
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

    def _build_input_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)
        group = QGroupBox("Input")
        grid = QGridLayout(group)
        self.video_path, self.srt_path, self.script_path = QLineEdit(), QLineEdit(), QLineEdit()
        self._file_row(grid, 0, "Video", self.video_path, self._browse_video)
        self._file_row(grid, 1, "SRT", self.srt_path, self._browse_srt)
        self._file_row(grid, 2, "Script", self.script_path, self._browse_script)
        layout.addWidget(group)
        group = QGroupBox("Mode")
        modes = QVBoxLayout(group)
        self.mode_group = QButtonGroup(self)
        for index, (label, value) in enumerate((("Full Auto", "A"), ("Use Vietnamese SRT", "B"), ("Use Vietnamese Script", "C"))):
            button = QRadioButton(label)
            button.setProperty("mode", value)
            button.setChecked(index == 0)
            self.mode_group.addButton(button)
            modes.addWidget(button)
        layout.addWidget(group)
        group = QGroupBox("Settings")
        form = QFormLayout(group)
        self.source_language = self._combo(["auto", "en", "zh", "vi"], "auto")
        self.tts_voice = self._combo(["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"], "vi-VN-HoaiMyNeural")
        self.output_format = self._combo(["keep_ratio", "tiktok_9_16_crop", "blur_background_9_16"], "keep_ratio")
        self.outline, self.max_chars_per_line = self._spin(0, 8, 2), self._spin(12, 80, 32)
        for label, widget in (("Source", self.source_language), ("Voice", self.tts_voice), ("Layout", self.output_format), ("Outline", self.outline), ("Max chars", self.max_chars_per_line)):
            form.addRow(label, widget)
        self.enable_audio_separation = QCheckBox("Separate vocals for transcription with Demucs")
        self.enable_audio_separation.setChecked(True)
        form.addRow(self.enable_audio_separation)
        volume = QWidget()
        volume_layout = QHBoxLayout(volume)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        self.original_video_volume = QSlider(Qt.Orientation.Horizontal)
        self.original_video_volume.setRange(0, 100)
        self.original_video_volume.setValue(60)
        self.volume_label = QLabel("60%")
        self.volume_label.setMinimumWidth(36)
        self.original_video_volume.valueChanged.connect(lambda value: self.volume_label.setText(f"{value}%"))
        volume_layout.addWidget(self.original_video_volume, 1)
        volume_layout.addWidget(self.volume_label)
        form.addRow("Original volume", volume)
        layout.addWidget(group)
        self.start_button = QPushButton("Create & Process")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._start_job)
        layout.addWidget(self.start_button)
        stop = QPushButton("Stop Active Job")
        stop.setObjectName("dangerButton")
        stop.clicked.connect(self._stop_job)
        layout.addWidget(stop)
        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_workspace(self):
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_preview_actions())
        status = QGroupBox("Selected Job")
        grid = QGridLayout(status)
        self.status_text, self.step_text, self.progress_text = QLabel("Ready"), QLabel("pending"), QLabel("0%")
        self.processing_text = QLabel("Processing: none")
        self.step_text.setStyleSheet("color: #667085;")
        self.processing_text.setStyleSheet("color: #667085;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        grid.addWidget(self.status_text, 0, 0, 1, 2)
        grid.addWidget(self.step_text, 1, 0, 1, 2)
        grid.addWidget(self.processing_text, 2, 0, 1, 2)
        grid.addWidget(self.progress, 3, 0)
        grid.addWidget(self.progress_text, 3, 1)
        buttons = QHBoxLayout()
        for text, callback in (("Open Output Preview", self._open_output_preview_editor), ("Open Job Folder", self._open_active_job_folder), ("Refresh", self._refresh_jobs)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch()
        grid.addLayout(buttons, 4, 0, 1, 2)
        layout.addWidget(status)
        logs = QGroupBox("Logs")
        logs_layout = QVBoxLayout(logs)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        logs_layout.addWidget(self.log_text)
        layout.addWidget(logs, 1)
        history_group = QGroupBox("Recent Jobs")
        history_layout = QVBoxLayout(history_group)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        delete = QPushButton("Delete Job")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_selected_job)
        toolbar.addWidget(delete)
        history_layout.addLayout(toolbar)
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["File", "Mode", "Status", "Updated"])
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.verticalHeader().setVisible(False)
        self.history.horizontalHeader().setStretchLastSection(True)
        self.history.setColumnWidth(0, 330)
        self.history.setColumnWidth(1, 65)
        self.history.setColumnWidth(2, 100)
        self.history.itemSelectionChanged.connect(self._select_history_job)
        history_layout.addWidget(self.history)
        layout.addWidget(history_group)
        return workspace

    def _build_preview_actions(self):
        panel = QGroupBox("Preview")
        layout = QHBoxLayout(panel)
        edit_input = QPushButton("Edit Input Preview")
        edit_input.setObjectName("primaryButton")
        edit_input.clicked.connect(self._open_input_preview_editor)
        layout.addWidget(edit_input)
        preview_output = QPushButton("Open Output Preview")
        preview_output.clicked.connect(self._open_output_preview_editor)
        layout.addWidget(preview_output)
        layout.addStretch()
        return panel

    @staticmethod
    def _combo(values, selected):
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(selected)
        return combo

    @staticmethod
    def _spin(minimum, maximum, value):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    @staticmethod
    def _file_row(layout, row, label, field, callback):
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(field, row, 1)
        button = QPushButton("Browse")
        button.clicked.connect(callback)
        layout.addWidget(button, row, 2)

    def _browse(self, title, filters, field):
        path, _ = QFileDialog.getOpenFileName(self, title, "", filters)
        if path:
            field.setText(path)

    def _browse_video(self):
        self._browse("Choose input video", "Video files (*.mp4 *.mov *.mkv);;All files (*.*)", self.video_path)
        if self.video_path.text().strip():
            self._clear_selected_job()
        if self.input_preview_editor and self.input_preview_editor.isVisible():
            self.input_preview_editor.set_source(self.video_path.text() or None)
    def _browse_srt(self): self._browse("Choose subtitle", "Subtitle files (*.srt);;All files (*.*)", self.srt_path)
    def _browse_script(self): self._browse("Choose script", "Text files (*.txt);;All files (*.*)", self.script_path)

    def _open_input_preview_editor(self):
        selected_job = job_store.get_job(self.selected_job_id) if self.selected_job_id else None
        video_path = selected_job.files.get("video_input") if selected_job else self.video_path.text().strip()
        if not video_path or not os.path.exists(video_path):
            QMessageBox.information(self, "Input preview", "Choose an input video before opening the preview editor.")
            return
        if not self.input_preview_editor:
            self.input_preview_editor = PreviewEditorDialog(interactive=True, parent=self)
            self.input_preview_editor.preview_changed.connect(self._apply_preview_edits)
        self.input_preview_editor.set_source(video_path)
        self.input_preview_editor.set_edit_state(
            self.subtitle_position_x,
            self.subtitle_position_y,
            self.subtitle_box_width,
            self.subtitle_box_height,
            self.caption_font_size,
        )
        self.input_preview_editor.showMaximized()
        self.input_preview_editor.raise_()
        self.input_preview_editor.activateWindow()

    def _open_output_preview_editor(self):
        job = job_store.get_job(self.selected_job_id) if self.selected_job_id else None
        output_path = job.files.get("final_video") if job else None
        if not output_path or not os.path.exists(output_path):
            QMessageBox.information(self, "Output preview", "Final video is not available yet.")
            return
        if not self.output_preview_editor:
            self.output_preview_editor = PreviewEditorDialog(interactive=False, parent=self)
        self.output_preview_editor.set_source(output_path)
        self.output_preview_editor.showMaximized()
        self.output_preview_editor.raise_()
        self.output_preview_editor.activateWindow()

    def _apply_preview_edits(self, subtitle_x, subtitle_y, box_width, box_height, font_size):
        self.subtitle_position_x = subtitle_x
        self.subtitle_position_y = subtitle_y
        self.subtitle_box_width = box_width
        self.subtitle_box_height = box_height
        self.caption_font_size = font_size

    def _build_config(self):
        checked = self.mode_group.checkedButton()
        return JobConfig(mode=checked.property("mode") if checked else "A", source_language=self.source_language.currentText(), target_language="vi", tts_voice=self.tts_voice.currentText(), subtitle_style=SubtitleStyle(font_size=self.caption_font_size, margin_bottom=40, outline=self.outline.value(), max_chars_per_line=self.max_chars_per_line.value(), position_x_percent=self.subtitle_position_x, position_y_percent=self.subtitle_position_y, box_width_percent=self.subtitle_box_width, box_height_percent=self.subtitle_box_height), output_format=self.output_format.currentText(), crop=CropSettings(), enable_audio_separation=self.enable_audio_separation.isChecked(), original_video_volume=self.original_video_volume.value())

    def _start_job(self):
        if self.is_processing:
            QMessageBox.warning(self, "Job running", "A job is already processing.")
            return
        if not self.video_path.text().strip():
            QMessageBox.critical(self, "Missing video", "Please choose an input video.")
            return
        try:
            job = create_desktop_job(self.video_path.text(), self._build_config(), self.srt_path.text() or None, self.script_path.text() or None)
        except Exception as exc:
            QMessageBox.critical(self, "Cannot create job", str(exc))
            return
        self.processing_job_id, self.selected_job_id, self.is_processing = job.job_id, job.job_id, True
        self._update_processing_indicator()
        self.start_button.setEnabled(False)
        self._clear_logs()
        self._load_job_logs(job.job_id)
        self._set_job_status(job)
        self.worker_thread = threading.Thread(target=self._run_pipeline, args=(job.job_id,), daemon=True)
        self.worker_thread.start()
        self._refresh_jobs()

    def _run_pipeline(self, job_id):
        try:
            from autodub.pipeline.process_job import process_job_sync
            process_job_sync(job_id)
        except Exception as exc:
            if job_id not in self.deleted_job_ids:
                message = f"Desktop worker failed before pipeline could start: {exc}"
                job_store.log_to_job(job_id, message)
                job_store.update_job(job_id, status="failed", error=str(exc), step="failed")
                if job_id == self.selected_job_id:
                    self.log_queue.put(message)
        finally:
            self.log_queue.put(f"__REFRESH__:{job_id}")

    def _stop_job(self):
        if self.processing_job_id and QMessageBox.question(self, "Stop job", "Stop the processing job?") == QMessageBox.StandardButton.Yes:
            job_id = self.processing_job_id
            cancel_job(job_id)
            job_store.update_job(job_id, status="cancelled", error=None, step="cancelled")
            job_store.log_to_job(job_id, "Stop requested. Active subprocesses were force-stopped.")
            self.processing_job_id = None
            self.is_processing = False
            self.start_button.setEnabled(True)
            self._update_processing_indicator()
            self._refresh_jobs()
            if self.selected_job_id == job_id:
                job = job_store.get_job(job_id)
                if job:
                    self._set_job_status(job)

    def _on_job_log(self, job_id, line):
        if job_id == self.selected_job_id:
            self.log_queue.put(line)

    def _drain_log_queue(self):
        while True:
            try: item = self.log_queue.get_nowait()
            except queue.Empty: break
            if item.startswith("__REFRESH__:"):
                completed_job_id = item.split(":", 1)[1]
                if completed_job_id == self.processing_job_id:
                    self.processing_job_id = None
                    self.is_processing = False
                    self.start_button.setEnabled(True)
                self._update_processing_indicator()
                job = job_store.get_job(self.selected_job_id) if self.selected_job_id else None
                self._refresh_jobs()
                if job: self._set_job_status(job)
                elif self.selected_job_id in self.deleted_job_ids: self._clear_selected_job()
            else: self._append_log(item)

    def _poll_jobs(self):
        processing = job_store.get_job(self.processing_job_id) if self.processing_job_id else None
        if processing and processing.status in {"done", "failed", "cancelled"}:
            self.processing_job_id = None
            self.is_processing = False
            self.start_button.setEnabled(True)
        self._update_processing_indicator()
        if self.selected_job_id:
            job = job_store.get_job(self.selected_job_id)
            if job: self._set_job_status(job)
            elif self.selected_job_id in self.deleted_job_ids: self._clear_selected_job()

    def _set_job_status(self, job):
        self.status_text.setText(f"{job.original_filename} | {job.status}")
        self.step_text.setText(f"Step: {job.step}")
        self.progress.setValue(job.progress)
        self.progress_text.setText(f"{job.progress}%")
        if job.job_id == self.processing_job_id and job.status in {"done", "failed", "cancelled"}:
            self.processing_job_id = None
            self.is_processing = False
            self.start_button.setEnabled(True)
        self._update_processing_indicator()
        if job.status == "done":
            output_path = job.files.get("final_video")
            if output_path and os.path.exists(output_path) and self.output_preview_editor and self.output_preview_editor.isVisible():
                self.output_preview_editor.set_source(output_path)

    def _append_log(self, line):
        self.log_text.appendPlainText(line)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _update_processing_indicator(self):
        processing = job_store.get_job(self.processing_job_id) if self.processing_job_id else None
        if processing:
            self.processing_text.setText(f"Processing: {processing.original_filename} | {processing.status}")
        else:
            self.processing_text.setText("Processing: none")

    def _clear_logs(self): self.log_text.clear()

    def _load_job_logs(self, job_id):
        path = job_store.get_job_logs_path(job_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file: self.log_text.setPlainText(file.read())
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _selected_job_id(self):
        row = self.history.currentRow()
        item = self.history.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _refresh_jobs(self):
        selected = self.selected_job_id or self._selected_job_id()
        jobs = job_store.list_jobs()[:30]
        self.history.blockSignals(True)
        self.history.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            for column, value in enumerate((job.original_filename, job.mode, job.status, job.updated_at)):
                item = QTableWidgetItem(str(value))
                if column == 0: item.setData(Qt.ItemDataRole.UserRole, job.job_id)
                self.history.setItem(row, column, item)
            if job.job_id == selected: self.history.selectRow(row)
        self.history.blockSignals(False)

    def _select_history_job(self):
        job_id = self._selected_job_id()
        job = job_store.get_job(job_id) if job_id else None
        if job:
            self.selected_job_id = job_id
            self._set_job_status(job)
            self._load_job_preview(job)
            self._clear_logs()
            self._load_job_logs(job_id)

    def _load_job_preview(self, job):
        self.subtitle_position_x = job.subtitle_style.position_x_percent
        self.subtitle_position_y = job.subtitle_style.position_y_percent
        self.caption_font_size = job.subtitle_style.font_size
        self.subtitle_box_width = job.subtitle_style.box_width_percent
        self.subtitle_box_height = job.subtitle_style.box_height_percent
        if self.input_preview_editor and self.input_preview_editor.isVisible():
            self.input_preview_editor.set_source(job.files.get("video_input"))
            self.input_preview_editor.set_edit_state(
                self.subtitle_position_x,
                self.subtitle_position_y,
                self.subtitle_box_width,
                self.subtitle_box_height,
                self.caption_font_size,
            )
        output_path = job.files.get("final_video")
        if output_path and os.path.exists(output_path) and self.output_preview_editor and self.output_preview_editor.isVisible():
            self.output_preview_editor.set_source(output_path)

    def _delete_selected_job(self):
        job_id = self._selected_job_id()
        if not job_id:
            QMessageBox.information(self, "No job selected", "Select a job in Recent Jobs first.")
            return
        job = job_store.get_job(job_id)
        label = job.original_filename if job else job_id
        if QMessageBox.question(self, "Delete job", f"Delete this job and all generated files?\n\n{label}\n\nIf it is running, it will be stopped first.") != QMessageBox.StandardButton.Yes: return
        if job and job.status == "processing":
            cancel_job(job_id)
            job_store.update_job(job_id, status="cancelled", error=None, step="cancelled")
        self.deleted_job_ids.add(job_id)
        try: deleted = job_store.delete_job(job_id)
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        if not deleted: QMessageBox.information(self, "Already removed", "Job folder is already gone.")
        if self.processing_job_id == job_id:
            self.processing_job_id = None
            self.is_processing = False
            self.start_button.setEnabled(True)
            self._update_processing_indicator()
        if self.selected_job_id == job_id:
            self._clear_selected_job()
        self._refresh_jobs()

    def _clear_selected_job(self):
        self.selected_job_id = None
        self.status_text.setText("Ready")
        self.step_text.setText("pending")
        self.progress.setValue(0)
        self.progress_text.setText("0%")
        self._clear_logs()

    def _open_output(self):
        job = job_store.get_job(self.selected_job_id) if self.selected_job_id else None
        path = job.files.get("final_video") if job else None
        if path and os.path.exists(path): self._open_path(path)
        else: QMessageBox.information(self, "Output unavailable", "Final video is not available yet.")

    def _open_active_job_folder(self):
        if self.selected_job_id: self._open_path(job_store.get_job_dir(self.selected_job_id))

    def _show_diagnostics(self):
        status = "OK" if is_ffmpeg_available() else "Missing"
        text = "\n".join((f"FFmpeg: {status}", get_ffmpeg_version(), f"Storage: {STORAGE_DIR}", f"App data: {APP_DATA_DIR}", f"Logs: {LOGS_DIR}", f"Cache: {CACHE_DIR}", f"Bin: {BIN_DIR}", f"Translator: {TRANSLATOR_PROVIDER}", f"Whisper model: {WHISPER_MODEL}"))
        QMessageBox.information(self, "Diagnostics", text)

    @staticmethod
    def _open_path(path):
        if path:
            if os.name == "nt": os.startfile(path)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])

    def closeEvent(self, event):
        unsubscribe_log(self._on_job_log)
        event.accept()
