"""Hand-crafted test for reddit_community_engagement canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_community_engagement", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe to r/MachineLearning
    ml = next(s for s in state.subreddits if s.name == targets["join_subreddit"])
    ml.is_subscribed = True
    if ml.id not in state.subscriptions:
        state.subscriptions.append(ml.id)
    # 2. Create post in r/MachineLearning
    state.posts.append(Post(
        id="post_new_ml", subreddit_id=ml.id, subreddit_name=ml.name,
        author_name=state.owner_username,
        title=targets["new_post_title"], body=targets["new_post_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink=f"/r/{ml.name}/comments/new",
    ))
    # 3. Upvote the AskReddit post, add a top-level comment
    state.get_post(targets["comment_post_id"]).vote_direction = 1
    state.comments.append(Comment(
        id="comment_new_top", post_id=targets["comment_post_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=0,
        awards=[], flair_text=None,
    ))
    # 4. Reply to MidnightCoder's comment
    state.comments.append(Comment(
        id="comment_new_reply", post_id=targets["comment_post_id"],
        parent_id=targets["reply_target_comment_id"],
        author_name=state.owner_username,
        body=targets["reply_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=1,
        awards=[], flair_text=None,
    ))
    # 5. Settings
    state.settings.default_comment_sort = "new"
    state.settings.theme = "dark"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_community_engagement")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_community_engagement")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_post_title_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Corrupt the MachineLearning post's title
    for p in state.posts:
        if p.subreddit_name == targets["join_subreddit"] and p.author_name == state.owner_username:
            p.title = "Not the required title"
    task = get_task("reddit_community_engagement")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_downvoting_decoy_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Downvote a decoy post — violates "Do not downvote"
    decoy_id = targets["decoy_post_ids"][0]
    state.get_post(decoy_id).vote_direction = -1
    task = get_task("reddit_community_engagement")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_reply_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Drop the reply comment
    state.comments = [
        c for c in state.comments
        if c.id != "comment_new_reply"
    ]
    task = get_task("reddit_community_engagement")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
