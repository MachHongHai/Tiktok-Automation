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

1. `autodub_desktop.py` relaunches itself with `.venv\Scripts\python.exe` when available.
2. `autodub.desktop.main` creates the Qt application and registers `AutoDubController` with the QML engine.
3. `AutoDubController` loads settings and project metadata, starts polling timers, and begins WhisperX warm-up on a background thread.
4. `Main.qml` presents Projects, Batch, Settings, and the shared processing workspace.
5. Closing the application unsubscribes log events and releases the warmed WhisperX model.

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

Every update persists progress, stage detail, current/total item counts, and timestamps. The QML progress surface reads this persisted data rather than maintaining a separate progress model.

## Pipeline

```text
video input
  -> extract audio
  -> optional Demucs separation
  -> WhisperX transcription and alignment
  -> HY-MT2 translation
  -> optional translation review
  -> SRT generation
  -> Edge TTS voice parts
  -> audio timeline construction
  -> FFmpeg render
```

### WhisperX

`pipeline.transcribe` owns a process-local ASR cache. Warm-up loads the configured WhisperX model in a background thread. Subsequent transcription calls reuse it when the device matches. Alignment models are short-lived and released after use because they are language-specific and can consume significant VRAM.

### Translation

HY-MT2 runs in a separate Python process. The parent writes a JSON request into the job `temp` directory, streams JSON-lines progress from the worker, then reads the JSON response. Isolating translation protects the Qt process from native Torch failures and releases the translation model after each job.

### Voice Synthesis

`pipeline.tts` creates one MP3 per translated segment. An asyncio semaphore bounds concurrent Edge TTS requests using `TTS_MAX_CONCURRENCY`, defaulting to three. Completion callbacks update both persistent progress and the job log.

### Checkpoints

`process_job.py` records checkpoint signatures for translation, subtitles, voice parts, mixed audio, and final rendering. A checkpoint is valid only when its signature matches current inputs and all expected outputs exist and are non-empty. This permits safe reuse while preventing stale output from being treated as current.

## Runtime Data and Packaging

`core.paths` separates mutable data from source code and from the frozen executable bundle. `RUNTIME_DATA_DIR` controls the root location. In a PyInstaller distribution, bundled code and Qt assets are read-only implementation files; jobs, models, logs, and outputs continue to use the selected runtime directory.

The build uses PyInstaller `--onedir` because Qt, Torch, WhisperX, and FFmpeg require adjacent native files. The executable is not designed to be relocated independently from its distribution directory.

## Observability

`services.job_store.log_to_job` is the authoritative pipeline log path. It writes a timestamped line to `logs.txt` and emits an in-process event. The desktop controller subscribes to the event stream, appends live lines to the selected project's log, and polls persisted job metadata for state changes.

## Concurrency Policy

- One foreground pipeline job is active at a time.
- Batch jobs are queued and run sequentially.
- WhisperX warm-up is background work and serialises model loading with a lock.
- HY-MT2 is isolated in one short-lived worker per translation phase.
- Edge TTS is the only bounded fan-out stage, limited to one through four concurrent requests.

This policy favours GPU stability and reproducibility over maximising throughput on a single workstation.
