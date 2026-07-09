# Auto Dub Video Local Desktop

Ứng dụng desktop Windows để tự động lồng tiếng và chèn phụ đề tiếng Việt cho video.

Pipeline chính:

```text
Import video -> tách audio -> nhận dạng giọng nói -> dịch phụ đề -> tạo giọng TTS -> đồng bộ timeline -> render video
```

Ứng dụng hiện chạy bằng giao diện desktop Python, không cần Node.js, React, Vite hoặc trình duyệt để sử dụng.

## Cấu Trúc Dự Án

```text
auto-dub-video-local/
  desktop_app.py              Entry point chạy desktop app
  backend/
    app/
      desktop/                Giao diện desktop tkinter/ttk
      core/                   Runtime path, logging, event nội bộ
      schemas/                Pydantic models
      services/               Job store, dịch thuật, Ollama runtime
      pipeline/               Các bước xử lý video/audio/subtitle/TTS
      utils/                  Helper FFmpeg, timecode, file
    requirements.txt
  scripts/
    install-desktop-env.ps1   Tạo venv và cài dependency
    run-desktop.ps1           Chạy app desktop từ source
    build-exe.ps1             Build file .exe bằng PyInstaller
  docs/
  storage/                    Job output khi chạy từ source
```

Khi chạy từ file `.exe`, dữ liệu người dùng sẽ nằm trong:

```text
%LOCALAPPDATA%\AutoDubVideoLocal\
  storage\jobs\
  logs\app.log
  .cache\
```

## Cài Đặt Chạy Từ Source

Yêu cầu:

- Windows 10/11
- Python 3.10+
- FFmpeg và FFprobe, hoặc đặt binary trong `backend/bin`

Chạy:

```powershell
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

Nếu không dùng script:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
cd ..
python desktop_app.py
```

## Build File EXE

```powershell
.\scripts\install-desktop-env.ps1
.\scripts\build-exe.ps1
```

Kết quả nằm trong:

```text
dist\AutoDubVideoLocal\AutoDubVideoLocal.exe
```

Khuyến nghị dùng `--onedir` thay vì `--onefile` vì PyTorch, WhisperX và Demucs có nhiều dependency lớn.

## Cấu Hình Dịch

Tạo file `.env` trong `backend/` hoặc `%LOCALAPPDATA%\AutoDubVideoLocal\.env`.

```env
TRANSLATOR_PROVIDER=openai_compatible
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Các provider hiện có:

- `mock`: giữ nguyên text, dùng để test pipeline.
- `openai_compatible`: gọi API tương thích OpenAI, dễ deploy nhất.
- `ollama`: chạy local LLM qua Ollama, phù hợp offline nhưng nặng hơn.

Ví dụ Ollama:

```env
TRANSLATOR_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
```

## Logging Và Debug

Ứng dụng có 2 lớp log:

- App log: `%LOCALAPPDATA%\AutoDubVideoLocal\logs\app.log`
- Job log: `storage\jobs\<job_id>\logs.txt`

Trong giao diện desktop, panel Logs hiển thị realtime các dòng từ job đang chạy. Nút Diagnostics cho biết trạng thái FFmpeg, đường dẫn storage, cache, bin và cấu hình model hiện tại.

## Ghi Chú Deploy

- Node.js không còn cần cho runtime.
- FFmpeg nên được bundle trong `backend/bin` trước khi build.
- Không nên nhét model Ollama/Whisper/Demucs lớn vào `.exe`; nên để app tải/cache ở lần chạy đầu.
- Nếu muốn bản nhẹ để test, tắt audio separation và dùng `openai_compatible` thay vì Ollama local.
