"""End-to-end tests for booking_reply_to_hotel canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Message
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_reply_to_hotel'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial_snap = sm.get_initial_snapshot(sid)
    initial_dict = initial_snap.model_dump()
    state = sm.get_state(sid)
    return dict(targets), initial_snap, initial_dict, state


def _run(targets, initial_snap, initial_dict, state):
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial_dict, state.model_dump())
    return match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial_snap, final=state)


def _make_reply(targets, suffix=""):
    return Message(
        id=f"msg_reply{suffix}",
        property_id=targets['property_id'],
        property_name=targets['property_name'],
        reservation_id=targets['reservation_id'],
        subject="Re: Pre-arrival Information",
        body="Dear hotel, I would like to confirm my check-in at 3 PM. I would prefer a quiet room on a higher floor if possible. Thank you for your help.",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        # Mark original message as read
        msg = next(m for m in state.messages if m.id == targets['message_id'])
        msg.read = True
        # Send reply
        state.messages.append(_make_reply(targets, suffix=f"_{seed}"))
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_subject_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    msg = next(m for m in state.messages if m.id == targets['message_id'])
    msg.read = True
    reply = _make_reply(targets)
    reply.subject = "Reply to your message"  # wrong subject
    state.messages.append(reply)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong subject should fail"


def test_missing_body_content_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    msg = next(m for m in state.messages if m.id == targets['message_id'])
    msg.read = True
    reply = _make_reply(targets)
    reply.body = "I will arrive at 3 PM."  # missing quiet room, higher floor, thank you
    state.messages.append(reply)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing required body content should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
