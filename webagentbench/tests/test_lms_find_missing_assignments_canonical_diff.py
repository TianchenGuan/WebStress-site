"""End-to-end tests for lms_find_missing_assignments canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_find_missing_assignments",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _split_ids(raw: str) -> list[str]:
    return [aid.strip() for aid in raw.split(",") if aid.strip()]


def _recoverable_ids(targets: dict[str, str]) -> list[str]:
    return _split_ids(targets["recoverable_assignment_ids"])


def _missing_ids(targets: dict[str, str]) -> list[str]:
    return _split_ids(targets["missing_assignment_ids"])


def _unrecoverable_ids(targets: dict[str, str]) -> list[str]:
    return _split_ids(targets["unrecoverable_assignment_ids"])


def _submit_assignment(state, assignment_id: str, file_name: str, status: str = "late") -> None:
    for assignment in state.assignments:
        if assignment.id == assignment_id:
            assignment.submission_status = status
            assignment.file_name = file_name
            assignment.attempt_count += 1
            assignment.submitted_at = datetime.now(timezone.utc)
            return
    raise ValueError(f"assignment {assignment_id!r} not found")


def _target_assignment_id(targets: dict[str, str]) -> str:
    recoverable = _recoverable_ids(targets)
    assert recoverable, "seed must include at least one recoverable missing assignment"
    return recoverable[0]


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    for aid in _recoverable_ids(targets):
        _submit_assignment(state, aid, "late_recovery.pdf", status="late")

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, _target_assignment_id(targets), "wrong_upload.pdf", status="late")

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting with the wrong file name should fail"


def test_wrong_status_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, _target_assignment_id(targets), "late_recovery.pdf", status="submitted")

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting a past-due assignment as submitted should fail"


def test_wrong_assignment_submitted_fails():
    sm, sid, targets, initial, state = _setup_session()

    unrecoverable = _unrecoverable_ids(targets)
    assert unrecoverable, "seed must include at least one unrecoverable missing assignment"
    _submit_assignment(state, unrecoverable[0], "late_recovery.pdf", status="late")

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "submitting an unrecoverable missing assignment should violate the target selector"
    )


def test_extra_non_target_assignment_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, _target_assignment_id(targets), "late_recovery.pdf", status="late")
    extra = next(
        (a for a in state.assignments if a.id not in set(_recoverable_ids(targets))),
        None,
    )
    assert extra is not None, "seed must include a non-target assignment"
    _submit_assignment(state, extra.id, "late_recovery.pdf", status="late")

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "submitting an extra non-target assignment should violate the assignment invariant"
    )


def test_extra_enrollment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, _target_assignment_id(targets), "late_recovery.pdf", status="late")
    state.enrollments[0].status = "dropped"

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "dropping a course while submitting recoverable assignments should violate "
        "the enrollment invariant"
    )


def test_missing_assignment_subset_invariant_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, _target_assignment_id(targets), "late_recovery.pdf", status="late")
    missing = _missing_ids(targets)
    assert len(missing) >= 1, "seed must include missing assignments"
    for aid in missing[1:]:
        _submit_assignment(state, aid, "late_recovery.pdf", status="late")

    task = get_task("lms_find_missing_assignments")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "submitting missing assignments outside the recoverable set should fail"
    )
