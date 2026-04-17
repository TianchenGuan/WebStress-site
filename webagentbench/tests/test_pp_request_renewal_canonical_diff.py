"""End-to-end tests for pp_request_renewal canonical_diff.

Task: "Your {target.zero_refill_medication} has 0 refills remaining.
Request a renewal so you can continue your medication."

Verifies:
  - Correct trajectory (status->pending_renewal + new ClinicalMessage with
    from_type=patient, category=rx_renewal, linked_entity_id=rx_id) passes 1.0.
  - Wrong-rx-renewed fails (a different prescription's status changed).
  - No-message-sent fails (status changed but no renewal message created).
  - No-status-change fails (message created but status untouched).
  - Wrong-category fails (message created but category != 'rx_renewal').
  - No-mutation fails (do-nothing trajectory).
"""

from webagentbench.backend.models.patient_portal import ClinicalMessage
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_request_renewal',
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


def _append_renewal_message(
    state, rx_id: str, provider_id: str, *,
    category: str = "rx_renewal",
    from_type: str = "patient",
    linked_entity_id: str | None = None,
    linked_entity_type: str = "prescription",
) -> ClinicalMessage:
    msg_id = state._gen_id("msg")
    msg = ClinicalMessage(
        id=msg_id,
        from_type=from_type,
        provider_id=provider_id,
        subject="Prescription renewal request",
        body="Requesting renewal for medication.",
        thread_id=f"thread_{msg_id}",
        category=category,
        is_read=True,
        linked_entity_id=linked_entity_id if linked_entity_id is not None else rx_id,
        linked_entity_type=linked_entity_type,
    )
    state.messages.append(msg)
    return msg


def _renew(state, rx_id: str) -> None:
    """Simulate the backend renewal route: status->pending_renewal + new msg."""
    rx = _get_rx(state, rx_id)
    rx.status = "pending_renewal"
    _append_renewal_message(state, rx_id, rx.provider_id)


def test_correct_trajectory_passes():
    """Target rx status flipped to pending_renewal AND a patient-authored
    rx_renewal ClinicalMessage linked to the target rx is created."""
    sm, sid, targets, initial, state = _setup_session()
    _renew(state, targets["zero_refill_rx_id"])

    task = get_task('pp_request_renewal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_rx_renewed_fails():
    """Agent flips a NON-target prescription's status to pending_renewal —
    should fail both the filtered invariant on other prescriptions AND the
    `where` selector on the update entry (and probably linked_entity_id)."""
    sm, sid, targets, initial, state = _setup_session()

    other_id = next(
        (rid for rid in targets["active_rx_ids"] if rid != targets["zero_refill_rx_id"]),
        None,
    )
    assert other_id is not None, "seed must produce >=1 non-target active rx"

    other = _get_rx(state, other_id)
    other.status = "pending_renewal"
    # Also send a correctly-structured message but linked to the wrong rx.
    _append_renewal_message(state, other_id, other.provider_id)

    task = get_task('pp_request_renewal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "renewing the wrong rx should fail the filtered invariant on other "
        "prescriptions AND the linked_entity_id predicate on the create."
    )


def test_no_message_sent_fails():
    """Status changed but no renewal message created — create[0] unsatisfied."""
    sm, sid, targets, initial, state = _setup_session()
    _get_rx(state, targets["zero_refill_rx_id"]).status = "pending_renewal"

    task = get_task('pp_request_renewal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "status flip alone must not pass — the renewal message create entry "
        "has no candidate."
    )
    assert report.score < 1.0, f"expected <1.0, got {report.score}"


def test_no_status_change_fails():
    """Renewal message created but rx status untouched — update[0] unsatisfied."""
    sm, sid, targets, initial, state = _setup_session()
    rx = _get_rx(state, targets["zero_refill_rx_id"])
    _append_renewal_message(state, rx.id, rx.provider_id)

    task = get_task('pp_request_renewal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "renewal message alone must not pass — status still 'active', "
        "update entry has no matching candidate."
    )
    assert report.score < 1.0, f"expected <1.0, got {report.score}"


def test_wrong_category_fails():
    """Status flipped + a patient message created, but category is 'clinical'
    instead of 'rx_renewal' — create[0] should reject the candidate."""
    sm, sid, targets, initial, state = _setup_session()
    rx = _get_rx(state, targets["zero_refill_rx_id"])
    rx.status = "pending_renewal"
    _append_renewal_message(state, rx.id, rx.provider_id, category="clinical")

    task = get_task('pp_request_renewal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "misrouted message (category != 'rx_renewal') must fail — category is "
        "the structural signal that the renewal reached the RX system."
    )


def test_no_mutation_fails():
    """Agent does nothing. Positive pool empty → passed=False (Class 1 guard)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_request_renewal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — neither update nor create "
        "entry has any matching candidate."
    )
    assert report.score < 1.0, f"expected <1.0, got {report.score}"
