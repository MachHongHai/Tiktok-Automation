import argparse
import gc
import json
from pathlib import Path


def _build_prompt(
    text: str,
    target_language_name: str,
) -> str:
    return f"Translate to {target_language_name}. Output only the translation:\n{text}"


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
    target_language_name = payload["target_language_name"]
    model, tokenizer, torch, device = _load_model(HYMT2_MODEL)
    translations = []
    try:
        for text in texts:
            messages = [{"role": "user", "content": _build_prompt(text, target_language_name)}]
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
                    do_sample=False,
                    max_new_tokens=192,
                )
            translations.append(tokenizer.decode(generated[0][input_length:], skip_special_tokens=True).strip())
            print(json.dumps({"event": "progress", "current": len(translations), "total": len(texts)}), flush=True)
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
