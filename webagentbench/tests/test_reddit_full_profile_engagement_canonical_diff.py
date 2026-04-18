"""Hand-crafted test for reddit_full_profile_engagement canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_full_profile_engagement", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    post = state.get_post(targets["post_id"])
    post.vote_direction = 1
    post.is_saved = True
    state.saved_post_ids.append(targets["post_id"])
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["post_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1,
        created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username,
        to_user=targets["target_user"],
        subject=targets["msg_subject"],
        body=targets["msg_body"],
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=None, context="",
    ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_full_profile_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_full_profile_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_comment_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Overwrite the comment body with wrong text.
    for c in state.comments:
        if c.id == "comment_new":
            c.body = "different text"
            break
    task = get_task("reddit_full_profile_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_message_to_wrong_recipient_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Change the outbound message's recipient
    for m in state.sent_messages:
        if m.id == "msg_new":
            m.to_user = "SomeoneElse"
            break
    task = get_task("reddit_full_profile_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
