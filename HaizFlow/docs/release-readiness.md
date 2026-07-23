# Tiêu chuẩn sẵn sàng phát hành

Tài liệu này là nguồn duy nhất theo dõi các rủi ro phát hành của ứng dụng Windows. Mỗi bản release phải cập nhật trạng thái, chạy toàn bộ release gate và lưu `BUILD-INFO.json` cùng `SHA256SUMS.txt` trong artifact.

Ngày rà soát: 2026-07-24

## Quy ước trạng thái

- **Hoàn tất:** đã có implementation và kiểm thử tự động.
- **Chặn phát hành:** chưa được phép phát hành công khai cho đến khi điều kiện được đáp ứng.
- **Còn lại:** chưa phải blocker của beta nội bộ nhưng phải xử lý trước production rộng.

## Danh sách kiểm soát

| ID | Hạng mục | Trạng thái | Điều kiện nghiệm thu |
| --- | --- | --- | --- |
| 1 | Định danh và xóa project an toàn | **Hoàn tất** | Project mới dùng UUID; project đơn/batch cùng tên có root riêng; legacy root được giữ; manifest, shared-root và path traversal được kiểm tra trước khi xóa. |
| 2 | License và third-party compliance | **Runtime đã nâng cấp, còn legal gate** | Source code dùng Apache-2.0; FFmpeg đã nâng lên 8.1.2 Essentials, pin SHA-256 và kèm source archive có chữ ký. Build sinh notices từ đúng `.venv`. Trước khi công khai vẫn phải cung cấp corresponding source/build material của các thư viện GPL liên kết tĩnh và được người chịu trách nhiệm pháp lý duyệt. |
| 3 | Frozen acceptance và artifact mới | **Chặn phát hành cho đến khi source sạch** | Build xóa artifact cũ có kiểm soát, tạo metadata/checksum sau smoke, CPU runtime probe, GPU probe khi khả dụng và Qt/QML smoke với data tạm. `dist/` không được commit, nên mỗi revision phát hành phải được commit trước, rồi build và nghiệm thu artifact mới. Artifact ngày 2026-07-16 chỉ là bằng chứng lịch sử, không thay thế nghiệm thu revision hiện tại. |
| 4 | Installer, nâng cấp và code signing | **Chờ certificate và artifact sạch** | Có định nghĩa Inno Setup, kiểm tra dung lượng theo artifact thật, version resource/icon và cơ chế ký Authenticode. Cần certificate thật, artifact từ worktree sạch và nghiệm thu trên Windows sạch trước khi ký EXE/installer. |
| 5 | Khóa revision và checksum model | **Hoàn tất** | HY-MT2 GPU khóa `9a341cd1…`, HY-MT2 CPU khóa `1cd52087…`, Whisper small khóa `536b0662…`; các file model có size/SHA-256 cố định. Build mặc định nhúng cả ba model và frozen smoke xác minh integrity. |
| 6 | Single-instance ứng dụng | **Hoàn tất** | `QLocalServer` tạo named pipe theo user. Instance thứ hai gửi yêu cầu activate rồi thoát; instance chính khôi phục cửa sổ. Stale server được xử lý và smoke mode không chiếm khóa. Khóa file/index là phạm vi riêng của ID 7. |
| 7 | Phục hồi project index | **Hoàn tất** | `projects.json` được khóa liên tiến trình, ghi atomic, giữ last-known-good `.bak`, sao chép bản hỏng sang quarantine và rebuild từ manifest trong các project root đã đăng ký. Backup được hợp nhất với manifest mới hơn; lỗi không thể phục hồi chặn ghi thay vì tạo index rỗng. |
| 8 | Schema migration | **Hoàn tất** | Project metadata dùng schema v4, video metadata dùng schema v5. Migration đổi `job.json`/`job_id` cũ thành `video.json`/`video_id`, lưu backup, giữ nguyên project root legacy và từ chối schema tương lai. |
| 9 | Dependency lock tái lập | **Hoàn tất** | `requirements-lock-py313-win64.txt` khóa 137 dependency trực tiếp/gián tiếp bằng SHA-256 cho Windows x64/Python 3.13; Torch khóa đúng biến thể cu128. Manifest fingerprint phát hiện source/lock lệch, installer dùng `--require-hashes`, build gate đối chiếu toàn bộ `.venv`. |
| 10 | Disk preflight và cache policy | **Hoàn tất cho build/installer** | Runtime kiểm tra đúng dung lượng model hiện có cộng 2 GiB headroom. Installer tính từ artifact sau build, giữ hai bản khi upgrade và cộng 2 GiB workspace; với artifact ~10,7 GiB sẽ yêu cầu khoảng 23,4 GiB trống. |
| 11 | Mô tả offline và quyền riêng tư | **Chặn phát hành** | UI và README nói rõ WhisperX/HY-MT2 local, Edge TTS và tải URL cần mạng; có thông báo dữ liệu gửi ra ngoài và hành vi khi offline. |
| 12 | Chẩn đoán production | **Còn lại** | Log rotation, Qt/thread exception hooks, build ID và chức năng export diagnostics có redaction. |
| 13 | Shutdown và phục hồi video gián đoạn | **Hoàn tất** | Close event hỏi xác nhận khi còn xử lý/tải; active video được pause, subprocess tree bị dừng, queue từ chối việc mới và chờ worker. Windows Job Object dọn process con khi app crash; lần mở sau chuyển metadata `processing` còn sót thành `paused` có thể resume. Smoke mode luôn dùng data tạm thay vì `.env` thật. |
| 14 | Portable storage theo thư mục cài đặt | **Hoàn tất** | `HAIZFLOW_HOME` là hard boundary; Qt/QML, Torch, Hugging Face, pip/uv, CUDA/Numba, temp, log, settings và model đều nằm dưới thư mục người dùng chọn. Source hiện dùng `D:\HaizFlowData`; smoke xác nhận không ghi lại `%LOCALAPPDATA%\HaizFlow`. |
| 15 | Hygiene source và cấu trúc desktop | **Chặn release build** | Hai utility không dùng đã bị xóa; thư mục `build/` phải rỗng trước clean build. Tám desktop controller sau refactor, QML facade và tài liệu kiến trúc phải cùng nằm trong một commit; `git status --porcelain` phải rỗng trước khi chạy build release. |

## License gate

Các nguồn chính thức dùng để xác định nghĩa vụ:

- Qt for Python licensing: https://doc.qt.io/qtforpython-6/licenses.html
- FFmpeg legal checklist: https://ffmpeg.org/legal.html
- FFmpeg license: https://ffmpeg.org/doxygen/trunk/md_LICENSE.html
- HY-MT2 model card: https://huggingface.co/tencent/Hy-MT2-1.8B
- Edge TTS repository và mô tả online service: https://github.com/rany2/edge-tts

Mỗi artifact phải chứa:

```text
LICENSE.txt
NOTICE.txt
THIRD_PARTY_NOTICES.md
licenses/
BUILD-INFO.json
SHA256SUMS.txt
```

`scripts/generate-third-party-notices.py --strict` phải thành công. Runtime hiện dùng `8.1.2-essentials_build-www.gyan.dev`, được pin bằng binary SHA-256 và manifest. Artifact kèm source archive chính thức `ffmpeg-8.1.2.tar.xz`, chữ ký PGP, license và README của binary package. Người phát hành vẫn phải cung cấp complete corresponding source/build material của các thư viện GPL được liên kết tĩnh; riêng tarball FFmpeg upstream chưa đủ để tự khẳng định hoàn tất toàn bộ nghĩa vụ này.

## Frozen release gate

Kết quả frozen bên dưới là mốc lịch sử trước khi hoàn thiện ID 5 và ID 6. Theo yêu cầu hiện tại, EXE chưa được build lại; do đó artifact cũ không được xem là release candidate cho source mới.

Kết quả kiểm chứng source hiện tại (2026-07-18):

- Bộ `scripts/test.ps1` phải đạt hoàn toàn ở commit phát hành; không ghi cố định số test trong tài liệu để tránh số liệu cũ.
- Qt/QML source smoke test thành công.
- Runtime gate xác nhận đúng ba revision model (Whisper, HY-MT2 CPU/GPU), CPU/GPU native runtime và FFmpeg.
- Integration test liên tiến trình xác nhận instance thứ hai kích hoạt instance chính rồi thoát.

Mốc frozen trước đó:

- Artifact: `dist\HaizFlow`, PyInstaller onedir, không nhúng model.
- Quy mô: 11.404 file, 5,38 GiB.
- Đã đối chiếu thành công toàn bộ 11.404 SHA-256 trong `SHA256SUMS.txt`.
- Frozen self-test, FFmpeg/FFprobe, CPU runtime probe, GPU runtime probe và Qt/QML startup đều thành công.
- Bộ unit test source tại mốc frozen: 98/98 thành công.
- `BUILD-INFO.json` ghi rõ commit, branch, dirty state, Python và trạng thái model bundle.

Build chuẩn:

```powershell
.\scripts\build-exe.ps1
```

Chuẩn bị model pinned và build offline (mặc định nhúng cả ba model):

```powershell
.\scripts\prepare-offline-models.ps1
.\scripts\build-exe.ps1
```

Quy trình bắt buộc của script:

1. Kiểm tra source runtime và package version.
2. Sinh third-party notices ở strict mode.
3. Xóa riêng artifact `dist\HaizFlow` cũ sau khi xác thực đường dẫn.
4. Build PyInstaller `--onedir`.
5. Chép application license, notices và license texts.
6. Tính dung lượng cài đặt từ artifact thực tế; build bị chặn nếu ổ đích không đủ không gian an toàn.
7. Chạy frozen self-test và FFmpeg/FFprobe.
8. Chạy CPU native runtime probe; chạy GPU probe nếu CUDA khả dụng.
9. Khởi tạo Qt/QML/Multimedia bằng data tạm, không warm model, rồi tự thoát.
10. Sau smoke mới tạo `BUILD-INFO.json`, SHA-256, rồi tự xác minh lại toàn bộ manifest.

`HaizFlow.spec` không còn là entrypoint build để tránh hai cấu hình PyInstaller khác nhau. Chỉ dùng `scripts\build-exe.ps1`; script cố định `cwd`, `distpath`, `workpath` và `specpath` dưới repository. Version resource và icon được sinh từ source trước khi chạy PyInstaller.

## Installer

`scripts\build-installer.ps1` chỉ nhận artifact đã có `SHA256SUMS.txt` hợp lệ, rồi gọi `installer\HaizFlow.iss`. Wizard cho người dùng chọn thư mục cài đặt writable; mặc định là per-user để tránh Program Files không có quyền ghi. `runtime\` là dữ liệu mutable và bị loại khỏi cả overwrite khi upgrade lẫn xóa khi uninstall, nên project, model và settings được giữ nguyên. Script có thể ký EXE/installer khi được cấp certificate qua `-SignCertificatePath` và mật khẩu qua biến môi trường `HAIZFLOW_SIGN_CERT_PASSWORD`; không có certificate thì artifact vẫn chỉ là unsigned RC.

`-SkipFrozenSmokeTest` chỉ dành cho chẩn đoán build, không được dùng để tạo artifact phát hành.

## Ma trận nghiệm thu trước production

- Windows 10 và Windows 11 x64 sạch.
- Máy CPU-only Intel và AMD với 8 GB, 16 GB và 32 GB RAM.
- NVIDIA 6 GB, 8 GB và lớn hơn; GPU không hỗ trợ BF16; driver cũ hoặc thiếu driver.
- Không mạng, mạng chậm, Edge TTS gián đoạn và URL extractor thay đổi.
- Tài khoản Windows và đường dẫn project có Unicode.
- Ổ gần đầy, project trên ổ rời, sleep/hibernate và mất nguồn GPU giữa pipeline.
- Mở app hai lần, nâng cấp từ dữ liệu legacy, pause/resume/restart và batch queue dài.

## Quyết định phát hành

Beta nội bộ được phép khi ID 1 và ID 3 đã qua release gate. Phát hành công khai bị chặn cho đến khi hoàn tất tối thiểu ID 2, 4, 5, 9 và 11. Tài liệu này không thay thế tư vấn pháp lý chuyên môn.
