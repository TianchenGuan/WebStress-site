"""End-to-end tests for lms_weighted_category_optimization canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_weighted_category_optimization",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return dict(targets), initial, state


def _submit_assignment(state, assignment_id: str, *, file_name: str) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submission_status = "submitted"
    assignment.file_name = file_name


def _report(initial, state, targets):
    task = get_task("lms_weighted_category_optimization")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _non_target_assignment(state, target_assignment_id: str):
    for assignment in state.assignments:
        if assignment.id != target_assignment_id:
            return assignment
    raise ValueError("seed must include at least one non-target assignment")


def test_correct_trajectory_passes():
    targets, initial, state = _setup_session()

    _submit_assignment(state, targets["worst_category_assignment_id"], file_name="category_boost.pdf")

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_id_fails():
    targets, initial, state = _setup_session()

    _submit_assignment(state, targets["decoy_assignment_id"], file_name="category_boost.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "submitting the decoy assignment should fail the target assignment selector"
    )


def test_wrong_file_name_fails():
    targets, initial, state = _setup_session()

    _submit_assignment(state, targets["worst_category_assignment_id"], file_name="wrong_upload.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the target assignment with the wrong file should fail"


def test_extra_mutation_fails():
    targets, initial, state = _setup_session()

    _submit_assignment(state, targets["worst_category_assignment_id"], file_name="category_boost.pdf")
    collateral = _non_target_assignment(state, targets["worst_category_assignment_id"])
    collateral.submission_status = "submitted"
    collateral.file_name = "extra_submission.pdf"

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "changing a second assignment should violate the non-target assignment invariant"
    )
