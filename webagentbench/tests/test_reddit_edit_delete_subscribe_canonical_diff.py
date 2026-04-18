"""Hand-crafted test for reddit_edit_delete_subscribe canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_edit_delete_subscribe", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Edit post body
    post = state.get_post(targets["edit_id"])
    post.body = targets["edit_body"]
    post.is_edited = True
    # Delete comment
    comment = state.get_comment(targets["del_comment_id"])
    comment.is_removed = True
    comment.body = "[deleted]"
    # Subscribe
    sr = next(s for s in state.subreddits if s.name == "Piracy")
    sr.is_subscribed = True
    if sr.id not in state.subscriptions:
        state.subscriptions.append(sr.id)
    # Settings
    state.settings.default_comment_sort = "new"
    task = get_task("reddit_edit_delete_subscribe")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_edit_delete_subscribe")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
