"""End-to-end tests for pp_wellness_visit_prep canonical_diff.

PCP wellness appt + bijections over due vaccines and overdue screenings.
"""

from datetime import datetime, timezone, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_wellness_visit_prep",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _snapshot_dict(snap):
    return snap.model_dump() if hasattr(snap, "model_dump") else snap


def _make_appt(*, id: str, provider_id: str, reason: str, offset_days: int = 7) -> Appointment:
    when = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return Appointment(
        id=id,
        provider_id=provider_id,
        datetime=when,
        type="in-person",
        status="scheduled",
        reason=reason,
    )


def _run(targets, initial, state):
    task = get_task("pp_wellness_visit_prep")
    final = state.model_dump()
    initial_dict = _snapshot_dict(initial)
    agent_diff = compute_diff(initial_dict, final)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial_dict, final=final,
    )


def _schedule_all_correct(targets, state):
    """Schedule PCP wellness + all due vaccines + all overdue screenings."""
    state.appointments.append(_make_appt(
        id="appt_pcp_wellness",
        provider_id=targets["pcp_id"],
        reason="Annual wellness visit",
    ))
    for i, name in enumerate(targets["due_vaccine_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_vax_{i}",
            provider_id=targets["pcp_id"],
            reason=name,
            offset_days=14 + i,
        ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}",
            provider_id=targets["pcp_id"],
            reason=name,
            offset_days=30 + i,
        ))


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    assert targets["due_vaccine_names"], "seed did not emit any due vaccines"
    assert targets["overdue_screening_names"], "seed did not emit any overdue screenings"

    _schedule_all_correct(targets, state)

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_wellness_apt_fails():
    """Vaccines and screenings scheduled, but no PCP wellness appt."""
    sm, sid, targets, initial, state = _setup_session()

    for i, name in enumerate(targets["due_vaccine_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_vax_{i}",
            provider_id=targets["pcp_id"],
            reason=name,
            offset_days=14 + i,
        ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}",
            provider_id=targets["pcp_id"],
            reason=name,
            offset_days=30 + i,
        ))

    report = _run(targets, initial, state)
    assert report.passed is False


def test_missing_vaccine_apt_fails():
    """PCP wellness + screenings scheduled, but no vaccine appts."""
    sm, sid, targets, initial, state = _setup_session()

    state.appointments.append(_make_appt(
        id="appt_pcp_wellness",
        provider_id=targets["pcp_id"],
        reason="Annual wellness visit",
    ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}",
            provider_id=targets["pcp_id"],
            reason=name,
            offset_days=30 + i,
        ))

    report = _run(targets, initial, state)
    assert report.passed is False


def test_wrong_vaccine_reason_fails():
    """Vaccine appts scheduled with reasons that match no vaccine name."""
    sm, sid, targets, initial, state = _setup_session()

    state.appointments.append(_make_appt(
        id="appt_pcp_wellness",
        provider_id=targets["pcp_id"],
        reason="Annual wellness visit",
    ))
    for i, _name in enumerate(targets["due_vaccine_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_vax_{i}",
            provider_id=targets["pcp_id"],
            reason="Immunization catch-up",  # doesn't match any vaccine name
            offset_days=14 + i,
        ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}",
            provider_id=targets["pcp_id"],
            reason=name,
            offset_days=30 + i,
        ))

    report = _run(targets, initial, state)
    assert report.passed is False


def test_no_mutation_fails():
    """Agent did nothing — must fail."""
    sm, sid, targets, initial, state = _setup_session()
    # no mutation
    report = _run(targets, initial, state)
    assert report.passed is False
    assert report.score < 1.0, f"do-nothing got score {report.score}"
