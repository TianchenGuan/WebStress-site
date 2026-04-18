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
    "Failure",
    "EvalReport",
    "match_diff",
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
        # len() on None / int / other non-sized values would propagate a
        # TypeError through the matcher. Conservatively return False so
        # optional fields that happen to be None on a given trajectory
        # don't crash the evaluator (Class 13).
        try:
            length_value = len(value)
        except TypeError:
            return False
        inner_scope = PredicateScope(
            value=length_value,
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
            # Restricted eval — mirrors webagentbench/evaluator.py line 76.
            # Only the safe-builtins allowlist is exposed; expression source
            # is author-controlled (task YAML).
            #
            # Merge the predicate scope into GLOBALS (not locals) so list/gen
            # comprehensions can see `x`, `v`, `target`, etc. Comprehensions
            # run in a nested function scope that only reads from globals —
            # keeping scope vars in locals makes them invisible inside
            # `any(... for v in target['...'])`-style expressions, which is a
            # common pattern authors want to write.
            globs: dict = {"__builtins__": _SAFE_BUILTINS, **_expr_scope(scope)}
            return bool(eval(arg, globs, {}))  # noqa: S307
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

def _strip_ignored_fields(entity_dict: dict, ignore_fields: tuple[str, ...]) -> dict:
    """Remove system-managed / side-effect fields from an entity dump so they
    don't appear in the diff. Caller passes the entity's
    ``DIFF_IGNORE_FIELDS`` class attribute."""
    if not ignore_fields:
        return entity_dict
    return {k: v for k, v in entity_dict.items() if k not in ignore_fields}


def _collections_of(state: Any) -> dict[str, list[dict]]:
    """Return ``{collection_name: [entity_dict, ...]}`` for a state snapshot.

    Accepts either:
      * a dict-of-lists (used by tests for convenience), or
      * a pydantic ``BaseModel`` (the production shape — every env state
        derives from ``BaseEnvState``).

    Non-list fields are ignored. Entities are normalised to plain dicts
    via ``model_dump()`` so the diff logic can treat both inputs uniformly.
    Fields listed in an entity class's ``DIFF_IGNORE_FIELDS`` attribute are
    stripped before comparison — this is how side-effect fields (e.g.
    ``Provider.available_slots`` consumed by appointment booking) become
    invisible to the collateral-damage sweep.
    """
    if isinstance(state, dict):
        return {k: list(v) for k, v in state.items() if isinstance(v, list)}

    from pydantic import BaseModel
    if isinstance(state, BaseModel):
        out: dict[str, list[dict]] = {}
        for name in type(state).model_fields:
            val = getattr(state, name)
            if not isinstance(val, list):
                continue
            # Entity-collection lists hold pydantic models (list[SomeEntity]).
            # State-level data lists (e.g. reddit's list[str] for
            # subscriptions, saved_post_ids, blocked_users) hold scalars
            # or non-entity dicts. compute_diff only tracks entity
            # collections — state-level lists should be asserted via
            # constraint expressions in the canonical_diff, not diffed
            # here. Skip any list whose elements aren't pydantic models
            # or plain dicts-with-id.
            dumped: list[dict] = []
            for v in val:
                if hasattr(v, "model_dump"):
                    entity_dict = v.model_dump()
                    ignore = getattr(type(v), "DIFF_IGNORE_FIELDS", ())
                    if ignore:
                        entity_dict = _strip_ignored_fields(entity_dict, ignore)
                    dumped.append(entity_dict)
                elif isinstance(v, dict):
                    dumped.append(dict(v))
                else:
                    # Scalar or non-dict element — whole list is a
                    # state-level scalar list. Drop the collection and
                    # move on; constraints can still reach it via
                    # `state.<name>`.
                    dumped = []
                    break
            else:
                out[name] = dumped
                continue
            # If we broke out of the loop because of a scalar element,
            # the for/else above didn't run — skip this field.
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


# ------------------------------------------------------------------
# ── Matcher (Task 4) ──
# ------------------------------------------------------------------
#
# ``match_diff`` checks an agent-produced diff against the authored
# ``canonical_diff`` block. Algorithm is specified in the canonical-diff
# design doc §4.
#
# This task implements only the non-bijection path plus invariant
# enforcement and the unaccounted sweep. Task 5 adds bijection matching
# via augmenting-path bipartite matching; Task 6 adds constraints,
# named_invariants, and partial-credit scoring.


@dataclass
class Failure:
    """One failed requirement in the match."""

    kind: str  # "missing_create", "predicate", "invariant", "unaccounted", "constraint"
    description: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    """Result of matching a diff against a canonical_diff block."""

    passed: bool
    score: float
    checks: list[dict] = field(default_factory=list)          # [{desc, passed, error}]
    negative_checks: list[dict] = field(default_factory=list)  # [{desc, passed, penalty}]
    failures: list[Failure] = field(default_factory=list)
    # Per-bijection graph details, for frontend viz. Each entry:
    #   {desc, entity, slots:[{label, matched_candidate_index|None}],
    #    candidates:[{label, id, is_excess}], edges:[[slot_i, cand_i], ...]}
    bijection_graphs: list[dict] = field(default_factory=list)


# Severity-to-penalty mapping used by invariant / constraint reporting.
_SEVERITY_PENALTY = {"critical": 0.3, "high": 0.2, "medium": 0.15, "low": 0.1}


# ------------------------------------------------------------------
# Matcher helpers
# ------------------------------------------------------------------

def _candidate_label(cand: Any) -> str:
    """Pick a short human-readable label for a Create candidate for the
    bijection-graph viz. Prefers common identifying fields; falls back to id."""
    fields = getattr(cand, "fields", None) or {}
    for key in ("name", "title", "subject", "provider_id", "vaccine_ref", "reason", "type"):
        val = fields.get(key)
        if val:
            return f"{val}"[:40]
    return str(getattr(cand, "entity_id", "?"))


def _build_collection_map(state: Any) -> dict[str, str]:
    """Return ``{entity_type_name: collection_field_name}`` by introspecting
    a pydantic state model.

    Handles irregular pluralisation (e.g. ``ClinicalMessage`` → ``messages``)
    where the naive ``lower() + 's'`` heuristic would produce the wrong name.
    Returns an empty mapping if ``state`` isn't a pydantic model (e.g. dict
    snapshots used in unit tests).
    """
    import typing as _typing

    from pydantic import BaseModel

    mapping: dict[str, str] = {}
    if not isinstance(state, BaseModel):
        return mapping
    for name, field_info in type(state).model_fields.items():
        ann = field_info.annotation
        if _typing.get_origin(ann) is list:
            args = _typing.get_args(ann)
            if args and hasattr(args[0], "__name__"):
                mapping[args[0].__name__] = name
    return mapping


def _collection_for(
    entity_type: str,
    collection_map: dict[str, str] | None = None,
) -> str:
    """Map entity TYPE (e.g. ``'Appointment'``) to collection name (``'appointments'``).

    When ``collection_map`` is provided (built from the state model via
    :func:`_build_collection_map`), irregular plurals resolve correctly.
    Otherwise, fall back to lowercase + ``'s'`` (which happens to work for
    most regular entities and for the test-dict snapshot shape).
    """
    if collection_map is not None and entity_type in collection_map:
        return collection_map[entity_type]
    lower = entity_type.lower()
    return lower if lower.endswith("s") else lower + "s"


def _predicate_holds(pred: dict, value: Any, scope: PredicateScope) -> bool:
    """Evaluate ``pred`` against ``value`` reusing ``scope`` for bindings."""
    scope.value = value
    return eval_predicate(pred, scope)


def _all_predicates_hold(
    props: dict[str, dict],
    fields: dict[str, Any],
    scope: PredicateScope,
) -> bool:
    """Return True iff every (field, predicate) pair in ``props`` holds against ``fields``."""
    for fname, pred in props.items():
        if not _predicate_holds(pred, fields.get(fname), scope):
            return False
    return True


def _build_scope(
    targets: dict,
    initial: Any,
    final: Any,
    bijection_var: Any = None,
    session_start: datetime | None = None,
) -> PredicateScope:
    """Construct a fresh ``PredicateScope`` for predicate evaluation."""
    return PredicateScope(
        value=None,
        target=targets,
        initial=initial,
        state=final,
        bijection_var=bijection_var,
        session_start=session_start,
    )


class _DotObj:
    """Dict-backed object exposing keys as attributes (for invariant filter exprs).

    The legacy ``webagentbench/evaluator.py`` filter convention binds ``a``
    to each candidate entity and lets authors write ``a.id in target.upcoming_ids``.
    We mirror that here so migrated tasks can reuse their existing filter
    expressions verbatim.
    """

    def __init__(self, d: dict[str, Any]) -> None:
        self.__dict__.update(d)


def _entity_dict_for_invariant(entry: "DiffEntry") -> dict[str, Any]:
    """Best-effort view of an entry as an entity dict for invariant-filter eval."""
    if isinstance(entry, Create):
        return entry.fields
    if isinstance(entry, Delete):
        return entry.last_fields
    # Update: reconstruct {id, <each changed field -> after value>}.
    return {
        "id": entry.entity_id,
        **{k: v[1] for k, v in entry.field_changes.items()},
    }


# ------------------------------------------------------------------
# ── Matcher (Task 5) ── Bijection helpers
# ------------------------------------------------------------------

def _eval_target_expr(expr_source: str, targets: dict) -> Any:
    """Evaluate a target-reference expression (e.g. ``target['due_ids']``).

    Uses the same restricted-eval pattern as ``{expr: ...}`` predicates —
    only the safe-builtins allowlist is exposed, and ``target`` is bound
    as a local. Source is author-controlled (task YAML).
    """
    globs = {"__builtins__": _SAFE_BUILTINS}
    return eval(expr_source, globs, {"target": targets})  # noqa: S307


def _max_bipartite_matching(
    edges: dict[int, set[int]],
    n_left: int,
    n_right: int,
) -> dict[int, int]:
    """Maximum bipartite matching via augmenting-path DFS.

    Returns ``{left_idx: right_idx}``. Left vertices are processed in order;
    right candidates are iterated in sorted order so tie-breaking is
    deterministic (spec §4.1).

    At task-level sizes (left ≤ 20, right ≤ 20), this is sub-millisecond;
    ~40 LOC vs Hopcroft-Karp's ~120, which is the D4 trade-off we picked.
    """
    match_l: dict[int, int] = {}
    match_r: dict[int, int] = {}

    def augment(u: int, visited: set[int]) -> bool:
        for v in sorted(edges.get(u, set())):
            if v in visited:
                continue
            visited.add(v)
            if v not in match_r or augment(match_r[v], visited):
                match_l[u] = v
                match_r[v] = u
                return True
        return False

    for u in range(n_left):
        augment(u, set())

    return match_l


# ------------------------------------------------------------------
# match_diff
# ------------------------------------------------------------------

def match_diff(
    agent_diff: list[DiffEntry],
    canonical: Any,  # CanonicalDiff
    targets: dict,
    initial: Any,
    final: Any,
    session_start: datetime | None = None,
) -> EvalReport:
    """Match an agent-produced diff against the authored canonical_diff.

    See ``docs/superpowers/specs/2026-04-16-correctness-diff-design.md`` §4.

    If ``canonical.oneof`` is set, each alternative block is evaluated and
    the highest-scoring report is returned.
    """
    if canonical.oneof:
        best: EvalReport | None = None
        for alt in canonical.oneof:
            report = _match_single_block(
                agent_diff, alt, targets, initial, final, session_start,
            )
            if best is None or report.score > best.score:
                best = report
        assert best is not None
        return best
    return _match_single_block(
        agent_diff, canonical, targets, initial, final, session_start,
    )


def _match_single_block(
    agent_diff: list[DiffEntry],
    block: Any,  # CanonicalDiffBlock
    targets: dict,
    initial: Any,
    final: Any,
    session_start: datetime | None,
) -> EvalReport:
    """Match ``agent_diff`` against a single canonical_diff alternative."""
    matched_ids: set[tuple[str, str]] = set()
    failures: list[Failure] = []
    checks: list[dict] = []
    negative_checks: list[dict] = []
    passed_weight = 0.0
    total_weight = 0.0
    # Map entity type → collection field name using the live state model so
    # irregular plurals (e.g. ClinicalMessage → messages) resolve correctly.
    collection_map = _build_collection_map(final)
    # Track excess candidates per bijection create[i] so named_invariants with
    # ref=create[i] can distinguish "under-saturation" (too few) from "excess"
    # (too many). The "did not schedule more than due" label is only about
    # excess; under-saturation is already reflected in the bijection check.
    bijection_excess: dict[int, bool] = {}
    # Frontend-facing graph data: one entry per bijection that ran matching.
    bijection_graphs: list[dict] = []

    # 1. Create entries (non-bijection only — Task 5 adds bijection).
    for i, entry in enumerate(block.create):
        total_weight += entry.weight
        if entry.bijection is not None:
            # Bijection case (Task 5): one-to-one match between target slots
            # and agent-diff Create entries via maximum bipartite matching.
            try:
                left = _eval_target_expr(entry.bijection.over, targets)
            except Exception as exc:
                checks.append({
                    "desc": entry.desc or f"Create required {entry.entity}(s) (target lookup failed)",
                    "passed": False,
                    "error": f"target expression failed: {exc}",
                })
                failures.append(Failure(
                    kind="missing_create",
                    description=f"bijection {entry.entity} target expression failed",
                    details={"entry_index": i, "error": str(exc)},
                ))
                continue

            n_left = len(left) if hasattr(left, "__len__") else 0

            if n_left == 0:
                # Empty target set for this seed — entry is not applicable.
                # Make it neutral: neither pool counts it, so score emerges
                # from the actually-applicable entries rather than being
                # inflated by vacuous satisfaction. Keep excess tracking so
                # named_invariants can still flag over-creation (agent
                # scheduled N>0 when 0 were needed).
                total_weight -= entry.weight
                collection_name = _collection_for(entry.entity, collection_map)
                excess_candidates = [
                    c for c in agent_diff
                    if isinstance(c, Create) and c.entity == collection_name
                    and (c.entity, c.entity_id) not in matched_ids
                ]
                bijection_excess[i] = len(excess_candidates) > 0
                base_desc = entry.desc or f"Create {entry.entity}(s) — 0 required"
                checks.append({
                    "desc": f"{base_desc} (not applicable for this seed)",
                    "passed": True,
                    "error": None,
                })
                continue

            # Candidates: unmatched Create entries of the right entity type.
            collection_name = _collection_for(entry.entity, collection_map)
            candidates = [
                c for c in agent_diff
                if isinstance(c, Create)
                and c.entity == collection_name
                and (c.entity, c.entity_id) not in matched_ids
            ]

            # Build bipartite graph edges: left = target slots, right = candidates.
            edges: dict[int, set[int]] = {li: set() for li in range(n_left)}
            for li, lv in enumerate(left):
                for cj, cand in enumerate(candidates):
                    local_scope = _build_scope(
                        targets, initial, final,
                        bijection_var=lv,
                        session_start=session_start,
                    )
                    if _all_predicates_hold(entry.properties, cand.fields, local_scope):
                        edges[li].add(cj)

            # Find maximum matching.
            matching = _max_bipartite_matching(edges, n_left, len(candidates))
            saturated = len(matching) == n_left
            # Excess = strictly more candidates than slots. Independent of
            # whether the match saturates; the "did not schedule too many"
            # claim is about over-creation, not under.
            bijection_excess[i] = len(candidates) > n_left

            base_desc = entry.desc or f"Create {n_left} required {entry.entity}(s)"
            # Record matched candidates regardless of saturation so the
            # unaccounted sweep doesn't double-flag partially-matched
            # candidates as collateral (Class 7 bug — matched_ids must
            # cover every candidate consumed by this bijection, not only
            # when the matching fully saturates).
            for _li, cj in matching.items():
                cand = candidates[cj]
                matched_ids.add((cand.entity, cand.entity_id))

            if saturated:
                passed_weight += entry.weight
                checks.append({
                    "desc": f"{base_desc} — {n_left} of {n_left} done",
                    "passed": True,
                    "error": None,
                })
            else:
                # Partial credit: N/M of the weight.
                fraction = len(matching) / n_left if n_left > 0 else 0.0
                passed_weight += entry.weight * fraction
                checks.append({
                    "desc": f"{base_desc} — {len(matching)} of {n_left} done",
                    "passed": False,
                    "error": f"matched {len(matching)} of {n_left}",
                })
                failures.append(Failure(
                    kind="missing_create",
                    description=(
                        f"bijection {entry.entity} unsaturated: "
                        f"matched {len(matching)} of {n_left}"
                    ),
                    details={
                        "entry_index": i,
                        "matched": len(matching),
                        "needed": n_left,
                    },
                ))

            # Emit graph data for the frontend bipartite viz.
            matched_cand_set = set(matching.values())
            graph_slots = [
                {"label": str(lv)[:40], "matched_candidate_index": matching.get(li)}
                for li, lv in enumerate(left)
            ]
            graph_candidates = []
            for cj, cand in enumerate(candidates):
                matched_slot: int | None = None
                for li, cidx in matching.items():
                    if cidx == cj:
                        matched_slot = li
                        break
                graph_candidates.append({
                    "label": _candidate_label(cand),
                    "id": cand.entity_id,
                    "matched_slot_index": matched_slot,
                    "is_excess": cj not in matched_cand_set,
                })
            bijection_graphs.append({
                "desc": base_desc,
                "entity": entry.entity,
                "saturated": saturated,
                "has_excess": bijection_excess[i],
                "slots": graph_slots,
                "candidates": graph_candidates,
                "edges_possible": sorted([[li, cj] for li, cjs in edges.items() for cj in cjs]),
            })
            continue

        # Non-bijection: find one unmatched Create candidate satisfying all predicates.
        passed = False
        collection_name = _collection_for(entry.entity, collection_map)
        for candidate in agent_diff:
            if not isinstance(candidate, Create):
                continue
            if candidate.entity != collection_name:
                continue
            if (candidate.entity, candidate.entity_id) in matched_ids:
                continue
            local_scope = _build_scope(
                targets, initial, final, session_start=session_start,
            )
            if _all_predicates_hold(entry.properties, candidate.fields, local_scope):
                matched_ids.add((candidate.entity, candidate.entity_id))
                passed = True
                break

        desc = entry.desc or f"Create a {entry.entity} with required properties"
        checks.append({
            "desc": desc,
            "passed": passed,
            "error": None if passed else "no candidate satisfied predicates",
        })
        if passed:
            passed_weight += entry.weight
        else:
            failures.append(Failure(
                kind="missing_create",
                description=desc,
                details={"entry_index": i},
            ))

    # 1.5 Update entries — mutation to an existing entity.
    # Each update has an optional `where` selector and `changes` predicates.
    # When a bijection is specified, we do a bipartite match between target
    # slots and Update candidates (same mechanics as create bijection).
    def _update_predicates_hold(entry_obj, candidate, bv=None):
        entity_dict = {"id": candidate.entity_id}
        for f, (_before, after) in candidate.field_changes.items():
            entity_dict[f] = after
        for fname, pred in entry_obj.where.items():
            local = _build_scope(targets, initial, final, bijection_var=bv, session_start=session_start)
            if not _predicate_holds(pred, entity_dict.get(fname), local):
                return False
        for fname, pred in entry_obj.changes.items():
            after_value = candidate.field_changes.get(fname, (None, entity_dict.get(fname)))[1]
            local = _build_scope(targets, initial, final, bijection_var=bv, session_start=session_start)
            if not _predicate_holds(pred, after_value, local):
                return False
        return True

    for i, entry in enumerate(block.update):
        total_weight += entry.weight
        collection_name = _collection_for(entry.entity, collection_map)
        base_desc = entry.desc or f"Update {entry.entity} matching selector"

        if entry.bijection is not None:
            try:
                left = _eval_target_expr(entry.bijection.over, targets)
            except Exception as exc:
                checks.append({
                    "desc": f"{base_desc} (target lookup failed)",
                    "passed": False, "error": f"target expression failed: {exc}",
                })
                failures.append(Failure(
                    kind="missing_update", description=base_desc,
                    details={"entry_index": i, "error": str(exc)},
                ))
                continue
            n_left = len(left) if hasattr(left, "__len__") else 0
            if n_left == 0:
                # Empty target set — entry not applicable for this seed.
                # Neutralize both pools so score reflects actually-applicable
                # entries (see Class 9 hazard).
                total_weight -= entry.weight
                checks.append({
                    "desc": f"{base_desc} (not applicable for this seed)",
                    "passed": True, "error": None,
                })
                continue
            candidates = [
                c for c in agent_diff
                if isinstance(c, Update) and c.entity == collection_name
                and (c.entity, c.entity_id) not in matched_ids
            ]
            edges: dict[int, set[int]] = {li: set() for li in range(n_left)}
            for li, lv in enumerate(left):
                for cj, cand in enumerate(candidates):
                    if _update_predicates_hold(entry, cand, bv=lv):
                        edges[li].add(cj)
            matching = _max_bipartite_matching(edges, n_left, len(candidates))
            saturated = len(matching) == n_left
            for _li, cj in matching.items():
                cand = candidates[cj]
                matched_ids.add((cand.entity, cand.entity_id))
            if saturated:
                passed_weight += entry.weight
                checks.append({
                    "desc": f"{base_desc} — {n_left} of {n_left} updated",
                    "passed": True, "error": None,
                })
            else:
                passed_weight += entry.weight * (len(matching) / n_left if n_left else 0.0)
                checks.append({
                    "desc": f"{base_desc} — {len(matching)} of {n_left} updated",
                    "passed": False,
                    "error": f"matched {len(matching)} of {n_left}",
                })
                failures.append(Failure(
                    kind="missing_update",
                    description=f"update bijection unsaturated: {len(matching)} of {n_left}",
                    details={"entry_index": i, "matched": len(matching), "needed": n_left},
                ))
            continue

        # Non-bijection update: match a single Update candidate.
        matched = False
        for candidate in agent_diff:
            if not isinstance(candidate, Update):
                continue
            if candidate.entity != collection_name:
                continue
            if (candidate.entity, candidate.entity_id) in matched_ids:
                continue
            if _update_predicates_hold(entry, candidate):
                matched_ids.add((candidate.entity, candidate.entity_id))
                matched = True
                break
        checks.append({
            "desc": base_desc,
            "passed": matched,
            "error": None if matched else "no Update entry matched both where and changes predicates",
        })
        if matched:
            passed_weight += entry.weight
        else:
            failures.append(Failure(
                kind="missing_update", description=base_desc,
                details={"entry_index": i},
            ))

    # 1.6 Delete entries.
    for i, entry in enumerate(block.delete):
        total_weight += entry.weight
        collection_name = _collection_for(entry.entity, collection_map)
        base_desc = entry.desc or f"Delete {entry.entity} matching selector"
        matched = False
        for candidate in agent_diff:
            if not isinstance(candidate, Delete):
                continue
            if candidate.entity != collection_name:
                continue
            if (candidate.entity, candidate.entity_id) in matched_ids:
                continue
            entity_dict = {"id": candidate.entity_id, **candidate.last_fields}
            where_ok = True
            for fname, pred in entry.where.items():
                scope = _build_scope(targets, initial, final, session_start=session_start)
                if not _predicate_holds(pred, entity_dict.get(fname), scope):
                    where_ok = False
                    break
            if where_ok:
                matched_ids.add((candidate.entity, candidate.entity_id))
                matched = True
                break
        checks.append({
            "desc": base_desc,
            "passed": matched,
            "error": None if matched else "no Delete entry matched the where selector",
        })
        if matched:
            passed_weight += entry.weight
        else:
            failures.append(Failure(
                kind="missing_delete", description=base_desc,
                details={"entry_index": i},
            ))

    # 2. Invariant enforcement. Invariants are PENALTY-ONLY — they do not
    # contribute to total_weight / passed_weight. Doing nothing must not
    # earn positive score just because nothing got mutated; only the
    # positive diff (create/update/delete) drives the numerator.
    for i, inv in enumerate(block.invariant):
        collection = inv.collection.removeprefix("state.")
        violated = False
        for entry in agent_diff:
            if entry.entity != collection:
                continue
            if (entry.entity, entry.entity_id) in matched_ids:
                continue
            if inv.filter:
                filter_globs = {"__builtins__": _SAFE_BUILTINS}
                entity_dict = _entity_dict_for_invariant(entry)
                filter_locals = {"a": _DotObj(entity_dict), "target": targets}
                try:
                    # Restricted eval — author-controlled source, safe-builtins only.
                    if not eval(inv.filter, filter_globs, filter_locals):  # noqa: S307
                        continue
                except Exception:
                    continue
            violated = True
            break

        desc = f"Preserve {inv.collection}"
        negative_checks.append({
            "desc": desc,
            "passed": not violated,
            "penalty": _SEVERITY_PENALTY["medium"],
        })
        if violated:
            failures.append(Failure(
                kind="invariant",
                description=desc,
                details={"entry_index": i},
            ))

    # 2.5 Constraints — state-level aggregates (spec §3.6). Penalty-only
    # on the negative side *unless* the block has no positive entries, in
    # which case constraints are promoted to the positive pool (Class 10
    # fix). Track per-constraint pass count so the promotion path can
    # compute score_raw = n_passed / n_total.
    constraints_total = 0
    constraints_passed = 0
    for i, c in enumerate(block.constraints):
        # Merge scope vars into GLOBALS (not locals) so list/gen
        # comprehensions and lambdas can see `state`, `initial`, `target`.
        # Same rationale as the {expr: ...} predicate path (hazard Class 8):
        # comprehensions run in a nested function scope that only reads
        # from globals — scope-as-locals makes them invisible inside
        # e.g. `max(..., key=lambda cid: initial.get_claim(cid)...)`.
        globs = {
            "__builtins__": _SAFE_BUILTINS,
            "state": final,
            "initial": initial,
            "target": targets,
        }
        try:
            # Restricted eval -- author-controlled source, safe-builtins only.
            ok = bool(eval(c.expr, globs, {}))  # noqa: S307
        except Exception:
            ok = False
        negative_checks.append({
            "desc": c.desc,
            "passed": ok,
            "penalty": _SEVERITY_PENALTY.get(c.severity, _SEVERITY_PENALTY["medium"]),
        })
        constraints_total += 1
        if ok:
            constraints_passed += 1
        if not ok:
            failures.append(Failure(
                kind="constraint",
                description=c.desc,
                details={"entry_index": i, "severity": c.severity},
            ))

    # 3. Unaccounted sweep.
    # Any agent_diff entry that (a) was not matched to a positive target and
    # (b) is not fully covered by an invariant is collateral. A FILTERED
    # invariant only protects entries that match its filter — entries in the
    # same collection but outside the filter still need to be accounted for
    # here (e.g. newly-created appointments when the invariant guards only
    # existing upcoming appointments).
    positive_cols = {
        _collection_for(e.entity, collection_map)
        for e in list(block.create) + list(block.update) + list(block.delete)
    }
    # Only UNFILTERED invariants fully cover their collection.
    invariant_cols_full = {
        inv.collection.removeprefix("state.")
        for inv in block.invariant
        if not inv.filter
    }
    for entry in agent_diff:
        if (entry.entity, entry.entity_id) in matched_ids:
            continue
        if entry.entity in invariant_cols_full:
            continue  # whole collection invariant already handled this entry
        # Also surface collateral failures as a visible negative_check so
        # users don't see score=1.0 but passed=False with no explanation.
        # Without a visible entry the discrepancy between the positive-
        # side score and the failures-based passed boolean looks like a bug
        # to anyone reading the eval panel.
        if entry.entity in positive_cols:
            desc = f"Unaccounted {type(entry).__name__.lower()} in {entry.entity} (id={entry.entity_id})"
            failures.append(Failure(
                kind="unaccounted", description=desc,
                details={"entity_id": entry.entity_id},
            ))
            negative_checks.append({
                "desc": desc, "passed": False,
                "penalty": _SEVERITY_PENALTY["medium"],
            })
        else:
            desc = f"Unexpected {type(entry).__name__.lower()} on {entry.entity} (id={entry.entity_id}) — collection not mentioned in diff"
            failures.append(Failure(
                kind="unaccounted", description=desc,
                details={"entity_id": entry.entity_id},
            ))
            negative_checks.append({
                "desc": desc, "passed": False,
                "penalty": _SEVERITY_PENALTY["high"],
            })

    # 3.5 Named-invariant attribution (spec §5)
    #
    # For each named_invariant, resolve its ref to a diff entry and rewrite
    # the corresponding entry's descriptor in checks/negative_checks with the
    # human-readable label and severity. This is presentation-only -- the
    # underlying pass/fail is determined by the diff rules above.
    for ni in block.named_invariants:
        m = re.match(r"(invariant|create|update|delete)\[(\d+)\]", ni.ref)
        if not m:
            continue
        kind, idx = m.group(1), int(m.group(2))
        severity = _SEVERITY_PENALTY.get(ni.severity, _SEVERITY_PENALTY["medium"])
        if kind == "invariant" and 0 <= idx < len(block.invariant):
            # Rewrite the matching negative_check
            target_collection = block.invariant[idx].collection
            for nc in negative_checks:
                if target_collection in nc["desc"] and nc["desc"].startswith("Preserve "):
                    nc["desc"] = ni.name
                    nc["penalty"] = severity
                    break
        elif kind == "create" and 0 <= idx < len(block.create):
            # `ref: create[N]` labels the *cardinality-upper-bound* claim
            # ("did not schedule more than due"). This is PASS when the
            # agent didn't produce excess candidates; it's FAIL only when
            # there are strictly more candidates than slots. Under-
            # saturation (too few) is reflected in the bijection check
            # itself, not here.
            has_excess = bijection_excess.get(idx, False)
            negative_checks.append({
                "desc": ni.name,
                "passed": not has_excess,
                "penalty": severity,
            })
        elif kind == "update" and 0 <= idx < len(block.update):
            # `ref: update[N]` relabels the positive check for an update
            # entry with the author-provided human name (Class 14). The
            # label is presentation-only — score and passed already come
            # from the underlying update match via passed_weight.
            entry = block.update[idx]
            default_desc = entry.desc or f"Update {entry.entity} matching selector"
            for check in checks:
                # Match either the exact desc or the "— N of N updated"
                # variant produced by bijection updates.
                if check["desc"] == default_desc or check["desc"].startswith(f"{default_desc} "):
                    check["desc"] = ni.name
                    break
        elif kind == "delete" and 0 <= idx < len(block.delete):
            # `ref: delete[N]` — same idea for delete entries (Class 14).
            entry = block.delete[idx]
            default_desc = entry.desc or f"Delete {entry.entity} matching selector"
            for check in checks:
                if check["desc"] == default_desc:
                    check["desc"] = ni.name
                    break

    # 4. Penalty-adjusted score
    #
    # Normal path: positive pool = passed_weight / total_weight.
    # Constraint-only path (Class 10 fix): when a block has no positive
    # entries but has constraints, promote constraints to the positive
    # pool so the score reflects constraint satisfaction instead of
    # defaulting to 1.0 and clipping downward by penalties. Constraints
    # stay in `negative_checks` for presentation, but their pass count
    # becomes the numerator. Invariants remain pure penalties.
    penalty = sum(
        nc["penalty"] for nc in negative_checks if not nc["passed"]
    )
    if total_weight > 0:
        score_raw = passed_weight / total_weight
    elif constraints_total > 0:
        score_raw = constraints_passed / constraints_total
        # Don't double-count: in the promoted path, failed constraints
        # already reduce the numerator, so remove their penalty from the
        # separate deduction to avoid two-for-one.
        penalty = sum(
            nc["penalty"] for nc in negative_checks
            if not nc["passed"] and nc["desc"] not in {c.desc for c in block.constraints}
        )
    else:
        score_raw = 1.0
    score = max(0.0, min(1.0, score_raw - penalty))
    passed = len(failures) == 0

    return EvalReport(
        passed=passed,
        score=score,
        checks=checks,
        negative_checks=negative_checks,
        failures=failures,
        bijection_graphs=bijection_graphs,
    )
