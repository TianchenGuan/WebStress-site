"""Hand-crafted test for reddit_full_community_manager canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_full_community_manager", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe to MachineLearning and Piracy
    for name in (targets["join1"], targets["join2"]):
        sr = next(s for s in state.subreddits if s.name == name)
        sr.is_subscribed = True
        if sr.id not in state.subscriptions:
            state.subscriptions.append(sr.id)
    # 2. Create post in ML
    ml = next(s for s in state.subreddits if s.name == targets["join1"])
    state.posts.append(Post(
        id="post_new_ml", subreddit_id=ml.id, subreddit_name=targets["join1"],
        author_name=state.owner_username, author_is_op=True,
        title=targets["post1_title"], body=targets["post1_body"],
        url="", post_type="text", score=1, upvote_ratio=1.0,
        comment_count=0, created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False,
        is_edited=False, is_spoiler=False, is_nsfw=False,
        flair_text=None, flair_color=None, awards=[],
        is_saved=False, is_hidden=False, vote_direction=1,
        permalink="/r/MachineLearning/comments/post_new_ml",
    ))
    # 3. Upvote AskReddit post + top-level comment
    state.get_post(targets["ask_id"]).vote_direction = 1
    state.comments.append(Comment(
        id="comment_top", post_id=targets["ask_id"], parent_id=None,
        author_name=state.owner_username, body=targets["ask_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=0, awards=[], flair_text=None,
    ))
    # 4. Reply to MidnightCoder
    state.comments.append(Comment(
        id="comment_reply", post_id=targets["ask_id"],
        parent_id=targets["reply_id"],
        author_name=state.owner_username, body=targets["reply_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=1, awards=[], flair_text=None,
    ))
    # 5. Messages
    for to in (targets["msg1_to"], targets["msg2_to"]):
        state.sent_messages.append(Message(
            id=f"msg_to_{to}", from_user=state.owner_username,
            to_user=to, subject=targets["msg_subject"],
            body=targets["msg_body"], created_at=datetime.now(timezone.utc),
            is_read=True, parent_id=None, context="",
        ))
    # 6. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 7. Settings
    state.settings.theme = "dark"
    state.settings.default_comment_sort = "new"
    state.settings.email_comment_reply = False
    state.settings.email_mentions = False


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_full_community_manager")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_full_community_manager")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_second_message_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Remove DataWizard42 message
    state.sent_messages = [m for m in state.sent_messages
                           if m.to_user != targets["msg2_to"]]
    task = get_task("reddit_full_community_manager")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_downvote_triggers_failure():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Downvote a decoy post — instruction forbids downvotes
    decoy_id = targets["decoy_ids"][0]
    state.get_post(decoy_id).vote_direction = -1
    task = get_task("reddit_full_community_manager")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_settings_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.email_mentions = True  # leave this enabled
    task = get_task("reddit_full_community_manager")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
