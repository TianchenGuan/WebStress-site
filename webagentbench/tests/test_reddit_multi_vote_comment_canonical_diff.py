"""Hand-crafted test for reddit_multi_vote_comment canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_multi_vote_comment", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    state.get_post(targets["game_id"]).vote_direction = 1
    state.get_post(targets["movie_id"]).vote_direction = -1
    state.get_post(targets["til_id"]).is_saved = True
    state.saved_post_ids.append(targets["til_id"])
    state.comments.append(Comment(
        id="comment_new", post_id=targets["til_id"], parent_id=None,
        author_name=state.owner_username,
        body="The honey badger truly does not care. They have incredibly thick skin that most predators cannot penetrate.",
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_multi_vote_comment")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_multi_vote_comment")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_comment_text_must_be_exact():
    _, _, targets, initial, state = _setup()
    state.get_post(targets["game_id"]).vote_direction = 1
    state.get_post(targets["movie_id"]).vote_direction = -1
    state.get_post(targets["til_id"]).is_saved = True
    state.saved_post_ids.append(targets["til_id"])
    state.comments.append(Comment(
        id="comment_new", post_id=targets["til_id"], parent_id=None,
        author_name=state.owner_username,
        body="They have incredibly thick skin.",
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_multi_vote_comment")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
