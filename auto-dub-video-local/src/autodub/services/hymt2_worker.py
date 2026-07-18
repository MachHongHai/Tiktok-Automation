import argparse
import gc
import json
import os
import re
import shutil
import sys
import traceback
from pathlib import Path

from autodub.core.hardware import processing_device_preference, runtime_profile


_INFERENCE_BATCH_SIZE = max(1, min(8, int(os.getenv("HYMT2_INFERENCE_BATCH_SIZE", "4"))))
_CONTEXT_SEGMENTS = 3
_MAX_CONTEXT_CHARACTERS = 1200
_MAX_BACKGROUND_CHARACTERS = 2400
_PROGRESS_PATH = None
_MODEL_RUNTIME = None
_TORCH_THREADING_CONFIGURED = False
_FIRST_GENERATION_PENDING = True
_MIN_GGUF_BYTES = 100 * 1024 * 1024
_MIN_CPU_MODEL_DISK_BYTES = 2 * 1024 ** 3
_MIN_GPU_MODEL_DISK_BYTES = 6 * 1024 ** 3
_OUTPUT_TOKEN_BUCKETS = (24, 48, 96, 160, 256)

def _configure_torch_threading(torch) -> None:
    """Configure process-wide Torch pools once, before CUDA probing starts work."""
    global _TORCH_THREADING_CONFIGURED
    if _TORCH_THREADING_CONFIGURED:
        return
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError as exc:
        # PyTorch permits this setting only once and only before parallel work.
        # A reused interpreter or a native dependency may already have frozen
        # the pool; keeping its existing value is safe for inference.
        if "cannot set number of interop threads" not in str(exc).lower():
            raise
    _TORCH_THREADING_CONFIGURED = True


def _prepare_torch_runtime():
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    import torch

    _configure_torch_threading(torch)
    return torch


def _emit_event(payload: dict) -> None:
    # Keep the worker protocol ASCII-safe so Windows console code pages cannot
    # corrupt or reject translated Unicode text. json.loads restores Unicode.
    line = json.dumps(payload, ensure_ascii=True)
    if _PROGRESS_PATH is not None:
        with open(_PROGRESS_PATH, "a", encoding="utf-8") as file:
            file.write(line + "\n")
        return
    if sys.stdout is not None:
        print(line, flush=True)


def _gib(value: int | float) -> float:
    return round(float(value) / (1024 ** 3), 2) if value else 0.0


def _emit_diagnostic(stage: str, torch=None, **details) -> None:
    """Emit a crash-surviving memory snapshot through the worker event stream."""
    snapshot = {
        "stage": stage,
        "pid": os.getpid(),
        "processing_device": processing_device_preference(),
        "python": sys.version.split()[0],
    }
    try:
        import psutil

        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        process = psutil.Process()
        snapshot.update(
            {
                "ram_available_gib": _gib(memory.available),
                "ram_total_gib": _gib(memory.total),
                "commit_or_swap_free_gib": _gib(swap.free),
                "commit_or_swap_total_gib": _gib(swap.total),
                "process_rss_gib": _gib(process.memory_info().rss),
            }
        )
    except Exception as exc:
        snapshot["system_memory_probe_error"] = f"{type(exc).__name__}: {exc}"

    if torch is not None:
        snapshot.update(
            {
                "torch": str(getattr(torch, "__version__", "unknown")),
                "torch_cuda": str(getattr(getattr(torch, "version", None), "cuda", "unknown")),
                "cuda_available": bool(torch.cuda.is_available()),
            }
        )
        if torch.cuda.is_available():
            try:
                free_vram, total_vram = torch.cuda.mem_get_info(0)
                snapshot.update(
                    {
                        "cuda_device": torch.cuda.get_device_name(0),
                        "vram_free_gib": _gib(free_vram),
                        "vram_total_gib": _gib(total_vram),
                        "vram_allocated_gib": _gib(torch.cuda.memory_allocated(0)),
                        "vram_reserved_gib": _gib(torch.cuda.memory_reserved(0)),
                    }
                )
            except Exception as exc:
                snapshot["cuda_memory_probe_error"] = f"{type(exc).__name__}: {exc}"
    snapshot.update(details)
    _emit_event({"event": "diagnostic", "detail": snapshot})


def _inference_batches(texts: list[str], batch_size: int | None = None):
    """Yield prompt batches; each prompt still produces exactly one subtitle."""
    if batch_size is None:
        profile = runtime_profile()
        if profile.is_cpu_only:
            batch_size = 1
        elif getattr(profile, "key", "") == "cuda_low_memory":
            batch_size = min(2, _INFERENCE_BATCH_SIZE)
        else:
            batch_size = _INFERENCE_BATCH_SIZE
    for start in range(0, len(texts), batch_size):
        yield start, min(len(texts), start + batch_size)


def _context_before_start(texts: list[str], core_start: int) -> int:
    start = max(0, core_start - _CONTEXT_SEGMENTS)
    while start < core_start and sum(len(text) for text in texts[start:core_start]) > _MAX_CONTEXT_CHARACTERS:
        start += 1
    return start


def _context_after_end(texts: list[str], core_end: int) -> int:
    end = min(len(texts), core_end + _CONTEXT_SEGMENTS)
    while end > core_end and sum(len(text) for text in texts[core_end:end]) > _MAX_CONTEXT_CHARACTERS:
        end -= 1
    return end


def _context_indices(texts: list[str], index: int) -> list[int]:
    """Return a chronological local context window around one subtitle."""
    before_start = _context_before_start(texts, index)
    after_end = _context_after_end(texts, index + 1)
    candidates = [
        *range(before_start, index),
        *range(index + 1, after_end),
    ]
    selected = []
    used_characters = 0
    for context_index in candidates:
        item_characters = len(texts[context_index])
        if used_characters + item_characters > _MAX_BACKGROUND_CHARACTERS:
            continue
        selected.append(context_index)
        used_characters += item_characters
    return sorted(selected)


def _is_standalone_label(text: str) -> bool:
    """Keep short labels independent so nearby subtitles cannot replace their identity."""
    normalized = (text or "").strip()
    words = re.findall(r"\w+", normalized, flags=re.UNICODE)
    return bool(normalized) and len(normalized) <= 48 and len(words) <= 4


def _build_prompt(
    texts: list[str],
    source_languages: list[str],
    index: int,
    target_language_name: str,
    *,
    include_context: bool = True,
) -> str:
    source_text = texts[index].strip()
    if _is_standalone_label(source_text):
        return (
            f"Translate this standalone subtitle label into {target_language_name}. Translate only the "
            "[Source Text]. Preserve the exact identity of any named item, rank letter, number, unit and "
            "punctuation. Do not infer or substitute a different item. Use standard target-language spelling. "
            "Only output the translated result without any additional explanation.\n\n"
            f"[Source Text]\n{source_text}"
        )

    context_block = ""
    if include_context:
        context_indices = _context_indices(texts, index)
        previous_context = "\n".join(
            f"P{index - context_index} [{source_languages[context_index]}]: {texts[context_index]}"
            for context_index in context_indices
            if context_index < index
        )
        following_context = "\n".join(
            f"N{context_index - index} [{source_languages[context_index]}]: {texts[context_index]}"
            for context_index in context_indices
            if context_index > index
        )
        context_parts = [
            "[Background Information - reference only]",
            f"Source language: {source_languages[index]}",
        ]
        if previous_context:
            context_parts.append(f"[Previous Subtitles]\n{previous_context}")
        if following_context:
            context_parts.append(f"[Following Subtitles]\n{following_context}")
        context_parts.append("[End Background Information]")
        context_block = "\n".join(context_parts) + "\n\n"

    return (
        f"{context_block}Please accurately translate the [Source Text] into {target_language_name}, "
        "taking the provided background information into consideration. Translate only the [Source Text], "
        "not the background, and never copy a background sentence even when its wording is similar. Preserve its "
        "meaning, names, numbers, and percentages exactly; do not paraphrase, expand, or omit information. Use "
        "standard spelling and natural grammar in the target language. "
        "Only output the translated result without any additional explanation.\n\n"
        f"[Source Text]\n{source_text}"
    )


def _build_translation_prompts(
    texts: list[str],
    source_languages: list[str],
    start: int,
    end: int,
    target_language_name: str,
) -> list[str]:
    return [
        _build_prompt(texts, source_languages, index, target_language_name)
        for index in range(start, end)
    ]


def _clean_single_translation(response: str) -> str:
    """Accept a plain or JSON-encoded translation for the one-item fallback."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = text
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], str):
        parsed = parsed[0]
    if not isinstance(parsed, str) or not parsed.strip():
        raise ValueError("HY-MT2 did not return a usable translation for one subtitle.")
    return parsed.strip().strip('"').strip()


def _output_token_budget(source_token_count: int) -> int:
    """Bound generation by the current subtitle, never by a longer batch peer."""
    requested = max(16, source_token_count * 3 + 8)
    return next((bucket for bucket in _OUTPUT_TOKEN_BUCKETS if requested <= bucket), _OUTPUT_TOKEN_BUCKETS[-1])


def _encode_prompts(tokenizer, torch, device: str, prompts: list[str]):
    rendered_prompts = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            tokenize=False,
        )
        for prompt in prompts
    ]
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    encoded = tokenizer(rendered_prompts, padding=True, return_tensors="pt")
    encoded = {name: value.to(device) for name, value in encoded.items()}
    encoded.pop("token_type_ids", None)
    return encoded


def _translate_prompt_batch(
    model,
    tokenizer,
    torch,
    device: str,
    prompts: list[str],
    source_texts: list[str],
) -> list[str]:
    global _FIRST_GENERATION_PENDING
    if device == "cpu-gguf":
        results = []
        for prompt, source_text in zip(prompts, source_texts):
            estimated_source_tokens = max(len(source_text.split()) * 2, len(source_text) // 4, 1)
            output_budget = _output_token_budget(estimated_source_tokens)
            response = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                top_p=1.0,
                top_k=0,
                repeat_penalty=1.0,
                max_tokens=output_budget,
            )
            try:
                content = response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError("HY-MT2 GGUF returned an invalid response.") from exc
            results.append(_clean_single_translation(content))
        return results

    grouped_indices: dict[int, list[int]] = {}
    for index, source_text in enumerate(source_texts):
        source_tokens = len(tokenizer.encode(source_text, add_special_tokens=False))
        grouped_indices.setdefault(_output_token_budget(source_tokens), []).append(index)

    results: list[str | None] = [None] * len(prompts)
    for output_budget, indices in grouped_indices.items():
        encoded = _encode_prompts(tokenizer, torch, device, [prompts[index] for index in indices])
        input_length = encoded["input_ids"].shape[-1]
        context_limit = getattr(model.config, "max_position_embeddings", 32768)
        available_output = context_limit - input_length
        if available_output < 16:
            raise RuntimeError("Translation context window is full before the subtitle batch can be generated.")
        first_generation = _FIRST_GENERATION_PENDING
        if first_generation:
            _emit_diagnostic(
                "first_generation_start",
                torch,
                prompt_count=len(indices),
                input_tokens=input_length,
                output_token_budget=min(output_budget, available_output),
            )
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                do_sample=False,
                max_new_tokens=min(output_budget, available_output),
                pad_token_id=tokenizer.pad_token_id,
            )
        if first_generation:
            _FIRST_GENERATION_PENDING = False
            _emit_diagnostic("first_generation_complete", torch, prompt_count=len(indices))
        if len(generated) != len(indices):
            raise RuntimeError("HY-MT2 inference did not return one result per subtitle prompt.")
        for index, output in zip(indices, generated):
            results[index] = _clean_single_translation(
                tokenizer.decode(output[input_length:], skip_special_tokens=True).strip()
            )
    if any(result is None for result in results):
        raise RuntimeError("HY-MT2 inference did not return one result per subtitle prompt.")
    return [result for result in results if result is not None]


def _cpu_model_path() -> str:
    from huggingface_hub import hf_hub_download

    from autodub.config import (
        HYMT2_CPU_MODEL_FILE,
        HYMT2_CPU_MODEL_REPO,
        HYMT2_CPU_MODEL_REVISION,
        MODELS_DIR,
    )
    from autodub.core.model_integrity import ModelIntegrityError, verify_cpu_model
    from autodub.core.paths import bundle_root

    model_directory = Path(MODELS_DIR) / "hymt2-gguf"
    model_path = model_directory / HYMT2_CPU_MODEL_FILE
    if model_path.is_file() and model_path.stat().st_size >= _MIN_GGUF_BYTES:
        try:
            return str(verify_cpu_model(model_path))
        except ModelIntegrityError as exc:
            raise RuntimeError(f"Installed HY-MT2 CPU model failed integrity verification: {exc}") from exc
    bundled_model = bundle_root() / "models" / "hymt2-gguf" / HYMT2_CPU_MODEL_FILE
    if bundled_model.is_file() and bundled_model.stat().st_size >= _MIN_GGUF_BYTES:
        try:
            return str(verify_cpu_model(bundled_model))
        except ModelIntegrityError as exc:
            raise RuntimeError(f"Bundled HY-MT2 CPU model failed integrity verification: {exc}") from exc
    if model_path.exists():
        model_path.unlink(missing_ok=True)
    _emit_event(
        {
            "event": "status",
            "detail": f"Downloading CPU translation model {HYMT2_CPU_MODEL_FILE}",
        }
    )
    model_directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(model_directory).free < _MIN_CPU_MODEL_DISK_BYTES:
        raise RuntimeError(
            f"At least 2 GB of free disk space is required to install {HYMT2_CPU_MODEL_FILE}."
        )
    try:
        downloaded = Path(hf_hub_download(
            repo_id=HYMT2_CPU_MODEL_REPO,
            filename=HYMT2_CPU_MODEL_FILE,
            revision=HYMT2_CPU_MODEL_REVISION,
            local_dir=str(model_directory),
        ))
        return str(verify_cpu_model(downloaded))
    except Exception as exc:
        raise RuntimeError(
            "The HY-MT2 CPU model is not installed. Connect once to download the official "
            f"{HYMT2_CPU_MODEL_FILE} model, or include it in the installer at {model_path}."
        ) from exc


def _transformers_snapshot_complete(snapshot_path: Path) -> bool:
    required_files = ("config.json", "tokenizer_config.json", "tokenizer.json")
    if not snapshot_path.is_dir() or not all(
        (snapshot_path / filename).is_file() for filename in required_files
    ):
        return False
    single_weights = snapshot_path / "model.safetensors"
    if single_weights.is_file() and single_weights.stat().st_size > 0:
        return True
    index_path = snapshot_path / "model.safetensors.index.json"
    if not index_path.is_file():
        return False
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        shards = set((index.get("weight_map") or {}).values())
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
    return bool(shards) and all(
        (snapshot_path / shard).is_file() and (snapshot_path / shard).stat().st_size > 0
        for shard in shards
    )


def _local_transformers_model_source(model_name: str) -> tuple[str, bool]:
    """Resolve an installed Hub model to its snapshot so startup stays offline."""
    from autodub.config import HF_HOME, HYMT2_MODEL_REVISION
    from autodub.core.model_integrity import ModelIntegrityError, verify_gpu_model
    from autodub.core.paths import bundle_root

    configured_path = Path(model_name).expanduser()
    if _transformers_snapshot_complete(configured_path):
        try:
            return str(verify_gpu_model(configured_path)), True
        except ModelIntegrityError as exc:
            raise RuntimeError(f"Configured HY-MT2 GPU model failed integrity verification: {exc}") from exc
    if configured_path.exists():
        raise RuntimeError(f"Configured HY-MT2 model directory is incomplete: {configured_path}")

    bundled_model = bundle_root() / "models" / "hymt2-transformers"
    if _transformers_snapshot_complete(bundled_model):
        try:
            return str(verify_gpu_model(bundled_model)), True
        except ModelIntegrityError as exc:
            raise RuntimeError(f"Bundled HY-MT2 GPU model failed integrity verification: {exc}") from exc
    if bundled_model.exists():
        raise RuntimeError(f"Bundled HY-MT2 model is incomplete: {bundled_model}")

    from huggingface_hub import snapshot_download

    snapshot_path = None
    try:
        snapshot_path = Path(
            snapshot_download(
                repo_id=model_name,
                revision=HYMT2_MODEL_REVISION,
                cache_dir=str(Path(HF_HOME) / "hub"),
                local_files_only=True,
            )
        )
    except Exception:
        pass

    if snapshot_path is not None and _transformers_snapshot_complete(snapshot_path):
        try:
            return str(verify_gpu_model(snapshot_path)), True
        except ModelIntegrityError as exc:
            raise RuntimeError(f"Cached HY-MT2 GPU model failed integrity verification: {exc}") from exc
    cache_root = Path(HF_HOME)
    cache_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(cache_root).free < _MIN_GPU_MODEL_DISK_BYTES:
        raise RuntimeError(
            "At least 6 GB of free disk space is required to install the HY-MT2 GPU model."
        )
    try:
        snapshot_path = Path(
            snapshot_download(
                repo_id=model_name,
                revision=HYMT2_MODEL_REVISION,
                cache_dir=str(Path(HF_HOME) / "hub"),
            )
        )
        return str(verify_gpu_model(snapshot_path)), True
    except Exception as exc:
        raise RuntimeError(
            f"Unable to install pinned HY-MT2 GPU revision {HYMT2_MODEL_REVISION}."
        ) from exc


def _load_model(model_name: str):
    # Configure Torch before runtime_profile() probes CUDA. CUDA telemetry can
    # initialize Torch's parallel runtime, after which interop threads are
    # immutable for the lifetime of this worker process.
    torch_runtime = _prepare_torch_runtime() if processing_device_preference() == "gpu" else None
    profile = runtime_profile()
    _emit_diagnostic(
        "runtime_profile_selected",
        torch_runtime,
        profile=profile.key,
        backend=profile.hymt2_backend,
        model=model_name,
    )
    if profile.hymt2_backend == "llama_cpp":
        from llama_cpp import Llama

        model_path = _cpu_model_path()
        _emit_event(
            {
                "event": "status",
                "detail": (
                    f"Loading HY-MT2 Q4 memory-safe model with {profile.cpu_threads} threads"
                    if profile.cuda_available
                    else f"Loading HY-MT2 Q4 CPU model with {profile.cpu_threads} threads"
                ),
            }
        )
        model = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_batch=256 if profile.key == "cpu_balanced" else 128,
            n_threads=profile.cpu_threads,
            n_threads_batch=profile.cpu_threads,
            n_gpu_layers=0,
            verbose=False,
        )
        _emit_event(
            {
                "event": "status",
                "detail": (
                    "HY-MT2 Q4 memory-safe model is ready; GPU remains available for speech and rendering"
                    if profile.cuda_available
                    else "HY-MT2 Q4 CPU model is ready"
                ),
            }
        )
        return model, None, None, "cpu-gguf"

    # Torch's loader is more stable on Windows when model deserialization does
    # not fan out across every logical processor.
    torch = torch_runtime or _prepare_torch_runtime()
    from transformers import AutoModelForCausalLM, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        requested_dtype = getattr(profile, "hymt2_dtype", "float16")
        bf16_supported = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
        dtype = torch.bfloat16 if requested_dtype == "bfloat16" and bf16_supported else torch.float16
        precision_label = "BF16" if dtype == torch.bfloat16 else "FP16"
    else:
        dtype = torch.float32
        precision_label = "FP32"
    model_source, local_files_only = _local_transformers_model_source(model_name)
    _emit_diagnostic(
        "tokenizer_load_start",
        torch,
        model=model_name,
        model_source=model_source,
        local_files_only=local_files_only,
        dtype=str(dtype),
        device=device,
    )
    _emit_event(
        {
            "event": "status",
            "detail": "Loading HY-MT2 tokenizer from local cache" if local_files_only else "Loading HY-MT2 tokenizer",
        }
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_source,
        trust_remote_code=True,
        local_files_only=local_files_only,
        # Transformers 4.57 misclassifies this local Hunyuan tokenizer as
        # Mistral. Keep Tencent's tokenizer unchanged while suppressing that fix.
        fix_mistral_regex=False,
    )
    _emit_diagnostic("tokenizer_load_complete", torch, model=model_name, device=device)
    staged_cuda_load = device == "cuda" and profile.key == "cuda_low_memory"
    load_options = {
        "dtype": dtype,
        "trust_remote_code": True,
        "use_safetensors": True,
        "local_files_only": local_files_only,
    }
    if staged_cuda_load:
        # Loading a single large safetensors shard directly into CUDA through
        # Transformers' meta-model path can trigger a native storage access
        # violation on Windows. Stage the same checkpoint in system
        # memory, then transfer the complete model to CUDA.
        load_options["low_cpu_mem_usage"] = False
        load_strategy = "staged_cpu_to_cuda"
    else:
        load_options["device_map"] = {"": device}
        load_options["low_cpu_mem_usage"] = True
        load_strategy = "direct_to_device"
    _emit_diagnostic(
        "weights_load_start",
        torch,
        model=model_name,
        dtype=str(dtype),
        device=device,
        load_strategy=load_strategy,
    )
    _emit_event(
        {
            "event": "status",
            "detail": (
                f"Loading full HY-MT2 {precision_label} weights in staged GPU mode"
                if staged_cuda_load
                else "Loading HY-MT2 weights"
            ),
        }
    )
    model = AutoModelForCausalLM.from_pretrained(model_source, **load_options)
    _emit_diagnostic(
        "weights_load_complete",
        torch,
        model=model_name,
        dtype=str(dtype),
        device="cpu" if staged_cuda_load else device,
        load_strategy=load_strategy,
    )
    if staged_cuda_load:
        _emit_event({"event": "status", "detail": f"Transferring full HY-MT2 {precision_label} model to CUDA"})
        _emit_diagnostic("cuda_transfer_start", torch, model=model_name, dtype=str(dtype))
        model.to(device)
        _emit_diagnostic("cuda_transfer_complete", torch, model=model_name, dtype=str(dtype))
    else:
        _emit_event({"event": "status", "detail": f"HY-MT2 weights loaded directly on {device}"})
    # Tencent's direct Transformers example uses deterministic generate().
    # Subtitle production values faithful, repeatable output over sampling
    # variation because one wrong noun corrupts both captions and TTS.
    model.generation_config.do_sample = False
    model.eval()
    _emit_diagnostic("model_ready", torch, model=model_name, dtype=str(dtype), device=device)
    _emit_event({"event": "status", "detail": "HY-MT2 model is ready"})
    return model, tokenizer, torch, device


def _model_runtime():
    global _MODEL_RUNTIME
    if _MODEL_RUNTIME is None:
        from autodub.config import HYMT2_MODEL

        _emit_event({"event": "status", "detail": "Loading HY-MT2 translation model"})
        _MODEL_RUNTIME = _load_model(HYMT2_MODEL)
    else:
        _emit_event({"event": "status", "detail": "Reusing HY-MT2 translation model"})
    return _MODEL_RUNTIME


def release_model() -> None:
    global _MODEL_RUNTIME
    if _MODEL_RUNTIME is None:
        return
    model, tokenizer, torch, _device = _MODEL_RUNTIME
    _MODEL_RUNTIME = None
    del model, tokenizer
    gc.collect()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def translate(payload: dict) -> list[str]:
    texts = payload["texts"]
    source_languages = payload.get("source_languages")
    if not isinstance(source_languages, list) or len(source_languages) != len(texts):
        source_languages = [payload.get("source_language") or "English"] * len(texts)
    target_language_name = payload["target_language_name"]
    target_key = target_language_name.casefold().strip()
    requires_translation = [
        source_language.casefold().strip() != target_key
        for source_language in source_languages
    ]
    if not any(requires_translation):
        _emit_event({"event": "progress", "current": len(texts), "total": len(texts)})
        return list(texts)

    model, tokenizer, torch, device = _model_runtime()
    translations = [None] * len(texts)
    for batch_start, batch_end in _inference_batches(texts):
        _emit_event(
            {
                "event": "batch_started",
                "start": batch_start + 1,
                "end": batch_end,
                "completed": batch_start,
                "total": len(texts),
            }
        )
        translated_indices = [
            index
            for index in range(batch_start, batch_end)
            if requires_translation[index]
        ]
        for index in range(batch_start, batch_end):
            if not requires_translation[index]:
                translations[index] = texts[index]

        if translated_indices:
            prompts = [
                _build_prompt(texts, source_languages, index, target_language_name)
                for index in translated_indices
            ]
            batch_translations = _translate_prompt_batch(
                model,
                tokenizer,
                torch,
                device,
                prompts,
                [texts[index] for index in translated_indices],
            )
            for index, translated_text in zip(translated_indices, batch_translations):
                translations[index] = translated_text

        _emit_event({"event": "progress", "current": batch_end, "total": len(texts)})
    if any(not isinstance(text, str) for text in translations):
        raise RuntimeError("HY-MT2 inference did not return one translation per subtitle prompt.")
    return translations


def _serve() -> int:
    try:
        for raw_line in sys.stdin:
            request_id = "unknown"
            try:
                request = json.loads(raw_line)
                request_id = request["request_id"]
                if request.get("command") == "shutdown":
                    _emit_event({"event": "response", "request_id": request_id, "stopped": True})
                    return 0
                if request.get("command") == "ping":
                    _emit_event({"event": "response", "request_id": request_id, "ready": True})
                    continue
                if request.get("command") == "warm":
                    _model_runtime()
                    _emit_event({"event": "response", "request_id": request_id, "warmed": True})
                    continue
                result = {"translations": translate(request["payload"])}
            except Exception as exc:
                _emit_diagnostic(
                    "python_exception",
                    details=f"{type(exc).__name__}: {exc}",
                    traceback=traceback.format_exc(),
                )
                result = {"error": f"HY-MT2 worker failed: {type(exc).__name__}: {exc}"}
            result.update({"event": "response", "request_id": request_id})
            _emit_event(result)
    finally:
        release_model()
    return 0


def main(argv=None) -> int:
    global _PROGRESS_PATH
    try:
        import faulthandler

        faulthandler.enable(all_threads=True)
    except (OSError, RuntimeError):
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--request")
    parser.add_argument("--response")
    parser.add_argument("--progress")
    parser.add_argument("--server", action="store_true")
    args = parser.parse_args(argv)
    if args.server:
        return _serve()
    if not args.request or not args.response:
        parser.error("--request and --response are required unless --server is used")
    response_path = Path(args.response)
    _PROGRESS_PATH = Path(args.progress) if args.progress else None
    if _PROGRESS_PATH is not None:
        _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PROGRESS_PATH.write_text("", encoding="utf-8")
    try:
        with open(args.request, "r", encoding="utf-8") as file:
            payload = json.load(file)
        result = {"translations": translate(payload)}
    except Exception as exc:
        result = {"error": f"HY-MT2 worker failed: {type(exc).__name__}: {exc}"}
    with open(response_path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False)
    release_model()
    _PROGRESS_PATH = None
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
