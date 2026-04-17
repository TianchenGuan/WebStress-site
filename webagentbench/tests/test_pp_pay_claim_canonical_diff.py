"""End-to-end tests for pp_pay_claim canonical_diff.

Task: "Pay the outstanding balance on your most recent approved insurance claim."

Verifies:
  - Correct trajectory (zero out patient_responsibility on the most-recent
    approved claim, by service_date with cid tiebreaker) passes, score 1.0.
  - Paying an older approved claim instead fails.
  - Paying a denied claim fails.
  - Do-nothing trajectory fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_pay_claim',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _most_recent_approved_claim_id(initial, targets) -> str:
    """Replicate the canonical selector: max by (service_date, cid)."""
    return max(
        targets["approved_claim_ids"],
        key=lambda cid: (initial.get_claim(cid).service_date, cid),
    )


def _pay_claim(state, clm_id: str) -> None:
    """Simulate the backend pay route: zero out patient_responsibility."""
    for c in state.claims:
        if c.id == clm_id:
            c.patient_responsibility = Decimal("0")
            return
    raise ValueError(f"claim {clm_id!r} not found in session state")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    target_id = _most_recent_approved_claim_id(initial, targets)
    _pay_claim(state, target_id)

    task = get_task('pp_pay_claim')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_older_claim_paid_fails():
    """Agent pays an older approved claim (NOT the most recent)."""
    sm, sid, targets, initial, state = _setup_session()
    target_id = _most_recent_approved_claim_id(initial, targets)

    older_id = next(
        (cid for cid in targets["approved_claim_ids"] if cid != target_id),
        None,
    )
    assert older_id is not None, (
        "seed must produce >=2 approved claims for this identity test to be "
        "non-vacuous (hazard Class 4)"
    )
    _pay_claim(state, older_id)

    task = get_task('pp_pay_claim')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "paying an older approved claim must fail — the `where` selector "
        "picks only the most-recent approved claim by service_date."
    )


def test_denied_claim_paid_fails():
    """Agent zeroes out patient_responsibility on a denied claim."""
    sm, sid, targets, initial, state = _setup_session()
    denied_ids = targets.get("denied_claim_ids") or []
    assert denied_ids, "seed must produce >=1 denied claim for this test"
    _pay_claim(state, denied_ids[0])

    task = get_task('pp_pay_claim')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "paying a denied claim must fail — the target is an approved claim, "
        "and the invariant sweep rejects mutations on non-target claims."
    )


def test_no_mutation_fails():
    """Agent does nothing. Positive update has zero matched candidates,
    so score must be 0.0 and passed=False (hazard Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_pay_claim')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — the positive update entry "
        "has no matching candidate."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"
