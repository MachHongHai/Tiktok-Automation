import argparse
import gc
import json
from pathlib import Path


def _build_prompt(
    text: str,
    context: list[str],
    source_language: str,
    target_language_name: str,
) -> str:
    context_block = "\n".join(f"- {line}" for line in context if line.strip())
    if context_block:
        context_block = (
            "Previous subtitle lines are context only. Do not include them in the result:\n"
            f"{context_block}\n\n"
        )
    return (
        f"Translate the following subtitle from {source_language} into {target_language_name}. "
        "Preserve meaning, names, numbers, and speaker intent. Do not correct, add, or omit content. "
        "Output only the complete translation, without quotation marks or explanation.\n\n"
        f"{context_block}Subtitle to translate:\n{text}"
    )


def _load_model(model_name: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=dtype,
        trust_remote_code=True,
    )
    model.to(device)
    model.eval()
    return model, tokenizer, torch, device


def translate(payload: dict) -> list[str]:
    from autodub.config import HYMT2_MODEL

    texts = payload["texts"]
    source_language = payload["source_language"]
    if source_language == "auto":
        source_language = "the detected source language"
    target_language_name = payload["target_language_name"]
    model, tokenizer, torch, device = _load_model(HYMT2_MODEL)
    translations = []
    try:
        for index, text in enumerate(texts):
            messages = [{"role": "user", "content": _build_prompt(
                text,
                texts[max(0, index - 3):index],
                source_language,
                target_language_name,
            )}]
            encoded = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            if isinstance(encoded, torch.Tensor):
                encoded = {"input_ids": encoded}
            encoded = {name: value.to(device) for name, value in encoded.items()}
            # HY-MT2's generation interface rejects this BERT-style tokenizer field.
            encoded.pop("token_type_ids", None)
            input_length = encoded["input_ids"].shape[-1]
            with torch.inference_mode():
                generated = model.generate(
                    **encoded,
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.6,
                    top_k=20,
                    repetition_penalty=1.05,
                    max_new_tokens=256,
                )
            translations.append(tokenizer.decode(generated[0][input_length:], skip_special_tokens=True).strip())
    finally:
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return translations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--response", required=True)
    args = parser.parse_args()
    response_path = Path(args.response)
    try:
        with open(args.request, "r", encoding="utf-8") as file:
            payload = json.load(file)
        result = {"translations": translate(payload)}
    except Exception as exc:
        result = {"error": f"HY-MT2 worker failed: {type(exc).__name__}: {exc}"}
    with open(response_path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False)
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
