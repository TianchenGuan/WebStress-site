"""Expression-based evaluation engine for WebAgentBench Gmail tasks.

Evaluates server-state check expressions defined in task YAML files against
the actual :class:`GmailState` at the end of an agent session.
"""

from __future__ import annotations

import re
from typing import Any


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

class _DotDict:
    """Thin wrapper that exposes *dict* values via dot access.

    Supports nested dotted access (e.g. ``target.compose_to``) by recursively
    wrapping nested dicts.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError:
            raise AttributeError(f"target has no attribute {name!r}") from None
        if isinstance(value, dict):
            return _DotDict(value)
        return value

    def __repr__(self) -> str:
        return f"_DotDict({self._data!r})"


# Regex matching ``{target.some_key}`` (including nested dots).
_TARGET_RE = re.compile(r"\{target\.([^}]+)\}")


def _sanitize_target_value(value: str) -> str:
    """Escape characters that could break out of string literals in eval expressions."""
    return (value
        .replace('\\', '\\\\')
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace('\n', '\\n')
        .replace('\r', '\\r'))


def _substitute_targets(expr: str, targets: dict[str, Any]) -> str:
    """Replace ``{target.xxx}`` placeholders with their string values."""

    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        # Walk dotted paths (e.g. "compose_to" or "nested.key")
        value: Any = targets
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
            if value is None:
                return match.group(0)  # leave placeholder if unresolved
        if isinstance(value, str):
            return _sanitize_target_value(value)
        return repr(value)

    return _TARGET_RE.sub(_replacer, expr)


# Restricted builtins exposed to check expressions.
_SAFE_BUILTINS: dict[str, Any] = {
    "any": any,
    "all": all,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "True": True,
    "False": False,
    "None": None,
    "list": list,
    "set": set,
    "sorted": sorted,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
}


def _eval_expr(expr: str, state: Any, targets: dict[str, Any]) -> tuple[bool, str | None]:
    """Compile and evaluate a single check expression.

    Returns ``(passed, error_string_or_None)``.
    """
    substituted = _substitute_targets(expr, targets)
    namespace: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "state": state,
        "target": _DotDict(targets),
    }
    try:
        code = compile(substituted, "<eval-check>", "eval")
        result = eval(code, namespace)
        return (bool(result), None)
    except Exception as exc:
        return (False, f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def evaluate(
    task: Any,
    *,
    server_state: Any,
    targets: dict[str, Any],
    trajectory: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run all checks defined in *task.eval* against *server_state*.

    Parameters
    ----------
    task:
        A :class:`TaskDefinition` (or any object whose ``.eval`` attribute
        holds an ``EvalConfig`` with ``.checks`` and ``.negative_checks``).
    server_state:
        The live :class:`GmailState` (or equivalent ``BaseEnvState``).
    targets:
        Resolved template variables (``{target.xxx}`` substitutions).
    trajectory:
        List of agent action dicts (currently unused by expression checks but
        accepted for forward-compatibility).

    Returns
    -------
    dict
        Evaluation result with ``score``, ``success``, ``reasoning``,
        ``checks``, ``negative_checks``, and ``final_score`` keys.
    """

    eval_config = getattr(task, "eval", None)

    # ------------------------------------------------------------------
    # Edge case: no evaluation criteria defined
    # ------------------------------------------------------------------
    if eval_config is None:
        return {
            "score": 0.0,
            "success": False,
            "reasoning": "No evaluation criteria defined",
            "checks": [],
            "negative_checks": [],
            "final_score": 0.0,
        }

    checks: list[Any] = getattr(eval_config, "checks", None) or []
    negative_checks: list[Any] = getattr(eval_config, "negative_checks", None) or []

    # ------------------------------------------------------------------
    # Evaluate positive checks
    # ------------------------------------------------------------------
    check_results: list[dict[str, Any]] = []
    passed_count = 0
    for check in checks:
        expr = check.expr
        desc = check.desc
        passed, error = _eval_expr(expr, server_state, targets)
        if passed:
            passed_count += 1
        check_results.append({
            "expr": expr,
            "desc": desc,
            "passed": passed,
            "error": error,
        })

    total_checks = len(checks)
    base_score = passed_count / total_checks if total_checks > 0 else 0.0

    # ------------------------------------------------------------------
    # Evaluate negative checks (penalties)
    # ------------------------------------------------------------------
    neg_results: list[dict[str, Any]] = []
    penalty_total = 0.0
    for neg in negative_checks:
        expr = neg.expr
        desc = neg.desc
        penalty = float(neg.penalty)
        passed, error = _eval_expr(expr, server_state, targets)
        # Only apply penalty if the expression evaluated cleanly and failed.
        # If it crashed (e.g. IndexError on empty state.sent), the check is
        # not applicable — don't penalise the agent for something that can't
        # be meaningfully assessed.
        if not passed and error is None:
            penalty_total += penalty
        neg_results.append({
            "expr": expr,
            "desc": desc,
            "passed": passed,
            "error": error,
            "penalty": penalty,
        })
    raw_penalty_total = penalty_total
    penalty_total = min(penalty_total, 0.95)

    # ------------------------------------------------------------------
    # Compute final score
    # ------------------------------------------------------------------
    score = max(-1.0, min(1.0, base_score - penalty_total))
    all_positive_passed = passed_count == total_checks
    success = all_positive_passed and score >= 0.5

    # ------------------------------------------------------------------
    # Build human-readable reasoning
    # ------------------------------------------------------------------
    lines: list[str] = []
    lines.append(f"Passed {passed_count}/{total_checks} checks.")
    for cr in check_results:
        status = "PASS" if cr["passed"] else "FAIL"
        line = f"  [{status}] {cr['desc']}"
        if cr["error"]:
            line += f" (error: {cr['error']})"
        lines.append(line)

    if neg_results:
        failed_negs = [nr for nr in neg_results if not nr["passed"]]
        if failed_negs:
            lines.append(f"Negative check penalties: {len(failed_negs)} triggered, total penalty {penalty_total:.2f}.")
            if raw_penalty_total != penalty_total:
                lines.append(f"  [INFO] Raw negative penalty {raw_penalty_total:.2f} was capped at 0.95.")
            for nr in failed_negs:
                lines.append(f"  [PENALTY -{nr['penalty']:.2f}] {nr['desc']}")
        else:
            lines.append("All negative checks passed (no penalties).")

    lines.append(f"Final score: {score:.3f} | Success: {success}")
    reasoning = "\n".join(lines)

    return {
        "score": score,
        "success": success,
        "reasoning": reasoning,
        "checks": check_results,
        "negative_checks": neg_results,
        "final_score": score,
    }
