import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline import transcribe
from haizflow.pipeline.process_video import _timing_file_is_current
from haizflow.pipeline.subtitle import split_segment_into_cues
from haizflow.schemas.video import VideoConfig
from haizflow.services import hymt2_worker, video_store, translation
from haizflow.services.hymt2_worker import (
    _build_prompt,
    _build_translation_prompts,
    _clean_single_translation,
    _context_after_end,
    _context_before_start,
    _context_indices,
    _inference_batches,
    _output_token_budget,
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
    def test_segment_language_detection_uses_immutable_sentence_clips(self):
        original_log = transcribe.log_to_video
        transcribe.log_to_video = lambda *_args, **_kwargs: None
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
                "test-video",
            )
        finally:
            transcribe.log_to_video = original_log

        self.assertEqual([segment["language"] for segment in detected], ["en", "vi"])
        self.assertEqual(model.model.clip_lengths, [16_000, 24_000])

    def test_transcription_uses_whisperx_batch_api_for_source_text(self):
        class WhisperModel:
            def __init__(self):
                self.calls = []
                self.model = _LanguageModel([("en", 0.99)])

            def transcribe(self, _audio, **kwargs):
                self.calls.append(kwargs)
                return {
                    "language": "en",
                    "segments": [{"start": 0.1, "end": 1.1, "text": "S tier."}],
                }

        model = WhisperModel()
        profile = SimpleNamespace(
            cuda_available=False,
            cpu_threads=4,
            whisper_batch_size=8,
        )
        original_runtime_profile = transcribe.runtime_profile
        original_load_model = transcribe.whisperx.load_model
        original_load_audio = transcribe.whisperx.load_audio
        original_align = transcribe._align_segments_by_language
        original_release = transcribe._release_cuda
        original_log = transcribe.log_to_video
        transcribe.runtime_profile = lambda: profile
        transcribe.whisperx.load_model = lambda *_args, **_kwargs: model
        transcribe.whisperx.load_audio = lambda _path: np.zeros(32_000, dtype=np.float32)
        transcribe._align_segments_by_language = lambda _audio, segments, *_args, **_kwargs: segments
        transcribe._release_cuda = lambda *_args, **_kwargs: None
        transcribe.log_to_video = lambda *_args, **_kwargs: None
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / "segments.json"
                output, language = transcribe.transcribe(
                    "audio.wav",
                    str(output_path),
                    "auto",
                    "test-video",
                )
        finally:
            transcribe.runtime_profile = original_runtime_profile
            transcribe.whisperx.load_model = original_load_model
            transcribe.whisperx.load_audio = original_load_audio
            transcribe._align_segments_by_language = original_align
            transcribe._release_cuda = original_release
            transcribe.log_to_video = original_log

        self.assertEqual(language, "en")
        self.assertEqual(output[0]["text"], "S tier.")
        self.assertEqual(model.calls, [{"batch_size": 8, "language": None}])

    def test_mixed_language_retranscription_changes_text_only(self):
        class WhisperModel:
            def transcribe(self, _audio, **kwargs):
                self.language = kwargs["language"]
                return {"segments": [{"text": " Xin chao."}]}

        model = WhisperModel()
        original_log = transcribe.log_to_video
        transcribe.log_to_video = lambda *_args, **_kwargs: None
        try:
            source = [
                {"start": 1.25, "end": 3.75, "text": "bad", "language": "vi", "language_confidence": 0.95},
            ]
            corrected = transcribe._retranscribe_mixed_language_segments(
                model,
                np.zeros(16_000 * 5, dtype=np.float32),
                source,
                "en",
                "test-video",
            )
        finally:
            transcribe.log_to_video = original_log

        self.assertEqual(len(corrected), 1)
        self.assertEqual((corrected[0]["start"], corrected[0]["end"]), (1.25, 3.75))
        self.assertEqual(corrected[0]["text"], "Xin chao.")
        self.assertEqual(model.language, "vi")

    def test_bad_alignment_is_rejected_without_compressing_the_source_span(self):
        source = {
            "start": 0.031,
            "end": 19.893,
            "text": "Cau thu nhat rat dai. Cau thu hai cung dai. Cau thu ba. Cau thu bon.",
            "language": "vi",
        }
        compressed = [
            {
                "start": 0.031,
                "end": 8.781,
                "text": source["text"],
                "words": [
                    {"word": word, "start": 0.031, "end": 0.081, "score": 0.01}
                    for word in source["text"].split()
                ],
            }
        ]
        original_load_align_model = transcribe.whisperx.load_align_model
        original_align = transcribe.whisperx.align
        original_release = transcribe._release_cuda
        original_log = transcribe.log_to_video
        transcribe.whisperx.load_align_model = lambda **_kwargs: (object(), {})
        transcribe.whisperx.align = lambda *_args, **_kwargs: {"segments": compressed}
        transcribe._release_cuda = lambda *_args, **_kwargs: None
        transcribe.log_to_video = lambda *_args, **_kwargs: None
        try:
            aligned = transcribe._align_segments_by_language(
                np.zeros(16_000 * 21, dtype=np.float32),
                [source],
                "cpu",
                "test-video",
            )
        finally:
            transcribe.whisperx.load_align_model = original_load_align_model
            transcribe.whisperx.align = original_align
            transcribe._release_cuda = original_release
            transcribe.log_to_video = original_log

        self.assertEqual(len(aligned), 4)
        self.assertEqual(aligned[0]["start"], source["start"])
        self.assertEqual(aligned[-1]["end"], source["end"])
        self.assertEqual(" ".join(segment["text"] for segment in aligned), source["text"])
        self.assertTrue(all(left["end"] <= right["start"] for left, right in zip(aligned, aligned[1:])))

    def test_valid_alignment_keeps_model_sentence_timestamps(self):
        source = {"start": 1.0, "end": 6.0, "text": "First sentence. Second sentence.", "language": "en"}
        candidate = [
            {
                "start": 1.1,
                "end": 3.0,
                "text": "First sentence.",
                "words": [{"word": "First", "start": 1.1, "end": 1.5, "score": 0.8}],
            },
            {
                "start": 3.1,
                "end": 5.8,
                "text": "Second sentence.",
                "words": [{"word": "Second", "start": 3.1, "end": 3.6, "score": 0.7}],
            },
        ]

        self.assertEqual(transcribe._alignment_quality(source, candidate), (True, "coverage=0.94"))

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
            original_log = translation.log_to_video
            translation._translate_with_hymt2_worker = lambda texts, **kwargs: captured.update(kwargs) or ["Bonjour", "Hello"]
            translation.log_to_video = lambda *_args, **_kwargs: None
            try:
                translated = translation.translate_segments(
                    str(input_path), str(output_path), "test-video", target_language="fr", source_language="en"
                )
            finally:
                translation._translate_with_hymt2_worker = original_worker
                translation.log_to_video = original_log

        self.assertEqual(captured["source_languages"], ["English", "Vietnamese"])
        self.assertEqual([segment["source_language"] for segment in translated], ["en", "vi"])
        self.assertEqual(
            [(segment["start"], segment["end"]) for segment in translated],
            [(0, 1), (1, 2)],
        )
        self.assertEqual([segment["timing_source"] for segment in translated], ["unknown", "unknown"])

    def test_subtitle_cues_keep_all_text_inside_the_source_timestamp(self):
        segment = {
            "start": 9.22,
            "end": 15.18,
            "text": "Neu ban them mot thia mat ong, chat dinh duong se den co bap nhanh hon.",
        }

        cues = split_segment_into_cues(segment, 24)

        self.assertGreater(len(cues), 1)
        self.assertEqual(cues[0]["start"], segment["start"])
        self.assertEqual(cues[-1]["end"], segment["end"])
        self.assertEqual(
            " ".join(cue["text"].replace("\n", " ") for cue in cues),
            segment["text"],
        )
        self.assertTrue(all(segment["start"] <= cue["start"] < cue["end"] <= segment["end"] for cue in cues))

    def test_resume_accepts_only_current_aligned_timestamp_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            current_path = Path(temp_dir) / "current.json"
            legacy_path = Path(temp_dir) / "legacy.json"
            current_path.write_text(
                json.dumps([
                    {
                        "start": 0,
                        "end": 1,
                        "text": "Hello",
                        "timing_source": transcribe.TIMING_SOURCE,
                    }
                ]),
                encoding="utf-8",
            )
            legacy_path.write_text(
                json.dumps([{"start": 0, "end": 1, "text": "Hello"}]),
                encoding="utf-8",
            )

            self.assertTrue(_timing_file_is_current(current_path))
            self.assertFalse(_timing_file_is_current(legacy_path))

    def test_hymt2_prompt_batches_preserve_order_and_context(self):
        texts = ["Hello", "How are you doing today friend?", "Fine.", "Thanks", "Bye"]
        self.assertEqual(list(_inference_batches(texts, batch_size=4)), [(0, 4), (4, 5)])
        self.assertEqual(_context_before_start(["A" * 1300, "B"], 2), 1)
        self.assertEqual(_context_after_end(["A", "B" * 1300], 1), 1)

        prompt = _build_prompt(
            ["Hello", "How are you doing today friend?", "Fine."],
            ["English", "English", "English"],
            1,
            "Vietnamese",
        )
        self.assertEqual(
            prompt,
            "[Background Information - reference only]\n"
            "Source language: English\n"
            "[Previous Subtitles]\n"
            "P1 [English]: Hello\n"
            "[Following Subtitles]\n"
            "N1 [English]: Fine.\n"
            "[End Background Information]\n\n"
            "Please accurately translate the [Source Text] into Vietnamese, taking the provided "
            "background information into consideration. Translate only the [Source Text], "
            "not the background, and never copy a background sentence even when its wording is similar. Preserve its "
            "meaning, names, numbers, and percentages exactly; do not paraphrase, expand, or omit information. "
            "Use standard spelling and natural grammar in the target language. "
            "Only output the translated result without any additional explanation.\n\n"
            "[Source Text]\n"
            "How are you doing today friend?",
        )

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
            [
                "Earlier context",
                "Honey details",
                "Top 20%.",
                "Adding a banana helps replenish glycogen after training.",
                "Top 10%.",
                "Later context",
            ],
            ["English"] * 6,
            3,
            "Vietnamese",
        )
        self.assertIn("Earlier context", focused_prompt)
        self.assertIn("Honey details", focused_prompt)
        self.assertIn("Top 20%.", focused_prompt)
        self.assertIn("Top 10%.", focused_prompt)
        self.assertIn("Later context", focused_prompt)
        self.assertLess(
            focused_prompt.index("[Background Information - reference only]"),
            focused_prompt.index("[Source Text]\nAdding a banana helps replenish glycogen"),
        )

        wide_prompt = _build_prompt(
            [f"Context line {number} contains enough ordinary words." for number in range(9)],
            ["English"] * 9,
            4,
            "Vietnamese",
        )
        for number in (1, 2, 3, 5, 6, 7):
            self.assertIn(f"Context line {number}", wide_prompt)
        for number in (0, 8):
            self.assertNotIn(f"Context line {number}", wide_prompt)

        long_texts = [f"Line {number} " + ("A" * 450) for number in range(20)]
        long_context_indices = _context_indices(long_texts, 10)
        self.assertNotIn(0, long_context_indices)
        self.assertIn(8, long_context_indices)
        self.assertIn(9, long_context_indices)
        self.assertIn(11, long_context_indices)
        self.assertIn(12, long_context_indices)
        self.assertNotIn(19, long_context_indices)
        self.assertLessEqual(
            sum(len(long_texts[context_index]) for context_index in long_context_indices),
            2400,
        )

        mixed_prompt = _build_prompt(
            [
                "Hello",
                "今日は特別なメニューがありますので、ぜひお試しください。",
                "¿Puedes hacerlo sin gluten para mi familia hoy?",
            ],
            ["English", "Japanese", "Spanish"],
            2,
            "Vietnamese",
        )
        self.assertIn("Hello", mixed_prompt)
        self.assertIn("今日は特別なメニューがありますので、ぜひお試しください。", mixed_prompt)
        self.assertIn("[Source Text]\n¿Puedes hacerlo sin gluten para mi familia hoy?", mixed_prompt)

        shake_texts = [
            "If you only drink a protein shake after training, you are in the top 50%.",
            "Add creatine for strength and recovery.",
            "Add honey to deliver nutrients faster.",
            "Add a banana to replenish glycogen.",
            "Top 10%.",
            "No gas in, no underfueling, just a shake that actually works.",
        ]
        shake_prompt = _build_prompt(
            shake_texts,
            ["English"] * len(shake_texts),
            len(shake_texts) - 1,
            "Vietnamese",
        )
        self.assertNotIn("If you only drink a protein shake", shake_prompt)
        self.assertIn("Add honey to deliver nutrients faster.", shake_prompt)
        self.assertIn("Add a banana to replenish glycogen.", shake_prompt)
        self.assertIn("Top 10%.", shake_prompt)
        self.assertIn("[Source Text]\nNo gas in, no underfueling, just a shake", shake_prompt)

        fruit_texts = [
            "for fat loss.",
            "S tier, elite for fat loss.",
            "Easy to digest, high in fiber, low calorie and great for cravings.",
            "Dry fruit.",
            "F tier, basically fruit with the water removed.",
            "Tiny portion, high calorie density, easy to destroy your deficit without noticing.",
        ]
        fruit_prompt = _build_prompt(
            fruit_texts,
            ["English"] * len(fruit_texts),
            4,
            "Vietnamese",
        )
        self.assertIn("[Source Text]\nF tier, basically fruit with the water removed.", fruit_prompt)
        self.assertIn("Tiny portion", fruit_prompt)

        kiwi_prompt = _build_prompt(
            fruit_texts + ["Mango.", "C tier.", "Easy to overeat.", "Kiwi."],
            ["English"] * 10,
            9,
            "Vietnamese",
        )
        self.assertIn("[Source Text]\nKiwi.", kiwi_prompt)
        self.assertIn("standalone subtitle label", kiwi_prompt)
        self.assertNotIn("Mango.", kiwi_prompt)
        self.assertNotIn("C tier.", kiwi_prompt)
        self.assertNotIn("[Previous Subtitles]", kiwi_prompt)

        default_prompt = _build_prompt(
            ["Hello"],
            ["English"],
            0,
            "Vietnamese",
            include_context=False,
        )
        self.assertEqual(
            default_prompt,
            "Translate this standalone subtitle label into Vietnamese. Translate only the "
            "[Source Text]. Preserve the exact identity of any named item, rank letter, number, unit and "
            "punctuation. Do not infer or substitute a different item. Use standard target-language spelling. "
            "Only output the translated result without any additional explanation.\n\n"
            "[Source Text]\n"
            "Hello",
        )

        isolated_kiwi_prompt = _build_prompt(
            ["Mango.", "C tier.", "Kiwi."],
            ["English"] * 3,
            2,
            "Vietnamese",
        )
        self.assertIn("standalone subtitle label", isolated_kiwi_prompt)
        self.assertIn("Do not infer or substitute a different item.", isolated_kiwi_prompt)
        self.assertNotIn("Mango.", isolated_kiwi_prompt)
        self.assertNotIn("C tier.", isolated_kiwi_prompt)
        self.assertEqual(_output_token_budget(2), 24)
        self.assertEqual(_output_token_budget(20), 96)

    def test_hymt2_mixed_language_batch_keeps_target_language_segments(self):
        captured_source_texts = []
        original_runtime = hymt2_worker._model_runtime
        original_runtime_profile = hymt2_worker.runtime_profile
        original_translate_batch = hymt2_worker._translate_prompt_batch
        original_emit = hymt2_worker._emit_event
        hymt2_worker._model_runtime = lambda: (object(), object(), object(), "cpu")
        hymt2_worker.runtime_profile = lambda: SimpleNamespace(is_cpu_only=False)
        hymt2_worker._translate_prompt_batch = (
            lambda _model, _tokenizer, _torch, _device, _prompts, source_texts: (
                captured_source_texts.extend(source_texts) or ["Xin chào", "Không gluten"]
            )
        )
        hymt2_worker._emit_event = lambda _payload: None
        try:
            translated = hymt2_worker.translate(
                {
                    "texts": ["Hello", "Đã sẵn sàng", "Sin gluten"],
                    "source_languages": ["English", "Vietnamese", "Spanish"],
                    "target_language_name": "Vietnamese",
                }
            )
        finally:
            hymt2_worker._model_runtime = original_runtime
            hymt2_worker.runtime_profile = original_runtime_profile
            hymt2_worker._translate_prompt_batch = original_translate_batch
            hymt2_worker._emit_event = original_emit

        self.assertEqual(captured_source_texts, ["Hello", "Sin gluten"])
        self.assertEqual(translated, ["Xin chào", "Đã sẵn sàng", "Không gluten"])

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
            [sys.executable, "-m", "haizflow.services.hymt2_worker", "--server"],
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

    def test_video_store_serializes_concurrent_updates_and_recovers_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_videos_dir = video_store.LEGACY_VIDEO_WORKSPACES_DIR
            video_store.LEGACY_VIDEO_WORKSPACES_DIR = temp_dir
            try:
                video = video_store.create_video("video-store-test", "input.mp4", VideoConfig())
                failures = []

                def update_progress(offset):
                    try:
                        for value in range(offset, 100, 10):
                            video_store.update_video(video.video_id, progress=value, step="processing")
                            self.assertIsNotNone(video_store.get_video(video.video_id))
                    except Exception as exc:  # pragma: no cover - assertion is reported below.
                        failures.append(exc)

                threads = [threading.Thread(target=update_progress, args=(offset,)) for offset in range(5)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(failures, [])
                path = Path(video_store.get_video_json_path(video.video_id))
                self.assertIsNotNone(video_store.get_video(video.video_id))
                self.assertTrue(Path(str(path) + ".bak").exists())

                path.write_text("{", encoding="utf-8")
                recovered = video_store.get_video(video.video_id)
                self.assertIsNotNone(recovered)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["video_id"], video.video_id)
            finally:
                video_store.LEGACY_VIDEO_WORKSPACES_DIR = original_videos_dir


if __name__ == "__main__":
    unittest.main()
