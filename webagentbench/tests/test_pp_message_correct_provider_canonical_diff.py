"""End-to-end tests for pp_message_correct_provider canonical_diff.

Task: schedule exactly one PCP appointment (the referring provider for a
pending orthopedic referral) at the next available PCP slot with reason
"Orthopedic referral status review". Do not schedule with the orthopedic
specialist, do not modify the pending referral, and do not send messages.

Trajectories covered:
- correct (PCP + earliest slot + exact reason) → passes 1.0
- scheduled with orthopedic provider instead of PCP → fails
- wrong reason (free-text mismatch) → fails
- not earliest slot (second-earliest PCP slot) → fails
- modified pending referral status → fails invariant
- no mutation (do-nothing) → fails
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_message_correct_provider",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_slot(initial, pcp_id: str):
    for p in initial.providers:
        if p.id == pcp_id:
            return min(s.datetime for s in p.available_slots)
    raise ValueError(f"PCP {pcp_id!r} missing from initial snapshot")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Orthopedic referral status review")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_referral_review",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
    ))

    task = get_task("pp_message_correct_provider")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_scheduled_orthopedic_instead_fails():
    """Scheduling with the orthopedic specialist instead of the PCP should fail."""
    sm, sid, targets, initial, state = _setup_session()
    ortho_ids = list(targets["ortho_provider_ids"])
    assert ortho_ids, "seed must produce at least one orthopedic provider"
    ortho = next(p for p in state.providers if p.id in ortho_ids and p.available_slots)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=ortho.id,
        datetime=min(s.datetime for s in ortho.available_slots),
    ))

    task = get_task("pp_message_correct_provider")
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
        datetime=_earliest_slot(initial, pcp_id),
        reason="Referral follow-up",  # close but not exact
    ))

    task = get_task("pp_message_correct_provider")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """PCP + correct reason but using the 2nd-earliest slot should fail the datetime expr."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    slots = sorted(
        s.datetime for p in initial.providers if p.id == pcp_id for s in p.available_slots
    )
    assert len(slots) >= 2, "seed must produce >=2 PCP slots for this test"
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=pcp_id,
        datetime=slots[1],  # second-earliest
    ))

    task = get_task("pp_message_correct_provider")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_modified_referral_status_fails():
    """Correct appointment, but the agent mutated a pending referral's status.
    The scoped invariant on state.referrals filtered by pending_ref_ids must flag it."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_referral_review",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
    ))
    pending_ids = set(targets["pending_ref_ids"])
    assert pending_ids, "seed must produce at least one pending referral"
    target_ref = next(r for r in state.referrals if r.id in pending_ids)
    target_ref.status = "approved"  # unauthorized mutation

    task = get_task("pp_message_correct_provider")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "mutating a pending referral's status must be caught by the "
        "state.referrals[pending_ref_ids] invariant"
    )


def test_no_mutation_fails():
    """Do-nothing trajectory must not pass — no appointment was created."""
    sm, sid, targets, initial, state = _setup_session()
    # (no mutation)

    task = get_task("pp_message_correct_provider")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
