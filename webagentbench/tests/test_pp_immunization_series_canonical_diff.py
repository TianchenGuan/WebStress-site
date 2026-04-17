"""End-to-end tests for pp_immunization_series canonical_diff.

Bijection CREATE pattern: one Appointment per remaining-dose slot
(``target['remaining_dose_slots']``). Each appointment uses the same
administering provider as the first dose and references the series
vaccine in its ``reason`` field. Consecutive new appointments must be
at least ~1 month apart (enforced by the constraints block).
"""

from datetime import datetime, timezone, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


TASK_ID = "pp_immunization_series"


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id=TASK_ID,
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _snapshot_dict(snap):
    return snap.model_dump() if hasattr(snap, "model_dump") else snap


def _dt_in_series_window(targets: dict, offset_days: int):
    """Pick a datetime inside the series scheduling window."""
    start = datetime.fromisoformat(
        targets["series_window_start"].replace("Z", "+00:00")
    )
    return start + timedelta(days=offset_days)


def _make_appt(*, id: str, provider_id: str, reason: str, when) -> Appointment:
    return Appointment(
        id=id,
        provider_id=provider_id,
        datetime=when,
        type="in-person",
        status="scheduled",
        reason=reason,
    )


def _run(targets, initial, state):
    task = get_task(TASK_ID)
    # Pass pydantic models directly so constraint expressions can access
    # ``state.appointments`` (attribute-style, matching the schedule_annual_
    # physical precedent). compute_diff handles both dict and pydantic input.
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )


def test_correct_trajectory_passes():
    """Schedule every remaining dose with the series provider + proper spacing."""
    sm, sid, targets, initial, state = _setup_session()
    slots = targets["remaining_dose_slots"]
    assert slots, "seed did not emit any remaining_dose_slots"

    # Spaced >=31 days apart — safely above the 28-day floor.
    for i, slot in enumerate(slots):
        state.appointments.append(_make_appt(
            id=f"appt_new_{i}",
            provider_id=targets["series_admin_provider_id"],
            reason=f"Hepatitis B vaccine — {slot}",
            when=_dt_in_series_window(targets, 7 + i * 31),
        ))

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_vaccine_fails():
    """Agent scheduled unrelated (flu) shots — reason predicate rejects them."""
    sm, sid, targets, initial, state = _setup_session()
    slots = targets["remaining_dose_slots"]

    for i, _slot in enumerate(slots):
        state.appointments.append(_make_appt(
            id=f"appt_new_{i}",
            provider_id=targets["series_admin_provider_id"],
            reason="Flu shot",  # no hepatitis/vaccine/immunization keyword
            when=_dt_in_series_window(targets, 7 + i * 31),
        ))

    report = _run(targets, initial, state)
    assert report.passed is False


def test_partial_fails():
    """Only one of the remaining doses scheduled — bijection under-saturated."""
    sm, sid, targets, initial, state = _setup_session()
    slots = targets["remaining_dose_slots"]
    assert len(slots) >= 2, "seed needs >=2 remaining doses for this test"

    # Schedule only the first remaining dose.
    state.appointments.append(_make_appt(
        id="appt_new_0",
        provider_id=targets["series_admin_provider_id"],
        reason=f"Hepatitis B vaccine — {slots[0]}",
        when=_dt_in_series_window(targets, 7),
    ))

    report = _run(targets, initial, state)
    assert report.passed is False


def test_no_mutation_fails():
    """Do-nothing trajectory must not earn positive score."""
    sm, sid, targets, initial, state = _setup_session()
    # no mutation
    report = _run(targets, initial, state)
    assert report.passed is False
    assert report.score < 1.0, f"do-nothing got score {report.score}"
