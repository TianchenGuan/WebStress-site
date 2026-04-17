"""End-to-end tests for booking_change_phone canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, BookingState
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_change_phone.yaml"
)
TASK_ID = "booking_change_phone"


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
        state.owner_phone = targets["new_phone"]
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    # Class 14: constraints-only
    assert report.passed is False


def test_wrong_phone_fails():
    task, targets, initial, state = _setup_session(0)
    state.owner_phone = "+1-999-999-9999"  # wrong
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong phone should fail"


def test_name_changed_fails():
    task, targets, initial, state = _setup_session(0)
    state.owner_phone = targets["new_phone"]
    state.owner_name = "Changed Name"  # should not change
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "changing name should fail"
