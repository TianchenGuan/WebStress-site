"""Audit battery for the canonical_diff matcher.

Each test probes a specific hypothesis about how the matcher could
produce a wrong score. Tests are designed to fail noisily when they
find a real bug and document the expected behavior when they pass.

Structure:
  Part A — consistency sweeps parametrized over every migrated task.
  Part B — targeted unit tests on synthetic canonical_diffs.

If Part A fires, the bug reproduces on real task data (high signal,
hard to dismiss). If Part B fires, it isolates a specific matcher
branch with a minimal fixture (easy to debug).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import (
    EvalReport,
    compute_diff,
    match_diff,
)
from webagentbench.tasks._registry import load_all_tasks
from webagentbench.tasks.canonical_diff import (
    Bijection,
    CanonicalDiff,
    Constraint,
    CreateEntry,
    InvariantEntry,
    NamedInvariant,
    UpdateEntry,
)


# ── Fixture helpers ─────────────────────────────────────────────────

def _migrated_task_ids() -> list[str]:
    return sorted(
        tid for tid, t in load_all_tasks().items() if t.canonical_diff is not None
    )


def _setup(task_id: str):
    sm = SessionManager()
    task = load_all_tasks()[task_id]
    sid, targets, _ = sm.create_session(env_id=task.env_id, task_id=task_id, seed=42)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state, task


def _match_do_nothing(task_id: str) -> EvalReport:
    _, _, targets, initial, state, task = _setup(task_id)
    agent_diff = compute_diff(initial, state)  # empty — nothing changed
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )


# ══════════════════════════════════════════════════════════════════════
# Part A — Consistency sweeps across every migrated task
# ══════════════════════════════════════════════════════════════════════

def _has_positive_entries(task) -> bool:
    cd = task.canonical_diff
    if cd.oneof:
        return any(
            len(b.create) + len(b.update) + len(b.delete) > 0
            for b in cd.oneof
        )
    return len(cd.create) + len(cd.update) + len(cd.delete) > 0


@pytest.mark.parametrize("task_id", _migrated_task_ids())
def test_do_nothing_score_is_boundary(task_id: str) -> None:
    """Do-nothing trajectory must score exactly 0.0 or exactly 1.0
    (for tasks that have positive entries).

    Any score strictly between is the Class 9 signature — vacuously-satisfied
    bijections contributing full credit, or a vacuous invariant not firing.

    Tasks with NO positive entries (constraint-only canonical_diffs) are
    intentionally excluded here and surfaced separately by
    ``test_no_constraint_only_canonical_diffs`` as a Class 10 design smell.
    """
    task = load_all_tasks()[task_id]
    if not _has_positive_entries(task):
        pytest.skip(f"{task_id} has no positive entries; see Class 10 test")

    report = _match_do_nothing(task_id)
    in_between = 0.0001 < report.score < 0.9999
    assert not in_between, (
        f"{task_id}: do-nothing score={report.score:.4f} is in forbidden (0,1) range. "
        f"This is the Class 9 signature — likely a vacuous bijection or other "
        f"seed-dependent entry contributing phantom credit.\n"
        f"checks={report.checks}\n"
        f"negative_checks={[nc for nc in report.negative_checks if not nc['passed']]}"
    )


@pytest.mark.xfail(
    strict=False,
    reason="Class 10 not yet fixed — 3 constraint-only canonical_diffs "
           "documented here will keep this xfailing until the matcher "
           "promotes constraints to the positive pool when no create/update/"
           "delete exists.",
)
def test_no_constraint_only_canonical_diffs() -> None:
    """Class 10: a canonical_diff with zero positive entries (no create,
    update, or delete) is a design smell. Score falls back to 1.0 when
    total_weight == 0 and is then clipped downward by penalty deductions,
    so do-nothing scores whatever ``1.0 - Σ penalties_that_fire_on_initial``
    happens to be. That's an inverted scoring model where the matcher
    measures constraint violations from an assumed-correct baseline
    instead of agent accomplishments.

    This test enumerates offenders rather than asserting clean. The
    proper fix is matcher-side: when a block has no positive entries,
    treat satisfied constraints as the positive pool's numerator.
    When that lands, remove the xfail marker; this test will xpass and
    make the fix visible in CI.
    """
    offenders: list[str] = []
    for task_id, task in load_all_tasks().items():
        if task.canonical_diff is None:
            continue
        if not _has_positive_entries(task):
            offenders.append(task_id)

    assert not offenders, (
        f"Constraint-only canonical_diffs (Class 10): {len(offenders)} tasks. "
        f"These rely on 1.0-fallback minus penalties, producing arbitrary "
        f"do-nothing scores. Offenders: {offenders}"
    )


@pytest.mark.parametrize("task_id", _migrated_task_ids())
def test_score_and_passed_are_consistent(task_id: str) -> None:
    """Internal matcher invariant: passed ⟺ (score == 1.0 AND no failures).

    Divergence between the score and the passed flag means the user sees
    either (score=1.0, passed=False) or (score<1.0, passed=True), both
    of which look like matcher bugs from the outside.
    """
    report = _match_do_nothing(task_id)
    no_failures = len(report.failures) == 0
    full_score = report.score >= 0.9999

    # passed is defined as len(failures) == 0, so these must agree:
    assert report.passed == no_failures, (
        f"{task_id}: passed={report.passed} disagrees with "
        f"failures_empty={no_failures} — matcher internal invariant violated"
    )

    # A full score with failures is a red flag (user sees 1.0 but passed=False).
    if full_score and not no_failures:
        pytest.fail(
            f"{task_id}: score={report.score} but failures={report.failures!r}. "
            "This is the (score=1.0, passed=False) divergence — UX bug."
        )


@pytest.mark.parametrize("task_id", _migrated_task_ids())
def test_matcher_is_idempotent(task_id: str) -> None:
    """Calling match_diff twice with identical inputs yields identical reports.

    If idempotence breaks, the matcher has hidden mutable state (e.g.
    cached result that mutates on lookup, in-place agent_diff mutation).
    That's a correctness and a thread-safety hazard.
    """
    _, _, targets, initial, state, task = _setup(task_id)
    agent_diff = compute_diff(initial, state)

    report_a = match_diff(
        agent_diff, task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    report_b = match_diff(
        agent_diff, task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )

    assert report_a.score == report_b.score, f"{task_id}: non-idempotent score"
    assert report_a.passed == report_b.passed, f"{task_id}: non-idempotent passed"
    assert len(report_a.failures) == len(report_b.failures), (
        f"{task_id}: non-idempotent failure count"
    )


# ══════════════════════════════════════════════════════════════════════
# Part B — Targeted probes on synthetic canonical_diffs
# ══════════════════════════════════════════════════════════════════════


def _task_with_real_initial(env_id: str = "patient_portal") -> tuple[Any, Any, dict]:
    """Borrow a real session to provide a plausible initial/final state
    for synthetic-diff tests that still need valid state objects."""
    all_tasks = load_all_tasks()
    # Use any migrated task from the env for its state shape.
    pick = next(
        t for t in all_tasks.values()
        if t.env_id == env_id and t.canonical_diff is not None
    )
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id=env_id, task_id=pick.task_id, seed=42)
    return sm.get_initial_snapshot(sid), sm.get_state(sid), dict(targets)


def test_invariant_filter_exception_does_not_silently_skip() -> None:
    """Bug hypothesis: invariant filter that raises is silently treated as
    "entity doesn't match filter", bypassing invariant enforcement entirely.

    A typo like ``filter: "a.nonexistent_field == 'x'"`` would make the
    matcher accept any mutation to the "protected" collection. That's a
    silent hole — invariant bypass by typo.

    Expected-correct behavior: either (a) surface the filter error as a
    failure, or (b) fail-safe by treating the exception as "filter matches"
    so the entity is still enforced. Current code chooses (c): silently
    skip the entity, which is the least safe option.
    """
    initial, final, targets = _task_with_real_initial()

    # Build a minimal invariant whose filter always raises.
    block = CanonicalDiff.model_validate({
        "invariant": [{
            "collection": "state.appointments",
            "filter": "a.totally_nonexistent_field.crash()",
            "preserve": "ALL",
        }],
    })

    # Inject a fake mutation so we can observe whether the invariant fires.
    from webagentbench.evaluator_diff import Update
    fake_diff = [Update(
        entity="appointments",
        entity_id="appt_does_not_exist",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(
        fake_diff, block, targets=targets, initial=initial, final=final,
    )

    # Document current behavior. If this starts failing, the matcher
    # tightened — which is probably an improvement.
    filter_silent = all(nc["passed"] for nc in report.negative_checks
                       if "Preserve state.appointments" in nc["desc"])
    assert filter_silent, (
        "Filter exception behavior changed. If filter errors now surface, "
        "great — update this test to expect the failure. If this is still "
        "passing, it documents the known silent-skip bug: invariant filter "
        "typos silently disable invariant enforcement."
    )


def test_oneof_picks_highest_score_first_seen_on_tie() -> None:
    """Document the oneof tie-breaking policy.

    match_diff uses ``report.score > best.score`` (strict), so on ties the
    first block wins. Verify the contract: if two alternatives both score
    0 (neither matches agent_diff), the first alternative's failures are
    the ones reported. This matters for error attribution — if alternative
    B has cleaner failure messages, users see A's.
    """
    initial, final, targets = _task_with_real_initial()

    # Two oneof alternatives, each with a different update-target entity
    # that doesn't exist in the diff. Both score 0 (no matches).
    diff = CanonicalDiff.model_validate({
        "oneof": [
            {"update": [{
                "entity": "Appointment",
                "where": {"id": {"eq": "first_alt_id"}},
                "changes": {"status": {"eq": "scheduled"}},
            }]},
            {"update": [{
                "entity": "Appointment",
                "where": {"id": {"eq": "second_alt_id"}},
                "changes": {"status": {"eq": "cancelled"}},
            }]},
        ],
    })

    report = match_diff([], diff, targets=targets, initial=initial, final=final)

    # Both score 0; document the winning alternative's failure attribution.
    # We just assert ONE block's failures were reported (not a merge or blank).
    assert len(report.failures) >= 1, (
        f"oneof with both alternatives failing produced no failures: report={report!r}"
    )
    descriptions = [f.description for f in report.failures]
    surfaced_alternative = any(
        "Appointment" in d or "scheduled" in d or "cancelled" in d
        for d in descriptions
    )
    assert surfaced_alternative, (
        f"No oneof alternative surfaced in failures: {descriptions!r}"
    )


def test_empty_canonical_diff_scores_one() -> None:
    """An empty canonical_diff (no entries anywhere) should give score=1.0
    and passed=True on do-nothing — vacuously correct.

    If this starts failing, the matcher grew a new required entry kind
    that an empty diff no longer satisfies.
    """
    initial, final, targets = _task_with_real_initial()
    empty = CanonicalDiff.model_validate({})
    report = match_diff([], empty, targets=targets, initial=initial, final=final)
    assert report.score == 1.0, f"empty diff score={report.score}, expected 1.0"
    assert report.passed is True


def test_constraint_expression_exception_becomes_penalty() -> None:
    """Bug hypothesis: constraint expression that raises is caught and
    treated as False (penalty fires). Asymmetric with invariant filter
    which is caught and treated as "skip" (no penalty).

    Document current behavior: constraint error → penalty. If the asymmetry
    is ever fixed, this test guides the migration.
    """
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "constraints": [{
            "expr": "state.totally_nonexistent.crash()",
            "desc": "intentionally broken constraint",
            "severity": "high",
        }],
    })

    report = match_diff([], block, targets=targets, initial=initial, final=final)

    # Constraint raising → ok=False → penalty applied.
    constraint_failed = any(
        not nc["passed"] for nc in report.negative_checks
        if "intentionally broken" in nc["desc"]
    )
    assert constraint_failed, (
        "Constraint exception did not fire as failure. If you fixed the "
        "silent behavior — update this test. Otherwise, the matcher is no "
        "longer fail-safe on malformed constraints."
    )

    # And the score took a hit.
    assert report.score < 1.0, (
        f"Constraint failure should penalize. score={report.score}"
    )


def test_do_nothing_with_real_task_score_is_zero_when_applicable() -> None:
    """Spot-check: for a task with non-empty positive entries that are
    applicable on seed=42, do-nothing must score exactly 0.0.

    Uses pp_schedule_annual_physical as a canonical example — single
    non-bijection create, always applicable. Zero tolerance for drift.
    """
    tid = "pp_schedule_annual_physical"
    if tid not in load_all_tasks() or load_all_tasks()[tid].canonical_diff is None:
        pytest.skip(f"{tid} not migrated on this branch")

    report = _match_do_nothing(tid)
    assert report.score == 0.0, (
        f"{tid} do-nothing score={report.score}, expected 0.0. "
        f"checks={[c for c in report.checks if c['passed']]}"
    )
    assert report.passed is False


def test_session_start_none_with_predicate_using_it() -> None:
    """Bug hypothesis: predicate ``x >= session_start`` when session_start
    is None. Behavior: predicate eval raises TypeError → caught silently
    → predicate returns False. Agent cannot win the check regardless of
    action.

    This is a footgun for tasks that use session_start in predicates but
    forget to plumb it through match_diff.
    """
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "any"}},
            "changes": {
                "booked_at": {"expr": "x >= session_start"},
            },
        }],
    })

    # No session_start argument.
    from webagentbench.evaluator_diff import Update
    fake = [Update(
        entity="appointments",
        entity_id="appt_1",
        field_changes={"booked_at": (None, datetime.now(timezone.utc))},
    )]

    report = match_diff(
        fake, block, targets=targets, initial=initial, final=final,
        session_start=None,
    )

    # Document: with session_start=None, predicate silently returns False.
    # If this assertion flips, someone tightened the matcher — good!
    assert report.score <= 1.0  # sanity; just exercise the path


def test_matcher_does_not_mutate_agent_diff() -> None:
    """Matcher must not mutate the agent_diff list it's passed (shared
    across trajectory storage, visualization, downstream telemetry).
    """
    initial, final, targets = _task_with_real_initial()
    from webagentbench.evaluator_diff import Create
    diff = [Create(entity="appointments", entity_id="x", fields={"id": "x"})]

    block = CanonicalDiff.model_validate({
        "create": [{
            "entity": "Appointment",
            "properties": {"id": {"eq": "x"}},
        }],
    })

    _ = match_diff(diff, block, targets=targets, initial=initial, final=final)
    assert len(diff) == 1, "agent_diff list length mutated"
    assert diff[0].entity_id == "x", "agent_diff entry mutated"


# ══════════════════════════════════════════════════════════════════════
# Part C — Predicate-layer probes (targeted bug hypotheses)
# ══════════════════════════════════════════════════════════════════════


def test_expr_predicate_swallows_author_typos() -> None:
    """Hypothesis: a malformed ``{expr: ...}`` predicate — e.g. referencing a
    target key that doesn't exist — silently returns False instead of
    surfacing the author error. Agents producing the right state would
    unfairly fail, and the author gets no feedback on the typo.

    Current behavior (:237-239): ``except Exception: return False``. This
    is the silent-reject footgun. If this test starts failing, someone
    made expr errors surface — good direction.
    """
    from webagentbench.evaluator_diff import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            # Typo: target doesn't have TYPO_KEY. Author meant something else.
            "changes": {"status": {"expr": "x == target['TYPO_KEY_THAT_DOESNT_EXIST']"}},
        }],
    })
    agent_did_right_thing = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(agent_did_right_thing, block,
                        targets=targets, initial=initial, final=final)

    # Bug present: report.passed is False because the expr silently returns
    # False on KeyError. The author should have gotten a loud signal instead.
    # This test documents the current (buggy) behavior; flip the assertion
    # when the matcher tightens.
    assert not report.passed, (
        "Author-typo expr no longer silently rejects — matcher tightened. "
        "Update this test to assert the positive direction (loud error)."
    )


def test_contains_predicate_list_element_semantics() -> None:
    """Hypothesis: ``contains: [elem1, elem2]`` uses Python ``in``, which on
    a list value checks LIST-AS-ELEMENT, not SUBSET. Authors typically want
    subset — this is a foot-gun.

    Concretely: value = ``[1, 2, 3]``, predicate ``{contains: [1, 2]}``:
      Python: ``[1, 2] in [1, 2, 3]`` → False
      Intended: ``{1, 2} ⊆ {1, 2, 3]`` → True

    For single-element: ``{contains: 1}`` on ``[1, 2, 3]`` works correctly.
    The trap is specifically the list-argument form.
    """
    from webagentbench.evaluator_diff import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"notes": {"contains": ["alpha", "beta"]}},
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"notes": (["alpha"], ["alpha", "beta", "gamma"])},
    )]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    # If predicate were subset-like, report.passed would be True (agent's
    # list includes both "alpha" and "beta"). With current element-in
    # semantics, ``["alpha", "beta"] in ["alpha", "beta", "gamma"]`` is
    # False, so the predicate fails.
    assert not report.passed, (
        "`contains: [list]` started accepting subset-like matches. "
        "Either rename predicate to `elem`/`subset` or this test needs updating. "
        "See evaluator_diff.py:172 — current semantic is `arg in value` (element)."
    )


def test_length_predicate_does_not_crash_on_none_value() -> None:
    """Hypothesis: ``{length: {eq: 0}}`` applied to a field whose value is
    None raises TypeError (``len(None)`` unpropagated). The matcher should
    return False gracefully instead of crashing.

    This test fails loudly if a TypeError escapes. If the matcher is already
    graceful, it passes.
    """
    from webagentbench.evaluator_diff import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"notes": {"length": {"eq": 0}}},
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"notes": ("something", None)},
    )]

    try:
        report = match_diff(diff, block, targets=targets,
                            initial=initial, final=final)
    except TypeError as exc:
        pytest.fail(
            f"BUG: matcher crashed on len(None) instead of returning False. "
            f"evaluator_diff.py:173-182 — wrap in try/except. {exc}"
        )
    assert isinstance(report.score, float)


def test_named_invariant_with_update_ref_applies_label() -> None:
    """Hypothesis: ``named_invariants: - ref: update[0]`` silently no-ops.

    Reading evaluator_diff.py:1110-1136, the attribution loop explicitly
    handles ``invariant`` and ``create`` refs. The ``update`` and ``delete``
    branches have no corresponding code — the loop just iterates past them.

    Impact: tasks with ``ref: update[0]  severity: high`` lose both the
    custom display label AND the severity override. Present-day migrated
    tasks rely on this for labeling (e.g. lms_end_of_semester_verification
    uses ``ref: update[0]`` and ``ref: update[1]``).
    """
    from webagentbench.evaluator_diff import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"status": {"eq": "cancelled"}},
            "desc": "default update description",
        }],
        "named_invariants": [{
            "name": "CUSTOM-LABEL-FOR-UPDATE-0",
            "ref": "update[0]",
            "severity": "high",
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    relabeled = any(c.get("desc") == "CUSTOM-LABEL-FOR-UPDATE-0"
                    for c in report.checks)
    assert relabeled, (
        "BUG: named_invariant with ref=update[N] silently no-ops. "
        "Loop at evaluator_diff.py:1110 handles 'invariant' and 'create' only; "
        "add a branch for 'update' and 'delete' that rewrites checks[idx].desc."
    )


def test_named_invariant_severity_override_applied_to_invariant() -> None:
    """Regression: ``named_invariants: - ref: invariant[0]  severity: critical``
    must override the default ``medium`` penalty on the invariant's
    negative_check.

    critical → 0.3 per _SEVERITY_PENALTY table. medium → 0.15.
    """
    from webagentbench.evaluator_diff import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "invariant": [{
            "collection": "state.appointments",
            "preserve": "ALL",
        }],
        "named_invariants": [{
            "name": "Do not disturb existing appointments",
            "ref": "invariant[0]",
            "severity": "critical",
        }],
    })
    # Trigger the invariant by mutating an appointment.
    diff = [Update(
        entity="appointments",
        entity_id="appt_anything",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    nc = next(
        (x for x in report.negative_checks
         if x["desc"] == "Do not disturb existing appointments"),
        None,
    )
    assert nc is not None, "named_invariant label was not applied to negative_check"
    assert nc["penalty"] == 0.3, (
        f"severity=critical should yield penalty 0.3, got {nc['penalty']}. "
        "Check that NamedInvariant severity propagation at "
        "evaluator_diff.py:1115-1122 is wired correctly."
    )


def test_matches_semantic_does_not_crash_on_plain_strings() -> None:
    """Exercise ``matches_semantic`` with ordinary string inputs. Regardless
    of whether an embedding model is available, the matcher must not crash.
    If the backend fails to load, matches_semantic should return False
    (conservative) rather than propagate the error.
    """
    from webagentbench.evaluator_diff import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"notes": {"matches_semantic": "meeting scheduled"}},
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"notes": ("", "scheduled a meeting")},
    )]

    # Just assert no exception escapes. Pass/fail score irrelevant.
    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)
    assert isinstance(report.score, float)


def test_bijection_excess_tracked_when_empty_target() -> None:
    """Class 9 fix kept ``bijection_excess`` tracking alive even for empty
    targets, so ``named_invariants: - ref: create[N]`` can still flag
    "agent scheduled N when 0 were needed."

    This test verifies: empty-target bijection + agent-created entity +
    ref=create[0] named_invariant → the named invariant FAILS (over-creation
    detected).
    """
    from webagentbench.evaluator_diff import Create
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "create": [{
            "entity": "Appointment",
            "bijection": {"over": "target['NONEXISTENT_EMPTY_KEY']",
                          "variable": "v"},
            "properties": {"id": {"any": True}},
        }],
        "named_invariants": [{
            "name": "Did not schedule more than required",
            "ref": "create[0]",
            "severity": "high",
        }],
    })
    # Agent creates an appointment when 0 were needed.
    diff = [Create(
        entity="appointments",
        entity_id="appt_x",
        fields={"id": "appt_x"},
    )]

    # targets must include the bijection key so _eval_target_expr doesn't
    # fail; give it an empty list.
    targets_with_empty = dict(targets)
    targets_with_empty["NONEXISTENT_EMPTY_KEY"] = []

    report = match_diff(diff, block, targets=targets_with_empty,
                        initial=initial, final=final)

    excess_nc = next(
        (x for x in report.negative_checks
         if x["desc"] == "Did not schedule more than required"),
        None,
    )
    assert excess_nc is not None, (
        "BUG: Class 9 fix lost bijection_excess tracking for empty-target "
        "bijections. Named invariant on create[0] should still fire when "
        "agent creates entities that weren't needed."
    )
    assert not excess_nc["passed"], (
        "Agent created 1 appointment when 0 were needed — "
        "named_invariant on create[0] should FAIL, got passed={}.".format(excess_nc["passed"])
    )
