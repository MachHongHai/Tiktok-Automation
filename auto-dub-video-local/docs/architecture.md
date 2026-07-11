# Desktop Architecture

## Layout

```text
src/autodub/
  desktop/      GUI PySide6 / Qt Widgets và desktop worker
  core/         Path runtime, logging, event bus
  schemas/      Pydantic DTOs
  services/     Job store, translator providers, Ollama runtime
  pipeline/     Audio/video processing steps
  utils/        Shared helpers
```

## Luồng Chạy

```text
autodub_desktop.py
  -> autodub.desktop.main
  -> autodub.desktop.ui.AutoDubDesktopApp
  -> autodub.services.desktop_jobs.create_desktop_job
  -> autodub.pipeline.process_job.process_job_sync
  -> data/jobs/<job_id>/
```

## Runtime Paths

Source mode:

```text
.env
data/cache/
data/logs/
runtime/bin/
data/jobs/
```

EXE mode:

```text
%LOCALAPPDATA%\AutoDubVideoLocal\data\
  cache/
  logs/
  models/ollama/
  jobs/
```

`runtime/bin` chứa FFmpeg, FFprobe và Ollama binaries khi chạy từ source. Khi build, thư mục này được bundle vào `_internal/bin`.

## Logging

`services.job_store.log_to_job()` là điểm log chuẩn cho pipeline:

1. Ghi vào `data/jobs/<job_id>/logs.txt`.
2. Emit qua `core.events`.
3. GUI append realtime vào panel Logs.

## Video Preview

`desktop.video_preview` owns the Qt Multimedia input/output players. `PreviewEditorDialog` is a dedicated maximized editor window, so vertical videos never expand the dashboard layout. Crop zoom, pan, and the draggable subtitle position are saved with the job. FFmpeg reproduces them using a temporary positioned ASS subtitle file during render.

## PyInstaller

Script build chính:

```powershell
.\scripts\build-exe.ps1
```

Build dùng `--onedir`. Danh sách `ExcludedModules` trong script chặn PyInstaller gom các package optional không dùng ở runtime desktop.

## Hướng Tối Ưu

- Tách bản Light không Demucs/WhisperX nếu cần bundle nhỏ.
- Cân nhắc `faster-whisper` cho deploy nhẹ hơn.
- Thêm Settings screen để sửa `.env` trong GUI.
- Thêm Export Debug Package để nén log/job diagnostics.
