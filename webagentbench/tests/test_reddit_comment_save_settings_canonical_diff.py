"""Hand-crafted test for reddit_comment_save_settings canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_comment_save_settings", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Save post
    state.get_post(targets["post_id"]).is_saved = True
    state.saved_post_ids.append(targets["post_id"])
    # Top-level comment
    state.comments.append(Comment(
        id="comment_new1", post_id=targets["post_id"], parent_id=None,
        author_name=state.owner_username, body=targets["top_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # Reply to singleton
    state.comments.append(Comment(
        id="comment_new2", post_id=targets["post_id"],
        parent_id=targets["reply_target_id"],
        author_name=state.owner_username, body=targets["reply_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=1,
        awards=[], flair_text=None,
    ))
    # Settings
    state.settings.default_comment_sort = "controversial"
    state.settings.auto_play_media = False
    task = get_task("reddit_comment_save_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_comment_save_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
