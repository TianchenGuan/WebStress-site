"""End-to-end tests for pp_respond_to_provider canonical_diff.

Task: "Your PCP sent you a message about adjusting your blood pressure medication.
Read the message, then schedule exactly one PCP follow-up appointment using the
next available PCP slot. Use the appointment reason exactly 'Blood pressure
medication adjustment follow-up'. Do not reply and do not send any messages."

Verifies:
  - Correct trajectory (read PCP bp message AND schedule PCP follow-up) passes 1.0.
  - Only-marked-read trajectory fails (missing create).
  - Only-appointment trajectory fails (missing update).
  - Wrong-message-marked-read trajectory fails (update where predicate).
  - Wrong-reason trajectory fails (create reason predicate).
  - Wrong-provider trajectory fails (create provider_id predicate).
  - Not-earliest-slot trajectory fails (create datetime predicate).
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_respond_to_provider',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_pcp_slot(initial, pcp_id: str):
    for p in initial.providers:
        if p.id == pcp_id:
            return min(s.datetime for s in p.available_slots)
    raise ValueError(f"PCP {pcp_id!r} not found in initial snapshot")


def _find_pcp_bp_message(state, pcp_id: str, all_msg_ids):
    for m in state.messages:
        if (
            m.from_type == "provider"
            and m.provider_id == pcp_id
            and m.subject == "Blood Pressure Medication Adjustment"
            and m.id in all_msg_ids
        ):
            return m
    raise ValueError("PCP blood-pressure medication adjustment message not found in seed")


def _mark_message_read(state, msg_id: str) -> None:
    for m in state.messages:
        if m.id == msg_id:
            m.is_read = True
            return
    raise ValueError(f"message {msg_id!r} not found in session state")


def _make_follow_up_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Blood pressure medication adjustment follow-up")
    return Appointment(**kwargs)


def _schedule_follow_up(state, pcp_id: str, datetime_value, *, reason=None, apt_id="appt_new_bp_followup"):
    state.appointments.append(_make_follow_up_appt(
        id=apt_id,
        provider_id=pcp_id,
        datetime=datetime_value,
        **({"reason": reason} if reason is not None else {}),
    ))


# ────────────────────────────────────────────────────────────────────


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    bp_msg = _find_pcp_bp_message(state, pcp_id, targets["all_msg_ids"])
    # The seeded bp message is unread (it's placed as the last message in its
    # thread and the thread is one of the unread threads). Mark it read AND
    # book the PCP follow-up at the earliest available slot.
    _mark_message_read(state, bp_msg.id)
    _schedule_follow_up(state, pcp_id, _earliest_pcp_slot(initial, pcp_id))

    task = get_task('pp_respond_to_provider')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_only_marked_read_no_appt_fails():
    """Agent marked the PCP bp message read but did not schedule the follow-up."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    bp_msg = _find_pcp_bp_message(state, pcp_id, targets["all_msg_ids"])
    _mark_message_read(state, bp_msg.id)
    # (no appointment created)

    task = get_task('pp_respond_to_provider')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing create must fail"
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_only_appt_no_read_fails():
    """Agent booked the PCP follow-up but never read the message."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    _schedule_follow_up(state, pcp_id, _earliest_pcp_slot(initial, pcp_id))
    # (PCP bp message remains unread)

    task = get_task('pp_respond_to_provider')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing update must fail"
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_wrong_message_marked_read_fails():
    """Agent mutates a different (non-PCP-bp) message's is_read flag and
    books the PCP follow-up, but leaves the PCP bp message untouched.

    Two failures expected:
      - update[0] unmatched (no Update on the bp message).
      - state.messages invariant violated (the other message was mutated).
    """
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    bp_msg_id = targets["bp_msg_id"]
    # Pick any message that is NOT the bp one and flip its is_read (either
    # direction counts as a mutation). Current seed has msg_1 as the only
    # unread; every other message is read and toggling unread→read→? either
    # way produces an Update in compute_diff.
    other_msg = next((m for m in state.messages if m.id != bp_msg_id), None)
    assert other_msg is not None, "seed must produce another message besides bp"
    other_msg.is_read = not other_msg.is_read
    # Book the follow-up so we isolate the read-check failure.
    _schedule_follow_up(state, pcp_id, _earliest_pcp_slot(initial, pcp_id))

    task = get_task('pp_respond_to_provider')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "marking a wrong message (instead of the PCP bp one) must fail — "
        "update[0] has no candidate and the state.messages invariant is violated"
    )


def test_wrong_reason_fails():
    """Agent marked the bp message read and booked PCP follow-up, but used
    a different reason string."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    bp_msg = _find_pcp_bp_message(state, pcp_id, targets["all_msg_ids"])
    _mark_message_read(state, bp_msg.id)
    _schedule_follow_up(
        state, pcp_id, _earliest_pcp_slot(initial, pcp_id),
        reason="BP follow-up",  # close but not the required exact string
    )

    task = get_task('pp_respond_to_provider')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong reason must fail create predicate"


def test_wrong_provider_fails():
    """Agent booked the follow-up with a non-PCP provider."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    bp_msg = _find_pcp_bp_message(state, pcp_id, targets["all_msg_ids"])
    _mark_message_read(state, bp_msg.id)
    other = next(
        p for p in initial.providers
        if p.id != pcp_id and p.available_slots
    )
    state.appointments.append(_make_follow_up_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task('pp_respond_to_provider')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "non-PCP provider must fail create predicate"


def test_not_earliest_slot_fails():
    """Agent booked the PCP follow-up at the 2nd-earliest PCP slot (not the
    required earliest)."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    bp_msg = _find_pcp_bp_message(state, pcp_id, targets["all_msg_ids"])
    _mark_message_read(state, bp_msg.id)
    slots = sorted(
        s.datetime for p in initial.providers
        if p.id == pcp_id for s in p.available_slots
    )
    assert len(slots) >= 2, "seed must produce >=2 PCP slots for this test"
    _schedule_follow_up(state, pcp_id, slots[1])  # 2nd-earliest

    task = get_task('pp_respond_to_provider')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "non-earliest slot must fail create datetime predicate"
