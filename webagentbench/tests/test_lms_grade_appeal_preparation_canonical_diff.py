"""End-to-end tests for lms_grade_appeal_preparation canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.models.lms import DiscussionPost
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_grade_appeal_preparation",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _disputed_ids(targets: dict[str, str]) -> list[str]:
    return [aid.strip() for aid in targets["most_disputed_assignment_ids"].split(",") if aid.strip()]


def _resubmit_assignment(state, assignment_id: str, *, file_name: str) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    submitted_at = assignment.due_at + timedelta(hours=1)
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = 2
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _post_dispute_notice(
    state,
    *,
    discussion_id: str,
    body: str,
    created_at: datetime,
) -> None:
    state.discussion_posts.append(
        DiscussionPost(
            id=f"post_{len(state.discussion_posts) + 1}",
            discussion_id=discussion_id,
            author_id=state.student.id,
            author_name=state.student.name,
            body=body,
            parent_post_id=None,
            timestamp=created_at,
            is_anonymous=False,
        )
    )


def _correct_body(targets: dict[str, str]) -> str:
    return (
        f"I am formally disputing {targets['course_code']} assignments "
        f"{targets['disputed_title_1']} and {targets['disputed_title_2']}. "
        "Please review the rubric maxima and the attached evidence."
    )


def _apply_correct_trajectory(state, targets: dict[str, str]) -> None:
    disputed_ids = _disputed_ids(targets)
    _resubmit_assignment(state, disputed_ids[0], file_name="appeal_evidence_1.pdf")
    _resubmit_assignment(state, disputed_ids[1], file_name="appeal_evidence_2.pdf")
    _post_dispute_notice(
        state,
        discussion_id=targets["target_discussion_id"],
        body=_correct_body(targets),
        created_at=_session_start(targets) + timedelta(minutes=5),
    )


def _report(initial, state, targets):
    task = get_task("lms_grade_appeal_preparation")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )


def _decoy_discussion_id(state, target_discussion_id: str) -> str:
    for discussion in state.discussions:
        if discussion.id != target_discussion_id:
            return discussion.id
    raise ValueError("seed must include a non-target discussion")


def _other_assignment_id(state, excluded_ids: set[str]) -> str:
    for assignment in state.assignments:
        if assignment.id not in excluded_ids:
            return assignment.id
    raise ValueError("seed must include a non-target assignment")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    _apply_correct_trajectory(state, targets)

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_first_file_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    disputed_ids = _disputed_ids(targets)
    _resubmit_assignment(state, disputed_ids[0], file_name="wrong_upload.pdf")
    _resubmit_assignment(state, disputed_ids[1], file_name="appeal_evidence_2.pdf")
    _post_dispute_notice(
        state,
        discussion_id=targets["target_discussion_id"],
        body=_correct_body(targets),
        created_at=_session_start(targets) + timedelta(minutes=5),
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "wrong first file should fail"


def test_wrong_second_file_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    disputed_ids = _disputed_ids(targets)
    _resubmit_assignment(state, disputed_ids[0], file_name="appeal_evidence_1.pdf")
    _resubmit_assignment(state, disputed_ids[1], file_name="wrong_upload.pdf")
    _post_dispute_notice(
        state,
        discussion_id=targets["target_discussion_id"],
        body=_correct_body(targets),
        created_at=_session_start(targets) + timedelta(minutes=5),
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "wrong second file should fail"


def test_wrong_discussion_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    _apply_correct_trajectory(state, targets)
    target_discussion_id = targets["target_discussion_id"]
    wrong_discussion_id = _decoy_discussion_id(state, target_discussion_id)
    state.discussion_posts[-1].discussion_id = wrong_discussion_id

    report = _report(initial, state, targets)
    assert report.passed is False, "posting in the wrong discussion should fail"


def test_wrong_body_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    disputed_ids = _disputed_ids(targets)
    _resubmit_assignment(state, disputed_ids[0], file_name="appeal_evidence_1.pdf")
    _resubmit_assignment(state, disputed_ids[1], file_name="appeal_evidence_2.pdf")
    _post_dispute_notice(
        state,
        discussion_id=targets["target_discussion_id"],
        body=f"I am formally disputing {targets['course_code']} assignments {targets['disputed_title_1']}.",
        created_at=_session_start(targets) + timedelta(minutes=5),
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "omitting one disputed assignment should fail"


def test_decoy_assignment_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    _apply_correct_trajectory(state, targets)
    _resubmit_assignment(state, targets["decoy_assignment_id"], file_name="appeal_evidence_1.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, "resubmitting the decoy assignment should fail"
