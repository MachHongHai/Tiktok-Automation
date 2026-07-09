# Desktop Improvement Suggestions

## Ưu Tiên Gần

1. Thêm màn hình Settings để chỉnh translator, model, storage path và bật/tắt Demucs mà không cần sửa `.env`.
2. Thêm nút Export Debug Package để nén `app.log`, `job.json`, `logs.txt` và thông tin diagnostics.
3. Thêm kiểm tra dependency lúc startup: FFmpeg, FFprobe, torch CUDA, Whisper model cache, Ollama status.
4. Thêm hàng đợi job thay vì chỉ xử lý một job active.
5. Cho phép resume hoặc retry từ bước lỗi nếu file trung gian còn tồn tại.

## Tối Ưu Đóng Gói EXE

- Dùng PyInstaller `--onedir`.
- Bundle FFmpeg trong `runtime/bin`.
- Không bundle model lớn vào executable.
- Lưu dữ liệu runtime trong `%LOCALAPPDATA%\AutoDubVideoLocal`.
- Tách bản Light và bản Offline:
  - Light: `openai_compatible`, Edge TTS, không Demucs mặc định.
  - Offline: Ollama, local STT, Demucs, cache model lớn.

## Tối Ưu Pipeline

- Cân nhắc thay WhisperX bằng `faster-whisper` nếu ưu tiên deploy nhẹ.
- Giữ WhisperX nếu cần alignment tốt hơn.
- Thêm cache TTS theo text + voice để tránh tạo lại audio giống nhau.
- Thêm batch size cấu hình được cho translation.
- Thêm validation output dịch để phát hiện dòng rỗng, chữ Trung, hoặc sai số lượng segment.

## UI/UX

- Thêm preview video output trong app.
- Thêm job detail drawer hiển thị input/output/temp files.
- Thêm progress theo từng step thay vì chỉ phần trăm tổng.
- Thêm nút mở folder storage, logs, cache riêng biệt.
