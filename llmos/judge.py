"""
Episode evaluation for LLMOS.

Evaluation order:
1. Programmatic (if success_criteria defined in instruction)
2. Heuristic (clear-cut: no actions, timeout)
3. LLM-as-judge (default for dynamic simulator episodes)
"""

import json
import logging
from typing import Any, Optional

from .utils.rendering import render_ui_as_text

logger = logging.getLogger(__name__)


def evaluate(
    instruction: dict,
    final_state: dict,
    history: list[dict],
    max_steps: int = 50,
    llm_client=None,
    judge_model: Optional[str] = None,
    judge_provider: Optional[str] = None,
) -> dict:
    """
    Evaluate an episode.

    Evaluation order:
    1. Programmatic (if success_criteria defined in instruction)
    2. Heuristic (clear-cut failures: no actions, timeout)
    3. LLM-as-judge (if llm_client provided)
    4. Fallback heuristic

    Args:
        llm_client: LLMClient instance for LLM-based evaluation.
        judge_model: Model name for LLM judge (uses config default if None).
        judge_provider: Provider for LLM judge (uses config default if None).
    """
    # 1. Programmatic evaluation
    if instruction and "success_criteria" in instruction:
        result = _programmatic_evaluate(instruction["success_criteria"], final_state)
        if result is not None:
            return result

    # 2. Clear-cut heuristic failures
    heuristic = _heuristic_evaluate(final_state, history, max_steps)
    if heuristic is not None:
        return heuristic

    # 3. LLM-as-judge
    if llm_client is not None:
        try:
            return _llm_evaluate(
                llm_client, instruction, final_state, history,
                model=judge_model, provider=judge_provider,
            )
        except Exception as e:
            logger.warning(f"LLM judge failed: {e}")

    # 4. Fallback: agent declared completion but we can't verify
    status = final_state.get("meta", {}).get("status", "running")
    if status == "completed":
        return _result(0.5, False, "Agent declared completion (unverified, no LLM judge)", "")
    return _result(0.0, False, "Episode ended without clear outcome", "")


# =============================================================================
# LLM-as-Judge
# =============================================================================

_JUDGE_SYSTEM_PROMPT = """\
You evaluate whether a computer-use agent completed its task correctly.

CRITICAL RULES:
- Do NOT trust success messages, completion banners, or status fields in the UI.
- Evaluate based on CONCRETE EVIDENCE: what specific actions the agent took,
  what values it entered/selected, and whether those actions satisfy each requirement.
- If success criteria are provided, verify EACH criterion individually against
  the action history.

Evaluation process:
1. Parse the task instruction into specific requirements.
2. If success criteria are provided, check each one against the action history.
3. Verify the final UI state shows the expected result.
4. Score based on how many requirements are clearly satisfied.

Scoring:
  1.0  = ALL requirements met with correct values AND task fully completed
  0.5  = Most requirements met but one or more minor issues
  0.0  = Some progress but significant requirements not met
 -0.5  = Attempted but wrong approach or wrong values
 -1.0  = No meaningful progress

Score 0.5 or BELOW if ANY of these are true:
- Agent selected a plausibly-correct but actually wrong value
- Agent stopped before completing all steps of a multi-step task
- Agent declared success without verifying the final state
- A success criterion is not clearly satisfied by the action history

Return JSON:
{
  "score": <-1.0 to 1.0>,
  "success": <true/false>,
  "criteria_check": [
    {"criterion": "<description>", "met": <true/false>, "evidence": "<what action/state proves it>"}
  ],
  "reasoning": "<brief explanation>",
  "feedback": "<one constructive tip>"
}
"""


def _format_criteria(final_state: dict) -> str:
    """Extract task_completion_criteria from hidden_state and format as checklist."""
    criteria = final_state.get("hidden_state", {}).get("task_completion_criteria", {})
    js_evals = criteria.get("js_eval", [])
    dom_checks = criteria.get("dom_check", [])

    if not js_evals and not dom_checks:
        return "No explicit success criteria provided."

    lines = []
    for i, expr in enumerate(js_evals, 1):
        lines.append(f"  {i}. {expr}")
    # Skip dom_check criteria — they use CSS selectors (#id) which only work
    # in real browsers. The simulator uses bid-based trees, so DOM checks are
    # structurally unverifiable and would cap scores at 0.5.
    return "\n".join(lines)


def _format_action_history(history: list[dict]) -> str:
    """Build detailed per-step action history."""
    lines = []
    for i, h in enumerate(history):
        action = h.get("action", {})
        atype = action.get("action_type", "?")
        parts = [f"Step {i+1}: {atype}"]
        if "bid" in action:
            parts.append(f"bid={action['bid']}")
        if "text" in action:
            parts.append(f'text="{action["text"][:80]}"')
        if "option" in action:
            parts.append(f'option="{action["option"][:80]}"')
        agent_thought = h.get("agent_thought", "")
        if agent_thought:
            parts.append(f'thought="{agent_thought[:100]}"')
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _llm_evaluate(
    llm_client,
    instruction: dict,
    final_state: dict,
    history: list[dict],
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> dict:
    """Evaluate using an LLM judge with criteria-based verification."""
    task = instruction.get("instruction", "Unknown") if instruction else "Unknown"
    status = final_state.get("meta", {}).get("status", "running")

    # Success criteria from template
    criteria_text = _format_criteria(final_state)

    # Detailed action history
    action_history_text = _format_action_history(history)

    # Recent events
    recent_events = []
    for entry in history[-5:]:
        for ev in entry.get("events", []) or []:
            if isinstance(ev, str) and ev:
                recent_events.append(ev[:200])
    events_text = "\n".join(recent_events) if recent_events else "None"

    # UI text (truncated)
    ui_text = render_ui_as_text(final_state)
    if len(ui_text) > 2000:
        ui_text = ui_text[:2000] + "\n... [truncated]"

    user_message = (
        f"## Task\n{task}\n\n"
        f"## Success Criteria (from template)\n{criteria_text}\n\n"
        f"## Action History ({len(history)} steps)\n{action_history_text}\n\n"
        f"## Final UI State (status={status})\n{ui_text}\n\n"
        f"## Recent Events\n{events_text}\n\n"
        f"Evaluate whether the agent completed the task correctly. "
        f"Check each criterion against the action history."
    )

    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = llm_client.complete(
        messages=messages,
        provider=provider,
        model_name=model,
        json_mode=True,
    )

    if isinstance(response, str):
        response = json.loads(response)

    # Normalize types
    if isinstance(response.get("score"), str):
        response["score"] = float(response["score"])
    if isinstance(response.get("success"), str):
        response["success"] = response["success"].strip().lower() == "true"

    score = response.get("score", 0.0)
    success = response.get("success", False)
    reasoning = response.get("reasoning", "")
    feedback = response.get("feedback", "")
    criteria_check = response.get("criteria_check", [])

    return _result(score, success, f"LLM judge: {reasoning}", feedback, criteria_check=criteria_check)


# =============================================================================
# Heuristic
# =============================================================================

def _heuristic_evaluate(
    final_state: dict,
    history: list[dict],
    max_steps: int,
) -> Optional[dict]:
    """Heuristic for clear-cut failures only. Returns None if uncertain."""
    tick = final_state.get("meta", {}).get("tick", 0)

    if len(history) == 0:
        return _result(-1.0, False, "No actions were taken", "Agent did not attempt the task")

    if tick >= max_steps:
        return _result(-0.5, False, f"Timeout at step {tick}", "Complete the task more efficiently")

    # Not clear-cut → return None so LLM judge handles it
    return None


# =============================================================================
# Programmatic
# =============================================================================

def _programmatic_evaluate(criteria: dict, final_state: dict) -> Optional[dict]:
    """Evaluate based on structured success criteria."""
    criteria_type = criteria.get("type")
    conditions = criteria.get("conditions", [])

    if criteria_type != "state_match" or not conditions:
        return None

    total_weight = 0.0
    earned_weight = 0.0

    for cond in conditions:
        weight = cond.get("weight", 1.0)
        total_weight += weight
        actual = _get_by_path(final_state, cond.get("path", ""))
        if _check(actual, cond.get("operator", "equals"), cond.get("value")):
            earned_weight += weight

    if total_weight == 0:
        return None

    raw = earned_weight / total_weight
    score = (raw * 2) - 1
    success = raw >= 0.9

    return _result(
        score, success,
        f"Programmatic: {earned_weight}/{total_weight} conditions met ({raw:.0%})",
        "See success_criteria conditions",
    )


def _get_by_path(obj: dict, path: str) -> Any:
    """Get value from nested dict using dot notation."""
    if not path:
        return obj
    current = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _check(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "contains":
        return expected in actual if isinstance(actual, (str, list, dict)) else False
    if operator == "exists":
        return actual is not None
    if operator == "not_exists":
        return actual is None
    if operator == "greater_than":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    if operator == "less_than":
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False
    return False


def _result(score: float, success: bool, reasoning: str, feedback: str, criteria_check: list | None = None) -> dict:
    r = {"score": score, "success": success, "reasoning": reasoning, "feedback": feedback}
    if criteria_check:
        r["criteria_check"] = criteria_check
    return r
