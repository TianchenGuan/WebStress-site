"""End-to-end tests for lms_check_assignment_grade canonical_diff."""

from pathlib import Path
import random

from webagentbench.backend.models.lms import LMSState
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.lms import LMSSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition


_TASK_YAML = Path(__file__).resolve().parents[1] / "tasks" / "lms" / "lms_check_assignment_grade.yaml"
TASK_ID = "lms_check_assignment_grade"


def _setup_session(seed: int):
    task = TaskDefinition.from_yaml(_TASK_YAML)
    runner = LMSSeedRunner()
    seeded_data, targets = runner.run(
        task=task,
        seed=seed,
        fake=FakeDataGenerator(seed),
        rng=random.Random(seed),
    )
    state = LMSState.model_validate(seeded_data)
    initial = state.model_copy(deep=True)
    return task, dict(targets), initial, state


def _submit_assignment(state, assignment_id: str, file_name: str = "improvement.pdf") -> None:
    for assignment in state.assignments:
        if assignment.id == assignment_id:
            assignment.submission_status = "submitted"
            assignment.file_name = file_name
            assignment.attempt_count += 1
            return
    raise ValueError(f"assignment {assignment_id!r} not found")


def _mark_read(state, announcement_id: str) -> None:
    for announcement in state.announcements:
        if announcement.id == announcement_id:
            announcement.is_read = True
            return
    raise ValueError(f"announcement {announcement_id!r} not found")


def _evaluate(task, initial, state, targets):
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _take_correct_action(state, targets) -> None:
    if targets["score_below_70"] == "true":
        _submit_assignment(state, targets["unsubmitted_hw_id"])
    else:
        _mark_read(state, targets["latest_announcement_id"])


def _take_wrong_branch_action(state, targets) -> None:
    if targets["score_below_70"] == "true":
        _mark_read(state, targets["latest_announcement_id"])
    else:
        _submit_assignment(state, targets["unsubmitted_hw_id"])


def _take_extra_action(state, targets) -> None:
    _take_correct_action(state, targets)
    extra = next(
        assignment
        for assignment in state.assignments
        if assignment.id != targets["unsubmitted_hw_id"]
    )
    _submit_assignment(state, extra.id)


def _take_wrong_target_action(state, targets) -> None:
    wrong_assignment = next(
        assignment
        for assignment in state.assignments
        if assignment.id != targets["unsubmitted_hw_id"]
    )
    _submit_assignment(state, wrong_assignment.id)


def test_correct_trajectory_passes():
    for seed in (0, 3):
        task, targets, initial, state = _setup_session(seed)
        _take_correct_action(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_fails():
    for seed in (0, 3):
        task, targets, initial, state = _setup_session(seed)
        _take_wrong_branch_action(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is False, f"seed {seed}: wrong branch should fail"


def test_extra_mutation_fails():
    for seed in (0, 3):
        task, targets, initial, state = _setup_session(seed)
        _take_extra_action(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is False, f"seed {seed}: extra mutation should fail"


def test_wrong_target_mutation_fails():
    for seed in (0, 3):
        task, targets, initial, state = _setup_session(seed)
        _take_wrong_target_action(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is False, f"seed {seed}: wrong target mutation should fail"
