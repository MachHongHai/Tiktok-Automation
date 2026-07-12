# Auto Dub Video Local

**Documentation:** English | [Tiếng Việt](README.vi.md)

Auto Dub Video Local is a Windows desktop application for producing translated, dubbed, and captioned video exports on a local machine. It is designed for offline-first project management: source media, processing artifacts, logs, model caches, and finished exports remain on user-controlled storage rather than being uploaded to an application server.

The application combines WhisperX speech recognition and alignment, Tencent HY-MT2 local machine translation, Edge TTS voice synthesis, and FFmpeg rendering behind a PySide6 and QML desktop interface.

> This project is intended for media that you own or are authorised to process. Verify the rights, privacy implications, and local regulations that apply to your source material and generated output.

## Free and Local-First

The application has no subscription, paid API key, hosted processing queue, or server-side video upload. WhisperX transcription, HY-MT2 translation, checkpoint caching, subtitle generation, audio mixing, and rendering execute on the user's computer. This design keeps source media and processing artifacts under the user's control while avoiding per-minute or per-video cloud processing charges.

The only network-dependent runtime stage is Edge TTS voice synthesis. It is used without an application-paid API key, but it requires Internet access and remains subject to the service availability and terms of its provider. The application does not claim that all model inference is non-AI; rather, it uses local AI models instead of sending video content to a hosted AI processing service.

## Capabilities

- Import MP4, MOV, and MKV source media into named local projects.
- Detect source speech language automatically or use a selected source language.
- Translate into the supported target-language list with the local HY-MT2 model.
- Select an Edge TTS voice for the target language.
- Choose either a fully automatic workflow or a translation-review workflow.
- Review and edit translated segments before TTS and rendering.
- Generate short, sequential subtitle cues suitable for social-video viewing.
- Edit subtitle placement and scale in a dedicated QML preview window.
- Preserve or reduce original audio, with optional Demucs vocal separation for music-heavy or noisy media.
- Pause a running project, reopen it from Projects, and resume it later.
- Reuse validated pipeline checkpoints when a project is restarted with compatible inputs.
- Run queued projects sequentially through the Batch workspace.

## System Design

```text
Source video
  -> audio extraction (FFmpeg)
  -> optional vocal separation (Demucs)
  -> transcription and alignment (WhisperX)
  -> translation (HY-MT2)
  -> optional human review
  -> voice synthesis (Edge TTS)
  -> audio timeline mixing
  -> subtitle composition and video rendering (FFmpeg)
```

The application warms the WhisperX ASR model in the background after startup. The first job can reuse that resident model when warm-up has completed. The model is released when the application exits.

## Technology Stack

| Area | Implementation |
| --- | --- |
| Desktop interface | PySide6, QML, Qt Quick Controls, Qt Multimedia |
| Speech recognition | WhisperX |
| Translation | Tencent HY-MT2-1.8B via an isolated local worker |
| Voice synthesis | Edge TTS |
| Audio and video processing | FFmpeg, Pydub, optional Demucs |
| Data validation | Pydantic |
| Packaging | PyInstaller (`--onedir`) |

Node.js, a browser frontend, React, Vite, FastAPI, and an external database are not required for the desktop runtime.

## Requirements

- Windows 10 or Windows 11.
- A supported Python installation for the pinned dependencies in `requirements.txt`.
- NVIDIA CUDA is strongly recommended for practical WhisperX and HY-MT2 performance. CPU execution is supported but substantially slower.
- FFmpeg and FFprobe in `runtime/bin` when running from source.
- Internet access is required by Edge TTS when voices are generated. Model downloads also require access to Hugging Face on first use.

## Quick Start

```powershell
git clone <repository-url>
cd auto-dub-video-local
Copy-Item .env.example .env
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

To run the application directly after the virtual environment has been created:

```powershell
.\.venv\Scripts\python.exe .\autodub_desktop.py
```

The desktop window opens maximised. WhisperX warm-up continues in the background; the interface remains usable while it loads.

## Configuration

Copy `.env.example` to `.env` and adjust only the settings you need.

```env
# Store jobs, logs, thumbnails, and model caches on a user-controlled drive.
RUNTIME_DATA_DIR=D:\AutoDubData

# WhisperX ASR model: tiny, base, small, medium, or large-v3.
WHISPER_MODEL=small

# Local translation model downloaded from Hugging Face on first use.
HYMT2_MODEL=tencent/Hy-MT2-1.8B

# Maximum simultaneous Edge TTS requests. Valid values are 1 through 4.
TTS_MAX_CONCURRENCY=3
```

`RUNTIME_DATA_DIR` is the most important setting for an offline desktop installation. If it is not set, runtime data defaults to `%LOCALAPPDATA%\AutoDubVideoLocal\data`. Set an absolute path, such as `D:\AutoDubData`, before importing large media if drive C should remain unused.

`HF_HOME` and `TORCH_HOME` can also be set to absolute paths when Hugging Face and Torch caches must be stored separately. See `.env.example` for examples.

## Workflows

### Full Auto

Full Auto runs the complete pipeline without interaction: transcription, translation, subtitle generation, TTS, audio mixing, and rendering.

### Review Translation

Review Translation pauses after HY-MT2 has produced the translated segments. The project enters `awaiting_review`; select **Review translation**, edit individual segments in the modal editor, then choose **Approve and continue**. The application proceeds with subtitle generation, TTS, mixing, and rendering without running WhisperX or HY-MT2 again.

## Projects, Pause, Resume, and Restart

Projects are independent local jobs represented by a thumbnail in the Projects workspace. Opening a project restores its input media, setup, logs, progress, and output actions.

- **Pause** stops active subprocesses and records the latest safe pipeline step.
- **Resume** continues from translated segments when that checkpoint exists; earlier incomplete stages are repeated safely.
- **Restart** applies the current Dubbing setup and runs the project again.
- **Replace** updates the project's stored input video and thumbnail; restart afterwards to process the replacement source.

## Checkpoint Cache

Each job stores checkpoint signatures in its `job.json`. A signature is derived from the relevant input files and settings, and an output is reused only when both the signature and expected files are valid.

| Change | Reused work | Work performed again |
| --- | --- | --- |
| No source or language change | Translation, subtitles, voices, audio mix, render when valid | None or only invalid/missing outputs |
| Voice change | Translation and subtitles | Voice synthesis, audio mix, render |
| Original-audio volume change | Translation, subtitles, voice parts | Audio mix, render |
| Subtitle style or layout change | Translation, voice parts, mixed audio | Subtitle composition, render |
| Source video, source language, target language, or separation change | None | Processing starts from the affected upstream stage |

Checkpoints are local implementation artifacts, not permanent archives. Deleting a project's `temp` directory intentionally invalidates the corresponding stages.

## Runtime Storage

With `RUNTIME_DATA_DIR=D:\AutoDubData`, the application uses a layout similar to:

```text
D:\AutoDubData\
  jobs\<job-id>\
    input\video.<ext>
    temp\audio.wav
    temp\source_segments.json
    temp\vi_segments.json
    temp\voice_parts\
    output\final.mp4
    logs.txt
    job.json
  projects\<project-name>\dubbed_video.mp4
  cache\thumbnails\
  cache\huggingface\
  cache\torch\
  logs\
  desktop-settings.json
```

The project output path may differ from the job's internal output directory because a named project writes its final export to the selected project folder.

To migrate legacy runtime data deliberately:

```powershell
.\scripts\migrate-runtime-data.ps1 -Move
```

Review the script output before using `-Move`.

## Logs and Diagnostics

Every job has a persistent log file at:

```text
<RUNTIME_DATA_DIR>\jobs\<job-id>\logs.txt
```

The Activity Log in the application tails the selected job's log. Progress text and log entries are emitted from the same translation and TTS callbacks, so messages such as `Translating segment 2 of 3` correspond to the visible processing state.

Application-level logs are stored under:

```text
<RUNTIME_DATA_DIR>\logs\
```

## Development

The source layout follows responsibility boundaries:

```text
src/autodub/
  desktop/       PySide6 application bootstrap, controller, and QML interface
  pipeline/      Extraction, ASR, translation orchestration, TTS, mixing, rendering
  services/      Job persistence, desktop-job creation, settings, translation worker
  schemas/       Pydantic data contracts
  core/          Paths, logging, and in-process events
  utils/         FFmpeg and shared utility functions
```

Use the source runtime while developing. Rebuild the executable only for a distributable release.

```powershell
.\scripts\run-desktop.ps1
```

## Build a Windows Distribution

```powershell
.\scripts\build-exe.ps1
```

The result is an `--onedir` PyInstaller distribution:

```text
dist\AutoDubVideoLocal\AutoDubVideoLocal.exe
```

`--onedir` is intentional. Torch, WhisperX, Qt, and their native libraries are large and rely on adjacent runtime files. Do not move only the executable out of its distribution directory.

## Performance Notes

- WhisperX is warmed on application startup and retained in memory until shutdown.
- HY-MT2 runs in an isolated worker and releases model memory after translation to protect GUI stability.
- Edge TTS uses a bounded concurrency of three requests by default; adjust `TTS_MAX_CONCURRENCY` only after observing network reliability.
- Demucs is disabled by default because it is expensive; enable it only when background music or noise materially degrades speech recognition.
- Sequential batch processing avoids competing for GPU memory across jobs.

## Known Constraints

- Edge TTS is a network service; synthesis requires connectivity and may be rate-limited.
- Translation quality depends on source transcription quality, language pair, and the local model.
- Timing is preserved by compressing overlong TTS segments; some language pairs may still sound faster than the original speech.
- The application is optimised for a single active processing job. Batch work is queued sequentially.

## Additional Documentation

- [Architecture](docs/architecture.md)
- [.env.example](.env.example)
- [requirements.txt](requirements.txt)
