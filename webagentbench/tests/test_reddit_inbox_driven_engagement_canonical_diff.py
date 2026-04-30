"""Hand-crafted test for reddit_inbox_driven_engagement canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_inbox_driven_engagement", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 2. Mark all messages read
    for m in state.messages:
        m.is_read = True
    # 3. Reply to r_from
    state.sent_messages.append(Message(
        id="msg_reply",
        from_user=state.owner_username,
        to_user=targets["r_from"],
        subject=f"Re: {targets['r_sub']}",
        body=targets["r_body"],
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=targets["r_id"], context="",
    ))
    # 4. Delete spam
    state.messages = [m for m in state.messages if m.id != targets["del_id"]]
    # 5. Upvote + save wn
    wn = state.get_post(targets["wn_id"])
    wn.vote_direction = 1
    wn.is_saved = True
    state.saved_post_ids.append(targets["wn_id"])
    # 6. Comment on prog
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["prog_id"], parent_id=None,
        author_name=state.owner_username,
        body=targets["c2"],
        score=1,
        created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 7. Subscribe to join and create ML post
    ml = next(s for s in state.subreddits if s.name == targets["join"])
    ml.is_subscribed = True
    state.subscriptions.append(ml.id)
    state.posts.append(Post(
        id="post_new",
        subreddit_id=ml.id,
        subreddit_name=targets["join"],
        author_name=state.owner_username,
        title=targets["post_title"],
        body=targets["post_body"],
        url="",
        post_type="text",
        score=1,
        upvote_ratio=1.0,
        comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False,
        flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False,
        vote_direction=1, permalink="",
    ))
    # 8. Settings
    state.settings.theme = "dark"
    state.settings.default_feed_sort = "new"
    state.settings.email_messages = False


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_inbox_driven_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_inbox_driven_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_spam_delete_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Re-add the spam message so delete is undone
    from webagentbench.backend.models.reddit import Message as MsgModel
    state.messages.append(MsgModel(
        id=targets["del_id"],
        from_user="ryushin6", to_user=state.owner_username,
        subject=targets["del_sub"], body="Spam.",
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    task = get_task("reddit_inbox_driven_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_settings_theme_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.theme = "light"
    task = get_task("reddit_inbox_driven_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_required_save_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    wn = state.get_post(targets["wn_id"])
    wn.is_saved = False
    if targets["wn_id"] in state.saved_post_ids:
        state.saved_post_ids.remove(targets["wn_id"])
    task = get_task("reddit_inbox_driven_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
