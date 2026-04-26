"""Canonical-diff matcher.

Matches agent-produced state diffs against canonical_diff YAML blocks:
create, update, delete requirements (positive checks), invariant and
constraint enforcement (negative checks), bijection matching, collateral
sweep, and named_invariant relabeling.

All expression evaluation is delegated to safe_eval (see safe_eval.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping

from .access import EntityView
from .diff import Create, Delete, DiffEntry, Update, collection_for, collections_of, index_by_id
from .predicates import PredicateScope, all_field_predicates_hold, eval_predicate
from .safe_eval import SafeEvalError, safe_eval
from .types import Failure, get_field, get_list


class Severity(str, Enum):
    """String-valued enum; mirrors ``StrEnum`` (Python 3.11+) while staying
    compatible with Python 3.10 (the project's declared floor).
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_PENALTY: dict[str, float] = {
    Severity.CRITICAL: 0.30,
    Severity.HIGH: 0.20,
    Severity.MEDIUM: 0.15,
    Severity.LOW: 0.10,
}


def _penalty_for(severity: str) -> float:
    return SEVERITY_PENALTY.get(severity, SEVERITY_PENALTY[Severity.MEDIUM])


@dataclass
class MatchReport:
    passed: bool
    score: float
    checks: list[dict[str, Any]] = field(default_factory=list)
    negative_checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    bijection_graphs: list[dict[str, Any]] = field(default_factory=list)
    constraints_total: int = 0
    constraints_passed: int = 0
    critical_constraints_total: int = 0
    critical_constraints_passed: int = 0


@dataclass
class MatchContext:
    """Per-block evaluation state shared across the create/update/delete matchers."""
    agent_diff: list[DiffEntry]
    targets: Mapping[str, Any]
    initial: Any
    final: Any
    session_start: datetime | None
    matched: set[tuple[str, str]] = field(default_factory=set)
    # Entries that targeted the right entity+collection but failed property
    # predicates (singleton) or weren't paired (bijection). The unaccounted
    # collateral sweep treats these like ``matched`` (skip flagging) so the
    # agent isn't double-charged: once for the missing positive, again for
    # the "near-miss" candidate sitting in the diff.
    near_misses: set[tuple[str, str]] = field(default_factory=set)
    checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    graphs: list[dict[str, Any]] = field(default_factory=list)
    bijection_excess: dict[int, bool] = field(default_factory=dict)


def _scope(
    targets: Mapping[str, Any], initial: Any, final: Any, *,
    value: Any = None, bijection_var: Any = None, session_start: datetime | None = None,
) -> PredicateScope:
    return PredicateScope(value, targets, initial, final, bijection_var, session_start)


def _target_expr(expr: str, targets: Mapping[str, Any], initial: Any, final: Any,
                  session_start: datetime | None = None) -> Any:
    return safe_eval(expr, {"target": targets, "initial": initial, "state": final, "session_start": session_start})


def _bipartite_matching(edges: Mapping[int, set[int]], n_left: int) -> dict[int, int]:
    match_l: dict[int, int] = {}
    match_r: dict[int, int] = {}

    def augment(left: int, seen: set[int]) -> bool:
        for right in sorted(edges.get(left, set())):
            if right in seen:
                continue
            seen.add(right)
            if right not in match_r or augment(match_r[right], seen):
                match_l[left] = right
                match_r[right] = left
                return True
        return False

    for left in range(n_left):
        augment(left, set())
    return match_l


def _candidate_label(entry: DiffEntry) -> str:
    fields: Mapping[str, Any]
    if isinstance(entry, Create):
        fields = entry.fields
    elif isinstance(entry, Delete):
        fields = entry.last_fields
    else:
        fields = {k: after for k, (_before, after) in entry.field_changes.items()}
    for key in ("name", "title", "subject", "provider_id", "reason", "type"):
        value = fields.get(key)
        if value:
            return str(value)[:40]
    return str(getattr(entry, "entity_id", "?"))


def _entry_dict_for_filter(entry: DiffEntry) -> dict[str, Any]:
    if isinstance(entry, Create):
        return entry.fields
    if isinstance(entry, Delete):
        return entry.last_fields
    return {"id": entry.entity_id, **{k: after for k, (_before, after) in entry.field_changes.items()}}


def _filter_matches(filter_expr: str | None, entry: DiffEntry, targets: Mapping[str, Any]) -> bool:
    if not filter_expr:
        return True
    try:
        return bool(safe_eval(filter_expr, {"a": EntityView(_entry_dict_for_filter(entry)), "target": targets}))
    except SafeEvalError:
        return False


def _updated_entity_dicts(update: Update, initial: Any, final: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    before = {"id": update.entity_id}
    before.update({f: pair[0] for f, pair in update.field_changes.items()})
    after = {"id": update.entity_id}
    after.update({f: pair[1] for f, pair in update.field_changes.items()})
    initial_idx = index_by_id(collections_of(initial).get(update.entity, []))
    final_idx = index_by_id(collections_of(final).get(update.entity, []))
    before = {**initial_idx.get(update.entity_id, {}), **before}
    after = {**final_idx.get(update.entity_id, {}), **after}
    return before, after


def _update_holds(entry: Any, candidate: Update, targets: Mapping[str, Any],
                  initial: Any, final: Any, *, v: Any = None, session_start: datetime | None = None) -> bool:
    before, after = _updated_entity_dicts(candidate, initial, final)
    for name, pred in (get_field(entry, "where", {}) or {}).items():
        if not eval_predicate(pred, _scope(targets, initial, final, value=before.get(name), bijection_var=v, session_start=session_start)):
            return False
    for name, pred in (get_field(entry, "changes", {}) or {}).items():
        if not eval_predicate(pred, _scope(targets, initial, final, value=after.get(name), bijection_var=v, session_start=session_start)):
            return False
    return True


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def match_diff(
    agent_diff: list[DiffEntry],
    canonical: Any,
    targets: Mapping[str, Any],
    initial: Any,
    final: Any,
    session_start: datetime | None = None,
) -> MatchReport:
    oneof = get_list(canonical, "oneof")
    if oneof:
        reports = [_match_block(agent_diff, alt, targets, initial, final, session_start) for alt in oneof]
        applicable = [
            r for r in reports
            if r.critical_constraints_total == 0
            or r.critical_constraints_passed == r.critical_constraints_total
        ]
        return max(applicable or reports, key=_oneof_key)
    return _match_block(agent_diff, canonical, targets, initial, final, session_start)


def _oneof_key(report: MatchReport) -> tuple[float, int, float, float, int, int]:
    constraint_ratio = report.constraints_passed / report.constraints_total if report.constraints_total else 1.0
    critical_ratio = report.critical_constraints_passed / report.critical_constraints_total if report.critical_constraints_total else 1.0
    failed_checks = sum(1 for c in report.checks if not c.get("passed"))
    failed_negatives = sum(1 for c in report.negative_checks if not c.get("passed"))
    return (report.score, int(report.passed), critical_ratio, constraint_ratio, -len(report.failures), -(failed_checks + failed_negatives))


# ---------------------------------------------------------------------------
# Block matcher
# ---------------------------------------------------------------------------

def _match_block(
    agent_diff: list[DiffEntry], block: Any,
    targets: Mapping[str, Any], initial: Any, final: Any,
    session_start: datetime | None,
) -> MatchReport:
    ctx = MatchContext(agent_diff, targets, initial, final, session_start)
    negative_checks: list[dict[str, Any]] = []
    passed_weight = 0.0
    total_weight = 0.0

    for kind in ("create", "update", "delete"):
        for idx, entry in enumerate(get_list(block, kind)):
            w, tw = _match_entry(kind, idx, entry, ctx)
            passed_weight += w
            total_weight += tw

    # Invariants
    for idx, inv in enumerate(get_list(block, "invariant")):
        collection = str(get_field(inv, "collection", "")).removeprefix("state.")
        violated = any(
            entry.entity == collection
            and (entry.entity, entry.entity_id) not in ctx.matched
            and _filter_matches(get_field(inv, "filter"), entry, targets)
            for entry in agent_diff
        )
        desc = f"Preserve {get_field(inv, 'collection')}"
        negative_checks.append({
            "desc": desc, "passed": not violated,
            "penalty": SEVERITY_PENALTY[Severity.MEDIUM], "_inv_index": idx,
        })
        if violated:
            ctx.failures.append(Failure("invariant", desc, {"entry_index": idx}))

    # Constraints
    constraints_total = constraints_passed = critical_total = critical_passed = 0
    constraint_descs: set[str] = set()
    for idx, constraint in enumerate(get_list(block, "constraints")):
        desc = str(get_field(constraint, "desc", f"Constraint {idx}"))
        expr_str = str(get_field(constraint, "expr", "False"))
        severity = str(get_field(constraint, "severity", Severity.MEDIUM))
        try:
            ok = bool(safe_eval(expr_str, {"state": final, "initial": initial, "target": targets, "session_start": session_start}))
        except SafeEvalError:
            ok = False
        negative_checks.append({
            "desc": desc, "passed": ok, "penalty": _penalty_for(severity),
            "_kind": "constraint",
        })
        constraint_descs.add(desc)
        constraints_total += 1
        constraints_passed += int(ok)
        if severity == Severity.CRITICAL:
            critical_total += 1
            critical_passed += int(ok)
        if not ok:
            ctx.failures.append(Failure("constraint", desc, {"entry_index": idx, "severity": severity}))

    # Collateral sweep
    positive_cols = {
        collection_for(get_field(e, "entity"), final, get_field(e, "collection"))
        for e in [*get_list(block, "create"), *get_list(block, "update"), *get_list(block, "delete")]
    }
    constraint_only = not positive_cols and bool(get_list(block, "constraints"))
    full_invariant_cols: set[str] = set()
    filtered_by_col: dict[str, list[Any]] = {}
    comprehensive_cols: set[str] = set()
    for inv in get_list(block, "invariant"):
        col = str(get_field(inv, "collection", "")).removeprefix("state.")
        if get_field(inv, "filter"):
            filtered_by_col.setdefault(col, []).append(inv)
            if bool(get_field(inv, "comprehensive", False)):
                comprehensive_cols.add(col)
        else:
            full_invariant_cols.add(col)

    if not constraint_only:
        for entry in agent_diff:
            if (entry.entity, entry.entity_id) in ctx.matched:
                continue
            # Near-misses (right entity+collection, failed predicates) are
            # already accounted for by the missing-positive failure recorded
            # in _match_entry — skip the second penalty here.
            if (entry.entity, entry.entity_id) in ctx.near_misses:
                continue
            if entry.entity in full_invariant_cols:
                continue
            filtered = filtered_by_col.get(entry.entity, [])
            if any(_filter_matches(get_field(inv, "filter"), entry, targets) for inv in filtered):
                continue
            if entry.entity in comprehensive_cols:
                continue
            if entry.entity in positive_cols:
                desc = f"Unaccounted {type(entry).__name__.lower()} in {entry.entity} (id={entry.entity_id})"
                penalty = SEVERITY_PENALTY[Severity.MEDIUM]
            else:
                desc = f"Unexpected {type(entry).__name__.lower()} on {entry.entity} (id={entry.entity_id}) — collection not mentioned in diff"
                penalty = SEVERITY_PENALTY[Severity.HIGH]
            ctx.failures.append(Failure("unaccounted", desc, {"entity_id": entry.entity_id}))
            negative_checks.append({"desc": desc, "passed": False, "penalty": penalty})

    # Named invariants
    _apply_named_invariants(block, ctx.checks, negative_checks, ctx.bijection_excess)

    # Score
    penalty_total = sum(float(nc.get("penalty", 0.0)) for nc in negative_checks if not nc.get("passed"))
    if total_weight > 0:
        raw_score = passed_weight / total_weight
    elif constraints_total:
        raw_score = constraints_passed / constraints_total
        penalty_total = sum(
            float(nc.get("penalty", 0.0))
            for nc in negative_checks
            if not nc.get("passed") and nc.get("desc") not in constraint_descs
        )
    else:
        raw_score = 1.0
    score = max(0.0, min(1.0, raw_score - penalty_total))

    return MatchReport(
        passed=not ctx.failures,
        score=score,
        checks=ctx.checks,
        negative_checks=negative_checks,
        failures=ctx.failures,
        bijection_graphs=ctx.graphs,
        constraints_total=constraints_total,
        constraints_passed=constraints_passed,
        critical_constraints_total=critical_total,
        critical_constraints_passed=critical_passed,
    )


# ---------------------------------------------------------------------------
# Per-entry matchers (return passed_weight, total_weight)
# ---------------------------------------------------------------------------

_DEFAULT_DESC: dict[str, str] = {
    "create": "Create a {entity} with required properties",
    "update": "Update {entity} matching selector",
    "delete": "Delete {entity} matching selector",
}

_SINGLETON_ERROR: dict[str, str] = {
    "create": "no candidate satisfied predicates",
    "update": "no Update entry matched both where and changes predicates",
    "delete": "no Delete entry matched the where selector",
}

_CHECK_SUFFIX: dict[str, str] = {
    "create": "done",
    "update": "updated",
    "delete": "done",
}

_DIFF_CLS: dict[str, type[DiffEntry]] = {
    "create": Create,
    "update": Update,
    "delete": Delete,
}


def _build_predicate(kind: str, entry: Any, ctx: MatchContext) -> Callable[[DiffEntry, Any], bool]:
    """Return a kind-specific `(candidate, slot_value) -> bool` predicate."""
    if kind == "create":
        properties = get_field(entry, "properties", {}) or {}
        def _check(candidate: DiffEntry, slot: Any) -> bool:
            return all_field_predicates_hold(
                properties, candidate.fields,  # type: ignore[attr-defined]
                _scope(ctx.targets, ctx.initial, ctx.final, bijection_var=slot, session_start=ctx.session_start),
            )
        return _check
    if kind == "update":
        def _check(candidate: DiffEntry, slot: Any) -> bool:
            return _update_holds(entry, candidate, ctx.targets, ctx.initial, ctx.final,  # type: ignore[arg-type]
                                 v=slot, session_start=ctx.session_start)
        return _check
    where = get_field(entry, "where", {}) or {}
    def _check(candidate: DiffEntry, slot: Any) -> bool:
        fields = {"id": candidate.entity_id, **candidate.last_fields}  # type: ignore[attr-defined]
        return all_field_predicates_hold(
            where, fields,
            _scope(ctx.targets, ctx.initial, ctx.final, bijection_var=slot, session_start=ctx.session_start),
        )
    return _check


def _match_entry(
    kind: str, idx: int, entry: Any, ctx: MatchContext,
) -> tuple[float, float]:
    weight = float(get_field(entry, "weight", 1.0))
    entity = get_field(entry, "entity")
    desc = get_field(entry, "desc") or _DEFAULT_DESC[kind].format(entity=entity)
    collection = collection_for(entity, ctx.final, get_field(entry, "collection"))
    bijection = get_field(entry, "bijection")
    failure_kind = f"missing_{kind}"
    diff_cls = _DIFF_CLS[kind]
    predicate = _build_predicate(kind, entry, ctx)

    candidates = [
        c for c in ctx.agent_diff
        if isinstance(c, diff_cls) and c.entity == collection and (c.entity, c.entity_id) not in ctx.matched
    ]

    if bijection is not None:
        try:
            slots = list(_target_expr(
                str(get_field(bijection, "over")), ctx.targets, ctx.initial, ctx.final,
                session_start=ctx.session_start,
            ))
        except Exception as exc:
            ctx.checks.append({"desc": desc, "passed": False, "error": f"target expression failed: {exc}"})
            ctx.failures.append(Failure(failure_kind, desc, {"entry_index": idx, "error": str(exc)}))
            return 0.0, weight

        if not slots:
            if kind == "create":
                ctx.bijection_excess[idx] = bool(candidates)
            ctx.checks.append({"desc": f"{desc} (not applicable for this seed)", "passed": True, "error": None})
            return 0.0, 0.0

        edges: dict[int, set[int]] = {i: set() for i in range(len(slots))}
        for left_i, slot in enumerate(slots):
            for right_i, candidate in enumerate(candidates):
                if predicate(candidate, slot):
                    edges[left_i].add(right_i)

        pairing = _bipartite_matching(edges, len(slots))
        for right_i in pairing.values():
            c = candidates[right_i]
            ctx.matched.add((c.entity, c.entity_id))

        # Bijection near-misses: when the bijection did NOT saturate (some
        # slots unmet), unpaired candidates with no edges to any slot are
        # treated as near-miss attempts — the missing-positive check already
        # records the gap, so the unaccounted sweep should not pile on a
        # second penalty. When the bijection IS saturated, surplus candidates
        # remain visible to the unaccounted sweep (legitimate over-creation).
        saturated = len(pairing) == len(slots)
        if not saturated:
            paired_right = set(pairing.values())
            edged_right = {r for rs in edges.values() for r in rs}
            for right_i, c in enumerate(candidates):
                if right_i in paired_right:
                    continue
                if right_i in edged_right:
                    # Had edges but lost to bipartite — count as legitimate
                    # surplus, leave for the unaccounted sweep.
                    continue
                ctx.near_misses.add((c.entity, c.entity_id))

        fraction = len(pairing) / len(slots)
        saturated = len(pairing) == len(slots)
        ctx.checks.append({
            "desc": f"{desc} — {len(pairing)} of {len(slots)} {_CHECK_SUFFIX[kind]}",
            "passed": saturated,
            "error": None if saturated else f"matched {len(pairing)} of {len(slots)}",
        })
        if not saturated:
            ctx.failures.append(Failure(
                failure_kind, desc,
                {"entry_index": idx, "matched": len(pairing), "needed": len(slots)},
            ))

        if kind == "create":
            eligible = {right_i for rights in edges.values() for right_i in rights}
            ctx.bijection_excess[idx] = len(eligible) > len(slots)
            ctx.graphs.append({
                "desc": desc, "entity": entity, "saturated": saturated,
                "has_excess": ctx.bijection_excess[idx],
                "slots": [
                    {"label": str(slot)[:40], "matched_candidate_index": pairing.get(i)}
                    for i, slot in enumerate(slots)
                ],
                "candidates": [
                    {"label": _candidate_label(c), "id": c.entity_id,
                     "matched_slot_index": next((l for l, r in pairing.items() if r == i), None),
                     "is_excess": i not in set(pairing.values())}
                    for i, c in enumerate(candidates)
                ],
                "edges_possible": sorted([[l, r] for l, rs in edges.items() for r in rs]),
            })
        return weight * fraction, weight

    found = next((c for c in candidates if predicate(c, None)), None)
    if found:
        ctx.matched.add((found.entity, found.entity_id))
    else:
        ctx.failures.append(Failure(failure_kind, desc, {"entry_index": idx}))
        # Singleton near-miss: the agent produced an entry on the right
        # entity+collection but its property predicates failed. Mark the
        # most-likely candidate (first available) as a near-miss so the
        # unaccounted collateral sweep doesn't pile a second penalty on top
        # of the missing-positive failure already recorded above.
        if candidates:
            cand = candidates[0]
            ctx.near_misses.add((cand.entity, cand.entity_id))
    ctx.checks.append({
        "desc": desc, "passed": found is not None,
        "error": None if found else _SINGLETON_ERROR[kind],
    })
    return (weight if found else 0.0), weight


# ---------------------------------------------------------------------------
# Named invariants — structural index resolution
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r"^(invariant|create|update|delete)\[(\d+)\]$")


def _apply_named_invariants(
    block: Any,
    checks: list[dict[str, Any]],
    negative_checks: list[dict[str, Any]],
    bijection_excess: Mapping[int, bool],
) -> None:
    for item in get_list(block, "named_invariants"):
        ref = str(get_field(item, "ref", ""))
        name = str(get_field(item, "name", ""))
        severity = str(get_field(item, "severity", "medium"))
        penalty = SEVERITY_PENALTY.get(severity, SEVERITY_PENALTY["medium"])
        match = _REF_PATTERN.match(ref)
        if not match or not name:
            continue
        kind = match.group(1)
        idx = int(match.group(2))

        if kind == "invariant":
            for nc in negative_checks:
                if nc.get("_inv_index") == idx:
                    nc["desc"] = name
                    nc["penalty"] = penalty
                    break
        elif kind == "create":
            negative_checks.append({"desc": name, "passed": not bijection_excess.get(idx, False), "penalty": penalty})
        elif kind in {"update", "delete"}:
            entries = get_list(block, kind)
            if idx < len(entries):
                entry_desc = get_field(entries[idx], "desc") or f"{kind.capitalize()} {get_field(entries[idx], 'entity')} matching selector"
                for check in checks:
                    if str(check.get("desc", "")).startswith(entry_desc):
                        check["desc"] = name
                        break

    for nc in negative_checks:
        nc.pop("_inv_index", None)
