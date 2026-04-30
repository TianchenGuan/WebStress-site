"""End-to-end tests for pp_cancel_reschedule canonical_diff.

Task: cancel the target dermatology appointment AND schedule a replacement
at a time that does not conflict with other upcoming appointments.

Shape: update + create combo — new structural shape for the pilot corpus.

Trajectories covered:
- correct: cancel target + create non-conflicting replacement → 1.0
- non-conflicting create but wrong target cancelled → fails
- correct cancel but replacement collides with another upcoming apt → fails
- only cancel, no replacement → partial (update passes, create fails)
- only create, no cancel → partial
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_cancel_reschedule",
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
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Dermatology follow-up")
    return Appointment(**kwargs)


def _target_derm_provider(initial, targets):
    target_apt = next(a for a in initial.appointments if a.id == targets["target_apt_id"])
    provider = next(p for p in initial.providers if p.id == target_apt.provider_id)
    assert provider.specialty == "dermatology"
    return provider


def _approved_derm_referral_id(initial, targets):
    approved = set(targets["approved_ref_ids"])
    for r in initial.referrals:
        if r.id in approved and r.status == "approved" and r.to_specialty == "dermatology":
            return r.id
    raise AssertionError("seed did not produce an approved dermatology referral")


def _non_conflicting_slot(initial, targets):
    """Pick an actual target-dermatologist slot that doesn't collide."""
    provider = _target_derm_provider(initial, targets)
    others = [a for a in initial.appointments
              if a.status == "scheduled"
              and a.id in targets["upcoming_ids"]
              and a.id != targets["target_apt_id"]]
    occupied = {a.datetime for a in others}
    slot = next((s for s in provider.available_slots if s.datetime not in occupied), None)
    assert slot is not None, "seed did not produce a non-conflicting dermatology slot"
    return slot.datetime


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _cancel(state, targets["target_apt_id"])
    new_time = _non_conflicting_slot(initial, targets)
    orig = next(a for a in initial.appointments if a.id == targets["target_apt_id"])
    state.appointments.append(_make_appt(
        id="appt_reschedule_new",
        provider_id=orig.provider_id,
        datetime=new_time,
        linked_referral_id=_approved_derm_referral_id(initial, targets),
    ))

    task = get_task("pp_cancel_reschedule")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_target_cancelled_fails():
    """Agent cancels a non-target upcoming appointment and creates a replacement."""
    sm, sid, targets, initial, state = _setup_session()
    other_id = next(i for i in targets["upcoming_ids"] if i != targets["target_apt_id"])
    _cancel(state, other_id)
    new_time = _non_conflicting_slot(initial, targets)
    orig = next(a for a in initial.appointments if a.id == targets["target_apt_id"])
    state.appointments.append(_make_appt(
        id="appt_new_wrong_cancel",
        provider_id=orig.provider_id,
        datetime=new_time,
        linked_referral_id=_approved_derm_referral_id(initial, targets),
    ))

    task = get_task("pp_cancel_reschedule")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling the wrong appointment should fail the update's where "
        "selector and the filtered invariant on other upcoming apts"
    )


def test_replacement_conflicts_with_other_upcoming_fails():
    """Agent cancels correctly but schedules the replacement at an existing upcoming time."""
    sm, sid, targets, initial, state = _setup_session()
    _cancel(state, targets["target_apt_id"])
    other = next(a for a in initial.appointments
                 if a.id in targets["upcoming_ids"]
                 and a.id != targets["target_apt_id"]
                 and a.status == "scheduled")
    orig = next(a for a in initial.appointments if a.id == targets["target_apt_id"])
    state.appointments.append(_make_appt(
        id="appt_reschedule_collision",
        provider_id=orig.provider_id,
        datetime=other.datetime,
        linked_referral_id=_approved_derm_referral_id(initial, targets),
    ))

    task = get_task("pp_cancel_reschedule")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "replacement at a time that collides with another upcoming appt "
        "must fail the create[0] datetime expr predicate"
    )


def test_only_cancel_no_replacement_fails():
    """Agent cancels but never schedules a replacement."""
    sm, sid, targets, initial, state = _setup_session()
    _cancel(state, targets["target_apt_id"])

    task = get_task("pp_cancel_reschedule")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "no replacement created → create[0] unmatched"
    assert report.score < 1.0


def test_only_create_no_cancel_fails():
    """Agent schedules a new appt but forgets to cancel the original."""
    sm, sid, targets, initial, state = _setup_session()
    new_time = _non_conflicting_slot(initial, targets)
    orig = next(a for a in initial.appointments if a.id == targets["target_apt_id"])
    state.appointments.append(_make_appt(
        id="appt_new_no_cancel",
        provider_id=orig.provider_id,
        datetime=new_time,
        linked_referral_id=_approved_derm_referral_id(initial, targets),
    ))

    task = get_task("pp_cancel_reschedule")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "update[0] unmatched without the cancel mutation"
    assert report.score < 1.0


def test_replacement_with_wrong_provider_fails():
    """Replacement must stay with the seeded dermatology provider/referral slot."""
    sm, sid, targets, initial, state = _setup_session()
    _cancel(state, targets["target_apt_id"])
    wrong = next(
        p for p in initial.providers
        if p.id != _target_derm_provider(initial, targets).id and p.available_slots
    )
    state.appointments.append(_make_appt(
        id="appt_wrong_provider",
        provider_id=wrong.id,
        datetime=wrong.available_slots[0].datetime,
        linked_referral_id=_approved_derm_referral_id(initial, targets),
    ))

    task = get_task("pp_cancel_reschedule")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong replacement provider must fail"
