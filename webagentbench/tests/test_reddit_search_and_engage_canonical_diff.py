"""Hand-crafted test for reddit_search_and_engage canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_search_and_engage", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Save Cloudflare post
    post = state.get_post(targets["target_post_id"])
    post.is_saved = True
    state.saved_post_ids.append(targets["target_post_id"])
    # 2. Top-level comment on it
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["target_post_id"], parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 3. Send message to ByteRunner
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username, to_user=targets["message_post_author"],
        subject=targets["message_subject"], body=targets["message_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_search_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_search_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_decoy_saved_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Save a decoy Cloudflare post
    decoy_id = targets["decoy_post_ids"][0]
    decoy = state.get_post(decoy_id)
    decoy.is_saved = True
    state.saved_post_ids.append(decoy_id)
    task = get_task("reddit_search_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_message_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    for m in state.sent_messages:
        if m.id == "msg_new":
            m.body = "Something totally different."
            break
    task = get_task("reddit_search_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
