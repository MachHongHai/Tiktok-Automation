# Auto Dub Video Local

Ứng dụng web chạy localhost giúp tự động hoá quy trình lồng tiếng (dubbing) và chèn phụ đề tiếng Việt cho video thông qua AI: Import video -> Nhận dạng giọng nói (Whisper) -> Dịch thuật phụ đề -> Lồng tiếng tiếng Việt (edge-tts) -> Đồng bộ timeline -> Render xuất video (FFmpeg).

---

## 🛠️ Yêu cầu hệ thống (Windows)

1. **FFmpeg & FFprobe**: Cần thiết để xử lý video và trích xuất/ghép âm thanh.
   * Tải FFmpeg từ [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
   * Giải nén và thêm thư mục `bin` vào biến môi trường **PATH** của hệ thống.
   * Kiểm tra trong cmd/powershell bằng lệnh: `ffmpeg -version` và `ffprobe -version`.
2. **Python 3.10+**: Để chạy backend FastAPI và mô hình AI.
3. **Node.js 18+ & npm**: Để chạy giao diện React (Vite).

---

## 🚀 Hướng dẫn Cài đặt & Chạy ứng dụng

### Cách 1: Chạy trực tiếp trên máy local (Khuyên dùng)

#### 1. Khởi động Backend
Mở một cửa sổ Terminal mới (CMD hoặc Powershell) tại thư mục gốc của project:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
*Lưu ý:* Khi chạy lần đầu tiên, hệ thống sẽ tự động tải mô hình `faster-whisper` (`small` theo mặc định).

#### 2. Khởi động Frontend
Mở một cửa sổ Terminal thứ hai tại thư mục gốc của project:
```bash
cd frontend
npm install
npm run dev
```

#### 3. Truy cập ứng dụng
Truy cập địa chỉ sau trên trình duyệt của bạn:
👉 **[http://localhost:5173](http://localhost:5173)**

---

### Cách 2: Chạy bằng Docker Compose (Yêu cầu cài đặt Docker Desktop)
Nếu bạn có Docker, bạn chỉ cần chạy duy nhất một lệnh tại thư mục gốc:
```bash
docker-compose up --build
```
Hệ thống sẽ tự dựng môi trường Linux chứa FFmpeg, FastAPI, và React Dev server. Truy cập cổng `5173` để sử dụng.

---

## 📖 Cách sử dụng ứng dụng

1. **Upload Video**: Kéo thả hoặc click chọn file video của bạn (`.mp4`, `.mov`, `.mkv`).
2. **Chọn chế độ xử lý (Mode)**:
   * **Mode A (Full Auto)**: Video đầu vào tự động được trích âm thanh -> Transcribe bằng Whisper -> Dịch phụ đề sang Tiếng Việt -> Tạo voice TTS -> Render video final.
   * **Mode B (Use Vietnamese Subtitle)**: Người dùng upload Video + file phụ đề tiếng Việt (`vi.srt`). Hệ thống bỏ qua bước dịch và khớp chính xác giọng TTS theo SRT để render video final.
   * **Mode C (Use Vietnamese Script)**: Người dùng upload Video + kịch bản tiếng Việt (`script_vi.txt`). Hệ thống nói cả kịch bản ra 1 file tiếng, sau đó chạy Whisper trên file tiếng đó để tự sinh phụ đề có timestamp chuẩn, rồi render vào video final.
3. **Cấu hình bổ sung**:
   * **TTS Voice**: Chọn giọng đọc Hoài Mỹ (Nữ) hoặc Nam Minh (Nam).
   * **Output Layout**: Chọn giữ nguyên tỷ lệ, cắt khung dọc 9:16 (TikTok), hoặc scale 9:16 kèm làm mờ 2 bên viền (Blur background).
   * **Style phụ đề**: Điều chỉnh kích thước font chữ, khoảng cách viền dưới (margin bottom), độ dày outline, và độ dài tối đa mỗi dòng.
4. **Bắt đầu pipeline**: Click **Process Video Dub** và theo dõi log chạy trực tiếp trên màn hình Console.
5. **Download kết quả**: Tải video final, file phụ đề `.srt`, file lồng tiếng riêng lẻ `.wav` hoặc kịch bản JSON.

---

## 🔀 Tùy chỉnh API dịch thuật trong `translate.py`

Tệp dịch thuật cốt lõi nằm ở [translate.py](file:///d:/Du-an/Tiktok%20Automation/auto-dub-video-local/backend/app/pipeline/translate.py). Để cấu hình dịch thuật, bạn có thể chỉnh sửa file `.env` ở thư mục `backend/`:

```env
# Options: mock, ollama, openai_compatible
TRANSLATOR_PROVIDER=mock
```

### Các Option Dịch Thuật:

1. **Mock (Mặc định)**:
   * Giữ nguyên ngôn ngữ gốc (Dùng để test pipeline không cần internet/máy chủ dịch).
2. **OpenAI-Compatible (Gọi API dịch của GPT-4, Groq, OpenRouter, DeepSeek)**:
   * Chỉnh sửa trong `.env`:
     ```env
     TRANSLATOR_PROVIDER=openai_compatible
     OPENAI_API_KEY=your-api-key-here
     OPENAI_BASE_URL=https://api.openai.com/v1   # Hoặc endpoint của Groq, DeepSeek...
     OPENAI_MODEL=gpt-3.5-turbo                  # Tên model bạn muốn dùng
     ```
3. **Ollama (Dịch local miễn phí bằng LLM chạy máy của bạn)**:
   * Chỉnh sửa trong `.env`:
     ```env
     TRANSLATOR_PROVIDER=ollama
     OLLAMA_BASE_URL=http://localhost:11434
     OLLAMA_MODEL=qwen2:7b                       # Tên model local đã pull về máy
     ```

### Nơi chỉnh sửa Code / Prompt Dịch Thuật:
Nếu bạn muốn đổi prompt dịch hoặc tích hợp một API dịch tùy chỉnh (ví dụ: Google Translate miễn phí hay API dịch chuyên dụng):
* Mở tệp [translate.py](file:///d:/Du-an/Tiktok%20Automation/auto-dub-video-local/backend/app/pipeline/translate.py).
* Thay đổi Prompt tại dòng:
  ```python
  prompt = f"Dịch và viết lại câu sau sang tiếng Việt tự nhiên, ngắn gọn, hợp video TikTok. Không giải thích, chỉ trả về câu tiếng Việt. Giữ ý chính, tránh câu quá dài. Câu gốc: {text}"
  ```
* Để viết thêm Provider mới: Tạo class kế thừa từ `BaseTranslator`, ghi đè hàm `translate(self, text, job_id)` và đăng ký class đó trong hàm `get_translator()`.
