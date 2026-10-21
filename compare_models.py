# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27,<1", "python-dotenv>=1,<2"]
# ///
"""Send one UTF-8 prompt to several OpenRouter models in parallel."""
import argparse
import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv


async def run_model(client, model, prompt, folder, index, max_tokens):
    start = time.perf_counter()
    data, status = {}, "OK"
    try:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens, "stream": False},
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise ValueError(json.dumps(data["error"]))
        text = data["choices"][0]["message"].get("content") or "[No text returned]"
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False, indent=2)
    except Exception as exc:
        status = "ERROR"
        text = f"{type(exc).__name__}: {exc}"
        key = client.headers.get("Authorization", "").removeprefix("Bearer ")
        if key:
            text = text.replace(key, "[REDACTED]")

    elapsed = time.perf_counter() - start
    usage = data.get("usage") or {}
    cost = usage.get("cost")
    cost_text = f"${float(cost):.10f}" if isinstance(cost, (int, float)) else "unavailable"
    finish = (data.get("choices") or [{}])[0].get("finish_reason", "unavailable")
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", model)[:140]
    output = folder / f"{index:02d}_{filename}.txt"
    output.write_text(
        f"Requested model: {model}\n"
        f"Returned model: {data.get('model', 'unavailable')}\n"
        f"Response ID: {data.get('id', 'unavailable')}\n"
        f"Status: {status}\n"
        f"Response time (complete HTTP request): {elapsed:.3f} seconds\n"
        f"Input tokens: {usage.get('prompt_tokens', 'unavailable')}\n"
        f"Output tokens: {usage.get('completion_tokens', 'unavailable')}\n"
        f"Total tokens: {usage.get('total_tokens', 'unavailable')}\n"
        f"Cost (USD, reported by OpenRouter): {cost_text}\n"
        f"Finish reason: {finish}\n"
        f"Full usage: {json.dumps(usage, ensure_ascii=False)}\n"
        f"\n--- RESPONSE ---\n\n{text}\n", encoding="utf-8",
    )
    print(f"{status}: {output} | {elapsed:.2f}s | {cost_text}")
    return status == "OK"


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", type=Path, help="UTF-8 .txt prompt file")
    parser.add_argument("--models", nargs="+", help="OpenRouter model IDs (overrides config)")
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).resolve().with_name("config.json"),
                        help="Model config JSON (default: config.json beside the script)")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    if args.max_tokens <= 0 or args.timeout <= 0:
        parser.error("--max-tokens and --timeout must be positive")
    if args.models is None:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            parser.error(f"Cannot load config {args.config}: {exc}")
        models = config.get("models") if isinstance(config, dict) else None
        if not isinstance(models, list) or not models or any(
            not isinstance(model, str) or not model.strip() for model in models
        ):
            parser.error(f"Config {args.config} must contain a nonempty 'models' list of model IDs")
        args.models = [model.strip() for model in models]
    load_dotenv(args.env)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        parser.error("Missing OPENROUTER_API_KEY in .env or environment")
    try:
        prompt = args.prompt.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        parser.error(str(exc))
    if not prompt.strip():
        parser.error("Prompt file is empty")
    folder = args.out / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder.mkdir(parents=True, exist_ok=False)
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {key}"}, timeout=args.timeout,
    ) as client:
        results = await asyncio.gather(*[
            run_model(client, model, prompt, folder, i, args.max_tokens)
            for i, model in enumerate(args.models, start=1)
        ])
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
