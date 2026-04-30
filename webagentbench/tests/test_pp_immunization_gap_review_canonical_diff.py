"""Regression coverage for pp_immunization_gap_review canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


TASK_ID = "pp_immunization_gap_review"


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


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Immunization")
    return Appointment(**kwargs)


def _run(targets, initial, state):
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _window_start(targets):
    return datetime.fromisoformat(targets["window_start"].replace("Z", "+00:00"))


def test_gap_review_correct_provider_and_window_passes():
    sm, sid, targets, initial, state = _setup_session()
    when = _window_start(targets) + timedelta(days=7)

    for imm_id in targets["due_imm_ids"]:
        state.appointments.append(_make_appt(
            id=f"appt_gap_{imm_id}",
            provider_id=targets["admin_providers"][imm_id][0],
            datetime=when,
        ))

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"


def test_gap_review_out_of_window_fails():
    sm, sid, targets, initial, state = _setup_session()
    when = _window_start(targets) - timedelta(days=1)

    for imm_id in targets["due_imm_ids"]:
        state.appointments.append(_make_appt(
            id=f"appt_gap_early_{imm_id}",
            provider_id=targets["admin_providers"][imm_id][0],
            datetime=when,
        ))

    report = _run(targets, initial, state)
    assert report.passed is False
