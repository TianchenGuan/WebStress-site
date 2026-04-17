"""End-to-end tests for pp_care_gap_analysis canonical_diff.

Shape: three non-bijection creates on Appointment (cardiology, endocrinology, PCP)
with exact reason strings and specialty-pool / PCP-id predicates.
"""

from datetime import timedelta

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_care_gap_analysis",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_slot(initial, provider_id):
    for p in initial.providers:
        if p.id == provider_id:
            return min(s.datetime for s in p.available_slots)
    raise ValueError(f"provider {provider_id!r} not found or has no slots")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    return Appointment(**kwargs)


def _seed_three_creates(targets, initial, state):
    cardio_id = targets["cardio_provider_ids"][0]
    endo_id = targets["endo_provider_ids"][0]
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_cardio_gap",
        provider_id=cardio_id,
        datetime=_earliest_slot(initial, cardio_id),
        reason="Atrial fibrillation care gap",
    ))
    state.appointments.append(_make_appt(
        id="appt_endo_gap",
        provider_id=endo_id,
        datetime=_earliest_slot(initial, endo_id),
        reason="Diabetes care gap",
    ))
    state.appointments.append(_make_appt(
        id="appt_pcp_gap",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
        reason="Abnormal lab follow-up",
    ))


def _run_match(state, initial, targets):
    task = get_task("pp_care_gap_analysis")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _seed_three_creates(targets, initial, state)
    report = _run_match(state, initial, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_cardiology_fails():
    sm, sid, targets, initial, state = _setup_session()
    endo_id = targets["endo_provider_ids"][0]
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_endo_gap",
        provider_id=endo_id,
        datetime=_earliest_slot(initial, endo_id),
        reason="Diabetes care gap",
    ))
    state.appointments.append(_make_appt(
        id="appt_pcp_gap",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
        reason="Abnormal lab follow-up",
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_reason_fails():
    sm, sid, targets, initial, state = _setup_session()
    _seed_three_creates(targets, initial, state)
    # Change the cardiology reason to something off-spec
    for a in state.appointments:
        if a.id == "appt_cardio_gap":
            a.reason = "AFib checkup"
            break
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_wrong_specialty_fails():
    sm, sid, targets, initial, state = _setup_session()
    # Swap cardiology create to use an endo provider
    endo_id = targets["endo_provider_ids"][0]
    state.appointments.append(_make_appt(
        id="appt_wrong_specialty",
        provider_id=endo_id,
        datetime=_earliest_slot(initial, endo_id),
        reason="Atrial fibrillation care gap",
    ))
    # Legitimate endo + pcp
    state.appointments.append(_make_appt(
        id="appt_endo_gap",
        provider_id=endo_id,
        datetime=_earliest_slot(initial, endo_id) + timedelta(days=1),
        reason="Diabetes care gap",
    ))
    state.appointments.append(_make_appt(
        id="appt_pcp_gap",
        provider_id=targets["pcp_id"],
        datetime=_earliest_slot(initial, targets["pcp_id"]),
        reason="Abnormal lab follow-up",
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_modified_rx_fails():
    sm, sid, targets, initial, state = _setup_session()
    _seed_three_creates(targets, initial, state)
    # Modify a prescription → violates invariant[1]
    if state.prescriptions:
        state.prescriptions[0].status = "discontinued"
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()
    report = _run_match(state, initial, targets)
    assert report.passed is False
    assert report.score == 0.0
