"""End-to-end tests for booking_change_bed_preference canonical_diff."""

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
    / "tasks" / "booking" / "booking_change_bed_preference.yaml"
)
TASK_ID = "booking_change_bed_preference"


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
        state.travel_preferences.preferred_bed_type = "queen"
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    # Class 14: constraints-only, no score==0 guarantee
    assert report.passed is False


def test_wrong_value_fails():
    task, targets, initial, state = _setup_session(0)
    state.travel_preferences.preferred_bed_type = "single"
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong bed type should fail"


def test_smoking_change_fails():
    task, targets, initial, state = _setup_session(0)
    state.travel_preferences.preferred_bed_type = "queen"
    state.travel_preferences.smoking = True  # should not be changed
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "changing smoking pref should fail"
