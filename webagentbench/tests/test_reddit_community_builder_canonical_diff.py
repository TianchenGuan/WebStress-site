"""Hand-crafted test for reddit_community_builder canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_community_builder", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe to j1, j2, j3
    for name in (targets["j1"], targets["j2"], targets["j3"]):
        sr = next(s for s in state.subreddits if s.name == name)
        sr.is_subscribed = True
        if sr.id not in state.subscriptions:
            state.subscriptions.append(sr.id)
    # 2. Create post in r/j1
    j1 = next(s for s in state.subreddits if s.name == targets["j1"])
    state.posts.append(Post(
        id="post_new_j1", subreddit_id=j1.id, subreddit_name=j1.name,
        author_name=state.owner_username,
        title=targets["p1_title"], body=targets["p1_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink=f"/r/{j1.name}/comments/new",
    ))
    # 3. Upvote programming post and comment "Great CI/CD improvements."
    state.get_post(targets["prog_id"]).vote_direction = 1
    state.comments.append(Comment(
        id="comment_new_prog", post_id=targets["prog_id"], parent_id=None,
        author_name=state.owner_username,
        body="Great CI/CD improvements.",
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=0,
        awards=[], flair_text=None,
    ))
    # 4. Send messages to NeuralNexus, ByteRunner, DataWizard42
    for idx, recipient in enumerate(("NeuralNexus", "ByteRunner", "DataWizard42")):
        state.sent_messages.append(Message(
            id=f"msg_new_{idx}", from_user=state.owner_username, to_user=recipient,
            subject=targets["ms"], body=targets["mb"],
            created_at=datetime.now(timezone.utc), is_read=True,
            parent_id=None,
        ))
    # 5. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 6. Settings
    state.settings.theme = "dark"
    state.settings.default_comment_sort = "new"
    state.settings.show_active_communities = False


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_community_builder")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_community_builder")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_comment_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Replace the CC comment body with something that doesn't contain the
    # required substring.
    for c in state.comments:
        if c.author_name == state.owner_username and c.post_id == targets["prog_id"]:
            c.body = "Nice work!"
    task = get_task("reddit_community_builder")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_comment_body_with_extra_text_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    for c in state.comments:
        if c.author_name == state.owner_username and c.post_id == targets["prog_id"]:
            c.body = f"{targets['cc']} Extra commentary."
    task = get_task("reddit_community_builder")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_recipient_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Drop one of the required messages — only 2 of 3 recipients got it.
    state.sent_messages = [
        m for m in state.sent_messages if m.to_user != "DataWizard42"
    ]
    task = get_task("reddit_community_builder")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_settings_theme_missing_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.theme = "light"  # revert theme change
    task = get_task("reddit_community_builder")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
