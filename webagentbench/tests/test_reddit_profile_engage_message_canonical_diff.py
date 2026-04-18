"""Hand-crafted test for reddit_profile_engage_message canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_profile_engage_message", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(targets, state):
    # 1. Upvote and save the target post
    p = state.get_post(targets["post_id"])
    p.vote_direction = 1
    p.is_saved = True
    state.saved_post_ids.append(targets["post_id"])
    # 2. Comment
    state.comments.append(Comment(
        id="comment_new_1",
        post_id=targets["post_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 3. Message
    state.sent_messages.append(Message(
        id="msg_outreach_1",
        from_user=state.owner_username,
        to_user=targets["user"],
        subject=targets["msg_sub"],
        body=targets["msg_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 4. Subscribe
    sr = next(s for s in state.subreddits if s.name == targets["join"])
    if not sr.is_subscribed:
        sr.is_subscribed = True
        if sr.id not in state.subscriptions:
            state.subscriptions.append(sr.id)
    # 5. Theme
    state.settings.theme = "dark"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    task = get_task("reddit_profile_engage_message")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_profile_engage_message")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_message_recipient_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Send message to wrong user
    state.sent_messages[-1].to_user = "SomeoneElse123"
    task = get_task("reddit_profile_engage_message")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
