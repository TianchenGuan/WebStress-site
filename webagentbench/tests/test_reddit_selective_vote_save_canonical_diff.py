"""Hand-crafted test for reddit_selective_vote_save canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_selective_vote_save", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Upvote EU post
    up = state.get_post(targets["up_id"])
    up.vote_direction = 1
    # 2. Downvote AI startup post
    down = state.get_post(targets["down_id"])
    down.vote_direction = -1
    # 3. Save Viking post
    save = state.get_post(targets["save_id"])
    save.is_saved = True
    state.saved_post_ids.append(targets["save_id"])
    # 4. Comment on Elden Ring post
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["comment_id"], parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 5. Mark all messages as read
    for m in state.messages:
        m.is_read = True
    # 6. Settings comment sort top
    state.settings.default_comment_sort = "top"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_selective_vote_save")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_selective_vote_save")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_vote_direction_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Flip the EU upvote into a downvote
    up = state.get_post(targets["up_id"])
    up.vote_direction = -1
    task = get_task("reddit_selective_vote_save")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_viking_accidentally_upvoted_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Instruction explicitly says: do not vote on the save target
    save = state.get_post(targets["save_id"])
    save.vote_direction = 1
    task = get_task("reddit_selective_vote_save")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
