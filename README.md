# HaizFlow

> **100% free, local-first video dubbing automation for Windows.**
>
> HaizFlow does not require a paid API key, subscription, cloud account, or per-video fee. Projects, source media, model caches, logs, checkpoints, and exports remain on the user's machine.

[English](#english) | [Tiếng Việt](#tieng-viet)

---

<a id="english"></a>

## English

### Overview

HaizFlow is a desktop application for turning source videos into translated, voiced, captioned exports through a local, project-based workflow. It is built for creators and small production teams who want practical automation without handing full videos to a SaaS backend.

The application separates **single-video work** from **batch work**, preserves each project's media and processing state locally, and lets the user pause, resume, restart, review translations, or replace the source without losing control of the workflow.

### Why HaizFlow

- **Free by design.** Local transcription, translation, media processing, checkpoints, and rendering do not require a paid HaizFlow API.
- **Local-first privacy.** There is no HaizFlow cloud backend, account system, or cloud database. Project data is stored in a user-selected local directory.
- **Production-oriented workflow.** Projects own their input media, thumbnails, logs, subtitle settings, checkpoints, intermediate files, and exports.
- **Human control where it matters.** Run in Full Auto mode or stop after translation to edit every line before TTS and rendering.
- **Hardware-aware execution.** The app supports GPU and CPU processing modes, validates runtime availability, and keeps queued work independent from UI navigation.
- **Modern desktop experience.** PySide6, QML, Qt Quick Controls, and Qt Multimedia provide a native Windows desktop interface rather than a browser shell.

### Core Capabilities

| Area | Capability |
| --- | --- |
| Project management | Separate single and batch workspaces, local project manifests, thumbnails, restart, resume, deletion, and folder access. |
| Media import | Local MP4/MOV/MKV files, drag and drop, folders for batch processing, individual supported video links, and channel discovery. |
| Channel import | YouTube, TikTok, and Douyin Beta channel scanning with ordering, duration filtering, duplicate detection, candidate selection, and independent downloads. |
| Transcription | WhisperX transcription, alignment, timed subtitle segments, and mixed-language detection at segment level. |
| Translation | Local Tencent HY-MT2 translation with a pinned model revision, bounded context windows, and optional translation review before dubbing. |
| Voice synthesis | Edge TTS voices filtered by target language, bounded concurrency, retries, and explicit per-line progress logging. |
| Audio | Keep original audio at an adjustable level or optionally separate vocals/background audio with Demucs. |
| Captions | Timed, short-form subtitle rendering and a dedicated QML subtitle-frame editor for placement and scaling. |
| Rendering | FFmpeg-based audio timeline construction, subtitle burn-in, output rendering, hardware encoder probing, and safe CPU fallback. |
| Reliability | Per-project checkpoints, pause/resume semantics, isolated model workers, model queueing, cancellation, and structured diagnostics. |

### Product Workflow

```text
Create project
  -> import a source video or batch media
  -> choose target language, voice, audio mode, and subtitle frame
  -> extract audio with FFmpeg
  -> transcribe and align with WhisperX
  -> translate locally with HY-MT2
  -> optional human translation review
  -> synthesize voices with Edge TTS
  -> build an audio timeline and preserve/mix source audio
  -> render timed subtitles and final video with FFmpeg
  -> open the export from the project
```

Channel imports deliberately stop before processing. Selected videos are added to a batch project first, so the user can inspect shared settings, subtitle presets, and individual overrides before starting the queue.

### Architecture

```text
PySide6 / QML desktop UI
        |
        +-- Project controller and local project store
        |       +-- project manifests, media metadata, logs, checkpoints
        |
        +-- Processing queue
        |       +-- one controlled media pipeline at a time per compute runtime
        |       +-- independent channel-download coordinator
        |
        +-- Isolated AI workers
        |       +-- WhisperX / Pyannote transcription and alignment
        |       +-- Tencent HY-MT2 translation
        |
        +-- Media services
                +-- FFmpeg / FFprobe
                +-- Edge TTS
                +-- optional Demucs separation
                +-- yt-dlp and Douyin helper integration
```

The UI remains usable while a video is processing. A newly submitted project is queued instead of competing for the same models or GPU memory. Channel scanning and downloads are coordinated separately from the model-processing queue.

### Technology Stack

| Layer | Technology |
| --- | --- |
| Desktop UI | Python, PySide6, QML, Qt Quick Controls, Qt Multimedia |
| Speech recognition | WhisperX, faster-whisper, Pyannote Audio |
| Translation | Tencent HY-MT2-1.8B, Transformers, llama.cpp CPU Q4 runtime |
| Speech synthesis | Edge TTS |
| Video and audio | FFmpeg, FFprobe, Pydub, optional Demucs |
| Import and extraction | yt-dlp, isolated Douyin helper |
| Data contracts | Pydantic, JSON project manifests |
| Packaging | PyInstaller `--onedir` for Windows |
| Quality controls | Hashed Windows dependency lock, runtime validation, smoke checks, unit tests |

### Hardware and Runtime Strategy

HaizFlow ships one source architecture for both GPU and CPU execution.

- **GPU mode:** recommended for NVIDIA CUDA devices with enough available VRAM. WhisperX and HY-MT2 are warmed in a controlled order to reduce first-job delay and avoid peak-memory collisions.
- **CPU mode:** uses WhisperX INT8 and HY-MT2 Q4. It is slower but keeps the product usable on computers without a discrete GPU.
- **Runtime safety:** the app exposes the active processing device, validates a requested CPU/GPU change, and keeps the active job stable when the user changes a preference. A genuine GPU loss can trigger controlled recovery rather than leaving a project in an ambiguous state.
- **Storage safety:** model cache, Torch cache, Hugging Face cache, uv/pip cache, temporary files, logs, and project data are configured through `RUNTIME_DATA_DIR` and related paths. The current local development setup keeps them on `D:\HaizFlowData`.

### Privacy, Cost, and Network Use

HaizFlow itself is free and does not run a paid processing backend. The transcription, translation, media composition, captions, checkpoints, and final rendering pipeline execute locally.

Some optional capabilities require an internet connection:

- Edge TTS sends translated text to Microsoft's speech service to generate audio. It does not require a paid HaizFlow API key.
- Link and channel import use the public platform extraction workflow through yt-dlp or the Douyin helper.
- First model download obtains model artifacts from their upstream distribution source.

Users are responsible for respecting copyright, platform terms, privacy obligations, and local law when importing or publishing media.

### Repository Layout

```text
HaizFlow/
  HaizFlow/
    src/haizflow/          Application package
    docs/                  Architecture and release-readiness notes
    scripts/               Environment, validation, packaging, and maintenance tools
    test/                  Automated tests
    runtime/               Bundled runtime manifest and media binaries when provided
    pyproject.toml         Python package metadata
    requirements-lock-...  Reproducible Windows dependency lock
```

### Quick Start: Source Mode

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow\HaizFlow
Copy-Item .env.example .env
```

Set a local data location before downloading models or importing large media:

```env
RUNTIME_DATA_DIR=D:\HaizFlowData
HF_HOME=D:\HaizFlowData\cache\huggingface
TORCH_HOME=D:\HaizFlowData\cache\torch
PIP_CACHE_DIR=D:\HaizFlowData\cache\pip
UV_CACHE_DIR=D:\HaizFlowData\cache\uv
HAIZFLOW_TMP_DIR=D:\HaizFlowData\cache\tmp
```

Install and run:

```powershell
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

For an existing virtual environment after moving the repository:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
```

### Verification and Development

```powershell
# Run the complete unit-test suite.
.\scripts\test.ps1

# Validate packages, hardware/runtime assumptions, FFmpeg, cache paths, and lock consistency.
.\.venv\Scripts\python.exe .\scripts\verify-runtime.py

# Validate the lock file without changing installed packages.
.\.venv\Scripts\python.exe .\scripts\verify-dependency-lock.py
```

The repository currently includes automated coverage for project lifecycle behavior, batch import, channel import, queue isolation, CPU/GPU runtime behavior, checkpoint/restart semantics, timeline rendering, TTS reliability, localization, and runtime probing.

### Packaging for Windows

```powershell
.\scripts\build-exe.ps1
```

The application uses PyInstaller `--onedir` packaging because Qt, Torch, WhisperX, FFmpeg, and native DLL dependencies need to stay adjacent to the executable. Build only when preparing a release; day-to-day development should run from source to preserve fast iteration.

### Documentation

- [Architecture](HaizFlow/docs/architecture.md)
- [Release readiness](HaizFlow/docs/release-readiness.md)
- [Environment template](HaizFlow/.env.example)
- [Package metadata](HaizFlow/pyproject.toml)
- [Dependency lock](HaizFlow/requirements-lock-py313-win64.txt)

### License and Notices

HaizFlow source is released under the repository license. Third-party software, model, FFmpeg, and channel-import notices are available in [`HaizFlow/licenses`](HaizFlow/licenses).

---

<a id="tieng-viet"></a>

## Tiếng Việt

### Tổng quan

HaizFlow là ứng dụng desktop Windows giúp chuyển video nguồn thành video đã dịch, lồng tiếng và gắn phụ đề theo một quy trình xử lý cục bộ, có quản lý dự án rõ ràng. Dự án hướng tới creator và nhóm sản xuất nhỏ muốn tự động hóa công việc nhưng vẫn kiểm soát dữ liệu, chất lượng bản dịch và đầu ra video.

Ứng dụng tách riêng không gian làm việc **Đơn lẻ** và **Hàng loạt**, lưu toàn bộ media, log, checkpoint, phụ đề và video xuất trong dự án cục bộ. Người dùng có thể tạm dừng, tiếp tục, chạy lại, duyệt bản dịch hoặc thay video nguồn mà không mất quyền kiểm soát workflow.

### Giá trị cốt lõi

- **Miễn phí 100%.** Pipeline chính không cần API trả phí, subscription hay tính phí theo số phút video.
- **Local-first.** HaizFlow không có backend cloud, tài khoản người dùng hoặc cơ sở dữ liệu cloud của sản phẩm. Dữ liệu dự án được lưu tại đường dẫn do người dùng chọn.
- **Thiết kế theo dự án.** Mỗi dự án tự sở hữu input, thumbnail, log, checkpoint, thiết lập phụ đề, file tạm và video xuất.
- **Tự động hóa nhưng vẫn có quyền duyệt.** Có thể chạy Full Auto hoặc dừng sau dịch để sửa từng câu trước khi tạo giọng nói.
- **Phù hợp nhiều cấu hình máy.** Hỗ trợ GPU NVIDIA CUDA và CPU; có kiểm tra runtime trước khi chạy để giảm lỗi môi trường.
- **Giao diện desktop hiện đại.** Xây dựng bằng PySide6 và QML thay vì bọc một trang web trong cửa sổ ứng dụng.

### Tính năng chính

| Nhóm | Khả năng |
| --- | --- |
| Quản lý dự án | Tách dự án đơn lẻ/hàng loạt, manifest cục bộ, thumbnail, mở lại, tiếp tục, chạy lại, xóa và mở thư mục dự án. |
| Nhập video | Nhập MP4/MOV/MKV, kéo thả, chọn thư mục cho batch, nhập liên kết video và tải video từ kênh hỗ trợ. |
| Tải từ kênh | Quét YouTube, TikTok và Douyin Beta; sắp xếp, lọc thời lượng, phát hiện trùng, chọn video rồi mới tải. |
| Nhận dạng | WhisperX tạo transcript, căn chỉnh thời gian, segment phụ đề và nhận diện ngôn ngữ theo từng segment. |
| Dịch thuật | Tencent HY-MT2 chạy local, khóa revision model, dùng context có giới hạn và hỗ trợ duyệt bản dịch trước khi lồng tiếng. |
| Lồng tiếng | Edge TTS lọc giọng theo ngôn ngữ đích, giới hạn song song, retry có kiểm soát và log theo từng câu. |
| Âm thanh | Giữ âm gốc với mức âm lượng tùy chỉnh hoặc tách giọng/nền bằng Demucs khi cần. |
| Phụ đề | Render subtitle theo thời gian; có cửa sổ QML riêng để chỉnh vị trí và kích thước khung phụ đề. |
| Render | FFmpeg tạo audio timeline, gắn phụ đề, render video đầu ra, dò encoder phần cứng và fallback CPU an toàn. |
| Độ tin cậy | Checkpoint theo dự án, pause/resume, worker model cô lập, hàng đợi, hủy và chẩn đoán lỗi có cấu trúc. |

### Quy trình xử lý

```text
Tạo dự án
  -> nhập video hoặc nhiều video
  -> chọn ngôn ngữ đích, giọng đọc, chế độ âm thanh, khung phụ đề
  -> FFmpeg tách audio
  -> WhisperX nhận dạng và căn chỉnh
  -> HY-MT2 dịch local
  -> tùy chọn duyệt/sửa bản dịch
  -> Edge TTS tạo voice
  -> ghép timeline audio với âm thanh nguồn
  -> FFmpeg render video và phụ đề
  -> mở video xuất trực tiếp từ dự án
```

Video được tải từ kênh chỉ được thêm vào project hàng loạt. Pipeline không tự chạy ngay để người dùng có thời gian kiểm tra thiết lập chung, preset phụ đề và tùy chỉnh riêng cho từng video.

### Kiến trúc và điểm nhấn kỹ thuật

HaizFlow dùng kiến trúc desktop tách rõ giao diện, dữ liệu dự án, hàng đợi xử lý, worker AI và dịch vụ media. Giao diện vẫn thao tác được trong khi một video đang chạy; video mới được đưa vào hàng đợi thay vì tranh chấp VRAM hoặc model với tiến trình hiện tại. Hàng đợi quét/tải kênh hoạt động độc lập với hàng đợi dùng model AI.

Các thành phần chính gồm:

- **PySide6/QML:** giao diện native Windows, điều hướng project, popup, preview và trạng thái tiến trình.
- **WhisperX/Pyannote:** nhận dạng lời nói, căn chỉnh timestamp và nhận diện đa ngôn ngữ theo segment.
- **Tencent HY-MT2:** dịch subtitle local trong worker riêng, có giới hạn context để vừa giữ ngữ cảnh vừa an toàn với video dài.
- **Edge TTS:** sinh audio theo câu, có retry và logging để dễ truy vết lỗi.
- **FFmpeg/Demucs:** xử lý audio/video, subtitle burn-in, mix âm thanh nguồn và render đầu ra.
- **Manifest JSON/Pydantic:** lưu cấu trúc dự án, checkpoint và contract dữ liệu rõ ràng để có thể tiếp tục mở rộng.

### CPU, GPU và lưu trữ

- **GPU:** khuyến nghị cho máy có NVIDIA CUDA và VRAM khả dụng đủ lớn. Model được warm-up theo thứ tự để tránh đỉnh VRAM ở lần chạy đầu.
- **CPU:** dùng WhisperX INT8 và HY-MT2 Q4. Chậm hơn nhưng vẫn hoạt động trên máy không có card rời.
- **An toàn runtime:** app kiểm tra thiết bị hiện tại, không làm gián đoạn job đang chạy chỉ vì người dùng đổi preference, và có hướng xử lý khi GPU thực sự mất khả dụng.
- **Dữ liệu trên ổ người dùng chọn:** `RUNTIME_DATA_DIR`, Hugging Face cache, Torch cache, pip/uv cache và file tạm đều có thể cấu hình. Thiết lập hiện tại dùng `D:\HaizFlowData` để không chiếm ổ C.

### Quyền riêng tư và chi phí

HaizFlow không vận hành backend xử lý trả phí. Nhận dạng, dịch, ghép media, tạo phụ đề, checkpoint và render cuối đều chạy trên máy cục bộ.

Một số bước cần Internet nhưng không phải dịch vụ API trả phí của HaizFlow:

- Edge TTS gửi nội dung văn bản đã dịch tới dịch vụ speech của Microsoft để tạo audio.
- Nhập video/link/kênh dùng cơ chế trích xuất nền tảng qua yt-dlp hoặc helper Douyin.
- Lần đầu chạy cần Internet để tải model từ nguồn phát hành chính thức.

Người dùng chịu trách nhiệm tuân thủ bản quyền, điều khoản nền tảng, quyền riêng tư và pháp luật địa phương khi nhập hoặc xuất bản video.

### Cài đặt và chạy từ source

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow\HaizFlow
Copy-Item .env.example .env
```

Chọn vị trí lưu dữ liệu trước khi tải model hoặc xử lý media lớn:

```env
RUNTIME_DATA_DIR=D:\HaizFlowData
HF_HOME=D:\HaizFlowData\cache\huggingface
TORCH_HOME=D:\HaizFlowData\cache\torch
PIP_CACHE_DIR=D:\HaizFlowData\cache\pip
UV_CACHE_DIR=D:\HaizFlowData\cache\uv
HAIZFLOW_TMP_DIR=D:\HaizFlowData\cache\tmp
```

```powershell
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

Nếu vừa đổi vị trí repository, cập nhật editable package một lần:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
```

### Kiểm thử, đóng gói và tài liệu kỹ thuật

```powershell
# Chạy toàn bộ unit test.
.\scripts\test.ps1

# Kiểm tra runtime, FFmpeg, cache path, dependency lock và môi trường.
.\.venv\Scripts\python.exe .\scripts\verify-runtime.py

# Đóng gói bản Windows khi chuẩn bị phát hành.
.\scripts\build-exe.ps1
```

Repository có kiểm thử cho vòng đời project, batch import, channel import, hàng đợi, CPU/GPU runtime, checkpoint/restart, render timeline, độ tin cậy TTS, localization và runtime probing.

Tài liệu kỹ thuật bổ sung:

- [Architecture](HaizFlow/docs/architecture.md)
- [Release readiness](HaizFlow/docs/release-readiness.md)
- [Environment template](HaizFlow/.env.example)
- [Package metadata](HaizFlow/pyproject.toml)
- [Dependency lock](HaizFlow/requirements-lock-py313-win64.txt)

### Giấy phép

Mã nguồn HaizFlow tuân theo giấy phép của repository. Thông báo về phần mềm, model, FFmpeg và channel-import bên thứ ba nằm tại [`HaizFlow/licenses`](HaizFlow/licenses).
