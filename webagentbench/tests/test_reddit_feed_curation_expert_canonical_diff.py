"""Hand-crafted test for reddit_feed_curation_expert canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_feed_curation_expert", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Hide off-topic technology post
    hide_post = state.get_post(targets["hide_id"])
    hide_post.is_hidden = True
    state.hidden_post_ids.append(targets["hide_id"])
    # 2. Upvote + save science post + comment
    sci_post = state.get_post(targets["sci_id"])
    sci_post.vote_direction = 1
    sci_post.is_saved = True
    state.saved_post_ids.append(targets["sci_id"])
    state.comments.append(Comment(
        id="comment_sci", post_id=targets["sci_id"], parent_id=None,
        author_name=state.owner_username, body=targets["sci_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=0, awards=[], flair_text=None,
    ))
    # 3. Save programming post (but do NOT vote)
    prog_post = state.get_post(targets["prog_id"])
    prog_post.is_saved = True
    state.saved_post_ids.append(targets["prog_id"])
    # 4. Send message
    state.sent_messages.append(Message(
        id="msg_new", from_user=state.owner_username,
        to_user=targets["msg_to"], subject=targets["msg_sub"],
        body=targets["msg_body"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 5. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 6. Feed sort top
    state.settings.default_feed_sort = "top"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_feed_curation_expert")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_feed_curation_expert")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_voted_on_programming_fails():
    """Instruction forbids voting on the programming post — only save it."""
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.get_post(targets["prog_id"]).vote_direction = 1
    task = get_task("reddit_feed_curation_expert")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_feed_sort_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.default_feed_sort = "hot"  # default, not top
    task = get_task("reddit_feed_curation_expert")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_science_comment_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    for c in state.comments:
        if c.author_name == state.owner_username and c.post_id == targets["sci_id"]:
            c.body = "Not the required comment text"
    task = get_task("reddit_feed_curation_expert")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
