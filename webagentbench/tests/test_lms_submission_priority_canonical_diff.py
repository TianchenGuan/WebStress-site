"""End-to-end tests for lms_submission_priority canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_submission_priority",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _priority_ids(targets: dict[str, str]) -> list[str]:
    raw = targets["priority_order_ids"]
    return [part.strip() for part in raw.split(",") if part.strip()]


def _apply_submission(state, assignment_id: str, file_name: str) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submission_status = "submitted"
    assignment.file_name = file_name
    assignment.attempt_count += 1
    assignment.submitted_at = datetime.now(timezone.utc)


def _report_for(state, initial, targets):
    task = get_task("lms_submission_priority")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    priority_ids = _priority_ids(targets)
    _apply_submission(state, priority_ids[0], "priority_1.pdf")
    _apply_submission(state, priority_ids[1], "priority_2.pdf")

    report = _report_for(state, initial, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report_for(state, initial, targets)
    assert report.passed is False, "doing nothing should fail"


def test_swapped_priority_files_fail():
    _, _, targets, initial, state = _setup_session()
    priority_ids = _priority_ids(targets)
    _apply_submission(state, priority_ids[0], "priority_2.pdf")
    _apply_submission(state, priority_ids[1], "priority_1.pdf")

    report = _report_for(state, initial, targets)
    assert report.passed is False, "swapping the priority files should fail"


def test_second_priority_missing_fails():
    _, _, targets, initial, state = _setup_session()
    priority_ids = _priority_ids(targets)
    _apply_submission(state, priority_ids[0], "priority_1.pdf")

    report = _report_for(state, initial, targets)
    assert report.passed is False, "submitting only one priority assignment should fail"


def test_additional_priority_submission_allowed():
    _, _, targets, initial, state = _setup_session()
    priority_ids = _priority_ids(targets)
    extra_priority_id = next(a.id for a in state.assignments if a.id not in priority_ids)
    targets["priority_order_ids"] = targets["priority_order_ids"] + "," + extra_priority_id
    priority_ids = _priority_ids(targets)
    _apply_submission(state, priority_ids[0], "priority_1.pdf")
    _apply_submission(state, priority_ids[1], "priority_2.pdf")
    _apply_submission(state, priority_ids[2], "priority_3.pdf")

    report = _report_for(state, initial, targets)
    assert report.passed is True, f"at least top two allows additional priority work: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_additional_priority_wrong_order_file_fails():
    _, _, targets, initial, state = _setup_session()
    priority_ids = _priority_ids(targets)
    extra_priority_id = next(a.id for a in state.assignments if a.id not in priority_ids)
    targets["priority_order_ids"] = targets["priority_order_ids"] + "," + extra_priority_id
    priority_ids = _priority_ids(targets)
    _apply_submission(state, priority_ids[0], "priority_1.pdf")
    _apply_submission(state, priority_ids[1], "priority_2.pdf")
    _apply_submission(state, priority_ids[2], "priority_4.pdf")

    report = _report_for(state, initial, targets)
    assert report.passed is False, "additional priority submissions must keep priority order filenames"


def test_wrong_assignment_with_priority_name_fails():
    _, _, targets, initial, state = _setup_session()
    priority_ids = _priority_ids(targets)
    _apply_submission(state, priority_ids[0], "priority_1.pdf")
    _apply_submission(state, priority_ids[1], "priority_2.pdf")
    wrong_id = next(a.id for a in state.assignments if a.id not in priority_ids)
    _apply_submission(state, wrong_id, "priority_3.pdf")

    report = _report_for(state, initial, targets)
    assert report.passed is False, (
        "submitting a non-priority assignment with a priority filename should fail"
    )


def test_extra_non_priority_submission_fails():
    _, _, targets, initial, state = _setup_session()
    priority_ids = _priority_ids(targets)
    _apply_submission(state, priority_ids[0], "priority_1.pdf")
    _apply_submission(state, priority_ids[1], "priority_2.pdf")
    wrong_id = next(a.id for a in state.assignments if a.id not in priority_ids)
    _apply_submission(state, wrong_id, "other.pdf")

    report = _report_for(state, initial, targets)
    assert report.passed is False, "extra assignment submissions should fail"
