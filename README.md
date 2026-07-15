# Auto Dub Video Local

**Tài liệu:** [English](README.md) | Tiếng Việt

Auto Dub Video Local là công cụ desktop Windows dùng để tạo video đã dịch, lồng tiếng và chèn phụ đề trên máy cá nhân. Dự án hướng đến mô hình local-first: video nguồn, file trung gian, log, cache model và video xuất đều nằm ở đường dẫn do người dùng kiểm soát.

> Chỉ xử lý video bạn sở hữu hoặc có quyền sử dụng. Người dùng chịu trách nhiệm về bản quyền, quyền riêng tư và quy định pháp luật liên quan đến video nguồn và video xuất.

## Miễn phí và Local-First

Đây là dự án **miễn phí 100% để cài đặt và sử dụng pipeline hiện tại**: không subscription, không API key trả phí, không hàng đợi xử lý trên server và không upload video lên backend của ứng dụng.

- WhisperX nhận dạng lời nói và căn thời gian chạy local trên máy.
- HY-MT2 dịch phụ đề chạy local trên máy.
- Cache checkpoint, tạo phụ đề, ghép audio và render video chạy local.
- Video nguồn, audio trung gian, model cache, log và output không bị gửi đến dịch vụ AI cloud của ứng dụng.

Ứng dụng được chạy **trên máy của người dùng**, không phải kiểu gửi video cho một AI cloud xử lý rồi nhận kết quả. Nhờ đó không phát sinh chi phí theo phút video hoặc theo số lần dịch, đồng thời dữ liệu nhạy cảm ở lại trên máy.

Riêng Edge TTS là bước tạo giọng cần Internet. Text của các câu đã dịch được gửi tới dịch vụ Edge TTS để sinh audio; tool không cần API key trả phí cho bước này.

## Chức năng

- Import video MP4, MOV hoặc MKV vào project đặt tên riêng.
- Nhập trực tiếp video từ liên kết YouTube, TikTok hoặc Douyin; app hiển thị metadata và tiến độ trước khi đưa video vào project.
- Tự nhận diện ngôn ngữ nguồn cho từng câu phụ đề, phù hợp cả video xen nhiều ngôn ngữ.
- Dịch sang các ngôn ngữ đích phổ biến bằng Tencent HY-MT2 local với ngữ cảnh subtitle lân cận.
- Chọn giọng Edge TTS phù hợp với ngôn ngữ đích.
- Chọn `Full auto` hoặc `Review then dub`.
- Sửa từng câu dịch trước khi TTS và render.
- Tạo subtitle ngắn, tuần tự, phù hợp cách đọc YouTube Shorts/TikTok.
- Chỉnh vị trí và kích thước khung subtitle bằng preview QML riêng.
- Giữ hoặc giảm âm thanh gốc; có tùy chọn Demucs cho video có nhạc nền/tạp âm.
- Pause, mở lại project cũ, Resume hoặc Restart.
- Tái sử dụng checkpoint để không xử lý lại những bước không bị ảnh hưởng.
- Xử lý Batch tuần tự để ổn định VRAM.

## Pipeline

```text
Video nguồn
  -> tách audio bằng FFmpeg
  -> tách giọng tùy chọn bằng Demucs
  -> nhận dạng, alignment và nhận diện ngôn ngữ theo từng câu phụ đề bằng WhisperX
  -> dịch bằng HY-MT2 local
  -> duyệt/sửa bản dịch tùy chọn
  -> tạo các đoạn voice bằng Edge TTS
  -> ghép timeline audio
  -> render video và subtitle bằng FFmpeg
```

Trên máy có CUDA, WhisperX và HY-MT2 được warm-up tuần tự ở nền khi app mở. Trên máy chỉ có CPU, app tự chọn batch và số luồng theo RAM, chỉ warm-up WhisperX khi đủ bộ nhớ, rồi tải HY-MT2 Q4 lúc bắt đầu dịch. Model dịch CPU được tự động giải phóng sau thời gian không hoạt động để tránh chiếm RAM lâu dài.

## Công nghệ

| Thành phần | Công nghệ |
| --- | --- |
| Desktop UI | PySide6, QML, Qt Quick Controls, Qt Multimedia |
| Nhận dạng giọng nói | WhisperX |
| Dịch | Tencent HY-MT2-1.8B trong local worker riêng |
| Lồng tiếng | Edge TTS |
| Xử lý media | FFmpeg, yt-dlp, Pydub, Demucs tùy chọn |
| Data contract | Pydantic |
| Đóng gói | PyInstaller `--onedir` |

Runtime desktop không cần Node.js, React, Vite, FastAPI, trình duyệt hay database cloud.

## Yêu cầu

- Windows 10 hoặc Windows 11.
- Python 3.11-3.13; dependency và metadata được pin trong `auto-dub-video-local/pyproject.toml`.
- NVIDIA CUDA được khuyến nghị để có tốc độ tốt nhất. Máy không có card đồ họa rời vẫn chạy được bằng WhisperX INT8 và HY-MT2 Q4 trên CPU; thời gian xử lý sẽ dài hơn.
- Có FFmpeg và FFprobe trong `runtime/bin` khi chạy source.
- Có Internet để nhập video từ liên kết, để Edge TTS tạo giọng và để tải model từ Hugging Face ở lần đầu.

## Cài đặt và chạy từ source

```powershell
git clone <repository-url>
cd auto-dub-video-local
Copy-Item .env.example .env
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

Một môi trường duy nhất hỗ trợ cả GPU và CPU. Chế độ xử lý được chọn trong **Settings > Processing device**:

- **GPU:** yêu cầu GPU NVIDIA CUDA với tối thiểu 6 GB VRAM. GPU 6-8 GB dùng batch nhỏ và giải phóng WhisperX trước khi dịch.
- **CPU:** dùng WhisperX INT8 và HY-MT2 Q4; yêu cầu khoảng 6 GB RAM trở lên.

```powershell
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

Hoặc chạy trực tiếp sau khi đã tạo virtual environment:

```powershell
.\.venv\Scripts\python.exe .\autodub_desktop.py
```

Kiểm tra toàn bộ runtime trước khi debug hoặc build:

```powershell
.\.venv\Scripts\python.exe .\scripts\verify-runtime.py
```

Script phát hiện sai Python environment, thiếu package, sai version, lỗi Qt/Torch, sai đường dẫn cache, thiếu FFmpeg và dependency conflict. `build-exe.ps1` tự chạy bản kiểm tra nghiêm ngặt hơn trước khi gọi PyInstaller.

App mở ở trạng thái maximized. Warm-up WhisperX và HY-MT2 chạy nền nên giao diện vẫn dùng được khi model đang load.

## Cấu hình

Tạo `.env` từ `.env.example`, sau đó chỉ sửa các biến cần thiết:

```env
# Nên đặt ổ D nếu không muốn cache/job chiếm ổ C.
RUNTIME_DATA_DIR=D:\AutoDubData

# tiny, base, small, medium hoặc large-v3.
WHISPER_MODEL=small

# Model dịch local, tải từ Hugging Face ở lần đầu.
HYMT2_MODEL=tencent/Hy-MT2-1.8B

# Số request Edge TTS song song; giá trị hợp lệ 1 đến 4.
TTS_MAX_CONCURRENCY=1
```

Nhánh CPU dùng model chính thức `Hy-MT2-1.8B-Q4_K_M.gguf`. Model được tải một lần vào `<RUNTIME_DATA_DIR>\models\hymt2-gguf`, hoặc có thể được đóng gói sẵn trong bản phát hành offline.

`RUNTIME_DATA_DIR` là biến quan trọng nhất. Nếu không đặt, runtime data sẽ vào `%LOCALAPPDATA%\AutoDubVideoLocal\data`. Đặt `D:\AutoDubData` trước khi import media lớn để cache model, chỉ mục project và toàn bộ workspace của project ở ổ D.

Có thể đặt `HF_HOME` và `TORCH_HOME` thành đường dẫn tuyệt đối nếu muốn tách Hugging Face/Torch cache khỏi runtime root.

## Workflow

### Full Auto

Chạy xuyên suốt: nhận dạng, dịch, tạo phụ đề, TTS, ghép audio và render mà không cần dừng.

### Review Then Dub

Sau khi HY-MT2 dịch xong, project chuyển sang trạng thái `awaiting_review`. Mở **Review translation**, chỉnh từng segment trong modal, sau đó bấm **Approve and continue**. Tool tiếp tục subtitle, TTS, ghép audio và render mà không gọi lại WhisperX hoặc HY-MT2.

## Project, Pause, Resume và Restart

Mỗi project là một job local và được hiển thị bằng thumbnail ở trang Projects. Khi mở project cũ, giao diện khôi phục video input, Dubbing setup, log, progress và các nút output.

- **Pause:** dừng subprocess đang chạy và lưu safe checkpoint.
- **Resume:** nếu bản dịch đã hoàn chỉnh, tiếp tục từ subtitle/TTS/render; các bước dở dang phía trước sẽ chạy lại an toàn.
- **Restart:** lưu Dubbing setup hiện tại rồi chạy lại project.
- **Replace:** thay video input đã lưu trong project, cập nhật thumbnail; sau đó dùng Restart để xử lý video mới.

## Checkpoint Cache và tốc độ

Tool lưu chữ ký checkpoint vào `job.json` và chỉ tái sử dụng output khi setup phù hợp và file còn tồn tại.

| Thay đổi | Bước được tái sử dụng | Bước chạy lại |
| --- | --- | --- |
| Không đổi source/ngôn ngữ | Translation, subtitle, voice, mix, render nếu checkpoint hợp lệ | Không có hoặc chỉ output thiếu |
| Đổi voice | Translation và subtitle | TTS, mix, render |
| Đổi âm lượng gốc | Translation, subtitle, voice | Mix và render |
| Đổi subtitle style | Translation, voice, audio mix | Subtitle và render |
| Đổi video, ngôn ngữ đích hoặc Demucs | Không dùng cache upstream | Chạy từ bước bị ảnh hưởng |

Điều này làm việc thử nhiều giọng hoặc subtitle style nhanh hơn rõ rệt so với chạy lại toàn bộ video.

## Lưu trữ runtime offline

Ví dụ với `RUNTIME_DATA_DIR=D:\AutoDubData`:

```text
D:\AutoDubData\
  projects\<project-name>\
    .autodub-project.json
    exports\
      dubbed_video.mp4
    videos\<video-id>\
      input\video.<ext>
      temp\audio.wav
      temp\source_segments.json
      temp\vi_segments.json
      temp\voice_parts\
      output\final.mp4
      logs.txt
      job.json
  cache\huggingface\
  cache\torch\
  logs\
  desktop-settings.json
```

Mỗi project tự chứa input, temp, log, metadata và video export. App sẽ tự chuyển workspace `jobs` của phiên bản cũ vào project khi khởi động. Có thể migrate dữ liệu cũ bằng:

```powershell
.\scripts\migrate-runtime-data.ps1 -Move
```

Hãy đọc output script trước khi dùng `-Move`.

## Log và theo dõi tiến trình

Log của từng job nằm tại:

```text
<project>\videos\<video-id>\logs.txt
```

Activity Log trong app hiển thị realtime log của project đang chọn. Text progress và log dùng cùng callback ở translation/TTS, nên dòng như `Translating segment 2 of 3` tương ứng trực tiếp với trạng thái trên progress bar.

App log nằm tại:

```text
<RUNTIME_DATA_DIR>\logs\
```

## Phát triển và build EXE

Khi sửa code, test bằng source runtime:

```powershell
.\scripts\run-desktop.ps1
```

Không cài package trực tiếp vào Python hệ thống. Mọi dependency desktop và ML được pin trong `pyproject.toml`; `requirements.txt` chỉ khai báo binary index và cài package editable. Khi cần tạo lại một environment sạch:

```powershell
.\scripts\install-desktop-env.ps1 -Recreate
```

Chạy kiểm tra chuẩn trước khi merge:

```powershell
.\scripts\test.ps1
.\.venv\Scripts\python.exe .\scripts\verify-runtime.py
```

Chỉ build EXE khi cần phát hành:

```powershell
.\scripts\build-exe.ps1
```

Một bản phát hành duy nhất chứa cả backend GPU và CPU:

```powershell
.\scripts\build-exe.ps1

# Tùy chọn: nhúng sẵn model Q4 để CPU không phải tải ở lần đầu
.\.venv\Scripts\python.exe .\scripts\prepare-cpu-model.py
.\scripts\build-exe.ps1 -IncludeCpuModel
```

Bản thống nhất lớn hơn bản CPU chuyên biệt vì chứa cả Torch CUDA và `llama.cpp`, nhưng người dùng chỉ cần cài một lần và có thể đổi thiết bị xử lý trong Settings.

Kết quả:

```text
dist\AutoDubVideoLocal\AutoDubVideoLocal.exe
```

Build dùng `--onedir` vì Qt, Torch, WhisperX và FFmpeg cần nhiều native files kề nhau. Không di chuyển riêng file `.exe` ra khỏi thư mục distribution.

## Hiệu năng và giới hạn

- CUDA warm-up WhisperX và HY-MT2 tuần tự khi app mở. CPU dùng INT8/Q4, batch thích ứng theo RAM và tự nhả worker dịch khi không hoạt động.
- FFmpeg tự probe NVENC, Intel Quick Sync và AMD AMF; nếu encoder phần cứng không dùng được, app tự thử lại bằng `libx264 veryfast`.
- Edge TTS mặc định gửi tuần tự một request để tránh lỗi `NoAudioReceived` do nhiều WebSocket đồng thời. Các câu lỗi vẫn được retry bằng kết nối mới và chỉ được ghi nhận khi MP3 hợp lệ; tool không âm thầm thay câu lỗi bằng khoảng lặng. Có thể tăng `TTS_MAX_CONCURRENCY`, nhưng độ ổn định sẽ giảm.
- Demucs tắt mặc định vì nặng; chỉ bật nếu nhạc nền/tạp âm làm giảm chất lượng nhận dạng.
- Batch chạy tuần tự để tránh cạnh tranh VRAM.
- TTS cần Internet; tốc độ cuối cùng còn phụ thuộc kết nối mạng và độ dài câu.
- Chất lượng đầu ra phụ thuộc transcript nguồn, cặp ngôn ngữ và model dịch local.

## Tài liệu bổ sung

- [Architecture (English)](auto-dub-video-local/docs/architecture.md)
- [Package metadata](auto-dub-video-local/pyproject.toml)
- [Environment template](auto-dub-video-local/.env.example)
- [Installer requirements](auto-dub-video-local/requirements.txt)
