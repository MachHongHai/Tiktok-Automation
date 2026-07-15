import asyncio
import contextlib
import json
import os
import re
import unicodedata
import uuid

import edge_tts

from autodub.config import TTS_MAX_CONCURRENCY
from autodub.pipeline.job_manager import check_cancellation, is_cancelled
from autodub.services.job_store import log_to_job


_INITIAL_RETRIES = 3
_RECOVERY_RETRIES = 5
_MP3_MIN_BYTES = 512
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def preprocess_text_for_tts(text: str) -> str:
    """Normalize transport-sensitive characters without changing words."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(
        str.maketrans(
            {
                "\u00a0": " ",
                "\u200b": "",
                "\u200c": "",
                "\u200d": "",
                "\ufeff": "",
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2013": ",",
                "\u2014": ",",
                "\u2026": "...",
            }
        )
    )
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text and text[-1] not in ".!?,;:":
        text += "."
    return text


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _is_valid_mp3(path: str) -> bool:
    """Reject zero-byte and partial Edge TTS responses before timeline assembly."""
    try:
        if os.path.getsize(path) < _MP3_MIN_BYTES:
            return False
        with open(path, "rb") as file:
            header = file.read(3)
    except OSError:
        return False
    if header == b"ID3":
        return True
    return len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0


def _tts_error_code(error: Exception) -> str:
    """Return a stable diagnostic label for the user-facing job log."""
    error_type = type(error).__name__.lower()
    message = str(error).lower()
    if "noaudioreceived" in error_type or "no audio was received" in message:
        return "edge_no_audio"
    if isinstance(error, asyncio.TimeoutError) or "timeout" in error_type or "timed out" in message:
        return "network_timeout"
    if "websocket" in error_type or "clientconnector" in error_type or "connection" in error_type:
        return "network_connection"
    if isinstance(error, ValueError):
        return "invalid_tts_input"
    if isinstance(error, OSError):
        return "file_io"
    if isinstance(error, RuntimeError) and "invalid mp3" in message:
        return "invalid_audio"
    return "unexpected_error"


def _tts_error_detail(error: Exception, limit: int = 180) -> str:
    message = _ANSI_ESCAPE.sub("", str(error))
    message = " ".join(message.split()) or type(error).__name__
    return message if len(message) <= limit else f"{message[: limit - 3]}..."


def _tts_text_preview(text: str, limit: int = 220) -> str:
    """Keep the active sentence visible without allowing it to break the job log."""
    preview = " ".join(str(text or "").split())
    preview = _ANSI_ESCAPE.sub("", preview).replace('"', "'")
    if len(preview) > limit:
        preview = f"{preview[: limit - 3]}..."
    return f'"{preview or "<empty>"}"'


async def _sleep_with_cancellation(delay: float, job_id: str | None) -> None:
    deadline = asyncio.get_running_loop().time() + max(0.0, delay)
    while True:
        if job_id:
            check_cancellation(job_id)
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(0.25, remaining))


async def _save_with_cancellation(communicate, path: str, job_id: str | None) -> None:
    task = asyncio.create_task(communicate.save(path))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.25)
            if job_id and is_cancelled(job_id):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                check_cancellation(job_id)
        await task
    except BaseException:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        raise


async def tts_segment_with_retry(
    text: str,
    voice: str,
    output_path: str,
    retries: int = _INITIAL_RETRIES,
    *,
    job_id: str | None = None,
    base_delay: float = 1.5,
    retry_callback=None,
) -> int:
    """Create one verified MP3 atomically, using a fresh connection per attempt."""
    processed_text = preprocess_text_for_tts(text)
    if not processed_text:
        raise ValueError("TTS text is empty after normalization.")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    last_error = None
    stagger = (sum(processed_text.encode("utf-8")) % 7) * 0.15
    for attempt in range(1, max(1, retries) + 1):
        if job_id:
            check_cancellation(job_id)
        temporary_path = f"{output_path}.part-{uuid.uuid4().hex}"
        try:
            communicate = edge_tts.Communicate(
                processed_text,
                voice,
                connect_timeout=15,
                receive_timeout=60,
            )
            await _save_with_cancellation(communicate, temporary_path, job_id)
            if not _is_valid_mp3(temporary_path):
                raise RuntimeError("Edge TTS returned an empty or invalid MP3 stream.")
            os.replace(temporary_path, output_path)
            return attempt
        except asyncio.CancelledError:
            _remove_file(temporary_path)
            raise
        except Exception as exc:
            _remove_file(temporary_path)
            if job_id and is_cancelled(job_id):
                check_cancellation(job_id)
            last_error = exc
            if attempt >= retries:
                break
            delay = min(12.0, base_delay * (2 ** (attempt - 1)) + stagger)
            if retry_callback:
                retry_callback(attempt, retries, exc, delay)
            await _sleep_with_cancellation(delay, job_id)
    raise RuntimeError(
        f"Edge TTS produced no valid audio after {max(1, retries)} attempts: {last_error}"
    ) from last_error


def _run_coroutine(coroutine):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coroutine)
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        asyncio.set_event_loop(None)
        loop.close()


def generate_voice_parts(
    segments_json_path: str,
    voice_parts_dir: str,
    voice: str,
    job_id: str,
    progress_callback=None,
):
    """Generate every segment, recovering transient online failures without silence."""
    request_mode = "sequential" if TTS_MAX_CONCURRENCY == 1 else "controlled_parallel"
    log_to_job(
        job_id,
        f"[TTS][SESSION_START] voice={voice} mode={request_mode} "
        f"max_concurrency={TTS_MAX_CONCURRENCY}",
    )
    os.makedirs(voice_parts_dir, exist_ok=True)
    with open(segments_json_path, "r", encoding="utf-8") as file:
        segments = json.load(file)

    async def run_all():
        total = len(segments)
        limiter = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
        completed = 0
        transient_failures = []

        def report_completed(index: int, *, phase: str, attempts: int, reused: bool = False) -> None:
            nonlocal completed
            completed += 1
            status = "REUSED" if reused else "COMPLETE"
            log_to_job(
                job_id,
                f"[TTS][{status}] segment={index}/{total} overall={completed}/{total} "
                f"phase={phase} attempts={attempts}",
            )
            if progress_callback:
                progress_callback(completed, total)

        def retry_logger(index: int, phase: str, text: str):
            def report(attempt, retries, error, delay):
                error_code = _tts_error_code(error)
                error_detail = _tts_error_detail(error)
                log_to_job(
                    job_id,
                    f"[TTS][RETRY] segment={index}/{total} phase={phase} attempt={attempt}/{retries} "
                    f"error={error_code} retry_in={delay:.1f}s text={_tts_text_preview(text)} "
                    f"detail={error_detail}",
                )

            return report

        async def synthesize(index, segment):
            text = str(segment.get("text") or "")
            part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
            if _is_valid_mp3(part_path):
                report_completed(index, phase="checkpoint", attempts=0, reused=True)
                return
            _remove_file(part_path)
            check_cancellation(job_id)
            log_to_job(
                job_id,
                f"[TTS][QUEUED] segment={index}/{total} characters={len(text)} "
                f"text={_tts_text_preview(text)}",
            )
            async with limiter:
                try:
                    log_to_job(
                        job_id,
                        f"[TTS][START] segment={index}/{total} phase=primary voice={voice} "
                        f"characters={len(text)} text={_tts_text_preview(text)} "
                        f"output={os.path.basename(part_path)}",
                    )
                    attempts = await tts_segment_with_retry(
                        text,
                        voice,
                        part_path,
                        _INITIAL_RETRIES,
                        job_id=job_id,
                        retry_callback=retry_logger(index, "primary", text),
                    )
                except Exception as exc:
                    if is_cancelled(job_id):
                        check_cancellation(job_id)
                    transient_failures.append((index, text, part_path, exc))
                    log_to_job(
                        job_id,
                        f"[TTS][RECOVERY_QUEUED] segment={index}/{total} "
                        f"error={_tts_error_code(exc)} text={_tts_text_preview(text)} "
                        f"detail={_tts_error_detail(exc)}",
                    )
                    return
            report_completed(index, phase="primary", attempts=attempts)

        if TTS_MAX_CONCURRENCY == 1:
            for index, segment in enumerate(segments, 1):
                await synthesize(index, segment)
        else:
            await asyncio.gather(
                *(synthesize(index, segment) for index, segment in enumerate(segments, 1))
            )

        permanent_failures = []
        if transient_failures:
            transient_failures.sort(key=lambda item: item[0])
            log_to_job(
                job_id,
                f"Recovering {len(transient_failures)} TTS segment(s) sequentially with fresh connections.",
            )
            await _sleep_with_cancellation(2.0, job_id)
            for index, text, part_path, initial_error in transient_failures:
                check_cancellation(job_id)
                log_to_job(
                    job_id,
                    f"[TTS][RECOVERY_START] segment={index}/{total} error={_tts_error_code(initial_error)} "
                    f"characters={len(text)} text={_tts_text_preview(text)}",
                )
                try:
                    attempts = await tts_segment_with_retry(
                        text,
                        voice,
                        part_path,
                        _RECOVERY_RETRIES,
                        job_id=job_id,
                        base_delay=2.5,
                        retry_callback=retry_logger(index, "recovery", text),
                    )
                except Exception as exc:
                    if is_cancelled(job_id):
                        check_cancellation(job_id)
                    permanent_failures.append((index, initial_error, exc))
                    _remove_file(part_path)
                    log_to_job(
                        job_id,
                        f"[TTS][FAILED] segment={index}/{total} phase=recovery "
                        f"error={_tts_error_code(exc)} text={_tts_text_preview(text)} "
                        f"detail={_tts_error_detail(exc)}",
                    )
                    continue
                report_completed(index, phase="recovery", attempts=attempts)

        invalid_indices = [
            index
            for index in range(1, total + 1)
            if not _is_valid_mp3(os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3"))
        ]
        if permanent_failures or invalid_indices:
            failed = sorted(set(invalid_indices) | {item[0] for item in permanent_failures})
            raise RuntimeError(
                "Edge TTS could not create valid audio for subtitle segment(s): "
                + ", ".join(str(index) for index in failed)
                + ". The project was stopped before rendering; resume it when the network service is available."
            )
        if completed != total:
            raise RuntimeError(f"TTS completion mismatch: verified {completed} of {total} segments.")

    _run_coroutine(run_all())
    log_to_job(job_id, "All segment voices were generated and verified successfully.")


def generate_single_voice(text: str, output_path: str, voice: str, job_id: str):
    """Create and verify a complete narration file."""
    log_to_job(job_id, f"Generating single narration voice file with '{voice}'.")

    async def run_single():
        await tts_segment_with_retry(text, voice, output_path, job_id=job_id)

    _run_coroutine(run_single())
    log_to_job(job_id, f"Successfully created narration file: {output_path}")
