"""End-to-end tests for pp_review_eob canonical_diff.

Task (post-w09 revision, 2026-04-20): "Review the EOB for your most recent
approved claim and pay the patient responsibility on that claim in full. Do
not pay or appeal any other claim, and do not send any messages."

The pre-w09 design used `oneof` with a constraint-only "do nothing when
responsibility > $200" branch (Branch B). Audit w09 found that on seed 42
the agent scored 1.0 without any observable action — the constraint-only
branch acts as an applicability gate that passes whenever the seed matches,
regardless of agent behaviour (see eval-hardening-playbook §2.7).

Revision: dropped Branch B. The task now unconditionally requires paying
the most-recent approved claim. Seeds that previously triggered the "skip"
branch now require payment as well.

Seed behaviour probed for this task:
  seed=42  → recent_resp=$724.74  → pay
  seed=2   → recent_resp=$39.58   → pay
  seed=200 → recent_resp=$165.29  → pay
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


# Representative seeds across the old-branch split — both should now require
# payment. Keeping both curated seeds documents the responsibility range.
_HIGH_RESP_SEED = 42    # recent_resp > $200
_LOW_RESP_SEED = 2      # recent_resp <= $200


def _setup_session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_review_eob',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _most_recent_approved(initial, targets) -> str:
    """Replicate the canonical selector: max by (service_date, cid)."""
    return max(
        targets['approved_claim_ids'],
        key=lambda cid: (initial.get_claim(cid).service_date, cid),
    )


def _pay_claim(state, clm_id: str) -> None:
    for c in state.claims:
        if c.id == clm_id:
            c.patient_responsibility = Decimal("0")
            return
    raise ValueError(f"claim {clm_id!r} not found")


# ---------------------------------------------------------------------
# Correct trajectories — agent pays the most-recent approved claim.
# ---------------------------------------------------------------------

def test_correct_trajectory_low_resp_passes():
    """Low responsibility seed: agent pays the most-recent approved claim."""
    _, _, targets, initial, state = _setup_session(_LOW_RESP_SEED)
    target_id = _most_recent_approved(initial, targets)
    _pay_claim(state, target_id)

    task = get_task('pp_review_eob')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_correct_trajectory_high_resp_passes():
    """High responsibility seed (was the old SKIP branch): also pay now."""
    _, _, targets, initial, state = _setup_session(_HIGH_RESP_SEED)
    target_id = _most_recent_approved(initial, targets)
    _pay_claim(state, target_id)

    task = get_task('pp_review_eob')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


# Alias required by the validate.py stage-4 probe.
def test_correct_trajectory_passes():
    test_correct_trajectory_low_resp_passes()


# ---------------------------------------------------------------------
# Negative trajectories — anything other than paying the target claim fails.
# ---------------------------------------------------------------------

def test_doing_nothing_fails():
    """Audit w09 regression: prior design gave score 1.0 on high-resp seeds
    when the agent did nothing. The revision must now fail."""
    _, _, targets, initial, state = _setup_session(_HIGH_RESP_SEED)

    task = get_task('pp_review_eob')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "doing nothing must fail — the task now unconditionally requires "
        "paying the most-recent approved claim; see audit_reports/w09.md."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_not_paid_when_low_resp_fails():
    """Low-resp seed, agent does nothing — must fail (same as high-resp)."""
    _, _, targets, initial, state = _setup_session(_LOW_RESP_SEED)

    task = get_task('pp_review_eob')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "leaving the claim unpaid must fail — pay is now unconditional."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_paid_wrong_claim_fails():
    """Agent pays a NON-most-recent approved claim — selector rejects it and
    the invariant on state.claims fires on the stray mutation."""
    _, _, targets, initial, state = _setup_session(_LOW_RESP_SEED)
    recent_id = _most_recent_approved(initial, targets)
    older_id = next(
        (cid for cid in targets['approved_claim_ids'] if cid != recent_id),
        None,
    )
    assert older_id is not None, (
        "seed must produce >=2 approved claims for the identity test to be "
        "non-vacuous (hazard Class 4)."
    )
    _pay_claim(state, older_id)

    task = get_task('pp_review_eob')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "paying the older approved claim must fail — the selector picks "
        "only the most-recent approved claim, and the invariant on "
        "state.claims fires on any other claim mutation."
    )


def test_message_sent_fails():
    """Agent sends a patient message as a side-effect — invariant on
    state.messages fires regardless of whether the pay step succeeded."""
    from webagentbench.backend.models.patient_portal import ClinicalMessage

    _, _, targets, initial, state = _setup_session(_LOW_RESP_SEED)
    target_id = _most_recent_approved(initial, targets)
    _pay_claim(state, target_id)
    state.messages.append(ClinicalMessage(
        id="msg_agent_side_effect",
        from_type="patient",
        provider_id=state.providers[0].id if state.providers else "prov_1",
        subject="Question about EOB",
        body="Why is my responsibility so high?",
        thread_id="thread_test",
    ))

    task = get_task('pp_review_eob')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "sending a patient message must fail — the task explicitly says "
        "'Do not send any messages' and invariant on state.messages catches it."
    )
