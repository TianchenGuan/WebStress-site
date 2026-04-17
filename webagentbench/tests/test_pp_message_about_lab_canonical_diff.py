"""End-to-end tests for pp_message_about_lab canonical_diff.

Task: find the most recent HbA1c result, schedule exactly one follow-up
appointment with its ordering provider using that provider's next available
slot. Use reason exactly "HbA1c result follow-up". Do not send messages.

Trajectories covered:
- correct (ordering provider + earliest slot + exact reason) → passes 1.0
- wrong provider (any provider that did NOT order the latest HbA1c) → fails
- wrong reason (free-text mismatch) → fails
- not earliest slot (second-earliest slot of the ordering provider) → fails
- no mutation (do-nothing) → fails
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_message_about_lab",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _ordering_provider_id(initial) -> str:
    """Canonical selector: provider who ordered the most-recent HbA1c lab.

    Mirrors the `expr` predicate in the canonical_diff.
    """
    latest = max(
        (lab for lab in initial.lab_results if lab.test_name == "HbA1c"),
        key=lambda lab: lab.collected_at,
    )
    return latest.ordered_by


def _earliest_slot(initial, provider_id: str):
    for p in initial.providers:
        if p.id == provider_id:
            return min(s.datetime for s in p.available_slots)
    raise ValueError(f"provider {provider_id!r} missing from initial snapshot")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "HbA1c result follow-up")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    prov_id = _ordering_provider_id(initial)
    state.appointments.append(_make_appt(
        id="appt_new_hba1c_followup",
        provider_id=prov_id,
        datetime=_earliest_slot(initial, prov_id),
    ))

    task = get_task("pp_message_about_lab")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_provider_fails():
    """Scheduling with any provider other than the HbA1c orderer should fail."""
    sm, sid, targets, initial, state = _setup_session()
    prov_id = _ordering_provider_id(initial)
    # Any provider with available slots that is NOT the ordering provider.
    other = next(
        p for p in state.providers
        if p.id != prov_id and p.available_slots
    )
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task("pp_message_about_lab")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "booking with a non-ordering provider must fail — the `provider_id` "
        "expr pins to the HbA1c orderer."
    )


def test_wrong_reason_fails():
    """Appointment reason doesn't match the required exact string."""
    sm, sid, targets, initial, state = _setup_session()
    prov_id = _ordering_provider_id(initial)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_reason",
        provider_id=prov_id,
        datetime=_earliest_slot(initial, prov_id),
        reason="HbA1c follow-up",  # close but not exact
    ))

    task = get_task("pp_message_about_lab")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Correct provider + reason but using the 2nd-earliest slot should fail."""
    sm, sid, targets, initial, state = _setup_session()
    prov_id = _ordering_provider_id(initial)
    slots = sorted(
        s.datetime for p in initial.providers if p.id == prov_id for s in p.available_slots
    )
    assert len(slots) >= 2, (
        "seed must produce >=2 slots for the ordering provider for this test "
        "to be non-vacuous"
    )
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=prov_id,
        datetime=slots[1],  # second-earliest
    ))

    task = get_task("pp_message_about_lab")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_no_mutation_fails():
    """Do-nothing trajectory must not pass (hazard Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()
    # (no mutation)

    task = get_task("pp_message_about_lab")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — the positive create entry "
        "has no matching candidate."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"
