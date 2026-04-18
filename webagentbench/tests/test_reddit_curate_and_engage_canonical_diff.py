"""Hand-crafted test for reddit_curate_and_engage canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_curate_and_engage", seed=seed
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Hide mildlyinfuriating post
    hide_post = state.get_post(targets["hide_id"])
    hide_post.is_hidden = True
    state.hidden_post_ids.append(targets["hide_id"])
    # 2. Save dataisbeautiful post
    save_post = state.get_post(targets["save_id"])
    save_post.is_saved = True
    state.saved_post_ids.append(targets["save_id"])
    # 3. Upvote ELI5 post
    upvote_post = state.get_post(targets["upvote_id"])
    upvote_post.vote_direction = 1
    # 4. Comment on the ELI5 post with exactly the target text
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["upvote_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1,
        created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=0, awards=[], flair_text=None,
    ))
    # 5. Enable compact view
    state.settings.compact_view = True


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_curate_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_curate_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_compact_view_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.compact_view = False  # revert the setting
    task = get_task("reddit_curate_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_post_hidden_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Agent hides an extra unrelated post
    other = next(p for p in state.posts
                 if p.id not in (targets["hide_id"], targets["save_id"], targets["upvote_id"]))
    other.is_hidden = True
    state.hidden_post_ids.append(other.id)
    task = get_task("reddit_curate_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_comment_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Replace the comment body with a wrong text
    for c in state.comments:
        if c.author_name == state.owner_username and c.post_id == targets["upvote_id"]:
            c.body = "Not the exact required text"
    task = get_task("reddit_curate_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
