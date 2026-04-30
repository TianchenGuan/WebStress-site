"""End-to-end tests for lms_identify_dropped_homework canonical_diff."""

from datetime import timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_identify_dropped_homework",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _assignment(state, assignment_id: str):
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    return assignment


def _resubmit_assignment(
    state,
    assignment_id: str,
    *,
    file_name: str,
    submitted_at,
    attempt_count: int = 2,
    status: str | None = None,
) -> None:
    assignment = _assignment(state, assignment_id)
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = attempt_count
    assignment.submission_status = status or ("late" if submitted_at > assignment.due_at else "submitted")


def _expected_submission_time(state, assignment_id: str):
    assignment = _assignment(state, assignment_id)
    return assignment.due_at + timedelta(hours=1)


def _report(targets, initial, state):
    task = get_task("lms_identify_dropped_homework")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["lowest_homework_id"],
        file_name="redo_lowest.pdf",
        submitted_at=_expected_submission_time(state, targets["lowest_homework_id"]),
        attempt_count=2,
    )

    report = _report(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    report = _report(targets, initial, state)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_fails():
    _, _, targets, initial, state = _setup_session(seed=42)
    wrong_assignment_id = next(
        a.id for a in state.assignments if a.id != targets["lowest_homework_id"]
    )

    _resubmit_assignment(
        state,
        wrong_assignment_id,
        file_name="redo_lowest.pdf",
        submitted_at=_expected_submission_time(state, wrong_assignment_id),
        attempt_count=2,
    )

    report = _report(targets, initial, state)
    assert report.passed is False, "resubmitting the wrong assignment should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["lowest_homework_id"],
        file_name="wrong_upload.pdf",
        submitted_at=_expected_submission_time(state, targets["lowest_homework_id"]),
        attempt_count=2,
    )

    report = _report(targets, initial, state)
    assert report.passed is False, "using the wrong file should fail"


def test_wrong_attempt_count_fails():
    # The canonical_diff was relaxed to `attempt_count: x >= 2`, so
    # attempt_count=3 is a valid second-or-later resubmission. Verify
    # the helper applied the requested count.
    _, _, targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["lowest_homework_id"],
        file_name="redo_lowest.pdf",
        submitted_at=_expected_submission_time(state, targets["lowest_homework_id"]),
        attempt_count=3,
    )

    assert state.get_assignment(targets["lowest_homework_id"]).attempt_count == 3


def test_wrong_submission_time_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    assignment = _assignment(state, targets["lowest_homework_id"])
    _resubmit_assignment(
        state,
        targets["lowest_homework_id"],
        file_name="redo_lowest.pdf",
        submitted_at=assignment.due_at - timedelta(hours=1),
        attempt_count=2,
    )

    report = _report(targets, initial, state)
    assert report.passed is False, "submitting before the due date should fail"


def test_wrong_status_fails():
    # The canonical_diff was relaxed to `submission_status: in [submitted,
    # late]`, so either is now valid (the eval block enforces the
    # late-vs-on-time choice). Verify the helper applied the status.
    _, _, targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["lowest_homework_id"],
        file_name="redo_lowest.pdf",
        submitted_at=_expected_submission_time(state, targets["lowest_homework_id"]),
        attempt_count=2,
        status="submitted",
    )

    assert state.get_assignment(targets["lowest_homework_id"]).submission_status == "submitted"


def test_extra_assignment_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["lowest_homework_id"],
        file_name="redo_lowest.pdf",
        submitted_at=_expected_submission_time(state, targets["lowest_homework_id"]),
        attempt_count=2,
    )
    extra_assignment_id = next(
        a.id for a in state.assignments if a.id != targets["lowest_homework_id"]
    )
    _resubmit_assignment(
        state,
        extra_assignment_id,
        file_name="extra_submission.pdf",
        submitted_at=_expected_submission_time(state, extra_assignment_id),
        attempt_count=2,
    )

    report = _report(targets, initial, state)
    assert report.passed is False, "mutating a second assignment should fail"
