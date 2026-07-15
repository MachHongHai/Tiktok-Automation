# Architecture

## Purpose and Boundaries

Auto Dub Video Local is a local-first Windows application. The desktop process owns the user interface, job state, and orchestration. Media processing happens in Python pipeline modules and external command-line tools. No HTTP backend, browser client, or cloud database is part of the runtime architecture.

```text
PySide6 / QML desktop shell
  -> AutoDubController
  -> local job store and project files
  -> pipeline orchestration
  -> WhisperX, HY-MT2 worker, Edge TTS, Demucs, FFmpeg
```

## Source Layout

```text
src/autodub/
  desktop/
    main.py                 Qt application bootstrap
    qml_controller.py       Thin QML-facing state and command coordinator
    catalog.py              Supported target languages and TTS voices
    localization.py         Localized native Qt dialog adapters
    media.py                Video-path, thumbnail, and OS-open helpers
    models.py               QAbstractListModel implementations for QML
    presenters.py           Project summaries and localized display mapping
    url_import.py           QML-facing background URL import state coordinator
    qml/                    Pages, dialogs, design tokens, and reusable controls
  pipeline/
    process_job.py          Stage orchestration and checkpoint validation
    extract_audio.py        FFmpeg audio extraction
    transcribe.py           WhisperX warm cache, transcription, and alignment
    audio_separation.py     Optional Demucs integration
    tts.py                  Bounded-concurrency Edge TTS synthesis
    audio_timeline.py       Timestamped speech and background-audio mixing
    subtitle.py             SRT generation
    render.py               FFmpeg video and ASS subtitle rendering
  services/
    job_store.py            Persistent job metadata and per-job logs
    desktop_jobs.py         Project-aware job creation and media import
    video_download.py       YouTube, TikTok, and Douyin URL inspection/download
    translation.py          HY-MT2 worker protocol
    hymt2_worker.py         Isolated local translation worker entry point
    desktop_settings.py     Theme and language persistence
  schemas/
    job.py                  JobConfig and JobInfo contracts
  core/
    paths.py                Source, frozen-app, and runtime-data path resolution
    events.py               In-process job-log notifications
```

## Ownership Rules

New code should follow these boundaries so features remain independently testable:

- `desktop/qml/` owns presentation, animation, layout, and direct user interaction.
- `desktop/qml_controller.py` translates QML commands into application operations and exposes observable state. It must not implement media algorithms.
- `desktop/models.py` owns list-model roles and update semantics. Add a new model here instead of embedding it in the controller.
- `services/` owns reusable application use cases, persistence, queues, and isolated model-worker protocols. Services must not import QML files.
- `pipeline/` owns ordered media stages. A stage receives explicit inputs, writes declared outputs, and reports progress through callbacks.
- `schemas/` owns persisted and cross-layer data contracts. Additive schema changes require defaults so existing projects remain readable.
- `core/` owns process-wide policy and infrastructure with no UI dependency.
- `utils/` is reserved for small stateless helpers; domain workflows belong in services or pipeline modules.

## Extension Guide

| Change | Primary location | Required follow-through |
| --- | --- | --- |
| New screen or dialog | `desktop/qml/` | Add reusable controls to `qmldir`; expose only required controller state. |
| New project command | `services/` | Add a narrow controller slot and unit tests for the service. |
| New pipeline stage | `pipeline/` | Add checkpoint signature, progress mapping, cancellation checks, and a persisted output path. |
| New translation or TTS provider | `services/` | Define one stable request/response boundary; keep provider details out of QML. |
| New persisted setting | `services/desktop_settings.py` | Add a default, validation, migration behavior, and QML binding. |
| New job/project field | `schemas/job.py` | Preserve backward compatibility and test loading old metadata. |

`pyproject.toml` is the canonical package and dependency declaration. `requirements.txt` only supplies the custom binary indexes and installs that package in editable mode for development. QML files are declared as package data so source installs and future non-PyInstaller distributions use the same asset layout.

Run `scripts/test.ps1` before merging. It compiles application, script, and test modules before running the complete unit suite. `scripts/verify-runtime.py` reads pinned versions directly from `pyproject.toml`, validates native runtime prerequisites, and is mandatory before an executable build.

## Application Lifecycle

1. `autodub_desktop.py` relaunches itself with `.venv\Scripts\python.exe` when available. The source launcher exits after creating the project-runtime process; it does not import Qt or ML packages from the system Python installation.
2. `autodub.desktop.main` creates the Qt application and registers `AutoDubController` with the QML engine.
3. `AutoDubController` loads settings and project metadata, starts polling timers, then warms the persistent HY-MT2 worker followed by WhisperX on a background thread.
4. `Main.qml` presents Projects, Batch, Settings, and the shared processing workspace.
5. Closing the application unsubscribes log events, shuts down the HY-MT2 worker, and releases both warmed models.

## Job State Model

`JobInfo` is persisted as `job.json` inside the owning project's `videos/<video-id>` workspace. Its important states are:

| State | Meaning |
| --- | --- |
| `pending` | Created but not processing. |
| `processing` | A pipeline stage is active. |
| `awaiting_review` | Translation is ready and waits for user edits. |
| `paused` | Processing was interrupted by the user; `resume_step` records the safe checkpoint. |
| `done` | Final video has been rendered. |
| `failed` | The pipeline captured an exception and wrote it to the job log. |
| `cancelled` | A destructive cancellation occurred. |

Every update persists progress, stage detail, current/total item counts, and timestamps. Job metadata uses a per-job lock plus atomic replacement (`temp -> fsync -> replace`) and retains the last valid `.bak` copy, so UI polling cannot observe a partially written `job.json`. The QML progress surface reads this persisted data rather than maintaining a separate progress model.

## Pipeline

```text
video input
  -> extract audio
  -> selected audio mode: preserve the original track, or use Demucs vocals/no-vocals separation
  -> WhisperX transcription, sentence alignment, and per-subtitle language identification
  -> HY-MT2 translation
  -> optional translation review
  -> SRT generation
  -> Edge TTS voice parts
  -> audio timeline construction
  -> FFmpeg render
```

Local files and downloaded links share the same import boundary. `services.video_download` validates an allowlist of
YouTube, TikTok, and Douyin hosts, uses yt-dlp to inspect one non-live video, and downloads into a project-owned
`.downloads` staging directory. `desktop.url_import` exposes metadata and progress to one shared QML dialog. Only after
the download is complete does the controller create or replace the persisted video workspace; successful, failed, and
cancelled downloads remove their staging directory. The processing queue therefore never observes a partial source file.

### WhisperX

`pipeline.transcribe` owns a process-local ASR cache. Warm-up loads the configured WhisperX model in a background thread when the detected memory profile can safely retain it. Subsequent transcription calls reuse it when the device matches. CUDA uses FP16 and a larger batch; CPU uses INT8, a RAM-aware batch of one to four, and a bounded thread count. Low-memory CPU profiles release the warm ASR model before translation. WhisperX first produces sentence-level subtitle boundaries, then the same ASR model identifies the language of each sentence from only that sentence's audio. Detected language switches are transcribed again with the appropriate tokenizer and aligned with the matching language model, so a mixed-language video is not forced into the language detected at its beginning. Alignment models are short-lived and released after use because they are language-specific and can consume significant memory.

Audio is decoded by the bundled FFmpeg process and passed to WhisperX as an in-memory waveform. The active pipeline therefore does not depend on TorchCodec's optional native decoder. Enabling that decoder on Windows would additionally require a compatible FFmpeg `full-shared` distribution; the static command-line FFmpeg bundle is intentionally kept smaller.

### Translation

HY-MT2 runs in a persistent separate process. In source mode the parent invokes the worker with the same project virtual-environment interpreter; in a frozen build it invokes the executable's internal `--hymt2-worker` entry point. The worker receives JSON-line requests over standard input and returns JSON-line status, item-progress, and response events. Each subtitle is translated independently while bounded preceding topic anchors are supplied as reference-only context. This keeps the one-input/one-output contract required by TTS, avoids subject leakage between adjacent subtitles, and prevents unbounded full-video prompts.

The runtime selects one of two inference backends according to the persisted `gpu` or `cpu` preference. CUDA uses the official Transformers BF16 model and keeps the warm worker for the desktop session. On supported 7-8 GB Windows GPUs, the same BF16 checkpoint is staged in system memory before transfer to CUDA to avoid a native Transformers meta-tensor loading failure; only the inference batch size is reduced. CPU mode uses the official `Hy-MT2-1.8B-Q4_K_M.gguf` model through `llama-cpp-python`, one prompt at a time. CPU translation is loaded only when needed and is released after a RAM-profile-dependent idle period. An installer may embed the GGUF file under `models/hymt2-gguf`; otherwise it is downloaded once into the configured runtime data directory.

### Voice Synthesis

`pipeline.tts` creates one MP3 per translated segment. Edge TTS requests run sequentially by default because its consumer WebSocket endpoint is less reliable under concurrent requests; `TTS_MAX_CONCURRENCY` remains an advanced override. Each response is written to a temporary file and promoted atomically only after MP3 validation. Segments that exhaust the primary retry budget are recovered with fresh connections and longer backoff. Persistent failures stop the pipeline before rendering instead of inserting silent audio. Completion callbacks update both persistent progress and the project log.

### Audio Source Modes

The two audio modes are mutually exclusive. Original mode mixes the source track at the user-selected volume. Separation mode transcribes the Demucs vocals track and mixes the no-vocals track at full volume; the original-volume setting is intentionally ignored. Both separated paths are persisted in the project workspace so translation review, pause/resume, and GPU recovery reuse the correct audio. If a separated background artifact is missing, the pipeline regenerates it instead of silently falling back to the source vocals.

### Checkpoints

`process_job.py` records checkpoint signatures for translation, subtitles, voice parts, mixed audio, and final rendering. A checkpoint is valid only when its signature matches current inputs and all expected outputs exist and are non-empty. This permits safe reuse while preventing stale output from being treated as current.

## Runtime Data and Packaging

`core.paths` separates mutable data from source code and from the frozen executable bundle. `RUNTIME_DATA_DIR` controls the app-level cache, models, settings, diagnostics, and project index. Each project owns all of its video data and can be stored under the location selected when creating that project.

```text
<project>/
  .autodub-project.json
  .downloads/                      Temporary URL downloads; removed after import
  exports/                         Final rendered videos
  videos/<video-id>/
    job.json, logs.txt
    input/, temp/, output/          Imported media and resumable workspace
```

There is no active global `jobs` workspace. On startup, a compatible legacy `RUNTIME_DATA_DIR/jobs/<video-id>` workspace is moved into its registered project and every stored file path is rewritten before processing resumes.

The build uses PyInstaller `--onedir` because Qt, Torch, WhisperX, and FFmpeg require adjacent native files. The executable is not designed to be relocated independently from its distribution directory.

The unified dependency set is version-pinned in `pyproject.toml`. It contains a CUDA-capable Torch build for GPU systems and `llama-cpp-python` for CPU translation. CUDA Torch remains able to execute CPU inference on systems without an NVIDIA driver, so one virtual environment and one installer cover both paths. `requirements.txt` supplies the custom wheel indexes and installs the package. `scripts/verify-runtime.py` validates the active environment, package versions, Qt modules, Torch build, cache locations, bundled FFmpeg tools, and `pip check`. `scripts/build-exe.ps1` runs this verifier before PyInstaller. The optional `-IncludeCpuModel` switch embeds the prepared GGUF model so CPU translation does not need a first-run model download.

`core.hardware` is the single policy source for CUDA visibility, VRAM/RAM requirements, the persisted device preference, thread limits, Whisper batch size, warm-up policy, translation lifetime, and CPU/GPU labels exposed in Settings. GPU selection requires CUDA and at least 7 GB VRAM; CPU selection requires approximately 6 GB system RAM. A 7-8 GB GPU uses a lower-memory profile that releases WhisperX before HY-MT2 translation while retaining the full BF16 translation model. FFmpeg separately probes NVENC, Quick Sync, and AMF because hardware video encoding can remain available while AI inference is set to CPU. A failed hardware render is retried with `libx264` and the `veryfast` preset.

## Observability

`services.job_store.log_to_job` is the authoritative pipeline log path. It writes a timestamped line to the selected video's `<project>/videos/<video-id>/logs.txt` and emits an in-process event. The desktop controller subscribes to the event stream, appends live lines to the selected project's log, and polls persisted job metadata for state changes. The separate app log is diagnostic-only and never contains project media or pipeline state.

Each HY-MT2 process also writes a bounded diagnostic log under `<runtime-data>/logs/hymt2-workers`. It records the model/backend, Python and Torch/CUDA versions, RAM/commit/VRAM snapshots at tokenizer load, weight load, CUDA transfer, model readiness, and first generation, plus Python tracebacks and Windows native exit codes. The parent retains the newest 25 worker logs and includes the exact file path in translation failures.

## Concurrency Policy

- One foreground pipeline job is active at a time.
- Batch jobs are queued and run sequentially.
- CUDA warms HY-MT2 and WhisperX sequentially in the background to avoid competing model loads. CPU profiles warm only WhisperX when RAM permits.
- HY-MT2 is isolated in one persistent worker; CPU profiles shut it down after an adaptive idle interval, while CUDA retains it for the desktop session.
- Edge TTS is the only bounded fan-out stage, limited to one through four concurrent requests.

This policy favours GPU stability and reproducibility over maximising throughput on a single workstation.
