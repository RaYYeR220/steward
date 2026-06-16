"""Day-1 smoke test for Qwen Cloud (GO/NO-GO gate).

Verifies, in order:
1. the API key works (lists available models),
2. a chat completion succeeds on a Max-tier model,
3. native function calling returns a well-formed tool call,
and reports latency + token usage for each call.

Usage (from the steward/ repo root, no project deps touched):
    uv run --with openai python scripts/smoke_qwen.py [--model MODEL_ID]

Reads QWEN_API_KEY from the environment or from a local .env file.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

LIST_RESOURCES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_resources",
        "description": "List all cloud resources in the connected account.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "description": "Optional filter, e.g. 'ecs_instance' or 'disk'.",
                }
            },
            "required": [],
        },
    },
}


def load_api_key() -> str:
    key = os.environ.get("QWEN_API_KEY")
    if not key:
        env_file = Path(__file__).resolve().parents[1] / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("QWEN_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key or key == "sk-your-key-here":
        sys.exit("No QWEN_API_KEY found (env var or steward/.env). Aborting.")
    return key


def pick_model(client: OpenAI, requested: str | None) -> str:
    t0 = time.perf_counter()
    models = sorted(m.id for m in client.models.list())
    dt = time.perf_counter() - t0
    print(f"[1/3] models.list OK in {dt:.2f}s — {len(models)} models")
    for m in models:
        print(f"      {m}")
    if requested:
        if requested not in models:
            print(f"WARNING: {requested!r} not in list; trying it anyway")
        return requested
    max_models = [m for m in models if "max" in m.lower()]
    if not max_models:
        sys.exit("No Max-tier model found; pass --model explicitly.")
    # Prefer the newest-looking max model (lexicographically last usually wins).
    choice = max_models[-1]
    print(f"      -> auto-selected {choice!r} (override with --model)")
    return choice


def smoke_completion(client: OpenAI, model: str) -> None:
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: STEWARD-OK"}],
        max_tokens=16,
    )
    dt = time.perf_counter() - t0
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    print(f"[2/3] chat completion OK in {dt:.2f}s — reply={text!r}")
    print(f"      tokens: prompt={usage.prompt_tokens} completion={usage.completion_tokens}")


def smoke_function_calling(client: OpenAI, model: str) -> None:
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": "What resources are in my cloud account? Use the tool.",
            }
        ],
        tools=[LIST_RESOURCES_TOOL],
        max_tokens=256,
    )
    dt = time.perf_counter() - t0
    msg = resp.choices[0].message
    calls = msg.tool_calls or []
    if not calls:
        sys.exit(
            f"[3/3] FAILED in {dt:.2f}s — model answered with text instead of a tool "
            f"call: {(msg.content or '')[:200]!r}"
        )
    call = calls[0]
    print(f"[3/3] function calling OK in {dt:.2f}s")
    print(f"      tool={call.function.name} args={call.function.arguments}")
    usage = resp.usage
    print(f"      tokens: prompt={usage.prompt_tokens} completion={usage.completion_tokens}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="exact model id to test (default: auto-pick a Max model)")
    args = parser.parse_args()

    client = OpenAI(api_key=load_api_key(), base_url=BASE_URL)
    model = pick_model(client, args.model)
    smoke_completion(client, model)
    smoke_function_calling(client, model)
    print(f"\nGO: Qwen Cloud is usable for Steward (model={model}).")


if __name__ == "__main__":
    main()
