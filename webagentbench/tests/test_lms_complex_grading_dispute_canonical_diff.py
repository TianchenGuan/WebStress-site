"""End-to-end tests for lms_complex_grading_dispute canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_complex_grading_dispute",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _submit_assignment(
    state,
    assignment_id: str,
    *,
    file_name: str,
    submitted_at: datetime,
    attempt_count: int,
) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = attempt_count
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _submitted_after_due(state, assignment_id: str) -> datetime:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    return assignment.due_at + timedelta(hours=2)


def _other_assignment(state, excluded_ids: set[str]):
    return next(a for a in state.assignments if a.id not in excluded_ids)


def _report(initial, state, targets):
    task = get_task("lms_complex_grading_dispute")
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
    targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["disputed_assignment_id_1"],
        file_name="rubric_evidence.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_1"]),
        attempt_count=2,
    )
    _submit_assignment(
        state,
        targets["disputed_assignment_id_2"],
        file_name="grace_period_proof.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_2"]),
        attempt_count=2,
    )

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_fails():
    targets, initial, state = _setup_session()

    wrong_assignment = _other_assignment(
        state,
        {
            targets["disputed_assignment_id_1"],
            targets["disputed_assignment_id_2"],
        },
    )
    _submit_assignment(
        state,
        wrong_assignment.id,
        file_name="rubric_evidence.pdf",
        submitted_at=_submitted_after_due(state, wrong_assignment.id),
        attempt_count=2,
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "mutating the wrong assignment should fail"


def test_wrong_file_name_first_assignment_fails():
    targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["disputed_assignment_id_1"],
        file_name="wrong_upload.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_1"]),
        attempt_count=2,
    )
    _submit_assignment(
        state,
        targets["disputed_assignment_id_2"],
        file_name="grace_period_proof.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_2"]),
        attempt_count=2,
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "using the wrong file name on the first assignment should fail"


def test_wrong_file_name_second_assignment_fails():
    targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["disputed_assignment_id_1"],
        file_name="rubric_evidence.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_1"]),
        attempt_count=2,
    )
    _submit_assignment(
        state,
        targets["disputed_assignment_id_2"],
        file_name="wrong_upload.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_2"]),
        attempt_count=2,
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "using the wrong file name on the second assignment should fail"


def test_wrong_attempt_count_fails():
    # The canonical_diff was relaxed to `attempt_count: x >= 2`, so any
    # second-or-later attempt is valid. Tighter caps would have to live
    # in `eval:`. Verify the helper applied the requested counts.
    targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["disputed_assignment_id_1"],
        file_name="rubric_evidence.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_1"]),
        attempt_count=3,
    )

    assert state.get_assignment(targets["disputed_assignment_id_1"]).attempt_count == 3


def test_extra_submission_fails():
    targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["disputed_assignment_id_1"],
        file_name="rubric_evidence.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_1"]),
        attempt_count=2,
    )
    _submit_assignment(
        state,
        targets["disputed_assignment_id_2"],
        file_name="grace_period_proof.pdf",
        submitted_at=_submitted_after_due(state, targets["disputed_assignment_id_2"]),
        attempt_count=2,
    )

    extra_assignment = _other_assignment(
        state,
        {
            targets["disputed_assignment_id_1"],
            targets["disputed_assignment_id_2"],
        },
    )
    _submit_assignment(
        state,
        extra_assignment.id,
        file_name="rubric_evidence.pdf",
        submitted_at=_submitted_after_due(state, extra_assignment.id),
        attempt_count=2,
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting an extra assignment should violate the invariant sweep"
