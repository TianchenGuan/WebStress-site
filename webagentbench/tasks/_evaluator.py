"""Expression-based evaluation engine for WebAgentBench tasks.

Evaluates server-state check expressions defined in task YAML files against
a **read-only snapshot** of the environment state at the end of an agent
session.  The snapshot is built once, before any check runs, so that
individual checks cannot mutate the evidence they verify.
"""

from __future__ import annotations

import ast
from decimal import Decimal
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
    "next": next,
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
    "Decimal": Decimal,
}


class _ReadOnlyProxy:
    """Recursively wraps an object to block attribute writes and expose
    read-only attribute/item access.  Method calls that are *known safe*
    (pure getters on Pydantic models) are forwarded; everything else is
    read-only by default.
    """

    __slots__ = ("_obj",)

    def __init__(self, obj: Any) -> None:
        object.__setattr__(self, "_obj", obj)

    def __getattr__(self, name: str) -> Any:
        value = getattr(object.__getattribute__(self, "_obj"), name)
        return _wrap_readonly(value)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("state is read-only during evaluation")

    def __getitem__(self, key: Any) -> Any:
        return _wrap_readonly(object.__getattribute__(self, "_obj")[key])

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_obj"))

    def __iter__(self):
        for item in object.__getattribute__(self, "_obj"):
            yield _wrap_readonly(item)

    def __contains__(self, item: Any) -> bool:
        return item in object.__getattribute__(self, "_obj")

    def __eq__(self, other: Any) -> bool:
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw == other

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(object.__getattribute__(self, "_obj"))

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, "_obj"))

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = object.__getattribute__(self, "_obj")(*args, **kwargs)
        return _wrap_readonly(result)

    def __repr__(self) -> str:
        return repr(object.__getattribute__(self, "_obj"))

    def __str__(self) -> str:
        return str(object.__getattribute__(self, "_obj"))

    # Comparison operators for sorting/ordering
    def __lt__(self, other: Any) -> bool:
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw < other

    def __le__(self, other: Any) -> bool:
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw <= other

    def __gt__(self, other: Any) -> bool:
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw > other

    def __ge__(self, other: Any) -> bool:
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw >= other

    # Arithmetic operators for Decimal/numeric fields
    def __add__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw + other

    def __radd__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return other + raw

    def __sub__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw - other

    def __rsub__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return other - raw

    def __mul__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw * other

    def __rmul__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return other * raw

    def __truediv__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw / other

    def __mod__(self, other: Any):
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, _ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw % other


def _wrap_readonly(value: Any) -> Any:
    """Wrap compound objects in a read-only proxy; pass through primitives."""
    if value is None or isinstance(value, (bool, int, float, str, Decimal, bytes)):
        return value
    if isinstance(value, _ReadOnlyProxy):
        return value
    return _ReadOnlyProxy(value)


# --------------- AST validation ---------------

_FORBIDDEN_DUNDER = frozenset({
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__import__", "__globals__", "__code__", "__builtins__",
    "__dict__", "__init__", "__new__", "__del__",
    "__getattribute__", "__setattr__", "__delattr__",
})


def _validate_ast(expr_source: str) -> str | None:
    """Return an error string if *expr_source* uses forbidden patterns, else None."""
    try:
        tree = ast.parse(expr_source, mode="eval")
    except SyntaxError as exc:
        return f"SyntaxError: {exc}"

    for node in ast.walk(tree):
        # Block dunder attribute access
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            if node.attr in _FORBIDDEN_DUNDER:
                return f"Forbidden attribute access: {node.attr}"
    return None


def _eval_expr(expr: str, state: Any, targets: dict[str, Any]) -> tuple[bool, str | None]:
    """Compile and evaluate a single check expression.

    The *state* object is wrapped in a read-only proxy so that check
    expressions cannot mutate the evidence they are verifying.

    Returns ``(passed, error_string_or_None)``.
    """
    substituted = _substitute_targets(expr, targets)

    # AST pre-validation
    ast_error = _validate_ast(substituted)
    if ast_error is not None:
        return (False, ast_error)

    namespace: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "state": _wrap_readonly(state),
        "target": _DotDict(targets),
    }
    try:
        code = compile(substituted, "<eval-check>", "eval")
        result = eval(code, namespace)
        return (bool(result), None)
    except Exception as exc:
        return (False, f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------
# Collateral-damage detection (analytics only, no score impact)
# ------------------------------------------------------------------

def _compute_collateral(initial: dict[str, Any] | None, state: Any) -> dict[str, Any]:
    """Diff initial snapshot against current state.

    Returns a structured report of all state mutations that occurred during
    the session, categorised by dimension.  This is analytics-only — the
    result is included in evaluation output but never affects the score.

    If no initial snapshot is available the report is empty.
    """
    if initial is None or not hasattr(state, "state_snapshot"):
        return {}

    current = state.state_snapshot()
    report: dict[str, Any] = {}

    # --- emails modified (flag changes on existing emails) ---
    modified_emails: list[dict[str, Any]] = []
    init_flags = initial.get("email_flags", {})
    curr_flags = current.get("email_flags", {})
    for eid, init_f in init_flags.items():
        curr_f = curr_flags.get(eid)
        if curr_f is None:
            continue  # email was deleted — tracked separately
        diffs = {k: {"before": init_f[k], "after": curr_f[k]}
                 for k in init_f if init_f[k] != curr_f.get(k)}
        if diffs:
            modified_emails.append({"email_id": eid, "changes": diffs})
    if modified_emails:
        report["emails_modified"] = modified_emails

    # --- emails deleted ---
    init_email_ids = set(initial.get("email_ids", []))
    curr_email_ids = set(current.get("email_ids", []))
    init_deleted = set(initial.get("deleted_ids", []))
    curr_deleted = set(current.get("deleted_ids", []))
    newly_deleted = curr_deleted - init_deleted
    if newly_deleted:
        report["emails_deleted"] = sorted(newly_deleted)

    # --- emails sent ---
    sent_delta = current.get("sent_count", 0) - initial.get("sent_count", 0)
    if sent_delta > 0:
        report["emails_sent"] = sent_delta

    # --- drafts ---
    draft_delta = current.get("draft_count", 0) - initial.get("draft_count", 0)
    if draft_delta != 0:
        report["drafts_delta"] = draft_delta

    # --- contacts changed ---
    init_contacts = initial.get("contacts", {})
    curr_contacts = current.get("contacts", {})
    contacts_added = sorted(set(curr_contacts) - set(init_contacts))
    contacts_removed = sorted(set(init_contacts) - set(curr_contacts))
    contacts_modified: list[dict[str, Any]] = []
    for cid in set(init_contacts) & set(curr_contacts):
        diffs = {k: {"before": init_contacts[cid][k], "after": curr_contacts[cid][k]}
                 for k in init_contacts[cid]
                 if init_contacts[cid][k] != curr_contacts[cid].get(k)}
        if diffs:
            contacts_modified.append({"contact_id": cid, "changes": diffs})
    if contacts_added:
        report["contacts_added"] = contacts_added
    if contacts_removed:
        report["contacts_removed"] = contacts_removed
    if contacts_modified:
        report["contacts_modified"] = contacts_modified

    # --- labels changed ---
    init_labels = initial.get("labels", {})
    curr_labels = current.get("labels", {})
    labels_added = sorted(set(curr_labels) - set(init_labels))
    labels_removed = sorted(set(init_labels) - set(curr_labels))
    labels_modified: list[dict[str, Any]] = []
    for lid in set(init_labels) & set(curr_labels):
        diffs = {k: {"before": init_labels[lid][k], "after": curr_labels[lid][k]}
                 for k in init_labels[lid]
                 if init_labels[lid][k] != curr_labels[lid].get(k)}
        if diffs:
            labels_modified.append({"label_id": lid, "changes": diffs})
    if labels_added:
        report["labels_added"] = labels_added
    if labels_removed:
        report["labels_removed"] = labels_removed
    if labels_modified:
        report["labels_modified"] = labels_modified

    # --- filters changed ---
    init_filters = initial.get("filters", {})
    curr_filters = current.get("filters", {})
    filters_added = sorted(set(curr_filters) - set(init_filters))
    filters_removed = sorted(set(init_filters) - set(curr_filters))
    if filters_added:
        report["filters_added"] = filters_added
    if filters_removed:
        report["filters_removed"] = filters_removed

    # --- settings changed ---
    init_settings = initial.get("settings", {})
    curr_settings = current.get("settings", {})
    settings_changed = {k: {"before": init_settings[k], "after": curr_settings[k]}
                        for k in init_settings
                        if init_settings.get(k) != curr_settings.get(k)}
    if settings_changed:
        report["settings_changed"] = settings_changed

    return report


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
    # Create an isolated copy of the state for evaluation so that
    # check expressions cannot mutate the live state (even via method
    # calls like state.touch()).
    # ------------------------------------------------------------------
    from copy import deepcopy
    eval_state = deepcopy(server_state)

    # ------------------------------------------------------------------
    # Evaluate positive checks
    # ------------------------------------------------------------------
    check_results: list[dict[str, Any]] = []
    passed_count = 0
    for check in checks:
        expr = check.expr
        desc = check.desc
        passed, error = _eval_expr(expr, eval_state, targets)
        if passed:
            passed_count += 1
        check_results.append({
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
        passed, error = _eval_expr(expr, eval_state, targets)
        # Only apply penalty if the expression evaluated cleanly and failed.
        # If it crashed (e.g. IndexError on empty state.sent), the check is
        # not applicable — don't penalise the agent for something that can't
        # be meaningfully assessed.
        if not passed and error is None:
            penalty_total += penalty
        neg_results.append({
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

    # ------------------------------------------------------------------
    # Collateral-damage detection (analytics only)
    # ------------------------------------------------------------------
    # Prefer the env's own compute_collateral() method (env-agnostic).
    # Fall back to the legacy Gmail-specific _compute_collateral() for
    # backwards compatibility.
    initial_snapshot = getattr(server_state, "_initial_snapshot", None)
    if initial_snapshot is not None and hasattr(server_state, "compute_collateral"):
        collateral = server_state.compute_collateral(initial_snapshot)
    else:
        # Legacy path: try the old attribute name and Gmail-specific diffing.
        initial_snapshot = initial_snapshot or getattr(server_state, "initial_snapshot", None)
        collateral = _compute_collateral(initial_snapshot, server_state)

    if collateral:
        dims = list(collateral.keys())
        lines.append(f"Collateral mutations detected ({len(dims)} dimensions): {', '.join(dims)}")
    else:
        lines.append("No collateral mutations detected.")

    lines.append(f"Final score: {score:.3f} | Success: {success}")
    reasoning = "\n".join(lines)

    result = {
        "score": score,
        "success": success,
        "reasoning": reasoning,
        "checks": check_results,
        "negative_checks": neg_results,
        "final_score": score,
    }
    if collateral:
        result["collateral"] = collateral
    return result
