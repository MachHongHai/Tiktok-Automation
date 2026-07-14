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
    qml_controller.py       QML-facing state, commands, and job coordination
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
    translation.py          HY-MT2 worker protocol
    hymt2_worker.py         Isolated local translation worker entry point
    desktop_settings.py     Theme and language persistence
  schemas/
    job.py                  JobConfig and JobInfo contracts
  core/
    paths.py                Source, frozen-app, and runtime-data path resolution
    events.py               In-process job-log notifications
```

## Application Lifecycle

1. `autodub_desktop.py` relaunches itself with `.venv\Scripts\python.exe` when available. The source launcher exits after creating the project-runtime process; it does not import Qt or ML packages from the system Python installation.
2. `autodub.desktop.main` creates the Qt application and registers `AutoDubController` with the QML engine.
3. `AutoDubController` loads settings and project metadata, starts polling timers, then warms WhisperX followed by the persistent HY-MT2 worker on a background thread.
4. `Main.qml` presents Projects, Batch, Settings, and the shared processing workspace.
5. Closing the application unsubscribes log events, shuts down the HY-MT2 worker, and releases both warmed models.

## Job State Model

`JobInfo` is persisted as `job.json` in the job directory. Its important states are:

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
  -> optional Demucs separation
  -> WhisperX transcription, sentence alignment, and per-subtitle language identification
  -> HY-MT2 translation
  -> optional translation review
  -> SRT generation
  -> Edge TTS voice parts
  -> audio timeline construction
  -> FFmpeg render
```

### WhisperX

`pipeline.transcribe` owns a process-local ASR cache. Warm-up loads the configured WhisperX model in a background thread. Subsequent transcription calls reuse it when the device matches. WhisperX first produces sentence-level subtitle boundaries, then the same ASR model identifies the language of each sentence from only that sentence's audio. Detected language switches are transcribed again with the appropriate tokenizer and aligned with the matching language model, so a mixed-language video is not forced into the language detected at its beginning. Alignment models are short-lived and released after use because they are language-specific and can consume significant VRAM.

Audio is decoded by the bundled FFmpeg process and passed to WhisperX as an in-memory waveform. The active pipeline therefore does not depend on TorchCodec's optional native decoder. Enabling that decoder on Windows would additionally require a compatible FFmpeg `full-shared` distribution; the static command-line FFmpeg bundle is intentionally kept smaller.

### Translation

HY-MT2 runs in a persistent separate process. In source mode the parent invokes the worker with the same project virtual-environment interpreter; in a frozen build it invokes the executable's internal `--hymt2-worker` entry point. The worker warms after WhisperX during app start, receives JSON-line requests over standard input, and returns JSON-line status, batch-progress, and response events. It translates bounded, sliding context windows: a core batch is translated as one ordered JSON array while two neighbouring subtitle sentences on each side are supplied only as context. This preserves sentence boundaries for TTS while retaining local dialogue context and avoiding an unbounded full-video prompt. The worker holds its model for subsequent jobs and releases it only on app shutdown, cancellation, timeout, or crash.

### Voice Synthesis

`pipeline.tts` creates one MP3 per translated segment. An asyncio semaphore bounds concurrent Edge TTS requests using `TTS_MAX_CONCURRENCY`, defaulting to three. Completion callbacks update both persistent progress and the job log.

### Checkpoints

`process_job.py` records checkpoint signatures for translation, subtitles, voice parts, mixed audio, and final rendering. A checkpoint is valid only when its signature matches current inputs and all expected outputs exist and are non-empty. This permits safe reuse while preventing stale output from being treated as current.

## Runtime Data and Packaging

`core.paths` separates mutable data from source code and from the frozen executable bundle. `RUNTIME_DATA_DIR` controls the root location. In a PyInstaller distribution, bundled code and Qt assets are read-only implementation files; jobs, models, logs, and outputs continue to use the selected runtime directory.

The build uses PyInstaller `--onedir` because Qt, Torch, WhisperX, and FFmpeg require adjacent native files. The executable is not designed to be relocated independently from its distribution directory.

The dependency set is version-pinned in `requirements.txt`. `scripts/verify-runtime.py` validates the active project virtual environment, package versions, Qt modules, Torch/CUDA visibility, cache locations, bundled FFmpeg tools, and `pip check`. `scripts/build-exe.ps1` runs this verifier before PyInstaller so a contaminated or incomplete environment cannot silently produce a release artifact.

## Observability

`services.job_store.log_to_job` is the authoritative pipeline log path. It writes a timestamped line to `logs.txt` and emits an in-process event. The desktop controller subscribes to the event stream, appends live lines to the selected project's log, and polls persisted job metadata for state changes.

## Concurrency Policy

- One foreground pipeline job is active at a time.
- Batch jobs are queued and run sequentially.
- WhisperX and HY-MT2 warm-up run sequentially in the background to avoid competing GPU loads.
- HY-MT2 is isolated in one persistent worker for the desktop session; a cancelled job force-stops that worker and the next request creates a clean replacement.
- Edge TTS is the only bounded fan-out stage, limited to one through four concurrent requests.

This policy favours GPU stability and reproducibility over maximising throughput on a single workstation.
