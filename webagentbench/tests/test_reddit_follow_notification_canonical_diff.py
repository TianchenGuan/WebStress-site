"""End-to-end tests for reddit_follow_notification canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_follow_notification", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Reddit seed has a duplicate notif_1 id bug (baseline + target_notification
    # both claim notif_1). compute_diff uses _index_by_id which keeps the LAST
    # occurrence, so mutate the last matching entry.
    matching = [n for n in state.notifications if n.id == targets["notification_id"]]
    matching[-1].is_read = True
    # Add the top-level comment
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["related_post_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=True, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_follow_notification")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_follow_notification")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
