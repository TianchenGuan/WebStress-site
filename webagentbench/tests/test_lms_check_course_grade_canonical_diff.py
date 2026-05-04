"""End-to-end tests for lms_check_course_grade canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.eval_core import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_check_course_grade",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _submit_assignment(state, assignment_id: str, *, file_name: str, submitted_at: datetime) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count += 1
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _mark_read(state, announcement_id: str) -> None:
    announcement = state.get_announcement(announcement_id)
    if announcement is None:
        raise ValueError(f"announcement {announcement_id!r} not found")
    announcement.is_read = True


def _matcher_report(initial, state, targets):
    task = get_task("lms_check_course_grade")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    _submit_assignment(
        state,
        targets["unsubmitted_hw_id"],
        file_name="catch_up.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_high_grade_branch_passes():
    sm, sid, targets, initial, state = _setup_session(seed=29)

    _mark_read(state, targets["latest_announcement_id"])

    report = _matcher_report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_low_grade_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    _mark_read(state, targets["latest_announcement_id"])

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "reading the announcement on the low-grade branch should fail"


def test_wrong_branch_high_grade_fails():
    sm, sid, targets, initial, state = _setup_session(seed=29)

    _submit_assignment(
        state,
        targets["unsubmitted_hw_id"],
        file_name="catch_up.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting homework on the high-grade branch should fail"


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    _submit_assignment(
        state,
        targets["unsubmitted_hw_id"],
        file_name="wrong_upload.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting the homework with the wrong file should fail"


def test_extra_mutation_fails():
    sm, sid, targets, initial, state = _setup_session(seed=42)

    _submit_assignment(
        state,
        targets["unsubmitted_hw_id"],
        file_name="catch_up.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )
    # Inject a *real* unrelated mutation (title rewrite) rather than a benign
    # is_read flip: opening an unrelated announcement is now treated as a
    # read-as-write side-effect and exempted from the "Preserve announcements"
    # invariant. We mutate a non-noise field to keep this regression test
    # meaningful.
    other = state.get_announcement(targets["latest_announcement_id"])
    other.title = f"{other.title} (edited)"

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, (
        "submitting the homework and editing an unrelated announcement title "
        "should violate the non-target invariant"
    )
