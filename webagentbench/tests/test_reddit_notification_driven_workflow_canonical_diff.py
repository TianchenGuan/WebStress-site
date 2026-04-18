"""Hand-crafted test for reddit_notification_driven_workflow canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_notification_driven_workflow", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(targets, state):
    # 1. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 2. Mark all messages read
    for m in state.messages:
        m.is_read = True
    # 3. Upvote + save post1
    p1 = state.get_post(targets["post1_id"])
    p1.vote_direction = 1
    p1.is_saved = True
    state.saved_post_ids.append(targets["post1_id"])
    # 4. Comment on post2
    state.comments.append(Comment(
        id="comment_new_1",
        post_id=targets["post2_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 5. Unsubscribe from leave_sub
    sr = next(s for s in state.subreddits if s.name == targets["leave_sub"])
    if sr.is_subscribed:
        sr.is_subscribed = False
        if sr.id in state.subscriptions:
            state.subscriptions.remove(sr.id)
    # 6. Theme dark
    state.settings.theme = "dark"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    task = get_task("reddit_notification_driven_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_notification_driven_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_comment_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Tamper with comment body to wrong text
    state.comments[-1].body = "Wrong comment"
    task = get_task("reddit_notification_driven_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
