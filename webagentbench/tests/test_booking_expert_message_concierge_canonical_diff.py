"""End-to-end tests for booking_expert_message_concierge canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_message_concierge'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.travel_preferences.preferred_bed_type = 'king'
    # Mark targeted messages as read.
    target_ids = {targets['msg_id_1'], targets['msg_id_2'], targets['msg_id_3']}
    for msg in state.messages:
        if msg.id in target_ids:
            msg.read = True
    # Also mark one additional property-origin message read to satisfy the
    # lenient update[4] entry "Any property-origin message may be marked read
    # while reviewing the inbox" in the YAML.
    extra_marked = False
    for msg in state.messages:
        if (msg.sender == 'property' and not msg.read
                and msg.id not in target_ids and not extra_marked):
            msg.read = True
            extra_marked = True
    # Create replies
    state.messages.append(Message(
        id="msg_reply1",
        property_id=targets['hotel_id_1'],
        property_name="Hotel 1",
        subject="Re: Check-in Time",
        body="I'll arrive around 3pm, please have my room ready",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_reply2",
        property_id=targets['hotel_id_2'],
        property_name="Hotel 2",
        subject="Re: Room Upgrade Offer",
        body="Yes, I'd love the upgrade with breakfast included",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_reply3",
        property_id=targets['hotel_id_3'],
        property_name="Hotel 3",
        subject="Re: Spa Appointment",
        body="Please book the couples massage for us",
        sender="guest",
        created_at=now,
    ))


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        sm, sid, targets, initial, state = _setup_session(seed=seed)
        _apply_correct_state(targets, state)

        task = get_task(TASK_ID)
        agent_diff = compute_diff(initial, state)
        report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.messages[-3].property_id = "prop_wrong_decoy"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
