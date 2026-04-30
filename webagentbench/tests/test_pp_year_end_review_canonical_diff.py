"""End-to-end tests for pp_year_end_review canonical_diff.

Task: comprehensive year-end health review — schedule one appointment per
due immunization (reason = vaccine name), one per overdue screening
(reason = screening name), one specialist follow-up on the expiring
referral (reason = "Expiring referral follow-up"), and appeal every
denied insurance claim that has an available EOB.
"""

from datetime import datetime, timezone, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_year_end_review',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _snapshot_dict(snap):
    return snap.model_dump() if hasattr(snap, "model_dump") else snap


def _make_appt(
    *, id: str, provider_id: str, reason: str,
    offset_days: int = 7, linked_referral_id: str | None = None,
) -> Appointment:
    when = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return Appointment(
        id=id,
        provider_id=provider_id,
        datetime=when,
        type="in-person",
        status="scheduled",
        reason=reason,
        linked_referral_id=linked_referral_id,
    )


def _appeal_claim(state, clm_id: str) -> None:
    for c in state.claims:
        if c.id == clm_id:
            c.status = "appealed"
            return
    raise ValueError(f"claim {clm_id!r} not found")


def _expiring_ref(initial, targets):
    return next(r for r in initial.referrals if r.id == targets["expiring_ref_id"])


def _specialist_provider(initial, targets):
    ref = _expiring_ref(initial, targets)
    return next(p for p in initial.providers if p.specialty == ref.to_specialty)


def _run(targets, initial, state):
    task = get_task("pp_year_end_review")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )


def _apply_correct_trajectory(state, targets):
    """Schedule all required appointments and appeal all denied claims."""
    pcp_id = "prov_1"
    specialist_id = _specialist_provider(state, targets).id

    for i, name in enumerate(targets["due_vaccine_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_vax_{i}",
            provider_id=pcp_id,
            reason=name,
            offset_days=14 + i,
        ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}",
            provider_id=pcp_id,
            reason=name,
            offset_days=30 + i,
        ))
    state.appointments.append(_make_appt(
        id="appt_ref_followup",
        provider_id=specialist_id,
        reason="Expiring referral follow-up",
        offset_days=50,
        linked_referral_id=targets["expiring_ref_id"],
    ))
    for cid in targets["denied_claim_ids"]:
        _appeal_claim(state, cid)


def test_correct_trajectory_passes():
    """Do every required action — all appointments + all appeals."""
    sm, sid, targets, initial, state = _setup_session()
    assert targets["due_vaccine_names"], "seed produced no due vaccines"
    assert targets["overdue_screening_names"], "seed produced no overdue screenings"
    assert targets["expiring_ref_id"], "seed produced no expiring referral"
    assert targets["denied_claim_ids"], "seed produced no denied claims"

    _apply_correct_trajectory(state, targets)
    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    """Agent did nothing — must fail (Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()
    report = _run(targets, initial, state)
    assert report.passed is False
    assert report.score < 1.0, f"do-nothing got score {report.score}"


def test_missing_vaccine_apts_fails():
    """All work except the vaccine bijection — must fail."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = "prov_1"
    specialist_id = _specialist_provider(initial, targets).id
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}", provider_id=pcp_id, reason=name,
            offset_days=30 + i,
        ))
    state.appointments.append(_make_appt(
        id="appt_ref_followup",
        provider_id=specialist_id,
        reason="Expiring referral follow-up",
        linked_referral_id=targets["expiring_ref_id"],
    ))
    for cid in targets["denied_claim_ids"]:
        _appeal_claim(state, cid)

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "trajectory missing vaccine appointments unexpectedly passed"
    )


def test_missing_appeals_fails():
    """Appointments scheduled but no claims appealed — must fail."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = "prov_1"
    specialist_id = _specialist_provider(initial, targets).id
    for i, name in enumerate(targets["due_vaccine_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_vax_{i}", provider_id=pcp_id, reason=name,
            offset_days=14 + i,
        ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}", provider_id=pcp_id, reason=name,
            offset_days=30 + i,
        ))
    state.appointments.append(_make_appt(
        id="appt_ref_followup",
        provider_id=specialist_id,
        reason="Expiring referral follow-up",
        linked_referral_id=targets["expiring_ref_id"],
    ))

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "trajectory skipping the claim appeals unexpectedly passed"
    )


def test_wrong_linked_referral_fails():
    """Follow-up appt points at a non-expiring referral — must fail
    (identity test for expiring_ref_id, hazard Class 4)."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = "prov_1"
    specialist_id = _specialist_provider(initial, targets).id
    for i, name in enumerate(targets["due_vaccine_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_vax_{i}", provider_id=pcp_id, reason=name,
            offset_days=14 + i,
        ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}", provider_id=pcp_id, reason=name,
            offset_days=30 + i,
        ))
    # Link to a bogus ref id instead of the expiring one.
    state.appointments.append(_make_appt(
        id="appt_ref_followup",
        provider_id=specialist_id,
        reason="Expiring referral follow-up",
        linked_referral_id="ref_bogus",
    ))
    for cid in targets["denied_claim_ids"]:
        _appeal_claim(state, cid)

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "follow-up with wrong linked_referral_id unexpectedly passed"
    )


def test_wrong_specialist_provider_for_expiring_referral_fails():
    """Follow-up uses the expiring referral but a provider whose specialty
    does not match that referral — must fail."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = "prov_1"
    ref = _expiring_ref(initial, targets)
    wrong_provider = next(
        p for p in initial.providers
        if p.specialty != ref.to_specialty
    )
    for i, name in enumerate(targets["due_vaccine_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_vax_{i}",
            provider_id=pcp_id,
            reason=name,
            offset_days=14 + i,
        ))
    for i, name in enumerate(targets["overdue_screening_names"]):
        state.appointments.append(_make_appt(
            id=f"appt_scr_{i}",
            provider_id=pcp_id,
            reason=name,
            offset_days=30 + i,
        ))
    state.appointments.append(_make_appt(
        id="appt_ref_wrong_provider",
        provider_id=wrong_provider.id,
        reason="Expiring referral follow-up",
        linked_referral_id=targets["expiring_ref_id"],
    ))
    for cid in targets["denied_claim_ids"]:
        _appeal_claim(state, cid)

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "expiring-referral follow-up with a non-matching provider unexpectedly passed"
    )


def test_discontinued_rx_fails():
    """Agent correctly completes the task but discontinues an expiring
    prescription — invariant on state.prescriptions must reject it."""
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_trajectory(state, targets)
    # Discontinue the first expiring prescription (violates instruction).
    if targets.get("expiring_rx_ids"):
        rx_id = targets["expiring_rx_ids"][0]
        for rx in state.prescriptions:
            if rx.id == rx_id:
                rx.status = "discontinued"
                break

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "discontinuing an expiring prescription unexpectedly passed; the "
        "state.prescriptions invariant must reject this mutation."
    )
