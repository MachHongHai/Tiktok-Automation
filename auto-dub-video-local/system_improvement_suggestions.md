# Đề xuất cải tiến hệ thống Tiktok Automation Dubbing (Local)

Tài liệu này tổng hợp các đề xuất cải tiến kỹ thuật cho hệ thống lồng tiếng tự động nhằm tối ưu hóa chất lượng sản phẩm đầu ra, tăng tốc độ xử lý và cải thiện trải nghiệm người dùng.

---

## 1. Chất lượng âm thanh & Lồng tiếng (Audio & Voice)

### 1.1. Thuật toán né tiếng thông minh (Auto Ducking)
* **Hiện trạng:** Video gốc/nhạc đệm bị giảm âm lượng cố định xuyên suốt toàn bộ thời lượng video.
* **Giải pháp:** Áp dụng kỹ thuật **Ducking**. Tự động phân tích mốc thời gian của giọng đọc:
  - Khi có giọng lồng tiếng phát ra: Giảm âm lượng video gốc xuống mức thấp (ví dụ: -20dB).
  - Khi có khoảng lặng (không có giọng đọc): Tự động tăng âm lượng video gốc lên lại mức bình thường (0dB hoặc mức cấu hình) để giữ tiếng động hiện trường sống động.
* **Công cụ hỗ trợ:** FFmpeg filter `sidechaincompress` hoặc xử lý trực tiếp tín hiệu biên độ sóng bằng `pydub`.

### 1.2. Lồng tiếng phân vai tự động (Multi-speaker Dubbing)
* **Hiện trạng:** Toàn bộ video chỉ sử dụng một giọng đọc duy nhất cho tất cả các nhân vật.
* **Giải pháp:** Tận dụng tính năng nhận diện người nói (Speaker Diarization) của WhisperX/Pyannote:
  - Phân nhóm các câu thoại theo ID người nói (Speaker 0, Speaker 1,...).
  - Áp dụng các giọng đọc nam/nữ hoặc tone giọng khác nhau từ Edge-TTS tương ứng với từng ID nhân vật.

---

## 2. Trải nghiệm người dùng & Quy trình làm việc (UX & Workflow)

### 2.1. Biên tập trung gian (Interactive Dubbing Workflow)
* **Hiện trạng:** Quy trình chạy tự động hoàn toàn từ đầu đến cuối, người dùng không thể can thiệp vào bản dịch hay mốc thời gian bị lệch.
* **Giải pháp:** Chia nhỏ quy trình xử lý thành 2 giai đoạn:
  - **Giai đoạn 1 (Phân tích & Dịch):** Hệ thống trích xuất âm thanh, dịch thuật và xuất ra giao diện biên tập phụ đề. Người dùng có thể sửa đổi nội dung dịch, căn chỉnh lại mốc thời gian (timeline), chọn giọng đọc cho từng câu.
  - **Giai đoạn 2 (Render):** Người dùng nhấn "Hoàn tất" để hệ thống tổng hợp giọng đọc (TTS) và ghép nối thành video cuối cùng.

### 2.2. Kiểm soát tác vụ triệt để (Process Management)
* **Hiện trạng:** Việc nhấn dừng tác vụ (Cancel) chưa giải phóng hoàn toàn các tiến trình nặng đang chạy ngầm như Demucs hay FFmpeg.
* **Giải pháp:** Triển khai cơ chế quản lý vòng đời tiến trình con:
  - Lưu trữ PID của tất cả các tiến trình con được sinh ra từ python (`subprocess.Popen`).
  - Khi nhận tín hiệu hủy tác vụ, thực hiện lệnh kết thúc toàn bộ cây tiến trình (`taskkill /F /T /PID` trên Windows) để giải phóng tài nguyên CPU/GPU ngay lập tức.

---

## 3. Hiệu năng & Tối ưu hóa tài nguyên (Performance)

### 3.1. Cơ chế giữ nóng mô hình AI (Model Warmup & Caching Service)
* **Hiện trạng:** Mỗi lượt chạy Job lại tiến hành nạp (load) và giải phóng (unload) các mô hình AI lớn của WhisperX và Demucs vào VRAM GPU, gây hao phí khoảng 10–15 giây cho mỗi video.
* **Giải pháp:** Thiết lập một Service chạy ngầm để duy trì các mô hình này trên VRAM đối với những trường hợp người dùng xử lý video hàng loạt (Batch Processing).

### 3.2. Chuyển đổi âm thanh song song (Parallel TTS Requests)
* **Hiện trạng:** Việc gửi yêu cầu tổng hợp giọng đọc tới Edge-TTS đang được thực hiện tuần tự hoặc batch nhỏ.
* **Giải pháp:** Tận dụng thư viện `asyncio` để gửi đồng thời (Parallel) tất cả các phân đoạn cần thuyết minh lên máy chủ Edge-TTS, tăng tốc độ xử lý phần âm thanh lên gấp 3-4 lần.

---

## 4. Dịch thuật nâng cao (Translation Quality)

### 4.1. Tích hợp từ điển thuật ngữ (Glossary/Translation Memory)
* **Hiện trạng:** LLM dịch tự do đôi khi làm mất đi tính nhất quán của các danh từ riêng, thuật ngữ kỹ thuật hoặc tên thương hiệu.
* **Giải pháp:** Cho phép người dùng cấu hình một bảng từ khóa dịch sẵn (ví dụ: `AI` -> `Trí tuệ nhân tạo`, `Apple` giữ nguyên). Backend sẽ chèn danh mục từ khóa này vào prompt gửi cho Ollama/Qwen để định hướng bản dịch chính xác nhất.

---

## 5. Nâng cấp Công cụ & Mô hình AI (Tools & Models)

### 5.1. Nâng cấp mô hình Nhận diện giọng nói (WhisperX Model Selection)
* **Hiện trạng:** Hệ thống đang cố định sử dụng mô hình WhisperX phiên bản `small`.
* **Giải pháp:** Cho phép người dùng chọn kích thước mô hình Whisper tùy theo cấu hình phần cứng:
  - Máy cấu hình yếu: `tiny`, `base` (nhận diện siêu nhanh nhưng độ chính xác thấp hơn).
  - Máy cấu hình mạnh/GPU lớn: `medium`, `large-v3` (nhận diện cực kỳ chính xác các từ khó, tiếng lóng, tiếng địa phương).

### 5.2. Chuyển đổi TTS hoàn toàn Offline (Local Text-to-Speech)
* **Hiện trạng:** Đang phụ thuộc vào `Edge-TTS` (cần kết nối Internet, có nguy cơ bị giới hạn lượt gọi/rate limit).
* **Giải pháp:** Tích hợp mô hình TTS chạy offline trực tiếp trên máy:
  - **Kokoro-82M:** Mô hình TTS thế hệ mới siêu nhẹ (chỉ khoảng 80M tham số), tốc độ sinh âm thanh cực nhanh và có chất lượng giọng đọc tự nhiên vượt trội (đã có bản tinh chỉnh tiếng Việt từ cộng đồng).
  - **XTTS-v2 hoặc F5-TTS:** Hỗ trợ tính năng **Voice Cloning** (nhân bản giọng nói) — người dùng chỉ cần cung cấp 1 đoạn âm thanh mẫu 3 giây của video gốc, hệ thống sẽ tự động bắt chước chính xác tone giọng của nhân vật đó để nói tiếng Việt.

### 5.3. Tối ưu hóa tách nhạc nền (Vocal Separation)
* **Hiện trạng:** Sử dụng `Demucs` mặc định chất lượng cao nhưng thời gian xử lý khá lâu.
* **Giải pháp:** Bổ sung cấu hình cho phép chuyển đổi sang các mô hình tách âm nhanh hơn:
  - **HTDemucs-light:** Bản rút gọn của Demucs giúp giảm 50% thời gian xử lý âm thanh.
  - **UVR5 (Roformer / MDX-Net):** Các kiến trúc tách giọng hát/nhạc nền tiên tiến nhất hiện nay, cho âm thanh sạch hơn và chạy nhanh hơn Demucs.

### 5.4. Đa dạng hóa mô hình LLM Dịch thuật
* **Hiện trạng:** Cố định sử dụng `qwen2.5:7b` qua Ollama.
* **Giải pháp:** 
  - Hỗ trợ các mô hình nhỏ gọn hơn như `Qwen2.5-Instruct-3B` hoặc `Llama-3-8B-Instruct-Vietnamese` giúp máy có VRAM yếu (dưới 6GB) vẫn dịch nhanh chóng.
  - Tích hợp thêm tùy chọn API dịch thuật trực tuyến (Gemini Flash API, GPT-4o-mini) như một tùy chọn phụ phòng khi máy user không đủ mạnh để chạy LLM cục bộ.

