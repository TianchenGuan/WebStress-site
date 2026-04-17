"""End-to-end tests for pp_resolve_specialist_conflicts canonical_diff.

Task: "You have two specialist appointments scheduled at overlapping times.
Identify which appointment was booked more recently and reschedule that one
to the next available slot with the same provider. Keep the earlier-booked
appointment unchanged."

Shape: update + create combo — cancel the later-booked of two conflicting
specialist appointments and create a replacement with the same provider at
the earliest available slot.

Trajectories covered:
  - correct: cancel later-booked + create new appt at earliest slot with
    same provider → 1.0
  - wrong appt cancelled (earlier-booked) → fails
  - wrong provider for new appt → fails
  - replacement not at earliest slot → fails
  - only cancel, no create → fails
  - do-nothing → fails
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_resolve_specialist_conflicts",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _later_booked_apt_id(initial, targets) -> str:
    """Replicate the canonical selector: max by (booked_at, aid)."""
    return max(
        targets["conflict_apt_ids"],
        key=lambda aid: (initial.get_appointment(aid).booked_at, aid),
    )


def _earlier_booked_apt_id(initial, targets) -> str:
    later = _later_booked_apt_id(initial, targets)
    return next(aid for aid in targets["conflict_apt_ids"] if aid != later)


def _cancel_apt(state, apt_id: str) -> None:
    for apt in state.appointments:
        if apt.id == apt_id:
            apt.status = "cancelled"
            return
    raise ValueError(f"appointment {apt_id!r} not found in session state")


def _earliest_slot_datetime(initial, provider_id: str):
    prov = next(p for p in initial.providers if p.id == provider_id)
    return min(s.datetime for s in prov.available_slots)


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Specialist follow-up")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    """Cancel the later-booked conflict appt + create replacement with the
    same provider at the earliest available slot."""
    sm, sid, targets, initial, state = _setup_session()
    later = _later_booked_apt_id(initial, targets)
    later_apt = initial.get_appointment(later)
    _cancel_apt(state, later)
    state.appointments.append(_make_appt(
        id="appt_resched_correct",
        provider_id=later_apt.provider_id,
        datetime=_earliest_slot_datetime(initial, later_apt.provider_id),
    ))

    task = get_task("pp_resolve_specialist_conflicts")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_apt_cancelled_fails():
    """Agent cancels the EARLIER-booked conflict appt (not the later one).
    Even with a correct-looking create, the where selector rejects."""
    sm, sid, targets, initial, state = _setup_session()
    later = _later_booked_apt_id(initial, targets)
    earlier = _earlier_booked_apt_id(initial, targets)
    earlier_apt = initial.get_appointment(earlier)
    later_apt = initial.get_appointment(later)
    _cancel_apt(state, earlier)
    # Create a replacement with later's provider at earliest slot (looks valid
    # for the create predicate but the update selector still targets `later`).
    state.appointments.append(_make_appt(
        id="appt_resched_wrong_cancel",
        provider_id=later_apt.provider_id,
        datetime=_earliest_slot_datetime(initial, later_apt.provider_id),
    ))

    task = get_task("pp_resolve_specialist_conflicts")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling the earlier-booked conflict appt must fail — the update "
        "`where` selector picks only the later-booked one, and the earlier one "
        "is protected by the filtered appointments invariant."
    )


def test_wrong_provider_fails():
    """Agent cancels correctly but schedules the replacement with a
    DIFFERENT provider (e.g. the earlier-booked conflict's provider)."""
    sm, sid, targets, initial, state = _setup_session()
    later = _later_booked_apt_id(initial, targets)
    earlier = _earlier_booked_apt_id(initial, targets)
    earlier_apt = initial.get_appointment(earlier)
    _cancel_apt(state, later)
    # Use the OTHER conflict appt's provider — violates the provider_id expr.
    state.appointments.append(_make_appt(
        id="appt_resched_wrong_provider",
        provider_id=earlier_apt.provider_id,
        datetime=_earliest_slot_datetime(initial, earlier_apt.provider_id),
    ))

    task = get_task("pp_resolve_specialist_conflicts")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "replacement with the wrong provider must fail create[0].provider_id "
        "expr predicate."
    )


def test_not_earliest_slot_fails():
    """Agent cancels correctly and uses the right provider, but books a slot
    that is NOT the earliest available."""
    sm, sid, targets, initial, state = _setup_session()
    later = _later_booked_apt_id(initial, targets)
    later_apt = initial.get_appointment(later)
    prov = next(p for p in initial.providers if p.id == later_apt.provider_id)
    slots_sorted = sorted(prov.available_slots, key=lambda s: s.datetime)
    assert len(slots_sorted) >= 2, (
        "seed must expose at least two available slots for the wrong-slot test"
    )
    non_earliest = slots_sorted[1].datetime
    _cancel_apt(state, later)
    state.appointments.append(_make_appt(
        id="appt_resched_wrong_slot",
        provider_id=later_apt.provider_id,
        datetime=non_earliest,
    ))

    task = get_task("pp_resolve_specialist_conflicts")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "replacement at a non-earliest slot must fail create[0].datetime "
        "expr predicate."
    )


def test_only_cancel_no_create_fails():
    """Agent cancels the later-booked appt but forgets to reschedule."""
    sm, sid, targets, initial, state = _setup_session()
    later = _later_booked_apt_id(initial, targets)
    _cancel_apt(state, later)

    task = get_task("pp_resolve_specialist_conflicts")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancel-only trajectory must fail — create[0] has no matched candidate."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_no_mutation_fails():
    """Agent does nothing. Both update[0] and create[0] have no candidates."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("pp_resolve_specialist_conflicts")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — both positive entries have "
        "no matching candidate (hazard Class 1 regression guard)."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"
