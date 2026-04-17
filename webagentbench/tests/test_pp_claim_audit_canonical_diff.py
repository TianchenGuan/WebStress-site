"""End-to-end tests for pp_claim_audit canonical_diff.

Task: "Review all your insurance claims. Identify all denied claims that
are still eligible for appeal (appeal deadline has not passed and an EOB
is available). From those eligible claims, select the top 3 by patient
responsibility amount (highest first; if two claims tie, break the tie
by claim ID). Appeal exactly those 3 claims using the claim appeal
action. Do not appeal any other claim and do not send any messages."

Verifies:
  - Correct trajectory (status='appealed' on all 3 top-appealable claims)
    passes, score 1.0.
  - Appealing only 2 of the 3 required → under-saturated bijection, fails.
  - Appealing 3 claims that aren't the required top-3 set → fails.
  - Appealing an approved claim instead → fails via invariant violation.
  - Do-nothing trajectory fails (hazard Class 1 guard).
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_claim_audit',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _appeal_claim(state, clm_id: str) -> None:
    """Simulate the backend appeal route: set status='appealed'."""
    for c in state.claims:
        if c.id == clm_id:
            c.status = "appealed"
            return
    raise ValueError(f"claim {clm_id!r} not found in session state")


def _expected_top_3(initial, targets) -> list[str]:
    """Replicate the canonical selector: eligible denied claims sorted by
    (-patient_responsibility, cid)[:3]. Used as a cross-check that the
    seed's `top_3_appealable_claim_ids` matches the instruction literally."""
    ctx_now = initial.created_at.isoformat()
    eligible: list[str] = []
    for cid in targets["denied_claim_ids"]:
        c = initial.get_claim(cid)
        if c is None:
            continue
        if c.eob_available and c.appeal_deadline.isoformat() >= ctx_now:
            eligible.append(cid)
    eligible.sort(
        key=lambda cid: (
            -float(initial.get_claim(cid).patient_responsibility),
            cid,
        ),
    )
    return eligible[:3]


def test_correct_trajectory_passes():
    """Appeal exactly the top-3 eligible denied claims."""
    sm, sid, targets, initial, state = _setup_session()
    expected = _expected_top_3(initial, targets)
    assert targets.get("top_3_appealable_claim_ids") == expected, (
        "seed's top_3_appealable_claim_ids must equal the literal "
        "eligibility-sort selector (regression guard against seed/diff drift); "
        f"got seed={targets.get('top_3_appealable_claim_ids')!r} "
        f"vs computed={expected!r}"
    )
    for cid in expected:
        _appeal_claim(state, cid)

    task = get_task('pp_claim_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_partial_fails():
    """Appeal only 2 of the 3 required claims — bijection under-saturates."""
    sm, sid, targets, initial, state = _setup_session()
    top_3 = targets["top_3_appealable_claim_ids"]
    assert len(top_3) == 3, f"seed must produce 3 appealable claims, got {top_3!r}"
    # Appeal only the first 2 of the required 3
    for cid in top_3[:2]:
        _appeal_claim(state, cid)

    task = get_task('pp_claim_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "appealing only 2 of the 3 required claims must fail — the "
        "bijection over top_3_appealable_claim_ids only saturates at 3."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_appealed_wrong_3_fails():
    """Appeal 3 denied claims that aren't the top-3 by patient_responsibility."""
    sm, sid, targets, initial, state = _setup_session()
    top_3 = set(targets["top_3_appealable_claim_ids"])
    wrong_ids = [cid for cid in targets["denied_claim_ids"] if cid not in top_3]
    assert len(wrong_ids) >= 1, (
        "seed must produce denied claims outside the top-3 for a non-vacuous "
        "identity test (hazard Class 4)"
    )
    # Appeal 2 from the top-3 plus 1 wrong one so candidate count == 3 but
    # the identity test still fails (still a wrong set).
    mixed = list(targets["top_3_appealable_claim_ids"])[:2] + [wrong_ids[0]]
    assert len(set(mixed)) == 3
    for cid in mixed:
        _appeal_claim(state, cid)

    task = get_task('pp_claim_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "appealing a wrong mix must fail — the invariant rejects mutations "
        "to claims outside the top-3, and the bijection under-saturates."
    )


def test_approved_claim_appealed_fails():
    """Appeal an approved claim instead of denied — must trip the invariant."""
    sm, sid, targets, initial, state = _setup_session()
    approved_ids = targets.get("approved_claim_ids") or []
    assert approved_ids, "seed must produce >=1 approved claim for this test"
    # Appeal all 3 required top-3 AND one approved claim as collateral damage
    for cid in targets["top_3_appealable_claim_ids"]:
        _appeal_claim(state, cid)
    _appeal_claim(state, approved_ids[0])

    task = get_task('pp_claim_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "modifying an approved claim must fail — the `a.id not in "
        "target['top_3_appealable_claim_ids']` invariant preserves every "
        "non-target claim."
    )


def test_no_mutation_fails():
    """Do-nothing trajectory: bijection has 3 slots, 0 candidates — must
    fail with score<1.0 (hazard Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_claim_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — the positive update entry "
        "has 0 of 3 matched candidates."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"
