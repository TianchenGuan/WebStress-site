from __future__ import annotations

import re
from typing import Any

from .state import SessionManager
from .tasks import TASK_INDEX


_SAFE_GLOBALS = {
    "__builtins__": {},
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}


class AdvancedEvaluator:
    """Deterministic evaluator for advanced environment tasks."""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def evaluate(
        self,
        session_id: str,
        task_id: str | None = None,
        benchmark_state: dict[str, Any] | None = None,
        trajectory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        state = self.session_manager.get(session_id)
        if benchmark_state is not None:
            self.session_manager.set_benchmark_state(session_id, benchmark_state)
        task_def = TASK_INDEX[task_id or state.task_id]
        targets = state.resolved_targets

        criteria_results = [
            self._evaluate_check(state, check, targets)
            for check in task_def.get("success_criteria", {}).get("checks", [])
        ]
        negative_results = [
            self._evaluate_negative_check(state, check, targets)
            for check in task_def.get("success_criteria", {}).get("negative_checks", [])
        ]

        total_checks = len(criteria_results)
        passed_checks = sum(1 for result in criteria_results if result["passed"])
        base_score = passed_checks / total_checks if total_checks else 0.0
        penalties = sum(result["penalty"] for result in negative_results if not result["passed"])
        trajectory_mod = self._trajectory_modifier(task_def, benchmark_state or {}, trajectory or [])
        final_score = max(0.0, min(1.0, round(base_score - penalties + trajectory_mod, 4)))
        success = all(result["passed"] for result in criteria_results) and all(
            result["passed"] for result in negative_results
        )

        return {
            "task_id": task_def["task_id"],
            "env_id": task_def["env_id"],
            "score": final_score,
            "success": success,
            "criteria_results": criteria_results,
            "negative_results": negative_results,
            "trajectory_mod": trajectory_mod,
            "final_score": final_score,
            "benchmark_completed": bool((benchmark_state or {}).get("completed")),
            "reasoning": self._reasoning(criteria_results, negative_results, final_score),
        }

    def _evaluate_check(self, state, check: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
        desc = self._render_text(check.get("desc", ""), targets)
        expr = self._substitute_expr(check["expr"], targets)
        try:
            scope = dict(_SAFE_GLOBALS)
            scope["state"] = state
            actual = eval(expr, scope, {})
            passed = bool(actual)
            return {"check": desc, "passed": passed, "actual": actual, "expr": expr}
        except Exception as exc:
            return {"check": desc, "passed": False, "error": str(exc), "expr": expr}

    def _evaluate_negative_check(self, state, check: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
        result = self._evaluate_check(state, check, targets)
        result["penalty"] = float(check.get("penalty", 0.0))
        return result

    def _trajectory_modifier(
        self,
        task_def: dict[str, Any],
        benchmark_state: dict[str, Any],
        trajectory: list[dict[str, Any]],
    ) -> float:
        expected_steps = int(task_def.get("expected_steps", 20))
        steps = len(trajectory) or len(benchmark_state.get("events", []))
        modifier = 0.0
        if steps:
            if steps <= max(4, int(expected_steps * 0.7)):
                modifier += 0.03
            elif steps > int(expected_steps * 1.8):
                modifier -= 0.05
        recent_actions = " ".join(str(item).lower() for item in trajectory[-3:])
        recent_events = " ".join(str(item).lower() for item in benchmark_state.get("events", [])[-3:])
        if any(token in recent_actions or token in recent_events for token in ("verify", "checked", "confirmed")):
            modifier += 0.02
        return max(-0.1, min(0.1, round(modifier, 3)))

    def _reasoning(
        self,
        criteria_results: list[dict[str, Any]],
        negative_results: list[dict[str, Any]],
        final_score: float,
    ) -> str:
        failed_checks = [f"Missing: {result['check']}" for result in criteria_results if not result["passed"]]
        failed_negative = [f"Penalty: {result['check']}" for result in negative_results if not result["passed"]]
        if not failed_checks and not failed_negative:
            return f"All checks passed; final score {final_score:.2f}"
        reasons = failed_checks[:2] + failed_negative[:2]
        return "; ".join(reasons)

    def _substitute_expr(self, expr: str, targets: dict[str, Any]) -> str:
        def in_string(match: re.Match[str]) -> str:
            quote = match.group(1)
            content = match.group(2)

            def replace_inner(inner_match: re.Match[str]) -> str:
                key = inner_match.group(1)
                if key not in targets:
                    raise KeyError(f"Unknown target placeholder: {key}")
                return str(targets[key])

            content = re.sub(r"\{target\.([a-zA-Z0-9_]+)\}", replace_inner, content)
            return f"{quote}{content}{quote}"

        expr = re.sub(r"(['\"])(.*?)\1", in_string, expr)

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in targets:
                raise KeyError(f"Unknown target placeholder: {key}")
            return repr(targets[key])

        return re.sub(r"\{target\.([a-zA-Z0-9_]+)\}", repl, expr)

    def _render_text(self, text: str, targets: dict[str, Any]) -> str:
        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(targets.get(key, match.group(0)))

        return re.sub(r"\{target\.([a-zA-Z0-9_]+)\}", repl, text)
