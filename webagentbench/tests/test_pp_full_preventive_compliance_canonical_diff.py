"""End-to-end tests for pp_full_preventive_compliance canonical_diff.

Task: "Complete all overdue preventive care actions using only appointments,
refills, and renewal requests: 1) Schedule appointments for overdue screenings,
2) Schedule appointments for due/overdue immunizations, 3) Refill expiring rxes
that still have refills remaining, 4) Use renewal flow for the expiring rx with
zero refills."

Verifies:
  - Correct trajectory (all four axes completed) scores 1.0.
  - Missing the refill axis fails (update[0] bijection unsaturated).
  - Missing the renewal-message axis fails (create[2] unsaturated even if
    status flipped).
  - Wrong-reason-per-slot fails (identity test: screening name must appear
    in its own appointment's reason — not just any overdue-count match).
  - Excess appointment fails the unaccounted sweep / bounded-creation invariant.
  - Do-nothing fails (positive pool empty — Class 1 guard).
"""

from datetime import datetime, timezone, timedelta

from webagentbench.backend.models.patient_portal import Appointment, ClinicalMessage
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_full_preventive_compliance',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _get_rx(state, rx_id: str):
    for r in state.prescriptions:
        if r.id == rx_id:
            return r
    raise ValueError(f"rx {rx_id!r} not found")


def _schedule_appointment(state, reason: str, provider_id: str) -> Appointment:
    """Append one future scheduled appointment with the given reason."""
    apt_id = state._gen_id("apt")
    apt = Appointment(
        id=apt_id,
        provider_id=provider_id,
        datetime=(datetime.now(timezone.utc) + timedelta(days=7)),
        type="in-person",
        status="scheduled",
        reason=reason,
    )
    state.appointments.append(apt)
    return apt


def _append_renewal_message(state, rx_id: str, provider_id: str) -> ClinicalMessage:
    msg_id = state._gen_id("msg")
    msg = ClinicalMessage(
        id=msg_id,
        from_type="patient",
        provider_id=provider_id,
        subject="Prescription renewal request",
        body="Requesting renewal.",
        thread_id=f"thread_{msg_id}",
        category="rx_renewal",
        is_read=True,
        linked_entity_id=rx_id,
        linked_entity_type="prescription",
    )
    state.messages.append(msg)
    return msg


def _refill(state, rx_id: str) -> None:
    """Simulate the backend refill route: refills -= 1, last_filled bumped."""
    rx = _get_rx(state, rx_id)
    rx.refills_remaining -= 1
    rx.last_filled = datetime.now(timezone.utc)


def _renew(state, rx_id: str) -> None:
    """Simulate the backend renewal route: status=pending_renewal + new msg."""
    rx = _get_rx(state, rx_id)
    rx.status = "pending_renewal"
    _append_renewal_message(state, rx_id, rx.provider_id)


def _do_full_compliance(state, targets) -> None:
    """Execute the complete correct trajectory: all four axes."""
    pcp_id = targets["pcp_id"]
    # 1) Appointments per overdue screening (reason = screening name).
    for name in targets["overdue_screening_names"]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    # 2) Appointments per due immunization (reason = vaccine name).
    for name in targets["due_vaccine_names"]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    # 3) Refill expiring rxes that still have refills.
    for rid in targets["expiring_with_refills_rx_ids"]:
        _refill(state, rid)
    # 4) Renew the expiring zero-refill rx(es).
    for rid in targets["expiring_zero_refill_rx_ids"]:
        _renew(state, rid)


def test_correct_trajectory_passes():
    """All four axes completed — score=1.0, passed=True."""
    sm, sid, targets, initial, state = _setup_session()
    # Sanity: seed must produce non-empty targets across every axis.
    assert targets["overdue_screening_names"], "seed produced no overdue screenings"
    assert targets["due_vaccine_names"], "seed produced no due vaccines"
    assert targets["expiring_with_refills_rx_ids"], "seed produced no expiring-with-refills rxes"
    assert targets["expiring_zero_refill_rx_ids"], "seed produced no expiring zero-refill rx"

    _do_full_compliance(state, targets)

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    """Do-nothing trajectory: positive pool empty -> passed=False."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "do-nothing trajectory must not pass"
    assert report.score < 1.0, f"expected <1.0, got {report.score}"


def test_missing_refill_fails():
    """Agent does appointments + renewal but skips refills. update[0] bijection
    unsaturated -> passed=False."""
    sm, sid, targets, initial, state = _setup_session()

    # Do everything EXCEPT the refills.
    pcp_id = targets["pcp_id"]
    for name in targets["overdue_screening_names"]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    for name in targets["due_vaccine_names"]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    for rid in targets["expiring_zero_refill_rx_ids"]:
        _renew(state, rid)

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "skipping refill axis must fail — update[0] bijection cannot saturate"
    )


def test_refill_side_effects_must_match_backend_decrement():
    """Bumping last_filled without decrementing exactly one refill must fail."""
    sm, sid, targets, initial, state = _setup_session()

    _do_full_compliance(state, targets)
    victim_id = targets["expiring_with_refills_rx_ids"][0]
    initial_rx = _get_rx(initial, victim_id)
    state_rx = _get_rx(state, victim_id)
    state_rx.refills_remaining = initial_rx.refills_remaining

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "refill updates must decrement refills_remaining by exactly one "
        "and advance last_filled"
    )


def test_status_flip_without_renewal_message_fails():
    """Renewal status flipped but no rx_renewal ClinicalMessage created.
    create[2] bijection unsaturated -> passed=False."""
    sm, sid, targets, initial, state = _setup_session()

    pcp_id = targets["pcp_id"]
    for name in targets["overdue_screening_names"]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    for name in targets["due_vaccine_names"]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    for rid in targets["expiring_with_refills_rx_ids"]:
        _refill(state, rid)
    # Flip status but DON'T send the renewal message.
    for rid in targets["expiring_zero_refill_rx_ids"]:
        _get_rx(state, rid).status = "pending_renewal"

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "status flip without rx_renewal message must fail — create[2] "
        "bijection has no candidates"
    )


def test_wrong_reason_fails_identity():
    """Agent schedules the correct number of appointments but the reason of
    each one does not contain the corresponding screening/vaccine name. The
    bijection's identity test (v.lower() in reason.lower()) must reject."""
    sm, sid, targets, initial, state = _setup_session()

    pcp_id = targets["pcp_id"]
    # Swap in bogus reasons instead of the actual screening/vaccine names.
    bogus = "Follow-up visit"
    for _ in targets["overdue_screening_names"]:
        _schedule_appointment(state, reason=bogus, provider_id=pcp_id)
    for _ in targets["due_vaccine_names"]:
        _schedule_appointment(state, reason=bogus, provider_id=pcp_id)
    for rid in targets["expiring_with_refills_rx_ids"]:
        _refill(state, rid)
    for rid in targets["expiring_zero_refill_rx_ids"]:
        _renew(state, rid)

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "appointments with wrong reasons must fail the reason-substring "
        "identity predicate in both create[0] and create[1] bijections"
    )


def test_excess_appointment_fails():
    """Correct trajectory PLUS one extra appointment. The unaccounted sweep /
    bounded-creation named invariant must surface it as a failure."""
    sm, sid, targets, initial, state = _setup_session()

    _do_full_compliance(state, targets)
    # Extra appointment with a reason that could ambiguously match any axis
    # — the bounded-creation invariant should still flag excess candidates.
    _schedule_appointment(
        state, reason="Extra unrelated checkup", provider_id=targets["pcp_id"],
    )

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "excess appointment must be surfaced by the unaccounted sweep"
    )


def test_partial_immunization_axis_credits_proportional_score():
    """2 of 3 immunizations + everything else correct → score > 0 but < 1.

    Documents that bijection matching in evaluator_diff.py line 926 gives
    len(matching) / n_left fraction of the entry weight when unsaturated.
    The task's axis split (screening, immunization, refill, renewal-message,
    status-flip) then weights each equally, so a missing 1-of-3 slot on
    one axis drops that axis's contribution but does not zero out the rest.
    """
    sm, sid, targets, initial, state = _setup_session()

    pcp_id = targets["pcp_id"]
    for name in targets["overdue_screening_names"]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    # Schedule only N-1 vaccines — leave the last one unfulfilled.
    vax = list(targets["due_vaccine_names"])
    for name in vax[:-1]:
        _schedule_appointment(state, reason=name, provider_id=pcp_id)
    for rid in targets["expiring_with_refills_rx_ids"]:
        _refill(state, rid)
    for rid in targets["expiring_zero_refill_rx_ids"]:
        _renew(state, rid)
        _append_renewal_message(state, rid, pcp_id)

    task = get_task('pp_full_preventive_compliance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )

    assert report.passed is False, "unsaturated immunization axis fails"
    assert 0.4 < report.score < 1.0, (
        f"expected partial credit strictly between 0 and 1, got {report.score}"
    )
