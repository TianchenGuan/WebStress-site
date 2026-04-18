"""Hand-crafted test for reddit_content_management canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_content_management", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Hide the funny post
    hide_post = state.get_post(targets["hide_id"])
    hide_post.is_hidden = True
    if hide_post.id not in state.hidden_post_ids:
        state.hidden_post_ids.append(hide_post.id)
    # 2. Unsave every meme post
    for mid in targets["meme_ids"]:
        mp = state.get_post(mid)
        if mp is not None:
            mp.is_saved = False
        if mid in state.saved_post_ids:
            state.saved_post_ids.remove(mid)
    # 3. Save the science post
    save_post = state.get_post(targets["save_id"])
    save_post.is_saved = True
    state.saved_post_ids.append(targets["save_id"])
    # 4. Create programming post
    prog_sub = next(s for s in state.subreddits if s.name == "programming")
    state.posts.append(Post(
        id="post_new_prog", subreddit_id=prog_sub.id, subreddit_name="programming",
        author_name=state.owner_username,
        title=targets["create_title"], body=targets["create_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink="/r/programming/comments/new",
    ))
    # 5. Settings
    state.settings.default_feed_sort = "new"
    state.settings.compact_view = True


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_content_management")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_content_management")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_hide_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Revert the hide
    state.get_post(targets["hide_id"]).is_hidden = False
    if targets["hide_id"] in state.hidden_post_ids:
        state.hidden_post_ids.remove(targets["hide_id"])
    task = get_task("reddit_content_management")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_partial_meme_unsave_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Re-save one of the memes — bijection saturation should fail
    first_meme = targets["meme_ids"][0]
    mp = state.get_post(first_meme)
    mp.is_saved = True
    state.saved_post_ids.append(first_meme)
    task = get_task("reddit_content_management")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_programming_post_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    for p in state.posts:
        if p.subreddit_name == "programming" and p.author_name == state.owner_username and p.title == targets["create_title"]:
            p.body = "Wrong body"
    task = get_task("reddit_content_management")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
