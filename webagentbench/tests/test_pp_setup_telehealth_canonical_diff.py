"""End-to-end tests for pp_setup_telehealth canonical_diff.

Task: cancel the target upcoming in-person appointment AND create a
telehealth replacement with the same provider at the earliest available
slot.

Shape: update + create combo (same shape as pp_cancel_reschedule).

Trajectories covered:
- correct: cancel target + create telehealth with same provider at
  earliest slot → passes 1.0
- wrong provider: create telehealth with a DIFFERENT provider → fails
- type still in-person: replacement is in-person, not telehealth → fails
- not earliest slot: replacement at 2nd earliest slot → fails
- only cancel (no replacement) → fails
- only create (no cancel) → fails
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_setup_telehealth",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _cancel(state, apt_id: str) -> None:
    for a in state.appointments:
        if a.id == apt_id:
            a.status = "cancelled"
            return
    raise ValueError(f"appointment {apt_id!r} not found")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "telehealth")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Telehealth follow-up")
    return Appointment(**kwargs)


def _provider_slots_sorted(initial, provider_id: str):
    for p in initial.providers:
        if p.id == provider_id:
            return sorted(s.datetime for s in p.available_slots)
    raise ValueError(f"provider {provider_id!r} missing from initial snapshot")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    orig = initial.get_appointment(targets["next_appointment_id"])
    earliest = _provider_slots_sorted(initial, orig.provider_id)[0]
    target_appt = next(a for a in state.appointments if a.id == targets["next_appointment_id"])
    target_appt.type = "telehealth"
    target_appt.status = "scheduled"
    target_appt.datetime = earliest

    task = get_task("pp_setup_telehealth")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_provider_fails():
    """Agent changes the target appointment to a different provider."""
    sm, sid, targets, initial, state = _setup_session()
    orig = initial.get_appointment(targets["next_appointment_id"])

    other = next(
        p for p in initial.providers
        if p.id != orig.provider_id
        and p.specialty in ("pcp", "billing", "admin")  # non-specialist to avoid referral prereq
        and p.available_slots
    )
    earliest_other = min(s.datetime for s in other.available_slots)
    target_appt = next(a for a in state.appointments if a.id == targets["next_appointment_id"])
    target_appt.type = "telehealth"
    target_appt.status = "scheduled"
    target_appt.provider_id = other.id
    target_appt.datetime = earliest_other

    task = get_task("pp_setup_telehealth")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "rescheduling to a different provider must fail the same-provider "
        "predicate"
    )


def test_type_still_in_person_fails():
    """Agent reschedules target as in-person instead of telehealth."""
    sm, sid, targets, initial, state = _setup_session()
    orig = initial.get_appointment(targets["next_appointment_id"])
    earliest = _provider_slots_sorted(initial, orig.provider_id)[0]
    target_appt = next(a for a in state.appointments if a.id == targets["next_appointment_id"])
    target_appt.type = "in-person"
    target_appt.status = "scheduled"
    target_appt.datetime = earliest

    task = get_task("pp_setup_telehealth")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "in-person reschedule must fail type == 'telehealth' predicate"
    )


def test_not_earliest_slot_fails():
    """Agent reschedules telehealth at the second earliest slot, not the earliest."""
    sm, sid, targets, initial, state = _setup_session()
    orig = initial.get_appointment(targets["next_appointment_id"])
    slots = _provider_slots_sorted(initial, orig.provider_id)
    assert len(slots) >= 2, "seed must expose ≥2 provider slots for this test"
    target_appt = next(a for a in state.appointments if a.id == targets["next_appointment_id"])
    target_appt.type = "telehealth"
    target_appt.status = "scheduled"
    target_appt.datetime = slots[1]

    task = get_task("pp_setup_telehealth")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "second-earliest slot must fail datetime == min(slot) predicate"
    )


def test_only_cancel_fails():
    """Agent cancels instead of using the Reschedule flow."""
    sm, sid, targets, initial, state = _setup_session()
    _cancel(state, targets["next_appointment_id"])

    task = get_task("pp_setup_telehealth")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "cancel-only trajectory must fail"
    assert report.score < 1.0


def test_create_without_reschedule_fails():
    """Agent creates a telehealth visit instead of rescheduling in place."""
    sm, sid, targets, initial, state = _setup_session()
    orig = initial.get_appointment(targets["next_appointment_id"])
    earliest = _provider_slots_sorted(initial, orig.provider_id)[0]
    state.appointments.append(_make_appt(
        id="appt_new_no_cancel",
        provider_id=orig.provider_id,
        datetime=earliest,
    ))

    task = get_task("pp_setup_telehealth")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "create-only trajectory must not satisfy in-place reschedule"
    assert report.score < 1.0
