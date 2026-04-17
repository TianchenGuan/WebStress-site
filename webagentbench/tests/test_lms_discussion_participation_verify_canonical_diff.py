"""End-to-end tests for lms_discussion_participation_verify canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.models.lms import DiscussionPost
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_discussion_participation_verify",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _discussion_ids(targets: dict[str, str]) -> list[str]:
    return [did.strip() for did in targets["discussion_ids"].split(",") if did.strip()]


def _timestamp(targets: dict[str, str], minutes: int) -> datetime:
    return datetime.fromisoformat(targets["session_start"]) + timedelta(minutes=minutes)


def _make_post(
    state,
    targets,
    *,
    discussion_id: str,
    body: str,
    parent_post_id: str | None = None,
    minutes: int = 5,
) -> DiscussionPost:
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


def _satisfy_all_discussions(state, targets) -> None:
    for index, discussion_id in enumerate(_discussion_ids(targets)):
        top_level = _make_post(
            state,
            targets,
            discussion_id=discussion_id,
            body=f"Top-level contribution for discussion {discussion_id}.",
            minutes=5 + (index * 2),
        )
        state.discussion_posts.append(top_level)
        state.discussion_posts.append(
            _make_post(
                state,
                targets,
                discussion_id=discussion_id,
                body=f"Reply contribution for discussion {discussion_id}.",
                parent_post_id=top_level.id,
                minutes=6 + (index * 2),
            )
        )


def _run(targets, initial, state):
    task = get_task("lms_discussion_participation_verify")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _satisfy_all_discussions(state, targets)

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _run(targets, initial, state)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_only_first_discussion_completed_fails():
    sm, sid, targets, initial, state = _setup_session()

    first_discussion_id = _discussion_ids(targets)[0]
    top_level = _make_post(
        state,
        targets,
        discussion_id=first_discussion_id,
        body="Only the first discussion gets completed.",
        minutes=5,
    )
    state.discussion_posts.append(top_level)
    state.discussion_posts.append(
        _make_post(
            state,
            targets,
            discussion_id=first_discussion_id,
            body="Reply in the first discussion only.",
            parent_post_id=top_level.id,
            minutes=6,
        )
    )

    report = _run(targets, initial, state)
    assert report.passed is False, "leaving some target discussions incomplete should fail"


def test_top_level_only_fails():
    sm, sid, targets, initial, state = _setup_session()

    for index, discussion_id in enumerate(_discussion_ids(targets)):
        state.discussion_posts.append(
            _make_post(
                state,
                targets,
                discussion_id=discussion_id,
                body=f"Top-level only for {discussion_id}.",
                minutes=5 + index,
            )
        )

    report = _run(targets, initial, state)
    assert report.passed is False, "missing replies should fail the participation requirement"


def test_extra_post_fails():
    sm, sid, targets, initial, state = _setup_session()

    _satisfy_all_discussions(state, targets)
    extra_discussion_id = _discussion_ids(targets)[0]
    state.discussion_posts.append(
        _make_post(
            state,
            targets,
            discussion_id=extra_discussion_id,
            body="Extra top-level post that should not be needed.",
            minutes=20,
        )
    )

    report = _run(targets, initial, state)
    assert report.passed is False, "creating extra posts should fail the create accounting"


def test_unrelated_enrollment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    _satisfy_all_discussions(state, targets)
    state.enrollments[0].status = "dropped"

    report = _run(targets, initial, state)
    assert report.passed is False, "dropping an enrollment should violate invariants"
