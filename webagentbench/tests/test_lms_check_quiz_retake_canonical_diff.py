"""End-to-end tests for lms_check_quiz_retake canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.models.lms import DiscussionPost
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_check_quiz_retake",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _retake_assignment(state, assignment_id: str, *, file_name: str = "retake.pdf") -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    submitted_at = assignment.due_at + timedelta(hours=1)
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count += 1
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _post_discussion(
    state,
    discussion_id: str,
    *,
    body: str = "Could I request a retake opportunity for this quiz?",
) -> None:
    state.discussion_posts.append(
        DiscussionPost(
            id=f"post_{len(state.discussion_posts) + 1}",
            discussion_id=discussion_id,
            author_id=state.student.id,
            author_name=state.student.name,
            body=body,
            timestamp=datetime.fromisoformat(state.resolved_targets["session_start"]) + timedelta(hours=1),
        )
    )


def _other_discussion_id(state, target_discussion_id: str) -> str:
    for discussion in state.discussions:
        if discussion.id != target_discussion_id:
            return discussion.id
    raise ValueError("no alternate discussion available")


def test_task_has_branching_canonical_diff_and_seed_integrity():
    _, _, targets, _, state = _setup_session(seed=42)

    task = get_task("lms_check_quiz_retake")
    assert task.canonical_diff is not None, "canonical_diff missing"
    assert task.canonical_diff.oneof is not None
    assert len(task.canonical_diff.oneof) == 2

    assignment = state.get_assignment(targets["target_assignment_id"])
    assert assignment is not None
    assert assignment.course_id == targets["target_course_id"]
    course = state.get_course(targets["target_course_id"])
    assert course is not None
    assert course.course_code == targets["course_code"]


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session(seed=42)

    _retake_assignment(state, targets["target_assignment_id"])

    task = get_task("lms_check_quiz_retake")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_retake_branch_rejects_wrong_file():
    _, _, targets, initial, state = _setup_session(seed=42)

    _retake_assignment(state, targets["target_assignment_id"], file_name="wrong_upload.pdf")

    task = get_task("lms_check_quiz_retake")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, "retaking with the wrong file should fail"


def test_retake_branch_rejects_discussion_post():
    _, _, targets, initial, state = _setup_session(seed=42)

    _post_discussion(state, targets["target_discussion_id"])

    task = get_task("lms_check_quiz_retake")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, "posting instead of retaking should fail"


def test_discussion_branch_passes():
    _, _, targets, initial, state = _setup_session(seed=3)

    _post_discussion(state, targets["target_discussion_id"])

    task = get_task("lms_check_quiz_retake")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_discussion_branch_rejects_wrong_discussion():
    _, _, targets, initial, state = _setup_session(seed=3)

    _post_discussion(state, _other_discussion_id(state, targets["target_discussion_id"]))

    task = get_task("lms_check_quiz_retake")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, "posting in the wrong discussion should fail"


def test_discussion_branch_rejects_quiz_resubmission():
    _, _, targets, initial, state = _setup_session(seed=3)

    _retake_assignment(state, targets["target_assignment_id"])

    task = get_task("lms_check_quiz_retake")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, "resubmitting the quiz when no attempts remain should fail"
