# Desktop Architecture

## Layout

```text
src/autodub/
  desktop/      GUI PySide6 + QML/Qt Quick, desktop worker
    qml/        QML screens, theme singleton, reusable controls
  core/         Path runtime, logging, event bus
  schemas/      Pydantic DTOs
  services/     Job store and HY-MT2 translation worker
  pipeline/     Audio/video processing steps
  utils/        Shared helpers
```

## Luồng Chạy

```text
autodub_desktop.py
  -> autodub.desktop.main
  -> autodub.desktop.qml_controller.AutoDubController
  -> desktop/qml/Main.qml
  -> autodub.services.desktop_jobs.create_desktop_job
  -> autodub.pipeline.process_job.process_job_sync
  -> %LOCALAPPDATA%/AutoDubVideoLocal/data/jobs/<job_id>/
```

## Runtime Paths

Source and EXE mode:

```text
%LOCALAPPDATA%\AutoDubVideoLocal\data\
  cache/
  logs/
  jobs/
```

Set `RUNTIME_DATA_DIR` to an absolute path such as `D:\AutoDubData` to store all mutable user data on another drive. Relative runtime paths are resolved inside the app data directory, never inside the source tree or executable bundle.

`scripts/migrate-runtime-data.ps1` moves legacy `project/data` only when run with the explicit `-Move` flag, so large model caches are not moved unexpectedly during app startup.

`runtime/bin` chứa FFmpeg và FFprobe khi chạy từ source. Khi build, thư mục này được bundle vào `_internal/bin`.

## Logging

`services.job_store.log_to_job()` là điểm log chuẩn cho pipeline:

1. Ghi vào `%LOCALAPPDATA%/AutoDubVideoLocal/data/jobs/<job_id>/logs.txt`.
2. Emit qua `core.events`.
3. GUI append realtime vào panel Logs.

## Translation Engines

The translation engine is selected per job and stored as `translator_provider` in the job metadata, so benchmarks remain attributable after the job finishes.

- `hymt2`: `tencent/Hy-MT2-1.8B`, runs locally in a dedicated worker when a job reaches translation. Its Hugging Face files are cached under `HF_HOME`; the worker exits after each job to release VRAM and isolate native Torch failures from the Qt GUI.

HY-MT2 receives the target language plus a short window of previous subtitle lines as context, then returns one translation for each subtitle segment.

Demucs is opt-in for new jobs. Use it when music or noisy background competes with the speaker; leave it disabled for clear speech to shorten the pipeline.

## Video Preview

`desktop/qml/PreviewWindow.qml` owns the Qt Multimedia input/output preview UI. It uses `MediaPlayer` and `VideoOutput` in QML. A single subtitle box is moved/resized in the input preview, and the final position/font size are saved through `AutoDubController.updatePreviewEdits()`. FFmpeg reproduces them using a temporary positioned ASS subtitle file during render.

## UI Framework

The main dashboard uses PySide6 + QML/Qt Quick Controls:

- `desktop.main` creates `QQmlApplicationEngine`.
- `desktop.qml_controller.AutoDubController` exposes jobs, settings, logs, and commands to QML.
- `desktop/qml/Theme.qml` owns visual tokens.
- `desktop/qml/Main.qml` composes a dark production-studio shell with `Create`, `Batch`, and `Jobs` navigation; `Job Detail` returns to the workspace that opened it.
- `CreateJobPage.qml` separates source media, dubbing setup, and current processing status.
- `BatchPage.qml` displays a thumbnail queue and runs queued jobs sequentially through the same pipeline worker.
- `JobsPage.qml` uses dense, scannable rows; `JobDetailPage.qml` separates run controls from the activity log.
- `desktop/qml/PreviewWindow.qml` provides the QML preview/editor window.
- Job creation is full-auto only in the desktop UI.

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
