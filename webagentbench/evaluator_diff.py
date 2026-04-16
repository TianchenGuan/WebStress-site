"""Diff-based evaluator — pure functions.

Implements the predicate evaluator for the canonical-diff grammar described in
``docs/superpowers/specs/2026-04-16-correctness-diff-design.md`` §3.2.

Public API (will grow in Tasks 3-6):
    eval_predicate(pred, scope) -> bool

The ``{expr: "..."}`` predicate reuses the restricted-globals pattern from the
legacy ``webagentbench/evaluator.py`` — no new security surface is introduced
here.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from webagentbench.evaluator import _fuzzy_eq

__all__ = [
    "PredicateScope",
    "eval_predicate",
    "Create",
    "Update",
    "Delete",
    "DiffEntry",
    "compute_diff",
]


# ------------------------------------------------------------------
# Scope
# ------------------------------------------------------------------

@dataclass
class PredicateScope:
    """Bindings available to predicates when they are evaluated.

    Attributes:
        value: The concrete value the predicate is evaluating (bound to ``x``
            in ``expr`` predicates).
        target: The task's ``target`` dict (constants declared in the task
            YAML).
        initial: A snapshot of the pre-action state, if relevant.
        state: A reference to the current full state, if relevant.
        bijection_var: The loop variable from a surrounding bijection, if any
            (bound to ``v`` in ``expr`` predicates).
        session_start: The session start time, if relevant (bound to
            ``session_start`` in ``expr`` predicates).
    """

    value: Any
    target: dict = field(default_factory=dict)
    initial: Any = None
    state: Any = None
    bijection_var: Any = None
    session_start: datetime | None = None


# ------------------------------------------------------------------
# Safe-builtins allowlist for the {expr: "..."} predicate.
# Mirrors webagentbench/evaluator.py line 65, expanded with types the
# canonical-diff expressions legitimately need (Decimal, datetime, etc.).
# ------------------------------------------------------------------

_SAFE_BUILTINS = {
    "str": str,
    "int": int,
    "float": float,
    "len": len,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "sum": sum,
    "min": min,
    "max": max,
    "any": any,
    "all": all,
    "range": range,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "Decimal": Decimal,
    "datetime": datetime,
    "timedelta": timedelta,
}


def _expr_scope(scope: PredicateScope) -> dict[str, Any]:
    """Build the locals dict passed to the restricted eval for ``{expr: "..."}``."""
    return {
        "x": scope.value,
        "v": scope.bijection_var,
        "target": scope.target,
        "initial": scope.initial,
        "state": scope.state,
        "session_start": scope.session_start,
        "now": lambda: datetime.now(timezone.utc),
    }


# ------------------------------------------------------------------
# matches_semantic support
# ------------------------------------------------------------------

def _semantic_match(a: Any, b: Any, threshold: float) -> bool:
    """Fuzzy text-similarity match.

    Falls back to ``_fuzzy_eq`` (exact / numeric-tolerance) first so callers
    who supplied numbers or exact-equal strings short-circuit cheaply; then
    uses ``difflib.SequenceMatcher.ratio()`` to gate on textual similarity.
    The legacy ``_fuzzy_eq`` is binary — it does not accept a threshold — so
    this wrapper is necessary to implement the spec's configurable cutoff.
    """
    if _fuzzy_eq(a, b):
        return True
    if a is None or b is None:
        return False
    sa = str(a)
    sb = str(b)
    return difflib.SequenceMatcher(None, sa, sb).ratio() >= threshold


# ------------------------------------------------------------------
# eval_predicate
# ------------------------------------------------------------------

def eval_predicate(pred: dict, scope: PredicateScope) -> bool:
    """Evaluate a single predicate against ``scope.value``.

    Predicate grammar is specified in the canonical-diff design doc §3.2.
    ``pred`` must be a single-key dict; the key selects the predicate kind.
    """
    if not isinstance(pred, dict) or len(pred) != 1:
        raise ValueError(
            f"predicate must be a single-key dict, got {pred!r}"
        )

    key = next(iter(pred))
    arg = pred[key]
    value = scope.value

    # ── scalar ────────────────────────────────────────────────────
    if key == "eq":
        return value == arg
    if key == "in":
        return value in arg
    if key == "between":
        lo, hi = arg
        return lo <= value <= hi
    if key == "any":
        return True

    # ── collection ────────────────────────────────────────────────
    if key == "set_eq":
        return set(value) == set(arg)
    if key == "subset":
        return set(value).issubset(set(arg))
    if key == "superset":
        return set(value).issuperset(set(arg))
    if key == "contains":
        return arg in value
    if key == "length":
        inner_scope = PredicateScope(
            value=len(value),
            target=scope.target,
            initial=scope.initial,
            state=scope.state,
            bijection_var=scope.bijection_var,
            session_start=scope.session_start,
        )
        return eval_predicate(arg, inner_scope)

    # ── text ──────────────────────────────────────────────────────
    if key == "substring":
        return arg in (value or "")
    if key == "substring_all":
        haystack = value or ""
        return all(s in haystack for s in arg)
    if key == "substring_any":
        haystack = value or ""
        return any(s in haystack for s in arg)
    if key == "regex":
        return re.search(arg, value or "") is not None
    if key == "matches_semantic":
        # Two shapes: {matches_semantic: "text"} or
        # {matches_semantic: {"value" | "s": "text", "threshold": 0.9}}.
        if isinstance(arg, dict):
            target_text = arg.get("value", arg.get("s"))
            threshold = float(arg.get("threshold", 0.8))
        else:
            target_text = arg
            threshold = 0.8
        return _semantic_match(value, target_text, threshold=threshold)

    # ── nested ────────────────────────────────────────────────────
    if key == "fields":
        if not isinstance(value, dict):
            return False
        for sub_field, sub_pred in arg.items():
            inner = PredicateScope(
                value=value.get(sub_field),
                target=scope.target,
                initial=scope.initial,
                state=scope.state,
                bijection_var=scope.bijection_var,
                session_start=scope.session_start,
            )
            if not eval_predicate(sub_pred, inner):
                return False
        return True

    # ── expr (restricted eval) ────────────────────────────────────
    if key == "expr":
        try:
            globs = {"__builtins__": _SAFE_BUILTINS}
            # Restricted eval — mirrors webagentbench/evaluator.py line 76.
            # Only the safe-builtins allowlist is exposed; expression source
            # is author-controlled (task YAML).
            return bool(eval(arg, globs, _expr_scope(scope)))  # noqa: S307
        except Exception:
            return False

    raise ValueError(f"unknown predicate key {key!r}")


# ------------------------------------------------------------------
# Diff entries
# ------------------------------------------------------------------
#
# ``compute_diff(initial, final)`` produces the net set of entity-level
# changes between two state snapshots. Semantics are defined in the
# canonical-diff design doc §3.7 ("net, not sequential") and §7.5
# ("entity identity is by ``.id``; sub-entity lists are collection-valued
# fields on the parent, not independent collections").
#
# Dataclasses are frozen so callers treat them as immutable tokens. ``dict``
# fields are allowed inside a frozen dataclass — ``frozen=True`` only blocks
# attribute reassignment, not mutation of mutable field values. We never
# hash these entries, so the non-hashable dict does not cause problems.


@dataclass(frozen=True)
class Create:
    """An entity that exists in ``final`` but not in ``initial``."""

    entity: str              # collection name, e.g. "appointments"
    entity_id: str
    fields: dict[str, Any]   # full entity dict as of ``final``


@dataclass(frozen=True)
class Update:
    """An entity that exists in both snapshots with at least one changed field."""

    entity: str
    entity_id: str
    field_changes: dict[str, tuple[Any, Any]]   # {field: (before, after)}


@dataclass(frozen=True)
class Delete:
    """An entity that exists in ``initial`` but not in ``final``."""

    entity: str
    entity_id: str
    last_fields: dict[str, Any]   # full entity dict as of ``initial``


DiffEntry = Create | Update | Delete


# ------------------------------------------------------------------
# compute_diff helpers
# ------------------------------------------------------------------

def _collections_of(state: Any) -> dict[str, list[dict]]:
    """Return ``{collection_name: [entity_dict, ...]}`` for a state snapshot.

    Accepts either:
      * a dict-of-lists (used by tests for convenience), or
      * a pydantic ``BaseModel`` (the production shape — every env state
        derives from ``BaseEnvState``).

    Non-list fields are ignored. Entities are normalised to plain dicts
    via ``model_dump()`` so the diff logic can treat both inputs uniformly.
    """
    if isinstance(state, dict):
        return {k: list(v) for k, v in state.items() if isinstance(v, list)}

    from pydantic import BaseModel
    if isinstance(state, BaseModel):
        out: dict[str, list[dict]] = {}
        for name in type(state).model_fields:
            val = getattr(state, name)
            if isinstance(val, list):
                out[name] = [
                    v.model_dump() if hasattr(v, "model_dump") else dict(v)
                    for v in val
                ]
        return out
    raise TypeError(f"compute_diff: unsupported state type {type(state)!r}")


def _index_by_id(entities: list[dict]) -> dict[str, dict]:
    """Index entities by their ``id`` field. Entities without ``id`` are skipped."""
    return {e["id"]: e for e in entities if "id" in e}


# ------------------------------------------------------------------
# compute_diff
# ------------------------------------------------------------------

def compute_diff(initial: Any, final: Any) -> list[DiffEntry]:
    """Compute the net state delta from ``initial`` to ``final``.

    Returns ``Create`` / ``Update`` / ``Delete`` entries per collection,
    sorted by ``(collection, kind, entity_id)`` for deterministic output.
    Kind ordering is ``Create`` < ``Delete`` < ``Update`` because
    ``sorted(created | deleted | updated)`` groups in the order they are
    appended below; within each kind, ids are already sorted.

    Semantics are *net* (spec §3.7): intermediate mutations that the agent
    performs and then reverts do not appear in the output.

    Accepts either dict-of-lists snapshots (test convenience) or pydantic
    ``BaseModel`` snapshots (production).
    """
    i_cols = _collections_of(initial)
    f_cols = _collections_of(final)
    out: list[DiffEntry] = []

    for col in sorted(set(i_cols) | set(f_cols)):
        before = _index_by_id(i_cols.get(col, []))
        after = _index_by_id(f_cols.get(col, []))

        created_ids = sorted(set(after) - set(before))
        deleted_ids = sorted(set(before) - set(after))
        maybe_updated = sorted(set(before) & set(after))

        for eid in created_ids:
            out.append(Create(entity=col, entity_id=eid, fields=after[eid]))
        for eid in deleted_ids:
            out.append(Delete(entity=col, entity_id=eid, last_fields=before[eid]))
        for eid in maybe_updated:
            changes = {
                k: (before[eid].get(k), after[eid].get(k))
                for k in set(before[eid]) | set(after[eid])
                if before[eid].get(k) != after[eid].get(k)
            }
            if changes:
                out.append(Update(entity=col, entity_id=eid, field_changes=changes))
    return out
