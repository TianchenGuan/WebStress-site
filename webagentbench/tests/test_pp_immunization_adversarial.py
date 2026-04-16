"""Adversarial regression battery for pp_immunization_gap_review.

Uses the Task 12 adversarial-case generator to synthesize final-states
that violate the canonical_diff, then asserts match_diff rejects each.

If this test fails, either:
  (a) the matcher regressed and is letting obviously-wrong states through, or
  (b) the canonical_diff got looser and is accepting states it shouldn't.

Both are regressions that must be fixed before merge.
"""

from copy import deepcopy

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task
from webagentbench.tasks.adversarial import synthesize_adversarial_cases


def _initial_state_as_dict(sm: SessionManager, sid: str) -> dict:
    snapshot = sm.get_initial_snapshot(sid)
    if hasattr(snapshot, "model_dump"):
        return snapshot.model_dump()
    return dict(snapshot) if snapshot else {}


def test_all_adversarial_cases_fail():
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    initial = _initial_state_as_dict(sm, sid)
    task = get_task("pp_immunization_gap_review")
    assert task.canonical_diff is not None, (
        "pp_immunization_gap_review missing canonical_diff — Task 10 didn't complete"
    )

    cases = synthesize_adversarial_cases(
        task.canonical_diff,
        initial=initial,
        targets=dict(targets),
    )
    assert len(cases) >= 3, (
        f"expected adversarial generator to produce >=3 cases for this task, got {len(cases)}"
    )

    failed_cases: list[str] = []
    for case in cases:
        final = case["final"]
        agent_diff = compute_diff(initial, final)
        report = match_diff(
            agent_diff, task.canonical_diff,
            targets=dict(targets),
            initial=initial, final=final,
        )
        if report.passed:
            failed_cases.append(
                f"adversarial case unexpectedly passed: {case['description']}"
            )

    assert not failed_cases, (
        "these adversarial cases should have been rejected but weren't:\n  "
        + "\n  ".join(failed_cases)
    )
