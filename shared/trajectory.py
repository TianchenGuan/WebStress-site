"""
Shared trajectory export for SFT training.

Converts trajectories from LLMOS or WebAgentBench into training-ready
formats compatible with popular finetuning frameworks.

Supported formats:
- "messages"  : OpenAI format — {"messages": [{role, content}, ...]}
- "sharegpt"  : LLaMA-Factory / ShareGPT — {"conversations": [{from, value}, ...]}

Usage:
    from shared.trajectory import export_conversations, batch_export

    # From LLMOS episode
    convos = export_conversations(episode, source="llmos")

    # From WebAgentBench result
    convos = export_conversations(result, source="wab")

    # Batch with filtering
    convos = batch_export(episodes, min_score=0.0, fmt="sharegpt")
"""

import json
from typing import Optional
from .format import SYSTEM_PROMPT


def export_conversations(
    data: dict,
    source: str = "auto",
    fmt: str = "messages",
) -> list[dict]:
    """
    Convert a single episode/result to training conversations.

    Args:
        data: Episode (LLMOS) or per-page result (WAB).
        source: "llmos", "wab", or "auto" (detect from data).
        fmt: Output format — "messages" (OpenAI) or "sharegpt" (LLaMA-Factory).

    Returns:
        List with one conversation dict (or empty list if data is unusable).
    """
    if source == "auto":
        if "page_id" in data or ("benchmark" in data and "results" in data):
            source = "wab"
        else:
            source = "llmos"

    # Support top-level WebAgentBench run artifacts in addition to single-page
    # result objects so callers can pass either JSON shape directly.
    if source == "wab" and isinstance(data.get("results"), list):
        return batch_export(data["results"], source="wab", fmt=fmt)

    if source == "wab":
        messages, metadata = _extract_wab(data)
    else:
        messages, metadata = _extract_llmos(data)

    if len(messages) < 3:  # need at least system + user + assistant
        return []

    convo = _format_conversation(messages, fmt)
    convo["metadata"] = metadata
    return [convo]


def batch_export(
    episodes: list[dict],
    source: str = "auto",
    fmt: str = "messages",
    min_score: Optional[float] = None,
    only_success: bool = False,
) -> list[dict]:
    """
    Export a batch of episodes/results.

    Args:
        episodes: List of episode dicts.
        source: "llmos", "wab", or "auto".
        fmt: "messages" or "sharegpt".
        min_score: Only include episodes with score >= this value.
        only_success: Only include successful episodes.

    Returns:
        Flat list of conversation dicts.
    """
    conversations = []
    for ep in episodes:
        # Score filtering
        score = _get_score(ep, source)
        if min_score is not None and score is not None and score < min_score:
            continue
        if only_success and not _get_success(ep, source):
            continue

        conversations.extend(export_conversations(ep, source=source, fmt=fmt))
    return conversations


# =============================================================================
# LLMOS extraction
# =============================================================================

def _extract_llmos(episode: dict) -> tuple[list[dict], dict]:
    """Extract messages and metadata from an LLMOS episode."""
    history = episode.get("history", [])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for step in history:
        agent_data = (
            step.get("agent_llm_data")
            or step.get("action", {}).get("_llm_data", {})
        )
        user_msg = agent_data.get("user_message")
        raw_response = agent_data.get("raw_response")

        if user_msg:
            messages.append({"role": "user", "content": user_msg})
        if raw_response:
            messages.append({"role": "assistant", "content": raw_response})

    instruction = episode.get("instruction", {})
    if isinstance(instruction, str):
        task_id, task_text = None, instruction
    else:
        task_id = instruction.get("task_id")
        task_text = instruction.get("instruction", str(instruction))

    metadata = {
        "source": "llmos",
        "task_id": task_id,
        "instruction": task_text,
        "score": episode.get("score"),
        "success": episode.get("success"),
        "steps": episode.get("steps"),
    }
    return messages, metadata


# =============================================================================
# WAB extraction
# =============================================================================

def _extract_wab(result: dict) -> tuple[list[dict], dict]:
    """Extract messages and metadata from a WAB result."""
    agent_data = result.get("agent", {})

    # Primary: saved messages (full conversations with observation trees)
    messages = agent_data.get("messages")

    if not messages:
        # Fallback: reconstruct from trajectory (lossy — no observation trees)
        messages = _reconstruct_from_trajectory(result)

    evaluation = result.get("evaluation", {})
    metadata = {
        "source": "webagentbench",
        "task_id": result.get("page_id"),
        "instruction": result.get("title"),
        "score": evaluation.get("score"),
        "success": evaluation.get("success"),
        "steps": agent_data.get("steps"),
    }
    return messages, metadata


def _reconstruct_from_trajectory(result: dict) -> list[dict]:
    """
    Best-effort reconstruction from trajectory steps.

    WARNING: This loses observation trees. The user messages will contain
    "[observation not recorded]" instead of the indexed accessibility tree.
    Data exported this way is NOT suitable for SFT training.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    agent_data = result.get("agent", {})
    trajectory = agent_data.get("trajectory", [])

    for i, step in enumerate(trajectory):
        # Reconstruct user message for first step
        if i == 0:
            instruction = ""
            page_id = result.get("page_id", "")
            # Try to get instruction from page_meta if available
            title = result.get("title", page_id)
            messages.append({
                "role": "user",
                "content": f"Task: {title}\n\n[observation not recorded]",
            })

        action = dict(step.get("action", {}))
        thought = step.get("thought", "")
        if thought:
            action["thought"] = thought
        messages.append({"role": "assistant", "content": json.dumps(action)})

        status = step.get("status", "")
        if status and status != "FINISH" and i < len(trajectory) - 1:
            messages.append({
                "role": "user",
                "content": f"Result: {status}\n\n[observation not recorded]",
            })

    return messages


# =============================================================================
# Format conversion
# =============================================================================

def _format_conversation(messages: list[dict], fmt: str) -> dict:
    """Convert messages to the requested output format."""
    if fmt == "sharegpt":
        role_map = {"system": "system", "user": "human", "assistant": "gpt"}
        return {
            "conversations": [
                {"from": role_map.get(m["role"], m["role"]), "value": m["content"]}
                for m in messages
            ]
        }
    # Default: OpenAI "messages" format
    return {"messages": messages}


# =============================================================================
# Helpers
# =============================================================================

def _get_score(ep: dict, source: str) -> Optional[float]:
    if source == "wab" or "page_id" in ep:
        return ep.get("evaluation", {}).get("score")
    return ep.get("score")


def _get_success(ep: dict, source: str) -> bool:
    if source == "wab" or "page_id" in ep:
        return ep.get("evaluation", {}).get("success", False)
    return ep.get("success", False)


# =============================================================================
# Legacy aliases (backwards compatibility)
# =============================================================================

def llmos_episode_to_conversations(episode: dict) -> list[dict]:
    return export_conversations(episode, source="llmos", fmt="messages")

def wab_result_to_conversations(result: dict) -> list[dict]:
    return export_conversations(result, source="wab", fmt="messages")
