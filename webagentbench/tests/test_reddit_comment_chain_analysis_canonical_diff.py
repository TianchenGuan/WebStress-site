"""Hand-crafted test for reddit_comment_chain_analysis canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_comment_chain_analysis", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    state.get_post(targets["post_id"]).vote_direction = 1
    state.get_comment(targets["save_id"]).is_saved = True
    state.saved_comment_ids.append(targets["save_id"])
    state.comments.append(Comment(
        id="c_top", post_id=targets["post_id"], parent_id=None,
        author_name=state.owner_username, body=targets["top_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    state.comments.append(Comment(
        id="c_r1", post_id=targets["post_id"], parent_id=targets["reply1_id"],
        author_name=state.owner_username, body=targets["reply1_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=1,
        awards=[], flair_text=None,
    ))
    state.comments.append(Comment(
        id="c_r2", post_id=targets["post_id"], parent_id=targets["reply2_id"],
        author_name=state.owner_username, body=targets["reply2_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=1,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_comment_chain_analysis")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_comment_chain_analysis")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_nested_reply_must_stay_on_target_post():
    _, _, targets, initial, state = _setup()
    state.get_post(targets["post_id"]).vote_direction = 1
    state.get_comment(targets["save_id"]).is_saved = True
    state.saved_comment_ids.append(targets["save_id"])
    wrong_post_id = next(p.id for p in state.posts if p.id != targets["post_id"])
    state.comments.append(Comment(
        id="c_top", post_id=targets["post_id"], parent_id=None,
        author_name=state.owner_username, body=targets["top_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    state.comments.append(Comment(
        id="c_r1", post_id=wrong_post_id, parent_id=targets["reply1_id"],
        author_name=state.owner_username, body=targets["reply1_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=1,
        awards=[], flair_text=None,
    ))
    state.comments.append(Comment(
        id="c_r2", post_id=targets["post_id"], parent_id=targets["reply2_id"],
        author_name=state.owner_username, body=targets["reply2_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=1,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_comment_chain_analysis")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
