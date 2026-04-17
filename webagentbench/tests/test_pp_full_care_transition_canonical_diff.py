"""End-to-end tests for pp_full_care_transition canonical_diff.

Task: continuity-of-care review across three providers:
  1) Schedule one PCP appointment with reason "Care continuity review".
  2) Schedule one cardiology appointment with reason
     "Cardiology continuity visit".
  3) Schedule one endocrinology appointment with reason
     "Endocrinology continuity visit".

Shape: three independent creates (one per specialty), no bijection.
Instruction also forbids messages, cancellations, and prescription changes.

Trajectories covered:
- correct (all three with exact reasons) -> passes 1.0
- wrong PCP reason string -> create[0] unmatched, fails
- missing cardiology appointment -> create[1] unmatched, fails
- cancelled an existing specialist appointment -> fails invariant[0]
- sent a patient message -> fails invariant[2]
- no mutation (do-nothing) -> fails
"""

from datetime import timedelta

from webagentbench.backend.models.patient_portal import Appointment, ClinicalMessage
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_full_care_transition",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    return Appointment(**kwargs)


def _future_dt(initial, *, days_ahead: int):
    """Pick a future datetime anchored off the latest existing slot."""
    latest = max(
        (a.datetime for a in initial.appointments if a.status == "scheduled"),
        default=None,
    )
    if latest is None:
        latest = min(
            s.datetime for p in initial.providers for s in p.available_slots
        )
    return latest + timedelta(days=days_ahead)


def _schedule_all_three(state, targets, initial):
    """Append the three correct appointments onto state."""
    pcp_id = targets["pcp_id"]
    cardio_ids = list(targets["cardio_provider_ids"])
    endo_ids = list(targets["endo_provider_ids"])

    base_dt = _future_dt(initial, days_ahead=10)

    state.appointments.append(_make_appt(
        id="appt_new_pcp",
        provider_id=pcp_id,
        datetime=base_dt,
        reason="Care continuity review",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_cardio",
        provider_id=cardio_ids[0],
        datetime=base_dt + timedelta(days=3),
        reason="Cardiology continuity visit",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_endo",
        provider_id=endo_ids[0],
        datetime=base_dt + timedelta(days=6),
        reason="Endocrinology continuity visit",
    ))


def test_correct_trajectory_passes():
    """All three continuity-review appointments scheduled correctly."""
    sm, sid, targets, initial, state = _setup_session()
    _schedule_all_three(state, targets, initial)

    task = get_task("pp_full_care_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_pcp_reason_fails():
    """PCP booked with the wrong reason string -> create[0] unmatched."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_ids = list(targets["cardio_provider_ids"])
    endo_ids = list(targets["endo_provider_ids"])

    base_dt = _future_dt(initial, days_ahead=10)
    state.appointments.append(_make_appt(
        id="appt_new_pcp",
        provider_id=pcp_id,
        datetime=base_dt,
        reason="Annual physical",  # wrong reason
    ))
    state.appointments.append(_make_appt(
        id="appt_new_cardio",
        provider_id=cardio_ids[0],
        datetime=base_dt + timedelta(days=3),
        reason="Cardiology continuity visit",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_endo",
        provider_id=endo_ids[0],
        datetime=base_dt + timedelta(days=6),
        reason="Endocrinology continuity visit",
    ))

    task = get_task("pp_full_care_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong PCP reason string must leave create[0] unmatched"
    )
    assert report.score < 1.0


def test_missing_cardiology_fails():
    """Only PCP + endo scheduled, no cardiology -> create[1] unmatched."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    endo_ids = list(targets["endo_provider_ids"])

    base_dt = _future_dt(initial, days_ahead=10)
    state.appointments.append(_make_appt(
        id="appt_new_pcp",
        provider_id=pcp_id,
        datetime=base_dt,
        reason="Care continuity review",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_endo",
        provider_id=endo_ids[0],
        datetime=base_dt + timedelta(days=6),
        reason="Endocrinology continuity visit",
    ))

    task = get_task("pp_full_care_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "missing cardiology appointment must leave create[1] unmatched"
    )
    assert report.score < 1.0


def test_cancelled_existing_appointment_fails():
    """Correct three creates but cancels a pre-existing appointment -> invariant[0] fails."""
    sm, sid, targets, initial, state = _setup_session()
    _schedule_all_three(state, targets, initial)

    # Mutate a pre-existing upcoming appointment (cancelled) — this should
    # trip the "existing appointments preserved" invariant.
    upcoming_ids = list(targets.get("upcoming_ids") or [])
    assert upcoming_ids, "seed did not emit any upcoming_ids — fixture drift"
    target_apt = next(a for a in state.appointments if a.id == upcoming_ids[0])
    target_apt.status = "cancelled"

    task = get_task("pp_full_care_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling an existing appointment must fail the preserve-existing invariant"
    )


def test_sent_message_fails():
    """Correct three creates but agent also sends a patient message -> invariant[2] fails."""
    sm, sid, targets, initial, state = _setup_session()
    _schedule_all_three(state, targets, initial)

    # Append a new patient->provider message — explicitly forbidden.
    state.messages.append(ClinicalMessage(
        id="msg_new_extra",
        from_type="patient",
        provider_id=targets["pcp_id"],
        subject="Quick question",
        body="Just wanted to confirm my appointments.",
        thread_id="thread_new",
    ))

    task = get_task("pp_full_care_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "sending any new patient message must trip the messages-preserved invariant"
    )


def test_no_mutation_fails():
    """Do-nothing trajectory must not pass (regression guard for Class 1)."""
    sm, sid, targets, initial, state = _setup_session()
    # no mutation

    task = get_task("pp_full_care_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "no-op trajectory must fail"
    assert report.score < 1.0
