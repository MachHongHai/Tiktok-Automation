# Auto Dub Video Local Desktop

Ứng dụng desktop Windows để tự động lồng tiếng và chèn phụ đề tiếng Việt cho video.

```text
Import video -> tách audio -> nhận dạng giọng nói -> dịch phụ đề -> tạo TTS -> đồng bộ timeline -> render video
```

Ứng dụng chạy bằng Python desktop GUI, không cần Node.js, React, Vite, FastAPI hoặc trình duyệt.

## Cấu Trúc Dự Án

```text
auto-dub-video-local/
  autodub_desktop.py          Entry point chạy app desktop
  src/autodub/                Source package chính
    desktop/                  GUI tkinter/ttk
    core/                     Runtime path, logging, event nội bộ
    schemas/                  Pydantic models
    services/                 Job store, translation, Ollama runtime
    pipeline/                 Audio/video/STT/TTS/render pipeline
    utils/                    FFmpeg, timecode, file helpers
  runtime/bin/                FFmpeg, FFprobe, Ollama binaries
  scripts/                    Script cài, chạy, build, test
  requirements.txt            Python dependencies
  .env                        Cấu hình local
  .venv/                      Virtual environment local
  .cache/                     Model/cache local
  storage/                    Job output khi chạy từ source
```

Khi chạy từ `.exe`, dữ liệu người dùng mặc định nằm trong:

```text
%LOCALAPPDATA%\AutoDubVideoLocal\
  storage\jobs\
  logs\app.log
  .cache\
```

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
TRANSLATOR_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11435
OLLAMA_MODEL=qwen2.5:7b
```

Provider hiện có:

- `mock`: giữ nguyên text, dùng để test pipeline.
- `openai_compatible`: gọi API tương thích OpenAI, dễ deploy.
- `ollama`: chạy LLM local, offline nhưng nặng hơn.

## Logging

- App log: `%LOCALAPPDATA%\AutoDubVideoLocal\logs\app.log`
- Job log: `storage\jobs\<job_id>\logs.txt`

Panel Logs trong GUI hiển thị realtime log của job đang chạy.

## Ghi Chú

- Node.js không còn cần cho runtime.
- Không nên nhét model lớn trực tiếp vào executable.
- Muốn test nhanh khi sửa code: chạy `.\scripts\run-desktop.ps1`.
- Chỉ build lại `.exe` khi muốn phát hành bản mới.
