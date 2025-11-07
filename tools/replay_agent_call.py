"""Replay a stored agent LLM call to reproduce empty responses.

This script loads a JSON dump produced in `runs/<episode>/llm/agent_step_XXXX.json`
and replays the exact request against the configured LLM endpoint. It lets you
verify whether the provider still returns an empty body and inspect the raw IO.

Usage (run from repo root):

    python tools/replay_agent_call.py \
        --payload runs/ep-123-.../llm/agent_step_0000.json \
        --with-schema   # optional, to enforce the action schema like the agent

Environment variables (same as the agent):
- `AGENT_OPENAI_BASE_URL`
- `AGENT_OPENAI_API_KEY`
- `AGENT_MODEL` (optional override; defaults to payload's model)

Nothing is executed automatically inside this script; run it manually to
reproduce the failure mode.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Optional

from llm_client import LLMClient


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_action_schema() -> Optional[dict[str, Any]]:
    schema_path = Path(__file__).resolve().parent.parent / "schema" / "action.json"
    try:
        with schema_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def replay(payload_path: Path, use_schema: bool, base_url: Optional[str], api_key: Optional[str], model_override: Optional[str]) -> None:
    payload = load_json(payload_path)
    system_prompt = payload.get("system_prompt", "")
    user_json = payload.get("user_json")
    model = model_override or payload.get("model")
    if not isinstance(user_json, dict):
        raise ValueError("Payload is missing user_json object")
    if not isinstance(system_prompt, str):
        raise ValueError("Payload is missing system_prompt string")

    client = LLMClient(
        model=model,
        temperature=float(payload.get("temperature", 0.0) or 0.0),
        seed=payload.get("seed"),
        base_url=base_url,
        api_key=api_key,
    )

    json_schema = load_action_schema() if use_schema else None

    print("System prompt length:", len(system_prompt))
    print("Requesting model:", model)
    try:
        out = client.complete_json(
            system_prompt=system_prompt,
            user_json=user_json,
            json_schema=json_schema,
            max_retries=0,
        )
        print("Model response:", out)
    except Exception as exc:
        print("Call raised:", exc)
    finally:
        last = getattr(client, "_last_io", None)
        if last:
            print("\nLast IO dump:")
            print(json.dumps(last, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a saved agent LLM request")
    parser.add_argument("--payload", type=Path, required=True, help="Path to agent_step_XXXX.json dump")
    parser.add_argument("--with-schema", action="store_true", help="Include the action JSON schema (matches agent behaviour)")
    parser.add_argument("--model", dest="model_override", type=str, help="Override model name", default=None)
    args = parser.parse_args()

    base_url = os.getenv("AGENT_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("AGENT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set AGENT_OPENAI_API_KEY or OPENAI_API_KEY before running this script.")

    replay(args.payload, args.with_schema, base_url, api_key, args.model_override)


if __name__ == "__main__":
    main()

