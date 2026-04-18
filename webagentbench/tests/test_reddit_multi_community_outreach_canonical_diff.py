"""Hand-crafted test for reddit_multi_community_outreach canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_multi_community_outreach", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe join1 + join2
    for name in (targets["join1"], targets["join2"]):
        sub = next(s for s in state.subreddits if s.name == name)
        sub.is_subscribed = True
        state.subscriptions.append(sub.id)
    # 2. Create post in join1
    join1_sub = next(s for s in state.subreddits if s.name == targets["join1"])
    state.posts.append(Post(
        id="post_new",
        subreddit_id=join1_sub.id,
        subreddit_name=targets["join1"],
        author_name=state.owner_username,
        title=targets["post1_title"],
        body=targets["post1_body"],
        url="", post_type="text",
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False, flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False,
        vote_direction=1, permalink="",
    ))
    # 3. Post comment on AskReddit post
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["comment_post_id"], parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 4. Send messages to both recipients
    for i, who in enumerate([targets["msg1_to"], targets["msg2_to"]]):
        state.sent_messages.append(Message(
            id=f"msg_{i}",
            from_user=state.owner_username,
            to_user=who,
            subject=targets["msg_subject"],
            body=targets["msg_body"],
            created_at=datetime.now(timezone.utc),
            is_read=False, parent_id=None, context="",
        ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_multi_community_outreach")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_multi_community_outreach")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_second_subscribe_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Undo join2 subscription
    join2 = next(s for s in state.subreddits if s.name == targets["join2"])
    join2.is_subscribed = False
    state.subscriptions.remove(join2.id)
    task = get_task("reddit_multi_community_outreach")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_comment_text_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    for c in state.comments:
        if c.id == "comment_new":
            c.body = "different text"
            break
    task = get_task("reddit_multi_community_outreach")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
