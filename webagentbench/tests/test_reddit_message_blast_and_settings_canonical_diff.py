"""Hand-crafted test for reddit_message_blast_and_settings canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_message_blast_and_settings", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _send(state, to_user, body, mid):
    state.sent_messages.append(Message(
        id=mid,
        from_user=state.owner_username,
        to_user=to_user,
        subject="ML meetup",
        body=body,
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=None, context="",
    ))


def _apply_correct(state, targets):
    for to in ("NeuralNexus", "ByteRunner", "DataWizard42"):
        _send(state, to, targets["msg_body"], f"msg_{to}")
    for n in state.notifications:
        n.is_read = True
    state.settings.theme = "dark"
    state.settings.show_active_communities = False
    state.settings.default_feed_sort = "new"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_message_blast_and_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_message_blast_and_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_one_recipient_fails():
    _, _, targets, initial, state = _setup()
    # Send only two of the three required
    _send(state, "NeuralNexus", targets["msg_body"], "m1")
    _send(state, "ByteRunner", targets["msg_body"], "m2")
    for n in state.notifications:
        n.is_read = True
    state.settings.theme = "dark"
    state.settings.show_active_communities = False
    state.settings.default_feed_sort = "new"
    task = get_task("reddit_message_blast_and_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_body_fails():
    _, _, targets, initial, state = _setup()
    _send(state, "NeuralNexus", "wrong body", "m1")
    _send(state, "ByteRunner", targets["msg_body"], "m2")
    _send(state, "DataWizard42", targets["msg_body"], "m3")
    for n in state.notifications:
        n.is_read = True
    state.settings.theme = "dark"
    state.settings.show_active_communities = False
    state.settings.default_feed_sort = "new"
    task = get_task("reddit_message_blast_and_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
