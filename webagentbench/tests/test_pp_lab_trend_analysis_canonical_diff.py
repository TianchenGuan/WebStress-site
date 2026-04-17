"""End-to-end tests for pp_lab_trend_analysis canonical_diff.

Task: review HbA1c trend (seed guarantees upward trend, so always schedule).
Schedule exactly one follow-up appointment at the next available
*endocrinology* slot (pooled across all endocrinology providers) with
reason "HbA1c trend review". No messages, no prescription changes.

Trajectories covered:
- correct (earliest endocrinology slot, correct reason) → 1.0 pass
- scheduled PCP instead of endocrinology → fails provider predicate
- wrong appointment reason → fails reason predicate
- not earliest endocrinology slot → fails datetime expr
- modified a prescription → fails state.prescriptions invariant
- no mutation (did nothing) → fails (create unmatched)
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_lab_trend_analysis",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_endo_slot(initial, endo_ids):
    """Earliest datetime across all endocrinology providers' available slots."""
    endo_set = set(endo_ids)
    return min(
        s.datetime
        for p in initial.providers
        if p.id in endo_set
        for s in p.available_slots
    )


def _provider_with_slot(initial, endo_ids, target_dt):
    """Return an endo provider id whose available_slots include target_dt."""
    endo_set = set(endo_ids)
    for p in initial.providers:
        if p.id in endo_set and any(s.datetime == target_dt for s in p.available_slots):
            return p.id
    raise ValueError(f"no endo provider offers slot {target_dt}")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "HbA1c trend review")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    earliest = _earliest_endo_slot(initial, endo_ids)
    provider_id = _provider_with_slot(initial, endo_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_endo_trend_review",
        provider_id=provider_id,
        datetime=earliest,
    ))

    task = get_task("pp_lab_trend_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_scheduled_pcp_instead_fails():
    """Agent scheduled with the PCP instead of an endocrinologist — PCP is
    not in the endo pool, so the provider_id predicate must reject it."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    endo_ids = targets["endo_provider_ids"]
    assert pcp_id not in endo_ids, "test precondition: PCP must not be in endo pool"
    pcp = next(p for p in initial.providers if p.id == pcp_id)
    pcp_earliest = min(s.datetime for s in pcp.available_slots)
    state.appointments.append(_make_appt(
        id="appt_new_pcp_instead",
        provider_id=pcp_id,
        datetime=pcp_earliest,
    ))

    task = get_task("pp_lab_trend_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "PCP is not an endocrinologist; provider_id predicate must fail"
    )


def test_wrong_reason_fails():
    """Appointment reason not equal to the required exact string."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    earliest = _earliest_endo_slot(initial, endo_ids)
    provider_id = _provider_with_slot(initial, endo_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_reason",
        provider_id=provider_id,
        datetime=earliest,
        reason="HbA1c follow up",  # close but not exact
    ))

    task = get_task("pp_lab_trend_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Endocrinology appointment booked at a slot later than the pool-wide
    earliest slot."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    endo_set = set(endo_ids)
    slots = sorted(
        s.datetime
        for p in initial.providers
        if p.id in endo_set
        for s in p.available_slots
    )
    assert len(slots) >= 2, "seed must produce >=2 endo slots for this test"
    later = slots[-1]  # definitely not pool-earliest
    provider_id = _provider_with_slot(initial, endo_ids, later)
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=provider_id,
        datetime=later,
    ))

    task = get_task("pp_lab_trend_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_modified_prescription_fails():
    """Agent scheduled the correct appointment but also mutated an active
    prescription's status — invariant on state.prescriptions must fail."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    earliest = _earliest_endo_slot(initial, endo_ids)
    provider_id = _provider_with_slot(initial, endo_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_endo_correct",
        provider_id=provider_id,
        datetime=earliest,
    ))
    active_ids = set(targets["active_rx_ids"])
    rx = next(r for r in state.prescriptions if r.id in active_ids)
    rx.status = "discontinued"

    task = get_task("pp_lab_trend_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "prescription mutation must trip the state.prescriptions invariant"
    )


def test_no_mutation_fails():
    """Agent did nothing — create[0] unmatched, must fail."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("pp_lab_trend_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory passed — positive-pool check was not enforced"
    )
    assert report.score < 1.0, (
        f"do-nothing scored {report.score}, expected < 1.0 (Class 1 hazard)"
    )
