"""End-to-end tests for booking_delete_saved_list canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, SavedList
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_delete_saved_list.yaml"
)
TASK_ID = "booking_delete_saved_list"


def _setup_session(seed: int):
    task = TaskDefinition.from_yaml(_TASK_YAML)
    runner = BookingSeedRunner()
    seeded_data, targets = runner.run(
        task=task, seed=seed,
        fake=FakeDataGenerator(seed), rng=random.Random(seed),
    )
    state = BookingState.model_validate(seeded_data)
    initial = state.model_copy(deep=True)
    return task, dict(targets), initial, state


def _evaluate(task, initial, state, targets):
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets), initial=initial, final=state,
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        state.delete_saved_list(targets["list_id"])
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_list_deleted_fails():
    task, targets, initial, state = _setup_session(0)
    other_list = next(sl for sl in state.saved_lists if sl.id != targets["list_id"])
    state.delete_saved_list(other_list.id)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "deleting wrong list should fail"


def test_extra_list_deleted_fails():
    task, targets, initial, state = _setup_session(0)
    state.delete_saved_list(targets["list_id"])
    # Also delete another list
    if state.saved_lists:
        state.delete_saved_list(state.saved_lists[0].id)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "deleting extra list should fail"
