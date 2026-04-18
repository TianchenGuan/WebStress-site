"""Hand-crafted test for reddit_notification_cascade canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_notification_cascade", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct_trajectory(targets, state):
    # 1. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 2. Mark all messages read
    for m in state.messages:
        m.is_read = True
    # 3. Reply to r_from (sent_message)
    state.sent_messages.append(Message(
        id="msg_reply_new",
        from_user=state.owner_username,
        to_user=targets["r_from"],
        subject=f"Re: {targets['r_sub']}",
        body=targets["r_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 4. Delete spam
    state.messages = [m for m in state.messages if m.id != targets["del_id"]]
    # 5. Worldnews post: upvote, save, comment
    wn = state.get_post(targets["wn_id"])
    wn.vote_direction = 1
    wn.is_saved = True
    state.saved_post_ids.append(targets["wn_id"])
    state.comments.append(Comment(
        id="comment_wn_new",
        post_id=targets["wn_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["c1"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 6. Programming post: save
    prog = state.get_post(targets["prog_id"])
    prog.is_saved = True
    state.saved_post_ids.append(targets["prog_id"])
    # 7. Subscribe to r/join
    ml = next(s for s in state.subreddits if s.name == targets["join"])
    ml.is_subscribed = True
    if ml.id not in state.subscriptions:
        state.subscriptions.append(ml.id)
    # 8. Create post in r/join
    state.posts.append(Post(
        id="post_new_ml",
        subreddit_id=ml.id,
        subreddit_name=targets["join"],
        author_name=state.owner_username,
        title=targets["pt"],
        body=targets["pb"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        vote_direction=1,
        permalink=f"/r/{targets['join']}/comments/new",
    ))
    # 9. Settings
    state.settings.theme = "dark"
    state.settings.default_feed_sort = "new"
    state.settings.email_messages = False


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct_trajectory(targets, state)
    task = get_task("reddit_notification_cascade")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_notification_cascade")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_reply_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct_trajectory(targets, state)
    # Tamper with the reply body
    state.sent_messages[-1].body = "Wrong reply text"
    task = get_task("reddit_notification_cascade")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
