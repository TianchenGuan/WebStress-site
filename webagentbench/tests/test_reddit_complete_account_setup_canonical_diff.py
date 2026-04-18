"""Hand-crafted test for reddit_complete_account_setup canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_complete_account_setup", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe to r/MachineLearning, r/Piracy, r/dataisbeautiful
    for name in ("MachineLearning", "Piracy", "dataisbeautiful"):
        sr = next(s for s in state.subreddits if s.name == name)
        sr.is_subscribed = True
        if sr.id not in state.subscriptions:
            state.subscriptions.append(sr.id)
    # 2. Settings
    state.settings.theme = "dark"
    state.settings.compact_view = True
    state.settings.default_feed_sort = "top"
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    # 3. Create post in r/MachineLearning
    ml = next(s for s in state.subreddits if s.name == "MachineLearning")
    state.posts.append(Post(
        id="post_new_ml", subreddit_id=ml.id, subreddit_name=ml.name,
        author_name=state.owner_username,
        title=targets["post_title"], body=targets["post_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink=f"/r/{ml.name}/comments/new",
    ))
    # 4. WN upvote, save, comment
    wn = state.get_post(targets["wn_id"])
    wn.vote_direction = 1
    wn.is_saved = True
    state.saved_post_ids.append(targets["wn_id"])
    state.comments.append(Comment(
        id="comment_wn_new", post_id=targets["wn_id"], parent_id=None,
        author_name=state.owner_username, body=targets["wn_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=0,
        awards=[], flair_text=None,
    ))
    # 5. Welcome message
    state.sent_messages.append(Message(
        id="msg_new_welcome", from_user=state.owner_username,
        to_user=targets["msg_to"], subject=targets["msg_sub"],
        body=targets["msg_body"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None,
    ))
    # 6. Mark all messages + notifications read
    for m in state.messages:
        m.is_read = True
    for n in state.notifications:
        n.is_read = True


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_complete_account_setup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_complete_account_setup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_subscription_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Revert one of the subscriptions
    pi = next(s for s in state.subreddits if s.name == "Piracy")
    pi.is_subscribed = False
    if pi.id in state.subscriptions:
        state.subscriptions.remove(pi.id)
    task = get_task("reddit_complete_account_setup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_post_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Corrupt the MachineLearning post body
    for p in state.posts:
        if p.subreddit_name == "MachineLearning" and p.author_name == state.owner_username and p.title == targets["post_title"]:
            p.body = "Wrong body"
    task = get_task("reddit_complete_account_setup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_compact_view_missing_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.compact_view = False  # revert
    task = get_task("reddit_complete_account_setup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
