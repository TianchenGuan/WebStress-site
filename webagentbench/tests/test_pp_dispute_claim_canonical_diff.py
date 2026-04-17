"""End-to-end tests for pp_dispute_claim canonical_diff.

Task: "Your most recent denied insurance claim has an available EOB. Review
the EOB, then file an appeal for that claim before the appeal deadline
passes."

Verifies:
  - Correct trajectory (status='appealed' on the most-recent denied claim by
    service_date with cid tiebreaker) passes, score 1.0.
  - Appealing an older denied claim instead fails.
  - Appealing an approved claim fails.
  - Do-nothing trajectory fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_dispute_claim',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _most_recent_denied_claim_id(initial, targets) -> str:
    """Replicate the canonical selector: max by (service_date, cid)."""
    return max(
        targets["denied_claim_ids"],
        key=lambda cid: (initial.get_claim(cid).service_date, cid),
    )


def _appeal_claim(state, clm_id: str) -> None:
    """Simulate the backend appeal route: set status='appealed'."""
    for c in state.claims:
        if c.id == clm_id:
            c.status = "appealed"
            return
    raise ValueError(f"claim {clm_id!r} not found in session state")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    target_id = _most_recent_denied_claim_id(initial, targets)
    # Cross-check that the derived seed target agrees with the canonical
    # selector (regression guard against seed/diff drift).
    assert targets.get("most_recent_denied_claim_id") == target_id, (
        "seed's most_recent_denied_claim_id must equal max-by-service_date; "
        f"got seed={targets.get('most_recent_denied_claim_id')!r} vs computed={target_id!r}"
    )
    _appeal_claim(state, target_id)

    task = get_task('pp_dispute_claim')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_older_denied_appealed_fails():
    """Agent appeals an older denied claim (NOT the most recent)."""
    sm, sid, targets, initial, state = _setup_session()
    target_id = _most_recent_denied_claim_id(initial, targets)

    older_id = next(
        (cid for cid in targets["denied_claim_ids"] if cid != target_id),
        None,
    )
    assert older_id is not None, (
        "seed must produce >=2 denied claims for this identity test to be "
        "non-vacuous (hazard Class 4)"
    )
    _appeal_claim(state, older_id)

    task = get_task('pp_dispute_claim')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "appealing an older denied claim must fail — the `where` selector "
        "picks only the most-recent denied claim by service_date."
    )


def test_approved_appealed_fails():
    """Agent sets status='appealed' on an approved claim instead."""
    sm, sid, targets, initial, state = _setup_session()
    approved_ids = targets.get("approved_claim_ids") or []
    assert approved_ids, "seed must produce >=1 approved claim for this test"
    _appeal_claim(state, approved_ids[0])

    task = get_task('pp_dispute_claim')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "appealing an approved claim must fail — the target is a denied "
        "claim, and the invariant sweep rejects mutations on non-target "
        "claims."
    )


def test_no_mutation_fails():
    """Agent does nothing. Positive update has zero matched candidates,
    so score must be <1.0 and passed=False (hazard Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_dispute_claim')
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
