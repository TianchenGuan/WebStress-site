"""End-to-end tests for lms_recoverable_late_assignments canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_recoverable_late_assignments",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _target_assignment_ids(targets: dict[str, str]) -> list[str]:
    return _ids(targets["missing_assignment_ids"]) + _ids(targets["late_assignment_ids"])


def _submit_recovery(state, targets, assignment_id: str, *, attempt_delta: int = 1) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submission_status = "late"
    assignment.file_name = "recovery_submission.pdf"
    assignment.attempt_count = assignment.attempt_count + attempt_delta
    assignment.submitted_at = datetime.fromisoformat(targets["session_start"]) + timedelta(minutes=5)


def _run(targets, initial, state):
    task = get_task("lms_recoverable_late_assignments")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=datetime.fromisoformat(targets["session_start"]),
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    for index, assignment_id in enumerate(_target_assignment_ids(targets)):
        assignment = state.get_assignment(assignment_id)
        if assignment is None:
            raise AssertionError(f"missing assignment {assignment_id!r}")
        assignment.submission_status = "late"
        assignment.file_name = "recovery_submission.pdf"
        assignment.attempt_count = assignment.attempt_count + 1
        assignment.submitted_at = datetime.fromisoformat(targets["session_start"]) + timedelta(minutes=5 + index)

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _run(targets, initial, state)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_id_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_ids = set(_target_assignment_ids(targets))
    wrong_assignment_id = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id not in target_ids
    )
    _submit_recovery(state, targets, wrong_assignment_id)

    report = _run(targets, initial, state)
    assert report.passed is False, "submitting the wrong assignment should fail the id selector"


def test_wrong_attempt_count_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _target_assignment_ids(targets)[0]
    _submit_recovery(state, targets, target_assignment_id, attempt_delta=2)

    report = _run(targets, initial, state)
    assert report.passed is False, "using the wrong attempt count should fail"


def test_extra_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    for assignment_id in _target_assignment_ids(targets):
        _submit_recovery(state, targets, assignment_id)

    target_ids = set(_target_assignment_ids(targets))
    extra_assignment_id = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id not in target_ids
    )
    _submit_recovery(state, targets, extra_assignment_id)

    report = _run(targets, initial, state)
    assert report.passed is False, "submitting an extra assignment should violate the invariant"
