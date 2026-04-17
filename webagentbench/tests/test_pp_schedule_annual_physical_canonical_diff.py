"""End-to-end tests for pp_schedule_annual_physical canonical_diff.

Task: schedule an in-person annual physical with the PCP AND an in-person
pre-visit lab work appointment at least 3 days before the physical, without
touching any other collection.

Shape: two creates + constraint (3-day gap).

Trajectories covered:
- correct (both appointments in-person, lab >=3 days before physical) -> 1.0
- only physical, no lab -> fails
- only lab, no physical -> fails
- gap too small (lab < 3 days before physical) -> fails via constraint
- one appointment is telehealth -> fails type predicate
- no mutation (do-nothing) -> fails
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
        task_id="pp_schedule_annual_physical",
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
    """Pick a future datetime based off the latest existing upcoming apt."""
    latest = max(
        (a.datetime for a in initial.appointments if a.status == "scheduled"),
        default=None,
    )
    if latest is None:
        latest = min(
            s.datetime for p in initial.providers for s in p.available_slots
        )
    return latest + timedelta(days=days_ahead)


def _other_provider_id(state, pcp_id: str) -> str:
    """Pick a non-PCP provider id (e.g. for lab appointments)."""
    return next(p.id for p in state.providers if p.id != pcp_id)


def test_correct_trajectory_passes():
    """Both appointments created, in-person, lab 4 days before physical."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    physical_dt = _future_dt(initial, days_ahead=30)
    lab_dt = physical_dt - timedelta(days=4)
    state.appointments.append(_make_appt(
        id="appt_new_physical",
        provider_id=pcp_id,
        datetime=physical_dt,
        reason="Annual physical exam",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_lab",
        provider_id=_other_provider_id(state, pcp_id),
        datetime=lab_dt,
        reason="Pre-visit lab work / blood panel",
    ))

    task = get_task("pp_schedule_annual_physical")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_only_physical_fails():
    """Physical scheduled but no lab -> create[1] unmatched."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_physical_only",
        provider_id=pcp_id,
        datetime=_future_dt(initial, days_ahead=30),
        reason="Annual physical",
    ))

    task = get_task("pp_schedule_annual_physical")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "without a lab appointment, create[1] must remain unmatched"
    )
    assert report.score < 1.0


def test_only_lab_fails():
    """Lab scheduled but no physical -> create[0] unmatched."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_lab_only",
        provider_id=_other_provider_id(state, pcp_id),
        datetime=_future_dt(initial, days_ahead=26),
        reason="Pre-visit lab work",
    ))

    task = get_task("pp_schedule_annual_physical")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "without a physical appointment, create[0] must remain unmatched"
    )
    assert report.score < 1.0


def test_gap_too_small_fails():
    """Lab less than 3 days before physical -> constraint fails."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    physical_dt = _future_dt(initial, days_ahead=30)
    lab_dt = physical_dt - timedelta(days=1)  # only 1 day prior
    state.appointments.append(_make_appt(
        id="appt_new_physical_tight",
        provider_id=pcp_id,
        datetime=physical_dt,
        reason="Annual physical",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_lab_tight",
        provider_id=_other_provider_id(state, pcp_id),
        datetime=lab_dt,
        reason="Pre-visit lab draw",
    ))

    task = get_task("pp_schedule_annual_physical")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "lab within 3 days of physical must fail the 3-day-gap constraint"
    )


def test_telehealth_fails():
    """One appointment is telehealth -> type predicate fails."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    physical_dt = _future_dt(initial, days_ahead=30)
    lab_dt = physical_dt - timedelta(days=5)
    state.appointments.append(_make_appt(
        id="appt_new_physical_tele",
        provider_id=pcp_id,
        datetime=physical_dt,
        type="telehealth",  # violates type predicate on create[0]
        reason="Annual physical",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_lab_inperson",
        provider_id=_other_provider_id(state, pcp_id),
        datetime=lab_dt,
        reason="Pre-visit lab work",
    ))

    task = get_task("pp_schedule_annual_physical")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "telehealth physical must fail the type: in-person predicate"
    )


def test_no_mutation_fails():
    """Do-nothing trajectory must not pass."""
    sm, sid, targets, initial, state = _setup_session()
    # no mutation

    task = get_task("pp_schedule_annual_physical")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "no-op trajectory must fail"
    assert report.score < 1.0
