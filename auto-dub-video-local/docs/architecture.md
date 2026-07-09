# Desktop Architecture

## Mục Tiêu

Dự án đã chuyển từ web app sang desktop app chạy local. Giao diện desktop gọi trực tiếp pipeline Python, không còn cần FastAPI, React, Vite hoặc Node.js trong đường chạy chính.

## Luồng Chạy

```text
desktop_app.py
  -> app.desktop.main
  -> app.desktop.ui.AutoDubDesktopApp
  -> app.services.desktop_jobs.create_desktop_job
  -> app.pipeline.process_job.process_job_sync
  -> storage/jobs/<job_id>/
```

## Module Chính

```text
backend/app/
  desktop/        GUI tkinter/ttk, worker thread, realtime logs
  core/           Path runtime, app log, event bus nội bộ
  schemas/        JobConfig, JobInfo, SubtitleStyle
  services/       Job store, translation providers, Ollama runtime
  pipeline/       Audio/video/STT/TTS/render steps
  utils/          FFmpeg/timecode/file helpers
```

## Logging

`services.job_store.log_to_job()` là điểm log chuẩn cho pipeline.

Mỗi dòng log được:

1. Ghi vào `storage/jobs/<job_id>/logs.txt`.
2. Phát qua `core.events.emit_log()`.
3. GUI nhận event và append vào panel Logs realtime.

App-level crash/startup log nằm ở:

```text
%LOCALAPPDATA%\AutoDubVideoLocal\logs\app.log
```

## Runtime Path

`core.paths` phân biệt source mode và frozen exe mode:

- Source mode: storage nằm trong project.
- EXE mode: storage/cache/logs nằm trong `%LOCALAPPDATA%\AutoDubVideoLocal`.

FFmpeg/Ollama binary được tìm theo thứ tự:

1. `BIN_DIR` env nếu có.
2. `backend/bin`.
3. `runtime/bin`.
4. `bin` cạnh app.

## Đóng Gói EXE

Script chính:

```powershell
.\scripts\build-exe.ps1
```

Build dùng PyInstaller `--onedir` để ổn định với PyTorch/WhisperX/Demucs.

Không khuyến nghị `--onefile` cho bản hiện tại vì startup chậm, file lớn và dễ lỗi native dependency.

## Hướng Tối Ưu Tiếp Theo

- Thay WhisperX bằng `faster-whisper` nếu cần bản `.exe` nhẹ hơn.
- Tắt Demucs mặc định cho bản test nhẹ.
- Thêm settings screen để sửa `.env` trong GUI.
- Thêm nút export diagnostics zip gồm `app.log`, `job.json`, `logs.txt`.
