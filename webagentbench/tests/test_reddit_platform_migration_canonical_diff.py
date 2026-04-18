"""Hand-crafted test for reddit_platform_migration canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_platform_migration", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(targets, state):
    # 1. Unsave posts from leave_sub (memes) and funny
    state.saved_post_ids = [
        pid for pid in state.saved_post_ids
        if not any(p.id == pid and p.subreddit_name in (targets["leave_sub"], "funny") for p in state.posts)
    ]
    for p in state.posts:
        if p.subreddit_name in (targets["leave_sub"], "funny"):
            p.is_saved = False
    # 2. Unsubscribe from leave_sub
    leave_sr = next(s for s in state.subreddits if s.name == targets["leave_sub"])
    if leave_sr.is_subscribed:
        leave_sr.is_subscribed = False
        if leave_sr.id in state.subscriptions:
            state.subscriptions.remove(leave_sr.id)
    # 3. Subscribe to join, j2, j3
    for name in [targets["join"], targets["j2"], targets["j3"]]:
        sr = next(s for s in state.subreddits if s.name == name)
        if not sr.is_subscribed:
            sr.is_subscribed = True
            if sr.id not in state.subscriptions:
                state.subscriptions.append(sr.id)
    # 4. Create post in join
    join_sr = next(s for s in state.subreddits if s.name == targets["join"])
    state.posts.append(Post(
        id="post_new_join",
        subreddit_id=join_sr.id,
        subreddit_name=targets["join"],
        author_name=state.owner_username,
        title=targets["post_title"],
        body=targets["post_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        vote_direction=1,
        permalink=f"/r/{targets['join']}/comments/new",
    ))
    # 5. Save wn post and comment
    wn = state.get_post(targets["wn_id"])
    wn.is_saved = True
    state.saved_post_ids.append(targets["wn_id"])
    state.comments.append(Comment(
        id="comment_wn_new",
        post_id=targets["wn_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["wn_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 6. Send message
    state.sent_messages.append(Message(
        id="msg_outreach",
        from_user=state.owner_username,
        to_user=targets["msg_to"],
        subject=targets["msg_sub"],
        body=targets["msg_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 7. Settings
    state.settings.theme = "dark"
    state.settings.default_feed_sort = "top"
    state.settings.compact_view = True
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    # 8. Mark all messages + notifications read
    for m in state.messages:
        m.is_read = True
    for n in state.notifications:
        n.is_read = True


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    task = get_task("reddit_platform_migration")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_platform_migration")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_post_title_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Create a wrong-title post by mutating the new post
    new_post = next(p for p in state.posts if p.id == "post_new_join")
    new_post.title = "Totally wrong title"
    task = get_task("reddit_platform_migration")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
