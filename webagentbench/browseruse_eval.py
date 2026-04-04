"""Browser-use eval helper functions.

Utilities for observation masking, agent output parsing, and trajectory
conversion used by the browser-use evaluation harness.
"""

from __future__ import annotations

import json
import re
from typing import Any


# ── 1. mask_observations ──────────────────────────────────────────────

def mask_observations(messages: list[dict], window: int = 10) -> list[dict]:
    """Keep first obs + last *window* obs in full; mask middle observations.

    All assistant messages are preserved unconditionally.
    """
    user_indices = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(user_indices) <= window + 1:
        return list(messages)
    keep = {user_indices[0]} | set(user_indices[-window:])
    return [
        {"role": "user", "content": "[observation omitted]"}
        if m["role"] == "user" and i not in keep
        else dict(m)
        for i, m in enumerate(messages)
    ]


# ── 2. parse_agent_output ────────────────────────────────────────────

_EMPTY_RESULT: dict[str, Any] = {
    "thinking": "",
    "memory": "",
    "next_goal": "",
    "action": [],
}

_PLAIN_RE = re.compile(
    r"^(click|input|scroll|go_back|done)\s*(\d+)?\s*(.*)$", re.IGNORECASE
)


def _strip_markdown_fences(raw: str) -> str:
    """Remove ```json ... ``` wrappers if present."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```json or ```)
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        # Remove closing fence
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def _parse_plain_text(raw: str) -> dict[str, Any]:
    """Best-effort parse of plain-text action like ``click 33``."""
    m = _PLAIN_RE.match(raw.strip())
    if not m:
        return dict(_EMPTY_RESULT)
    verb = m.group(1).lower()
    idx_str = m.group(2)
    rest = m.group(3).strip().strip('"').strip("'")

    result = dict(_EMPTY_RESULT)

    if verb == "click" and idx_str is not None:
        result["action"] = [{"click": {"index": int(idx_str)}}]
    elif verb == "input" and idx_str is not None:
        result["action"] = [{"input_text": {"index": int(idx_str), "text": rest}}]
    elif verb == "scroll":
        direction = idx_str or rest or "down"
        if direction in ("up",):
            result["action"] = [{"scroll_up": {"amount": 300}}]
        else:
            result["action"] = [{"scroll_down": {"amount": 300}}]
    elif verb == "go_back":
        result["action"] = [{"go_back": {}}]
    elif verb == "done":
        result["action"] = [{"done": {"text": rest or "done", "success": True}}]

    return result


def parse_agent_output(raw: str) -> dict[str, Any]:
    """Parse structured JSON (or plain-text fallback) from agent output."""
    if not raw or not raw.strip():
        return dict(_EMPTY_RESULT)

    cleaned = _strip_markdown_fences(raw)

    # Try JSON first
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return {
                "thinking": parsed.get("thinking", ""),
                "memory": parsed.get("memory", ""),
                "next_goal": parsed.get("next_goal", ""),
                "action": parsed.get("action", []),
            }
    except json.JSONDecodeError:
        pass

    # Plain-text fallback
    return _parse_plain_text(cleaned)


# ── 3. action_to_trajectory_format ───────────────────────────────────

def action_to_trajectory_format(action: dict) -> dict:
    """Convert a single browser-use action dict to demo-site replay format."""
    if "click" in action:
        return {"action": "click", "ref": str(action["click"]["index"])}

    if "input_text" in action:
        payload = action["input_text"]
        return {"action": "fill", "ref": str(payload["index"]), "value": payload["text"]}

    if "select_option" in action:
        payload = action["select_option"]
        return {"action": "select", "ref": str(payload["index"]), "value": payload["option"]}

    if "scroll_down" in action:
        return {"action": "scroll", "direction": "down"}

    if "scroll_up" in action:
        return {"action": "scroll", "direction": "up"}

    if "go_back" in action:
        return {"action": "back"}

    if "done" in action:
        return {"action": "finish", "answer": action["done"].get("text", "")}

    return {"action": "unknown"}


# ── 4. dom_element_to_target ─────────────────────────────────────────

_TAG_TO_ROLE: dict[str, str] = {
    "button": "button",
    "a": "link",
    "input": "textbox",
    "textarea": "textbox",
    "select": "combobox",
    "article": "article",
}


def dom_element_to_target(tag_name: str, attributes: dict, text: str = "") -> dict:
    """Convert DOM element info to a replay target ``{role, name}``."""
    role = _TAG_TO_ROLE.get(tag_name, tag_name)

    # Name priority: aria-label > placeholder > text
    name = (
        attributes.get("aria-label")
        or attributes.get("placeholder")
        or text
        or ""
    )

    return {"role": role, "name": name}


# ── 5. build_trajectory_step ─────────────────────────────────────────

_ENV_PATH_RE = re.compile(r"/env/(?:gmail|robinhood)(/[^?]*)")


def _extract_replay_path(url: str) -> str:
    """Extract path component after ``/env/gmail`` or ``/env/robinhood``."""
    m = _ENV_PATH_RE.search(url)
    if not m:
        return "/"
    path = m.group(1)
    # Normalise trailing slash to bare "/"
    return path if path and path != "/" else "/"


def _get_action_index(action: dict) -> int | None:
    """Return the element index referenced by an action, or None."""
    for key in ("click", "input_text", "select_option"):
        if key in action:
            return action[key].get("index")
    return None


def build_trajectory_step(
    step_num: int,
    thinking: str,
    memory: str,
    actions: list[dict],
    dom_elements: dict[int, tuple | dict],
    url: str,
    status: str,
    elapsed: float,
) -> dict:
    """Build one trajectory step matching the demo-site replay format."""
    # Action conversion
    if actions:
        first = actions[0]
        converted_action = action_to_trajectory_format(first)
        idx = _get_action_index(first)
    else:
        converted_action = {"action": "unknown"}
        idx = None

    # Target lookup
    targets: dict = {}
    if idx is not None and idx in dom_elements:
        elem = dom_elements[idx]
        if isinstance(elem, tuple):
            targets = dom_element_to_target(*elem)
        else:
            targets = dom_element_to_target(
                elem.get("tag_name", ""),
                elem.get("attributes", {}),
                elem.get("text", ""),
            )

    replay_path = _extract_replay_path(url)

    return {
        "step": step_num,
        "thought": thinking,
        "action": converted_action,
        "targets": targets,
        "status": status,
        "elapsed_seconds": elapsed,
        "replay_path": replay_path,
        "result_path": replay_path,
    }
