"""End-to-end tests for pp_message_pcp canonical_diff.

Task: review medication list, then schedule exactly one PCP appointment at
the next available slot with reason "Medication side effect review". Do not
send any messages.

Trajectories covered:
- correct (PCP + earliest slot + exact reason) → passes 1.0
- wrong provider (not PCP) → fails
- wrong reason (free-text mismatch) → fails
- not earliest slot (second-earliest PCP slot) → fails
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
        task_id="pp_message_pcp",
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
    kwargs.setdefault("reason", "Medication side effect review")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_med_side_effect_review",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
    ))

    task = get_task("pp_message_pcp")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_provider_fails():
    """Scheduling with a non-PCP provider should fail the provider_id expr."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    other = next(p for p in state.providers if p.id != pcp_id and p.available_slots)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task("pp_message_pcp")
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
        reason="Medication review",  # close but not exact
    ))

    task = get_task("pp_message_pcp")
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

    task = get_task("pp_message_pcp")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_no_mutation_fails():
    """Do-nothing trajectory must not pass — no appointment was created."""
    sm, sid, targets, initial, state = _setup_session()
    # (no mutation)

    task = get_task("pp_message_pcp")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
