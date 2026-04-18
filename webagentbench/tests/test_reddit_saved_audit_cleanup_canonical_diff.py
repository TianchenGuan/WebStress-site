"""Hand-crafted test for reddit_saved_audit_cleanup canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_saved_audit_cleanup", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Unsave any memes posts
    meme_ids = [p.id for p in state.posts if p.subreddit_name == "memes" and p.id in state.saved_post_ids]
    for pid in meme_ids:
        post = state.get_post(pid)
        post.is_saved = False
        state.saved_post_ids.remove(pid)
    # 2. Save Intel post
    intel = state.get_post(targets["save1_id"])
    intel.is_saved = True
    state.saved_post_ids.append(targets["save1_id"])
    # 3. Save + upvote walking post
    walking = state.get_post(targets["save2_id"])
    walking.is_saved = True
    walking.vote_direction = 1
    state.saved_post_ids.append(targets["save2_id"])
    # 4. Settings
    state.settings.default_feed_sort = "top"
    state.settings.default_comment_sort = "new"
    # 5. Send message
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username, to_user=targets["msg_to"],
        subject=targets["msg_subject"], body=targets["msg_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_saved_audit_cleanup")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_saved_audit_cleanup")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_memes_unsave_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Re-save a memes post to violate the memes-unsaved constraint
    memes_post = next(p for p in state.posts if p.subreddit_name == "memes")
    memes_post.is_saved = True
    if memes_post.id not in state.saved_post_ids:
        state.saved_post_ids.append(memes_post.id)
    task = get_task("reddit_saved_audit_cleanup")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_walking_not_upvoted_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Revert the upvote on the walking post
    walking = state.get_post(targets["save2_id"])
    walking.vote_direction = 0
    task = get_task("reddit_saved_audit_cleanup")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
