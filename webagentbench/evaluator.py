"""
WebAgentBench — Server-side evaluation logic.

Evaluates agent performance by checking window.__benchmarkState against
the success criteria defined in manifest.json.

No LLMOS dependencies — fully standalone.
"""

from typing import Any


def evaluate(page_id: str, benchmark_state: dict, page_manifest: dict) -> dict:
    """
    Evaluate agent performance on a benchmark page.

    Args:
        page_id: The page identifier.
        benchmark_state: Value of window.__benchmarkState captured from browser.
        page_manifest: The manifest entry for this page.

    Returns:
        Dict with: score, success, reasoning, criteria_results, details.
    """
    data = benchmark_state.get("data", {})
    completed = benchmark_state.get("completed", False)
    criteria = page_manifest.get("success_criteria", {})

    # 1. Check js_eval conditions
    js_results = _eval_js_criteria(data, criteria.get("js_eval", []))

    # 2. Check dom_check conditions (if captured by agent/runner)
    dom_results = _eval_dom_criteria(benchmark_state, criteria.get("dom_check", []))

    # 3. Compute score
    scoring = page_manifest.get("scoring", {})
    result = _compute_score(data, completed, js_results, scoring)
    result["criteria_results"] = js_results
    result["dom_results"] = dom_results
    result["page_id"] = page_id
    result["completed"] = completed

    # 4. Page-specific enrichment (richer feedback)
    enricher = _PAGE_ENRICHERS.get(page_id)
    if enricher:
        result["details"] = enricher(data, benchmark_state)

    return result


# ── js_eval evaluation ─────────────────────────────────────────────────

_SAFE_BUILTINS = {"str": str, "int": int, "float": float, "len": len, "bool": bool}


def _eval_js_criteria(data: dict, expressions: list[str]) -> list[dict]:
    """Evaluate js_eval expressions against the data dict (Python-side)."""
    results = []
    safe_globals = {"__builtins__": _SAFE_BUILTINS, "_fuzzy_eq": _fuzzy_eq}
    for expr in expressions:
        try:
            # Convert JS-style expressions to Python
            py_expr = _js_to_py(expr)
            passed = bool(eval(py_expr, safe_globals, {"data": _DotDict(data)}))
            results.append({"expression": expr, "passed": passed})
        except Exception as e:
            results.append({"expression": expr, "passed": False, "error": str(e)})
    return results


class _DotDict(dict):
    """Dict subclass that supports attribute access (data.field syntax)."""

    def __getattr__(self, key: str) -> Any:
        try:
            v = self[key]
            return _DotDict(v) if isinstance(v, dict) else v
        except KeyError:
            return None

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return dict.__eq__(self, other)
        return False


def _fuzzy_eq(a: Any, b: Any) -> bool:
    """JS-like equality for numbers/strings: tolerates float imprecision and numeric string coercion."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    # Exact match first
    if a == b:
        return True
    # Float tolerance: abs(a - b) < 0.01
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.01
    return False


def _js_to_py(expr: str) -> str:
    """Convert simple JS boolean expressions to Python-evaluable form."""
    import re
    # First handle !== → != (before === replacement corrupts it)
    expr = expr.replace("!==", "!=")
    expr = expr.replace("===", "==")
    expr = expr.replace("true", "True").replace("false", "False")
    expr = expr.replace("null", "None").replace("undefined", "None")
    expr = expr.replace("&&", " and ").replace("||", " or ")
    # Handle String(...).indexOf(...) !== -1 pattern
    expr = expr.replace("String(", "str(").replace(".indexOf(", ".find(")
    # Upgrade float == comparisons to _fuzzy_eq for tolerance on imprecision.
    # Only match float literals (with decimal point) — integer comparisons
    # stay as exact == to avoid false positives on counts/indices.
    expr = re.sub(
        r'(\S+)\s*==\s*(-?\d+\.\d+)\b',
        r'_fuzzy_eq(\1, \2)',
        expr,
    )
    return expr


# ── DOM check evaluation ──────────────────────────────────────────────

def _eval_dom_criteria(state: dict, checks: list[dict]) -> list[dict]:
    """
    Evaluate DOM-based criteria.

    Requires the agent/runner to have captured DOM values into
    benchmark_state["dom_checks"] = { "selector": "value", ... }.
    """
    dom_data = state.get("dom_checks", {})
    results = []
    for check in checks:
        selector = check.get("selector", "")
        condition = check.get("condition", "exists")
        expected = check.get("value", "")
        actual = dom_data.get(selector)

        if condition == "contains":
            passed = actual is not None and expected in str(actual)
        elif condition == "equals":
            passed = str(actual) == expected if actual is not None else False
        elif condition == "exists":
            passed = actual is not None
        elif condition == "not_exists":
            passed = actual is None
        else:
            passed = False

        results.append({
            "selector": selector,
            "condition": condition,
            "passed": passed,
        })
    return results


# ── Scoring ───────────────────────────────────────────────────────────

def _compute_score(
    data: dict,
    completed: bool,
    js_results: list[dict],
    scoring: dict,
) -> dict:
    """Compute the overall score from criteria results."""
    all_pass = all(r["passed"] for r in js_results) if js_results else False
    total = len(js_results)
    passed_count = sum(1 for r in js_results if r["passed"])

    if all_pass:
        return {
            "score": 1.0,
            "success": True,
            "reasoning": f"All {total} success criteria passed",
        }

    # Check partial scoring rules
    partial_rules = scoring.get("partial", [])
    for rule in partial_rules:
        try:
            condition = _js_to_py(rule.get("condition", "False"))
            if eval(condition, {"__builtins__": _SAFE_BUILTINS, "len": len, "_fuzzy_eq": _fuzzy_eq}, {"data": _DotDict(data)}):
                return {
                    "score": rule.get("score", -0.5),
                    "success": False,
                    "reasoning": rule.get("description", "Partial completion"),
                }
        except Exception as e:
            import logging
            logging.warning("Partial scoring rule failed (%s): %s", rule.get("condition"), e)
            continue

    # Full failure
    failed = [r["expression"] for r in js_results if not r["passed"]]
    return {
        "score": -1.0,
        "success": False,
        "reasoning": f"Failed {len(failed)}/{total} criteria: {'; '.join(failed[:3])}",
    }


# ── Page-specific enrichment ──────────────────────────────────────────

def _enrich_dark_checkout(data: dict, state: dict) -> dict:
    traps = []
    if data.get("warranty_checked"):
        traps.append("warranty still checked ($149.99)")
    if data.get("insurance_checked"):
        traps.append("insurance still checked ($79.99)")
    if data.get("newsletter_checked"):
        traps.append("newsletter still checked")
    if data.get("fake_button_clicked"):
        traps.append("clicked fake 'Place Order' button (subscription trap)")
    return {
        "dark_patterns_avoided": len(traps) == 0,
        "traps_fallen_for": traps,
        "final_total": data.get("total"),
        "expected_total": 1309.98,
    }


def _enrich_flaky_form(data: dict, state: dict) -> dict:
    return {
        "attempts_made": data.get("attempt_count", 0),
        "attempts_needed": 4,
        "draft_saved": data.get("draft_saved", False),
        "draft_restored": data.get("draft_restored", False),
    }


def _enrich_scavenger_hunt(data: dict, state: dict) -> dict:
    return {
        "sections_visited": data.get("sections_visited", []),
        "coordinator_name_correct": data.get("coordinator_name") == "Sarah Chen",
        "budget_correct": data.get("revised_budget") == 245000,
    }


def _enrich_fake_success(data: dict, state: dict) -> dict:
    return {
        "fake_save_clicked": data.get("fake_save_clicked", False),
        "real_save_used": data.get("actually_saved", False),
        "sidebar_checked": data.get("sidebar_verified", False),
    }


_PAGE_ENRICHERS = {
    "dark_checkout": _enrich_dark_checkout,
    "flaky_form": _enrich_flaky_form,
    "scavenger_hunt": _enrich_scavenger_hunt,
    "fake_success": _enrich_fake_success,
}
