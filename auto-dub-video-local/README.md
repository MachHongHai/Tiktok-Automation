# Auto Dub Video Local Desktop

Ứng dụng desktop Windows để tự động lồng tiếng và chèn phụ đề tiếng Việt cho video.

```text
Import video -> tách audio -> nhận dạng giọng nói -> dịch phụ đề -> tạo TTS -> đồng bộ timeline -> render video
```

Ứng dụng chạy bằng Python desktop GUI dùng PySide6 + QML/Qt Quick Controls, không cần Node.js, React, Vite, FastAPI hoặc trình duyệt.

## Cấu Trúc Dự Án

```text
auto-dub-video-local/
  autodub_desktop.py          Entry point chạy app desktop
  src/autodub/                Source package chính
    desktop/                  GUI PySide6 + QML/Qt Quick
      qml/                    QML screens, theme tokens, reusable controls
    core/                     Runtime path, logging, event nội bộ
    schemas/                  Pydantic models
    services/                 Job store, HY-MT2 translation worker
    pipeline/                 Audio/video/STT/TTS/render pipeline
    utils/                    FFmpeg, timecode, file helpers
  runtime/bin/                FFmpeg and FFprobe binaries
  scripts/                    Script cài, chạy, build, test
  requirements.txt            Python dependencies
  .env                        Cấu hình local
  .venv/                      Virtual environment local
```

Khi chạy từ source hoặc `.exe`, dữ liệu runtime mặc định nằm ngoài source/bundle:

```text
%LOCALAPPDATA%\AutoDubVideoLocal\data\
  jobs\
  logs\
  cache\
```

Set `RUNTIME_DATA_DIR` to an absolute path such as `D:\AutoDubData` to keep all offline jobs, outputs, logs, thumbnails, and model caches on drive D. Use `scripts\migrate-runtime-data.ps1 -Move` to move legacy `project\data` only after choosing the destination.

## Chạy Từ Source

Yêu cầu:

- Windows 10/11
- Python 3.10+
- FFmpeg/FFprobe trong `runtime/bin`

```powershell
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

Chạy trực tiếp:

```powershell
.\.venv\Scripts\python.exe .\autodub_desktop.py
```

## Build EXE

```powershell
.\scripts\build-exe.ps1
```

Kết quả:

```text
dist\AutoDubVideoLocal\AutoDubVideoLocal.exe
```

Build dùng PyInstaller `--onedir` vì Torch, WhisperX và Demucs có nhiều dependency lớn. Script build đã exclude các dependency optional như Jupyter, TensorBoard, Matplotlib, Pandas, SQLAlchemy, torchvision và yt-dlp.

## Cấu Hình Dịch

Tạo hoặc sửa file `.env` ở root dự án, hoặc `%LOCALAPPDATA%\AutoDubVideoLocal\.env`.

```env
HYMT2_MODEL=tencent/Hy-MT2-1.8B
```

Ứng dụng chỉ dùng `hymt2`: Tencent HY-MT2 1.8B chạy local trong worker riêng. Lần đầu tải khoảng 4 GB vào Hugging Face cache; worker thoát sau mỗi job để trả VRAM và bảo vệ GUI.

## Preview And Captions

- `Preview Subtitle` opens a QML/Qt Quick preview window. A single blue subtitle box starts near the bottom of the video; drag inside to move it or any edge to resize it, with text scaling to match.
- `Output Preview` opens the completed dubbed file in the same QML preview window pattern.
- The SRT compiler splits transcript blocks into short sequential cues, capped at two lines per cue for YouTube/TikTok-style reading.

## UI Framework

- Main dashboard: PySide6 + QML/Qt Quick Controls.
- Design direction: dark production-studio workspace with a neutral palette, compact controls, semantic status colors, and reusable theme tokens.
- Navigation includes `Create`, `Batch`, and `Jobs`; selecting any queue or library item opens its dedicated detail workspace with run status, actions, and a large activity log.
- Preview editor: QML/Qt Quick with Qt Multimedia `MediaPlayer` and `VideoOutput`.
- Job creation: full-auto mode only.
- Batch processing creates all jobs up front, generates a thumbnail for each video, and runs them sequentially to avoid competing for GPU memory.

## Logging

- App log: `%LOCALAPPDATA%\AutoDubVideoLocal\data\logs\app.log`
- Job log: `%LOCALAPPDATA%\AutoDubVideoLocal\data\jobs\<job_id>\logs.txt`

Panel Logs trong GUI hiển thị realtime log của job đang chạy.

## Ghi Chú

- Node.js không còn cần cho runtime.
- Demucs mặc định tắt để xử lý video nói nhanh hơn. Bật `Separate vocals with Demucs before transcription` khi video có nhạc nền hoặc tiếng ồn lấn giọng nói.
- Không nên nhét model lớn trực tiếp vào executable.
- Muốn test nhanh khi sửa code: chạy `.\scripts\run-desktop.ps1`.
- Chỉ build lại `.exe` khi muốn phát hành bản mới.
