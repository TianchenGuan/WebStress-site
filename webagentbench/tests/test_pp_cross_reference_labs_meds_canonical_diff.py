"""End-to-end tests for pp_cross_reference_labs_meds canonical_diff.

Task: schedule exactly one PCP appointment at the next available slot with
reason "Drug interaction and abnormal lab review", without touching
prescriptions (critical), messages, labs, claims, referrals, or
pre-existing appointments.

Trajectories covered:
- correct (earliest slot, correct provider + reason) → passes 1.0
- wrong provider (not PCP) → fails
- wrong reason (free-text mismatch) → fails
- not earliest slot → fails
- discontinued interacting Rx (critical invariant) → fails
- no mutation (do-nothing) → fails with score 0.0
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_cross_reference_labs_meds",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_slot(initial, pcp_id: str):
    for p in initial.providers:
        if p.id == pcp_id:
            return min(s.datetime for s in p.available_slots)
    raise ValueError(f"PCP {pcp_id!r} missing from initial snapshot")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Drug interaction and abnormal lab review")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_xref_review",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
    ))

    task = get_task("pp_cross_reference_labs_meds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_provider_fails():
    """Appointment scheduled with a non-PCP provider — expr on provider_id fails."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    other = next(p for p in state.providers if p.id != pcp_id and p.available_slots)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task("pp_cross_reference_labs_meds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_reason_fails():
    """Appointment reason doesn't match the required exact string."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_wrong_reason",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
        reason="Drug interaction review",  # missing the lab clause
    ))

    task = get_task("pp_cross_reference_labs_meds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Appointment uses a PCP slot other than the earliest."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    slots = sorted(
        (s.datetime for p in initial.providers if p.id == pcp_id for s in p.available_slots)
    )
    assert len(slots) >= 2, "seed must produce >=2 PCP slots for this test"
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=pcp_id,
        datetime=slots[1],  # second-earliest
    ))

    task = get_task("pp_cross_reference_labs_meds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_discontinued_rx_fails():
    """Correct appointment but agent also discontinued an interacting Rx —
    the critical prescriptions invariant should fire."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    state.appointments.append(_make_appt(
        id="appt_new_xref_review",
        provider_id=pcp_id,
        datetime=_earliest_slot(initial, pcp_id),
    ))
    interacting_ids = set(targets["interacting_rx_ids"])
    assert interacting_ids, "seed must produce interacting prescriptions"
    mutated = False
    for rx in state.prescriptions:
        if rx.id in interacting_ids:
            rx.status = "discontinued"
            mutated = True
            break
    assert mutated, "no interacting prescription found in state to mutate"

    task = get_task("pp_cross_reference_labs_meds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "discontinuing an interacting prescription should violate the "
        "critical prescriptions invariant"
    )


def test_no_mutation_fails():
    """Agent does nothing — must score 0.0 and fail (no scheduled appointment)."""
    sm, sid, targets, initial, state = _setup_session()
    # state is untouched; no appointment created.

    task = get_task("pp_cross_reference_labs_meds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "do-nothing trajectory must fail"
    assert report.score == 0.0, f"do-nothing score must be 0.0, got {report.score}"
