import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from autodub.config import APP_DATA_DIR, BIN_DIR, CACHE_DIR, LOGS_DIR, STORAGE_DIR, TRANSLATOR_PROVIDER, WHISPER_MODEL
from autodub.core.events import subscribe_log, unsubscribe_log
from autodub.pipeline.job_manager import cancel_job
from autodub.schemas.job import JobConfig, SubtitleStyle
from autodub.services.desktop_jobs import create_desktop_job
from autodub.services.ollama_runtime import ensure_ollama_running
from autodub.services import job_store
from autodub.utils.ffmpeg import get_ffmpeg_version, is_ffmpeg_available


class AutoDubDesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto Dub Video Local")
        self.geometry("1280x820")
        self.minsize(1100, 720)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.active_job_id: str | None = None
        self.worker_thread: threading.Thread | None = None
        self.is_processing = False
        self.deleted_job_ids: set[str] = set()

        self._init_vars()
        self._configure_style()
        self._build_layout()
        self._refresh_jobs()
        subscribe_log(self._on_job_log)
        self._start_ollama_preload()

        self.after(250, self._drain_log_queue)
        self.after(1000, self._poll_active_job)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_vars(self):
        self.video_path = tk.StringVar()
        self.srt_path = tk.StringVar()
        self.script_path = tk.StringVar()
        self.mode = tk.StringVar(value="A")
        self.source_language = tk.StringVar(value="auto")
        self.target_language = tk.StringVar(value="vi")
        self.tts_voice = tk.StringVar(value="vi-VN-HoaiMyNeural")
        self.output_format = tk.StringVar(value="keep_ratio")
        self.font_size = tk.IntVar(value=14)
        self.margin_bottom = tk.IntVar(value=40)
        self.outline = tk.IntVar(value=2)
        self.max_chars_per_line = tk.IntVar(value=32)
        self.enable_audio_separation = tk.BooleanVar(value=True)
        self.original_video_volume = tk.IntVar(value=60)

        self.status_text = tk.StringVar(value="Ready")
        self.progress_text = tk.StringVar(value="0%")
        self.step_text = tk.StringVar(value="pending")
        self.diagnostics_text = tk.StringVar()

    def _configure_style(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.configure(bg="#f5f7fb")
        self.style.configure("TFrame", background="#f5f7fb")
        self.style.configure("Panel.TFrame", background="#ffffff", borderwidth=1, relief="solid")
        self.style.configure("TLabel", background="#f5f7fb", foreground="#172033", font=("Segoe UI", 10))
        self.style.configure("Panel.TLabel", background="#ffffff", foreground="#172033", font=("Segoe UI", 10))
        self.style.configure("Title.TLabel", background="#f5f7fb", foreground="#101828", font=("Segoe UI Semibold", 18))
        self.style.configure("Section.TLabel", background="#ffffff", foreground="#101828", font=("Segoe UI Semibold", 11))
        self.style.configure("TButton", font=("Segoe UI", 10), padding=(12, 7))
        self.style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(14, 8))
        self.style.configure("Danger.TButton", font=("Segoe UI Semibold", 10), padding=(14, 8))
        self.style.configure("Horizontal.TProgressbar", troughcolor="#e6eaf2", background="#2563eb", thickness=12)

    def _build_layout(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=0, minsize=430)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Auto Dub Video Local", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=f"Desktop mode | Translator: {TRANSLATOR_PROVIDER} | Whisper: {WHISPER_MODEL}",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        ttk.Button(header, text="Open App Data", command=lambda: self._open_path(APP_DATA_DIR)).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(header, text="Diagnostics", command=self._show_diagnostics).grid(row=0, column=2, padx=(8, 0))

        left = ttk.Frame(root, style="Panel.TFrame", padding=14)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(1, weight=1)

        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_inputs(left)
        self._build_status(right)
        self._build_logs(right)
        self._build_history(right)

    def _build_inputs(self, parent):
        row = 0
        ttk.Label(parent, text="Input", style="Section.TLabel").grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row += 1

        row = self._file_row(parent, row, "Video", self.video_path, self._browse_video)
        row = self._file_row(parent, row, "SRT", self.srt_path, self._browse_srt)
        row = self._file_row(parent, row, "Script", self.script_path, self._browse_script)

        ttk.Separator(parent).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
        row += 1

        ttk.Label(parent, text="Mode", style="Section.TLabel").grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1
        modes = [
            ("Full Auto", "A"),
            ("Use Vietnamese SRT", "B"),
            ("Use Vietnamese Script", "C"),
        ]
        for label, value in modes:
            ttk.Radiobutton(parent, text=label, value=value, variable=self.mode).grid(row=row, column=0, columnspan=3, sticky="w", pady=2)
            row += 1

        ttk.Separator(parent).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
        row += 1

        ttk.Label(parent, text="Settings", style="Section.TLabel").grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        row = self._combo_row(parent, row, "Source", self.source_language, ["auto", "en", "zh", "vi"])
        row = self._combo_row(parent, row, "Voice", self.tts_voice, ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"])
        row = self._combo_row(parent, row, "Layout", self.output_format, ["keep_ratio", "tiktok_9_16_crop", "blur_background_9_16"])
        row = self._spin_row(parent, row, "Font size", self.font_size, 8, 64)
        row = self._spin_row(parent, row, "Bottom margin", self.margin_bottom, 0, 300)
        row = self._spin_row(parent, row, "Outline", self.outline, 0, 8)
        row = self._spin_row(parent, row, "Max chars", self.max_chars_per_line, 12, 80)

        ttk.Checkbutton(parent, text="Separate vocals for transcription with Demucs", variable=self.enable_audio_separation).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(8, 2)
        )
        row += 1

        ttk.Label(parent, text="Original volume", style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Scale(parent, from_=0, to=100, orient="horizontal", variable=self.original_video_volume).grid(row=row, column=1, sticky="ew", padx=8)
        ttk.Label(parent, textvariable=self.original_video_volume, style="Panel.TLabel", width=4).grid(row=row, column=2, sticky="e")
        row += 1

        ttk.Separator(parent).grid(row=row, column=0, columnspan=3, sticky="ew", pady=14)
        row += 1

        ttk.Button(parent, text="Create & Process", style="Accent.TButton", command=self._start_job).grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8)
        )
        row += 1
        ttk.Button(parent, text="Stop Active Job", style="Danger.TButton", command=self._stop_job).grid(row=row, column=0, columnspan=3, sticky="ew")

    def _build_status(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="Current Job", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, textvariable=self.status_text, style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 2))
        ttk.Label(panel, textvariable=self.step_text, style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.progress = ttk.Progressbar(panel, orient="horizontal", mode="determinate", maximum=100)
        self.progress.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(panel, textvariable=self.progress_text, style="Panel.TLabel").grid(row=3, column=1, sticky="e", padx=(10, 0))

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="Open Output", command=self._open_output).pack(side="left")
        ttk.Button(buttons, text="Open Job Folder", command=self._open_active_job_folder).pack(side="left", padx=8)
        ttk.Button(buttons, text="Refresh", command=self._refresh_jobs).pack(side="left")

    def _build_logs(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(row=1, column=0, sticky="nsew", pady=14)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        ttk.Label(panel, text="Logs", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.log_text = tk.Text(panel, wrap="word", height=18, bg="#0f172a", fg="#dbeafe", insertbackground="#dbeafe", relief="flat")
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(panel, command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def _build_history(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(row=2, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="Recent Jobs", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        toolbar = ttk.Frame(panel, style="Panel.TFrame")
        toolbar.grid(row=0, column=1, sticky="e", pady=(0, 8))
        ttk.Button(toolbar, text="Delete Job", style="Danger.TButton", command=self._delete_selected_job).pack(side="left")

        columns = ("file", "mode", "status", "updated")
        self.history = ttk.Treeview(panel, columns=columns, show="headings", height=6)
        self.history.heading("file", text="File")
        self.history.heading("mode", text="Mode")
        self.history.heading("status", text="Status")
        self.history.heading("updated", text="Updated")
        self.history.column("file", width=360)
        self.history.column("mode", width=80, anchor="center")
        self.history.column("status", width=110, anchor="center")
        self.history.column("updated", width=180, anchor="center")
        self.history.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.history.bind("<<TreeviewSelect>>", self._select_history_job)

    def _file_row(self, parent, row, label, variable, command):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8)
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2, sticky="e")
        return row + 1

    def _combo_row(self, parent, row, label, variable, values):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly").grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        return row + 1

    def _spin_row(self, parent, row, label, variable, start, end):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Spinbox(parent, textvariable=variable, from_=start, to=end, width=8).grid(row=row, column=1, sticky="w", padx=8)
        return row + 1

    def _browse_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mov *.mkv"), ("All files", "*.*")])
        if path:
            self.video_path.set(path)

    def _browse_srt(self):
        path = filedialog.askopenfilename(filetypes=[("Subtitle files", "*.srt"), ("All files", "*.*")])
        if path:
            self.srt_path.set(path)

    def _browse_script(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.script_path.set(path)

    def _build_config(self) -> JobConfig:
        return JobConfig(
            mode=self.mode.get(),
            source_language=self.source_language.get(),
            target_language=self.target_language.get(),
            tts_voice=self.tts_voice.get(),
            subtitle_style=SubtitleStyle(
                font_size=self.font_size.get(),
                margin_bottom=self.margin_bottom.get(),
                outline=self.outline.get(),
                max_chars_per_line=self.max_chars_per_line.get(),
            ),
            output_format=self.output_format.get(),
            enable_audio_separation=self.enable_audio_separation.get(),
            original_video_volume=self.original_video_volume.get(),
        )

    def _start_ollama_preload(self):
        thread = threading.Thread(target=lambda: ensure_ollama_running(warm_model=True), daemon=True)
        thread.start()

    def _start_job(self):
        if self.is_processing:
            messagebox.showwarning("Job running", "A job is already processing.")
            return
        if not self.video_path.get():
            messagebox.showerror("Missing video", "Please choose an input video.")
            return

        try:
            job = create_desktop_job(
                self.video_path.get(),
                self._build_config(),
                self.srt_path.get() or None,
                self.script_path.get() or None,
            )
        except Exception as exc:
            messagebox.showerror("Cannot create job", str(exc))
            return

        self.active_job_id = job.job_id
        self.is_processing = True
        self._clear_logs()
        self._load_job_logs(job.job_id)
        self._set_job_status(job)

        self.worker_thread = threading.Thread(target=self._run_pipeline, args=(job.job_id,), daemon=True)
        self.worker_thread.start()
        self._refresh_jobs()

    def _run_pipeline(self, job_id: str):
        try:
            from autodub.pipeline.process_job import process_job_sync

            process_job_sync(job_id)
        except Exception as exc:
            if job_id in self.deleted_job_ids:
                return
            message = f"Desktop worker failed before pipeline could start: {exc}"
            job_store.log_to_job(job_id, message)
            job_store.update_job(job_id, status="failed", error=str(exc), step="failed")
            self.log_queue.put(message)
        finally:
            self.log_queue.put("__REFRESH__")

    def _stop_job(self):
        if not self.active_job_id:
            return
        if messagebox.askyesno("Stop job", "Stop the active job?"):
            cancel_job(self.active_job_id)

    def _on_job_log(self, job_id: str, line: str):
        if job_id == self.active_job_id:
            self.log_queue.put(line)

    def _drain_log_queue(self):
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if item == "__REFRESH__":
                self.is_processing = False
                self._refresh_jobs()
                if self.active_job_id:
                    job = job_store.get_job(self.active_job_id)
                    if job:
                        self._set_job_status(job)
                    elif self.active_job_id in self.deleted_job_ids:
                        self._clear_active_job()
            else:
                self._append_log(item)
        self.after(250, self._drain_log_queue)

    def _poll_active_job(self):
        if self.active_job_id:
            job = job_store.get_job(self.active_job_id)
            if job:
                self._set_job_status(job)
            elif self.active_job_id in self.deleted_job_ids:
                self._clear_active_job()
        self.after(1000, self._poll_active_job)

    def _set_job_status(self, job):
        self.status_text.set(f"{job.original_filename} | {job.status}")
        self.step_text.set(f"Step: {job.step}")
        self.progress["value"] = job.progress
        self.progress_text.set(f"{job.progress}%")
        if job.status in {"done", "failed"}:
            self.is_processing = False

    def _append_log(self, line: str):
        self.log_text.insert("end", f"{line}\n")
        self.log_text.see("end")

    def _clear_logs(self):
        self.log_text.delete("1.0", "end")

    def _load_job_logs(self, job_id: str):
        log_path = job_store.get_job_logs_path(job_id)
        if not os.path.exists(log_path):
            return
        with open(log_path, "r", encoding="utf-8") as f:
            self.log_text.insert("end", f.read())
            self.log_text.see("end")

    def _refresh_jobs(self):
        selected = self.history.selection()
        for item in self.history.get_children():
            self.history.delete(item)
        for job in job_store.list_jobs()[:30]:
            self.history.insert("", "end", iid=job.job_id, values=(job.original_filename, job.mode, job.status, job.updated_at))
        for job_id in selected:
            if self.history.exists(job_id):
                self.history.selection_set(job_id)

    def _select_history_job(self, _event):
        selected = self.history.selection()
        if not selected:
            return
        job_id = selected[0]
        job = job_store.get_job(job_id)
        if not job:
            return
        self.active_job_id = job_id
        self._set_job_status(job)
        self._clear_logs()
        self._load_job_logs(job_id)

    def _delete_selected_job(self):
        selected = self.history.selection()
        if not selected:
            messagebox.showinfo("No job selected", "Select a job in Recent Jobs first.")
            return

        job_id = selected[0]
        job = job_store.get_job(job_id)
        label = job.original_filename if job else job_id
        if not messagebox.askyesno(
            "Delete job",
            f"Delete this job and all generated files?\n\n{label}\n\nIf it is running, it will be stopped first.",
        ):
            return

        if job and job.status == "processing":
            cancel_job(job_id)

        self.deleted_job_ids.add(job_id)

        try:
            deleted = job_store.delete_job(job_id)
        except Exception as exc:
            messagebox.showerror("Delete failed", str(exc))
            return

        if not deleted:
            messagebox.showinfo("Already removed", "Job folder is already gone.")

        if self.active_job_id == job_id:
            self._clear_active_job()

        self._refresh_jobs()

    def _clear_active_job(self):
        self.active_job_id = None
        self.is_processing = False
        self.status_text.set("Ready")
        self.step_text.set("pending")
        self.progress["value"] = 0
        self.progress_text.set("0%")
        self._clear_logs()

    def _open_output(self):
        job = job_store.get_job(self.active_job_id) if self.active_job_id else None
        path = job.files.get("final_video") if job else None
        if path and os.path.exists(path):
            self._open_path(path)
        else:
            messagebox.showinfo("Output unavailable", "Final video is not available yet.")

    def _open_active_job_folder(self):
        if not self.active_job_id:
            return
        self._open_path(job_store.get_job_dir(self.active_job_id))

    def _show_diagnostics(self):
        ffmpeg_status = "OK" if is_ffmpeg_available() else "Missing"
        text = "\n".join(
            [
                f"FFmpeg: {ffmpeg_status}",
                get_ffmpeg_version(),
                f"Storage: {STORAGE_DIR}",
                f"App data: {APP_DATA_DIR}",
                f"Logs: {LOGS_DIR}",
                f"Cache: {CACHE_DIR}",
                f"Bin: {BIN_DIR}",
                f"Translator: {TRANSLATOR_PROVIDER}",
                f"Whisper model: {WHISPER_MODEL}",
            ]
        )
        messagebox.showinfo("Diagnostics", text)

    def _open_path(self, path: str):
        if not path:
            return
        if os.name == "nt":
            os.startfile(path)
        else:
            import subprocess

            subprocess.Popen(["xdg-open", path])

    def _on_close(self):
        unsubscribe_log(self._on_job_log)
        self.destroy()

