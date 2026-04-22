"""Hand-crafted test for reddit_account_cleanup canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_account_cleanup", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Unsave all memes posts — flip both saved_post_ids and Post.is_saved to
    # mirror the real POST /posts/{id}/unsave endpoint. The weight-0 bijection
    # update on Post covers the is_saved changes so the preserve-ALL
    # invariant on state.posts doesn't fire for the intended unsaves.
    memes_ids = {p.id for p in state.posts if p.subreddit_name == targets["unsave_sub"]}
    state.saved_post_ids = [pid for pid in state.saved_post_ids if pid not in memes_ids]
    for p in state.posts:
        if p.id in memes_ids:
            p.is_saved = False
    # Unsubscribe memes
    for s in state.subreddits:
        if s.name == targets["leave_sub"]:
            s.is_subscribed = False
            if s.id in state.subscriptions:
                state.subscriptions.remove(s.id)
    # Settings
    state.settings.theme = "dark"
    state.settings.show_online_status = False
    state.settings.default_comment_sort = "new"
    # Comment on news post
    state.comments.append(Comment(
        id="comment_new", post_id=targets["comment_post_id"], parent_id=None,
        author_name=state.owner_username, body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_account_cleanup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_account_cleanup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
