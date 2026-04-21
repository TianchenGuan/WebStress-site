"""End-to-end tests for pp_emergency_prep canonical_diff.

Task: review the emergency action plan. The only write action is scheduling
*exactly one* PCP appointment with reason "Medication wallet card review" at
that PCP's next available slot, with appointment notes listing every allergy
on the patient profile (this forces the agent to actually read the profile
rather than skip the verification steps). Must not modify profile fields,
prescriptions, or send messages.

Shape: one non-bijection create + three read-only constraints + invariants.

Trajectories covered:
- correct (PCP + earliest PCP slot + exact reason + allergies-in-notes + profile intact) -> 1.0
- wrong_provider (booked with non-PCP provider) -> fails
- wrong_reason (booked with other reason text) -> fails
- not_earliest_slot (PCP correct, second-earliest slot) -> fails
- missing_allergies_in_notes (correct booking but notes omit allergies) -> fails
- allergy_dropped (correct booking, but drops a seeded allergy) -> fails
- message_sent (correct booking, but also sends a patient message) -> fails
- no_mutation (empty trajectory) -> fails, score 0.0
"""

from webagentbench.backend.models.patient_portal import (
    Appointment,
    ClinicalMessage,
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_emergency_prep",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _pcp_earliest_slot(initial, targets):
    pcp_id = targets["pcp_id"]
    for p in initial.providers:
        if p.id == pcp_id:
            return min(s.datetime for s in p.available_slots)
    raise ValueError(f"PCP {pcp_id!r} missing from initial snapshot")


def _pcp_sorted_slots(initial, targets):
    pcp_id = targets["pcp_id"]
    for p in initial.providers:
        if p.id == pcp_id:
            return sorted(s.datetime for s in p.available_slots)
    raise ValueError(f"PCP {pcp_id!r} missing from initial snapshot")


def _allergies_notes(initial) -> str:
    """Comma-joined allergies matching the canonical-diff notes check."""
    return ", ".join(initial.patient.allergies)


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Medication wallet card review")
    return Appointment(**kwargs)


def _run_match(state, initial, targets):
    task = get_task("pp_emergency_prep")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.appointments.append(_make_appt(
        id="appt_new_wallet_card",
        provider_id=targets["pcp_id"],
        datetime=_pcp_earliest_slot(initial, targets),
        notes=f"Allergies to cross-check: {_allergies_notes(initial)}",
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_allergies_in_notes_fails():
    """Correct booking but the agent skipped reading the profile — notes do
    not contain the seeded allergies → canonical-diff notes check fails."""
    sm, sid, targets, initial, state = _setup_session()
    state.appointments.append(_make_appt(
        id="appt_new_wallet_card",
        provider_id=targets["pcp_id"],
        datetime=_pcp_earliest_slot(initial, targets),
        notes="Wallet card follow-up (no allergies listed)",
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_wrong_provider_fails():
    """Agent booked with a non-PCP provider."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    other = next(
        (p for p in state.providers if p.id != pcp_id and p.available_slots),
        None,
    )
    assert other is not None, "seed lacks a non-PCP provider with slots"
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_wrong_reason_fails():
    """Agent booked the PCP at the earliest slot but with the wrong reason."""
    sm, sid, targets, initial, state = _setup_session()
    state.appointments.append(_make_appt(
        id="appt_new_wrong_reason",
        provider_id=targets["pcp_id"],
        datetime=_pcp_earliest_slot(initial, targets),
        reason="Medication review",  # not "Medication wallet card review"
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Correct PCP and reason but booked at the second-earliest slot."""
    sm, sid, targets, initial, state = _setup_session()
    slots = _pcp_sorted_slots(initial, targets)
    assert len(slots) >= 2, "PCP must have >= 2 slots for this test"
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=targets["pcp_id"],
        datetime=slots[1],
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_allergy_dropped_fails():
    """Correct booking but agent removed a seeded allergy -> constraint fails."""
    sm, sid, targets, initial, state = _setup_session()
    state.appointments.append(_make_appt(
        id="appt_new_wallet_card",
        provider_id=targets["pcp_id"],
        datetime=_pcp_earliest_slot(initial, targets),
        notes=f"Allergies to cross-check: {_allergies_notes(initial)}",
    ))
    assert state.patient.allergies, "seed must populate at least one allergy"
    state.patient.allergies = state.patient.allergies[1:]
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_message_sent_fails():
    """Correct booking but agent also sends a clinical message -> invariant fails."""
    from datetime import datetime, timezone
    sm, sid, targets, initial, state = _setup_session()
    state.appointments.append(_make_appt(
        id="appt_new_wallet_card",
        provider_id=targets["pcp_id"],
        datetime=_pcp_earliest_slot(initial, targets),
        notes=f"Allergies to cross-check: {_allergies_notes(initial)}",
    ))
    state.messages.append(ClinicalMessage(
        id="msg_patient_extra",
        from_type="patient",
        provider_id=targets["pcp_id"],
        subject="Emergency plan question",
        body="Can you confirm my contacts?",
        thread_id="thread_new",
        timestamp=datetime.now(timezone.utc),
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_no_mutation_fails():
    """Do-nothing trajectory must not pass."""
    sm, sid, targets, initial, state = _setup_session()
    report = _run_match(state, initial, targets)
    assert report.passed is False
    assert report.score == 0.0, f"expected 0.0 (no-op), got {report.score}"
