"""End-to-end tests for pp_lab_medication_loop canonical_diff.

Task: schedule exactly one endocrinology follow-up appointment at the
endocrinologist's next available slot with reason "Critical HbA1c
follow-up", without modifying medications, messages, labs, claims,
referrals, immunizations, pharmacies, or pre-existing appointments.

Trajectories covered:
- correct (earliest endo slot, endo provider + exact reason) → passes 1.0
- wrong provider (PCP instead of endo) → fails
- wrong reason string → fails
- not earliest endo slot → fails
- modified active prescription (critical invariant) → fails
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
        task_id="pp_lab_medication_loop",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_endo_slot(initial, endo_ids):
    endo_set = set(endo_ids)
    slots = [
        s.datetime
        for p in initial.providers
        if p.id in endo_set
        for s in p.available_slots
    ]
    if not slots:
        raise ValueError(f"no available slots for endo providers {endo_set!r}")
    return min(slots)


def _endo_provider_for_earliest(initial, endo_ids):
    endo_set = set(endo_ids)
    earliest = _earliest_endo_slot(initial, endo_ids)
    for p in initial.providers:
        if p.id in endo_set and any(s.datetime == earliest for s in p.available_slots):
            return p.id
    raise ValueError("no endo provider holds the earliest slot")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Critical HbA1c follow-up")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    provider_id = _endo_provider_for_earliest(initial, endo_ids)
    state.appointments.append(_make_appt(
        id="appt_new_hba1c_review",
        provider_id=provider_id,
        datetime=_earliest_endo_slot(initial, endo_ids),
    ))

    task = get_task("pp_lab_medication_loop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_provider_fails():
    """Appointment scheduled with the PCP (non-endo) — provider_id expr rejects it."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    # Use a PCP slot (the task says "not your PCP").
    pcp_slot = min(
        s.datetime for p in initial.providers if p.id == pcp_id for s in p.available_slots
    )
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=pcp_id,
        datetime=pcp_slot,
    ))

    task = get_task("pp_lab_medication_loop")
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
    endo_ids = targets["endo_provider_ids"]
    provider_id = _endo_provider_for_earliest(initial, endo_ids)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_reason",
        provider_id=provider_id,
        datetime=_earliest_endo_slot(initial, endo_ids),
        reason="HbA1c follow-up",  # missing "Critical" prefix
    ))

    task = get_task("pp_lab_medication_loop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Appointment uses an endo slot other than the earliest."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = set(targets["endo_provider_ids"])
    slots = sorted(
        s.datetime
        for p in initial.providers
        if p.id in endo_ids
        for s in p.available_slots
    )
    assert len(slots) >= 2, "seed must produce >=2 endo slots for this test"
    # Find an endo provider that has the second-earliest slot.
    second = slots[1]
    provider_id = next(
        p.id for p in initial.providers
        if p.id in endo_ids and any(s.datetime == second for s in p.available_slots)
    )
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=provider_id,
        datetime=second,
    ))

    task = get_task("pp_lab_medication_loop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_modified_prescription_fails():
    """Correct appointment but agent also discontinued an active prescription —
    the critical prescriptions invariant should fire."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    provider_id = _endo_provider_for_earliest(initial, endo_ids)
    state.appointments.append(_make_appt(
        id="appt_new_hba1c_review",
        provider_id=provider_id,
        datetime=_earliest_endo_slot(initial, endo_ids),
    ))
    active_ids = set(targets["active_rx_ids"])
    assert active_ids, "seed must produce active prescriptions"
    mutated = False
    for rx in state.prescriptions:
        if rx.id in active_ids:
            rx.status = "discontinued"
            mutated = True
            break
    assert mutated, "no active prescription found in state to mutate"

    task = get_task("pp_lab_medication_loop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "discontinuing an active prescription should violate the "
        "critical prescriptions invariant"
    )


def test_no_mutation_fails():
    """Agent does nothing — must score 0.0 and fail (no scheduled appointment)."""
    sm, sid, targets, initial, state = _setup_session()
    # state is untouched; no appointment created.

    task = get_task("pp_lab_medication_loop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "do-nothing trajectory must fail"
    assert report.score == 0.0, f"do-nothing score must be 0.0, got {report.score}"
