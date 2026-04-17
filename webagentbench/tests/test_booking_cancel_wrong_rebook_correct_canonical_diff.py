"""End-to-end tests for booking_cancel_wrong_rebook_correct canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Reservation
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_cancel_wrong_rebook_correct.yaml"
)
TASK_ID = "booking_cancel_wrong_rebook_correct"


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


def _apply_correct_actions(state, targets):
    state.cancel_reservation(targets["wrong_res_id"])
    state.modify_reservation(
        targets["correct_res_id"],
        special_requests="Extra pillows and hypoallergenic bedding please. Celebrating anniversary.",
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _apply_correct_actions(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_cancel_wrong_reservation_only_fails():
    task, targets, initial, state = _setup_session(0)
    state.cancel_reservation(targets["wrong_res_id"])
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "cancel only without modify should fail"


def test_wrong_cancel_target_fails():
    task, targets, initial, state = _setup_session(0)
    # Cancel the correct reservation instead of the wrong one
    state.cancel_reservation(targets["correct_res_id"])
    state.modify_reservation(
        targets["wrong_res_id"],
        special_requests="Extra pillows and hypoallergenic bedding. Celebrating anniversary.",
    )
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "cancelling correct reservation should fail"
