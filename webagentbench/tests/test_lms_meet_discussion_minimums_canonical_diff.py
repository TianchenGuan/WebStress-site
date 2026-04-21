"""End-to-end tests for lms_meet_discussion_minimums canonical_diff."""

from datetime import datetime, timedelta, timezone

from webagentbench.backend.models.lms import DiscussionPost
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_meet_discussion_minimums",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _timestamp(targets, minutes: int) -> datetime:
    return datetime.fromisoformat(targets["session_start"]) + timedelta(minutes=minutes)


def _make_post(state, targets, *, discussion_id: str, body: str, parent_post_id=None, minutes: int = 5):
    return DiscussionPost(
        id=f"post_{len(state.discussion_posts) + 100}",
        discussion_id=discussion_id,
        author_id=state.student.id,
        author_name=state.student.name,
        body=body,
        parent_post_id=parent_post_id,
        timestamp=_timestamp(targets, minutes),
        updated_at=None,
        is_anonymous=False,
    )


def _run(targets, initial, state):
    task = get_task("lms_meet_discussion_minimums")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _make_minimum_participation(state, targets) -> None:
    target_discussion_id = targets["target_discussion_id"]
    top_level = _make_post(
        state,
        targets,
        discussion_id=target_discussion_id,
        body="I agree with the discussion prompt and want to add a short response.",
        minutes=5,
    )
    state.discussion_posts.append(top_level)
    state.discussion_posts.append(
        _make_post(
            state,
            targets,
            discussion_id=target_discussion_id,
            body="Replying with a follow-up point to satisfy the reply minimum.",
            parent_post_id=top_level.id,
            minutes=6,
        )
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _make_minimum_participation(state, targets)

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _run(targets, initial, state)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_top_level_post_only_fails():
    sm, sid, targets, initial, state = _setup_session()

    state.discussion_posts.append(
        _make_post(
            state,
            targets,
            discussion_id=targets["target_discussion_id"],
            body="Top-level post only.",
            minutes=5,
        )
    )

    report = _run(targets, initial, state)
    assert report.passed is False, "missing the reply should fail the minimums"


def test_reply_only_fails():
    sm, sid, targets, initial, state = _setup_session()

    parent = next(
        p for p in state.discussion_posts
        if p.discussion_id == targets["target_discussion_id"]
    )
    state.discussion_posts.append(
        _make_post(
            state,
            targets,
            discussion_id=targets["target_discussion_id"],
            body="Reply only.",
            parent_post_id=parent.id,
            minutes=5,
        )
    )

    report = _run(targets, initial, state)
    assert report.passed is False, "missing the top-level post should fail the minimums"


def test_wrong_discussion_fails():
    sm, sid, targets, initial, state = _setup_session()

    other_discussion = next(
        d for d in state.discussions
        if d.id != targets["target_discussion_id"]
    )
    _make_minimum_participation(state, targets | {"target_discussion_id": other_discussion.id})

    report = _run(targets, initial, state)
    assert report.passed is False, "posting in the wrong discussion should fail"


def test_extra_post_in_target_discussion_allowed():
    # The canonical_diff invariant on state.discussion_posts has filter
    # `a.discussion_id != target['target_discussion_id']` with
    # comprehensive:true, so extra posts INSIDE the target discussion are
    # permitted (over-participation doesn't violate the "meet minimums"
    # goal). Posts in OTHER discussions still fail — covered by
    # test_post_in_wrong_discussion_fails.
    sm, sid, targets, initial, state = _setup_session()

    _make_minimum_participation(state, targets)
    state.discussion_posts.append(
        _make_post(
            state,
            targets,
            discussion_id=targets["target_discussion_id"],
            body="An extra top-level post that is now allowed.",
            minutes=7,
        )
    )

    report = _run(targets, initial, state)
    assert report.passed is True, (
        "extra posts inside the target discussion must be allowed under "
        "comprehensive filter semantics"
    )


def test_unrelated_enrollment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    _make_minimum_participation(state, targets)
    state.enrollments[0].status = "dropped"

    report = _run(targets, initial, state)
    assert report.passed is False, "dropping an enrollment should violate invariants"
