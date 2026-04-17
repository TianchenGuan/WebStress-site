"""End-to-end tests for pp_treatment_cost_comparison canonical_diff.

Task: schedule exactly one PCP appointment at the next available PCP slot with
the reason "Treatment cost comparison review", without touching prescriptions,
claims, or referrals (including the prior-auth referral).

Trajectories covered:
- correct (earliest PCP slot, correct provider + reason) → passes 1.0
- wrong provider (not PCP) → fails
- wrong reason (free-text mismatch) → fails
- not earliest slot (second-earliest PCP slot) → fails
- modified referral (flip prior_auth_ref_id prior_auth_status) → fails
- modified claim (flip approved claim patient_responsibility) → fails
- no mutation → fails
"""

from decimal import Decimal

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_treatment_cost_comparison",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_pcp_slot(initial, pcp_id: str):
    slots: list = []
    for p in initial.providers:
        if p.id == pcp_id:
            slots.extend(s.datetime for s in p.available_slots)
    if not slots:
        raise ValueError(f"PCP {pcp_id!r} has no available slots in initial snapshot")
    return min(slots)


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Treatment cost comparison review")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_cost_review",
        provider_id=pcp_id,
        datetime=_earliest_pcp_slot(initial, pcp_id),
    ))

    task = get_task("pp_treatment_cost_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_provider_fails():
    """Appointment scheduled with a non-PCP provider — predicate on provider_id fails."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    other = next(p for p in state.providers if p.id != pcp_id and p.available_slots)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task("pp_treatment_cost_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_reason_fails():
    """Appointment reason doesn't match the required exact string."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_wrong_reason",
        provider_id=pcp_id,
        datetime=_earliest_pcp_slot(initial, pcp_id),
        reason="Cost review",  # close but not exact
    ))

    task = get_task("pp_treatment_cost_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Appointment uses a PCP slot later than the earliest."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    pcp_slots = sorted(
        s.datetime for p in initial.providers if p.id == pcp_id for s in p.available_slots
    )
    assert len(pcp_slots) >= 2, "seed must produce >=2 PCP slots for this test"
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=pcp_id,
        datetime=pcp_slots[1],  # second-earliest
    ))

    task = get_task("pp_treatment_cost_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_modified_referral_fails():
    """Agent correctly schedules but also flips the prior-auth referral status —
    invariant on state.referrals should reject the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_cost_review",
        provider_id=pcp_id,
        datetime=_earliest_pcp_slot(initial, pcp_id),
    ))
    prior_auth_ref_id = targets["prior_auth_ref_id"]
    assert prior_auth_ref_id, "seed must produce a prior_auth_ref_id"
    mutated = False
    for r in state.referrals:
        if r.id == prior_auth_ref_id:
            r.prior_auth_status = "denied"
            mutated = True
            break
    assert mutated, f"referral {prior_auth_ref_id!r} missing from state"

    task = get_task("pp_treatment_cost_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "modifying the prior-auth referral must fail via the referrals invariant"
    )


def test_modified_claim_fails():
    """Agent correctly schedules but also bumps an approved claim's
    patient_responsibility — invariant on state.claims should reject the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_cost_review",
        provider_id=pcp_id,
        datetime=_earliest_pcp_slot(initial, pcp_id),
    ))
    approved_ids = targets.get("approved_claim_ids") or []
    assert approved_ids, "seed must produce at least one approved claim"
    mutated = False
    for c in state.claims:
        if c.id == approved_ids[0]:
            c.patient_responsibility = Decimal(str(c.patient_responsibility)) + Decimal("10.00")
            mutated = True
            break
    assert mutated, f"claim {approved_ids[0]!r} missing from state"

    task = get_task("pp_treatment_cost_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "modifying a claim balance must fail via the claims invariant"
    )


def test_no_mutation_fails():
    """Agent does nothing. Positive create has zero matched candidates,
    so score must be <1.0 and passed=False (hazard Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("pp_treatment_cost_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — the positive create entry "
        "has no matching candidate."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"
