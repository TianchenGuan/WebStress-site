"""Quick probe to inspect Qwen's JSON response behaviour.

Run this script manually to see whether `qwen/qwen3-vl-235b-a22b-thinking`
returns content in `message.content`, `tool_calls`, or both, and whether the
model accepts the `json_schema` response format.

Usage:
    python tools/check_qwen_schema_support.py \
        --type json_schema   # default, also supports json_object / none

Environment variables (same as the agent):
    AGENT_OPENAI_API_KEY (required)
    AGENT_OPENAI_BASE_URL (optional)
    AGENT_MODEL (defaults to the Qwen thinking model)

No network calls are issued automatically by this repository; run the script
yourself once you are ready to test against the provider.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Optional

try:
    from openai import OpenAI  # type: ignore
except ImportError as exc:  # pragma: no cover - guidance only
    raise SystemExit("Install the openai package before running this script: pip install openai") from exc


def build_messages() -> list[dict[str, Any]]:
    system = (
        "You are a test agent. Respond with exactly one JSON object containing the keys "
        "action and target. action must be 'double_click'. target must be an object with element_id 'icon_browser'."
    )
    user = {"instruction": "Open the browser by double-clicking its icon."}
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
    ]


def build_response_format(kind: str) -> Optional[Dict[str, Any]]:
    if kind == "none":
        return None
    if kind == "json_object":
        return {"type": "json_object"}
    if kind == "json_schema":
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["double_click"]},
                "target": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string"}
                    },
                    "required": ["element_id"],
                    "additionalProperties": False,
                },
            },
            "required": ["action", "target"],
            "additionalProperties": False,
        }
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "agent_action",
                "schema": schema,
            },
        }
    raise ValueError(f"Unsupported response format: {kind}")


def describe_response(resp: Any) -> Dict[str, Any]:
    choice = resp.choices[0]
    message = choice.message
    data: Dict[str, Any] = {
        "finish_reason": choice.finish_reason,
        "content": message.content,
    }
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = [
            {
                "id": getattr(tc, "id", None),
                "type": getattr(tc, "type", None),
                "function": {
                    "name": getattr(getattr(tc, "function", None), "name", None),
                    "arguments": getattr(getattr(tc, "function", None), "arguments", None),
                },
            }
            for tc in tool_calls
        ]
    fn_call = getattr(message, "function_call", None)
    if fn_call:
        data["function_call"] = {
            "name": getattr(fn_call, "name", None),
            "arguments": getattr(fn_call, "arguments", None),
        }
    return data


def replay(response_format_kind: str) -> None:
    base_url = os.getenv("AGENT_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("AGENT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set AGENT_OPENAI_API_KEY (or OPENAI_API_KEY) before running this script.")

    model = os.getenv("AGENT_MODEL", "qwen/qwen3-vl-235b-a22b-thinking")
    client = OpenAI(api_key=api_key, base_url=base_url)

    params: Dict[str, Any] = {
        "model": model,
        "messages": build_messages(),
    }
    response_format = build_response_format(response_format_kind)
    if response_format is not None:
        params["response_format"] = response_format

    print("Calling model:", model)
    print("Response format:", response_format_kind)
    resp = client.chat.completions.create(**params)
    desc = describe_response(resp)
    print("\nRaw response descriptor:\n", json.dumps(desc, indent=2, ensure_ascii=False))
    if desc.get("content"):
        try:
            parsed = json.loads(desc["content"])  # type: ignore[arg-type]
            print("\nParsed content JSON:", parsed)
        except Exception as exc:
            print("\nContent not valid JSON:", exc)
    if "tool_calls" in desc:
        for i, tc in enumerate(desc["tool_calls"], start=1):
            args = tc.get("function", {}).get("arguments")
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    print(f"\nParsed tool call #{i} arguments:", parsed)
                except Exception as exc:
                    print(f"\nTool call #{i} arguments not valid JSON:", exc)


def main() -> None:
    parser = argparse.ArgumentParser("Check Qwen response format handling")
    parser.add_argument(
        "--type",
        dest="response_format",
        choices=["json_schema", "json_object", "none"],
        default="json_schema",
        help="Which response_format to request from the model (default: json_schema)",
    )
    args = parser.parse_args()
    replay(args.response_format)


if __name__ == "__main__":
    main()

