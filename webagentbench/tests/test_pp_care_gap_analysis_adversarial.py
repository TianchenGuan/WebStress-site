"""Adversarial regression battery for pp_care_gap_analysis.

Auto-generated — no manual TODO. The generator synthesizes violating
final-states per predicate and asserts the matcher rejects every one.

If this test FAILS, either:
  (a) the matcher regressed and is accepting an obviously-wrong state, or
  (b) the canonical_diff got looser and admits states it shouldn't.
Both are regressions that must be fixed before the PR merges.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task
from webagentbench.tasks.adversarial import synthesize_adversarial_cases


def _initial_state_as_dict(sm: SessionManager, sid: str) -> dict:
    snap = sm.get_initial_snapshot(sid)
    if hasattr(snap, "model_dump"):
        return snap.model_dump()
    return dict(snap) if snap else {}


def test_all_adversarial_cases_fail():
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_care_gap_analysis',
        seed=42,
    )
    initial = _initial_state_as_dict(sm, sid)
    task = get_task('pp_care_gap_analysis')
    assert task.canonical_diff is not None, (
        "canonical_diff missing — migrate the task first or run Tool B "
        "to scaffold the authoring context."
    )

    cases = synthesize_adversarial_cases(
        task.canonical_diff,
        initial=initial,
        targets=dict(targets),
    )
    assert len(cases) >= 1, (
        f"adversarial generator produced no cases for pp_care_gap_analysis — "
        "likely a canonical_diff with no negatable predicates."
    )

    unexpectedly_passed: list[str] = []
    for case in cases:
        final = case["final"]
        agent_diff = compute_diff(initial, final)
        report = match_diff(
            agent_diff, task.canonical_diff,
            targets=dict(targets),
            initial=initial, final=final,
        )
        if report.passed:
            unexpectedly_passed.append(
                f"case {case['description']!r} passed when it should have been rejected"
            )

    assert not unexpectedly_passed, (
        "Adversarial cases leaked through the matcher:\n  "
        + "\n  ".join(unexpectedly_passed)
    )
