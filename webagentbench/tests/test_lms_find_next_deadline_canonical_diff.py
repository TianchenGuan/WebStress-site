"""End-to-end tests for lms_find_next_deadline canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_find_next_deadline",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _submit_assignment(state, assignment_id: str, file_name: str) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submission_status = "submitted"
    assignment.file_name = file_name
    assignment.attempt_count += 1
    assignment.submitted_at = datetime.now(timezone.utc)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["next_deadline_assignment_id"], "early_draft.pdf")

    task = get_task("lms_find_next_deadline")
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

    task = get_task("lms_find_next_deadline")
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


def test_wrong_assignment_fails():
    sm, sid, targets, initial, state = _setup_session()

    wrong_assignment = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id != targets["next_deadline_assignment_id"]
    )
    _submit_assignment(state, wrong_assignment, "early_draft.pdf")

    task = get_task("lms_find_next_deadline")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting the wrong assignment should fail the id selector"


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["next_deadline_assignment_id"], "wrong_draft.pdf")

    task = get_task("lms_find_next_deadline")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "using the wrong file name should fail"


def test_extra_submission_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["next_deadline_assignment_id"], "early_draft.pdf")
    wrong_assignment = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id != targets["next_deadline_assignment_id"]
    )
    _submit_assignment(state, wrong_assignment, "early_draft.pdf")

    task = get_task("lms_find_next_deadline")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting an extra assignment should violate the assignment invariant"
