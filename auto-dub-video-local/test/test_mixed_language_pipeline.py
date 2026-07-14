import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.pipeline import transcribe
from autodub.schemas.job import JobConfig
from autodub.services import hymt2_worker, job_store, translation
from autodub.services.hymt2_worker import (
    _build_prompt,
    _build_translation_prompts,
    _clean_single_translation,
    _context_after_end,
    _context_before_start,
    _inference_batches,
)


class _LanguageModel:
    def __init__(self, languages):
        self.languages = iter(languages)
        self.clip_lengths = []

    def detect_language(self, **kwargs):
        self.clip_lengths.append(len(kwargs["audio"]))
        language, confidence = next(self.languages)
        return language, confidence, [(language, confidence)]


class _AsrModel:
    def __init__(self, languages):
        self.model = _LanguageModel(languages)


class MixedLanguagePipelineTests(unittest.TestCase):
    def test_segment_language_detection_and_alignment_mapping(self):
        original_log = transcribe.log_to_job
        transcribe.log_to_job = lambda *_args, **_kwargs: None
        try:
            segments = [
                {"start": 0.0, "end": 1.0, "text": "Hello"},
                {"start": 2.0, "end": 3.5, "text": "Xin chao"},
            ]
            model = _AsrModel([("en", 0.98), ("vi", 0.92)])
            detected = transcribe._detect_segment_languages(
                model,
                np.zeros(16_000 * 5, dtype=np.float32),
                segments,
                "en",
                "test-job",
            )
        finally:
            transcribe.log_to_job = original_log

        self.assertEqual([segment["language"] for segment in detected], ["en", "vi"])
        self.assertEqual(model.model.clip_lengths, [16_000, 24_000])
        language, confidence = transcribe._language_for_aligned_segment(
            {"start": 2.1, "end": 3.2}, detected, "en"
        )
        self.assertEqual(language, "vi")
        self.assertEqual(confidence, 0.92)

    def test_translation_uses_the_language_from_each_segment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "source.json"
            output_path = Path(temp_dir) / "translated.json"
            input_path.write_text(
                json.dumps(
                    [
                        {"start": 0, "end": 1, "text": "Hello", "language": "en"},
                        {"start": 1, "end": 2, "text": "Xin chao", "language": "vi"},
                    ]
                ),
                encoding="utf-8",
            )
            captured = {}
            original_worker = translation._translate_with_hymt2_worker
            original_log = translation.log_to_job
            translation._translate_with_hymt2_worker = lambda texts, **kwargs: captured.update(kwargs) or ["Bonjour", "Hello"]
            translation.log_to_job = lambda *_args, **_kwargs: None
            try:
                translated = translation.translate_segments(
                    str(input_path), str(output_path), "test-job", target_language="fr", source_language="en"
                )
            finally:
                translation._translate_with_hymt2_worker = original_worker
                translation.log_to_job = original_log

        self.assertEqual(captured["source_languages"], ["English", "Vietnamese"])
        self.assertEqual([segment["source_language"] for segment in translated], ["en", "vi"])

    def test_alignment_uses_a_model_per_detected_language(self):
        loaded_languages = []
        original_load = transcribe.whisperx.load_align_model
        original_align = transcribe.whisperx.align
        original_log = transcribe.log_to_job
        transcribe.whisperx.load_align_model = lambda language_code, device: (loaded_languages.append(language_code) or object(), {})
        transcribe.whisperx.align = lambda segments, *_args, **_kwargs: {"segments": segments}
        transcribe.log_to_job = lambda *_args, **_kwargs: None
        try:
            aligned = transcribe._align_segments_by_language(
                np.zeros(16_000 * 4, dtype=np.float32),
                [
                    {"start": 2, "end": 3, "text": "Konnichiwa", "language": "ja"},
                    {"start": 0, "end": 1, "text": "Hello", "language": "en"},
                ],
                "cpu",
                "test-job",
            )
        finally:
            transcribe.whisperx.load_align_model = original_load
            transcribe.whisperx.align = original_align
            transcribe.log_to_job = original_log

        self.assertEqual(loaded_languages, ["ja", "en"])
        self.assertEqual([segment["text"] for segment in aligned], ["Hello", "Konnichiwa"])

    def test_hymt2_prompt_batches_preserve_order_and_context(self):
        texts = ["Hello", "How are you?", "Fine.", "Thanks", "Bye"]
        self.assertEqual(list(_inference_batches(texts, batch_size=4)), [(0, 4), (4, 5)])
        self.assertEqual(_context_before_start(["A" * 900, "B"], 2), 1)
        self.assertEqual(_context_after_end(["A", "B" * 900], 1), 1)

        prompt = _build_prompt(
            ["Hello", "How are you?", "Fine."],
            ["English", "English", "English"],
            1,
            "Vietnamese",
        )
        self.assertIn("[Background Information]", prompt)
        self.assertIn("Previous subtitle: Hello", prompt)
        self.assertIn("Following subtitle: Fine.", prompt)
        self.assertIn("[Source Text]\nHow are you?", prompt)
        self.assertIn("Translate only the [Source Text], not the background", prompt)
        self.assertIn("do not paraphrase, expand, or omit information", prompt)
        self.assertIn("Only output the translated result", prompt)
        self.assertNotIn("JSON", prompt)

        prompts = _build_translation_prompts(
            texts,
            ["English"] * len(texts),
            0,
            4,
            "Vietnamese",
        )
        self.assertEqual(len(prompts), 4)
        self.assertIn("[Source Text]\nHello", prompts[0])
        self.assertIn("[Source Text]\nThanks", prompts[3])

        focused_prompt = _build_prompt(
            ["Honey details", "Top 20%.", "Banana details", "Top 10%."],
            ["English"] * 4,
            2,
            "Vietnamese",
        )
        self.assertNotIn("Honey details", focused_prompt)
        self.assertIn("Previous subtitle: Top 20%.", focused_prompt)
        self.assertIn("Following subtitle: Top 10%.", focused_prompt)

    def test_hymt2_worker_writes_response_and_progress_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            request_path = Path(temp_dir) / "request.json"
            response_path = Path(temp_dir) / "response.json"
            progress_path = Path(temp_dir) / "progress.jsonl"
            request_path.write_text(
                json.dumps(
                    {
                        "texts": ["Hello"],
                        "source_languages": ["English"],
                        "target_language_name": "Vietnamese",
                    }
                ),
                encoding="utf-8",
            )
            original_translate = hymt2_worker.translate
            hymt2_worker.translate = lambda _payload: ["Xin chao"]
            try:
                exit_code = hymt2_worker.main(
                    [
                        "--request",
                        str(request_path),
                        "--response",
                        str(response_path),
                        "--progress",
                        str(progress_path),
                    ]
                )
            finally:
                hymt2_worker.translate = original_translate

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(response_path.read_text(encoding="utf-8")), {"translations": ["Xin chao"]})
            self.assertTrue(progress_path.is_file())

    def test_hymt2_single_fallback_accepts_plain_and_json_text(self):
        self.assertEqual(_clean_single_translation("Xin chao"), "Xin chao")
        self.assertEqual(_clean_single_translation('"Xin chao"'), "Xin chao")
        self.assertEqual(_clean_single_translation('["Xin chao"]'), "Xin chao")

    def test_hymt2_server_protocol_starts_and_stops_without_loading_the_model(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(SRC) + os.pathsep + environment.get("PYTHONPATH", "")
        process = subprocess.Popen(
            [sys.executable, "-m", "autodub.services.hymt2_worker", "--server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        try:
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write('{"request_id":"ping-1","command":"ping"}\n')
            process.stdin.flush()
            self.assertEqual(json.loads(process.stdout.readline()), {"event": "response", "request_id": "ping-1", "ready": True})
            process.stdin.write('{"request_id":"stop-1","command":"shutdown"}\n')
            process.stdin.flush()
            self.assertEqual(json.loads(process.stdout.readline()), {"event": "response", "request_id": "stop-1", "stopped": True})
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                process.kill()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_job_store_serializes_concurrent_updates_and_recovers_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_jobs_dir = job_store.JOBS_DIR
            job_store.JOBS_DIR = temp_dir
            try:
                job = job_store.create_job("job-store-test", "input.mp4", JobConfig())
                failures = []

                def update_progress(offset):
                    try:
                        for value in range(offset, 100, 10):
                            job_store.update_job(job.job_id, progress=value, step="processing")
                            self.assertIsNotNone(job_store.get_job(job.job_id))
                    except Exception as exc:  # pragma: no cover - assertion is reported below.
                        failures.append(exc)

                threads = [threading.Thread(target=update_progress, args=(offset,)) for offset in range(5)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(failures, [])
                path = Path(job_store.get_job_json_path(job.job_id))
                self.assertIsNotNone(job_store.get_job(job.job_id))
                self.assertTrue(Path(str(path) + ".bak").exists())

                path.write_text("{", encoding="utf-8")
                recovered = job_store.get_job(job.job_id)
                self.assertIsNotNone(recovered)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["job_id"], job.job_id)
            finally:
                job_store.JOBS_DIR = original_jobs_dir


if __name__ == "__main__":
    unittest.main()
