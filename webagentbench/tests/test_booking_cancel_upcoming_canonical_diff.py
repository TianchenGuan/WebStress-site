"""End-to-end tests for booking_cancel_upcoming canonical_diff."""

from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition


_TASK_YAML = Path(__file__).resolve().parents[1] / "tasks" / "booking" / "booking_cancel_upcoming.yaml"
TASK_ID = "booking_cancel_upcoming"


def _setup_session(seed: int):
    task = TaskDefinition.from_yaml(_TASK_YAML)
    runner = BookingSeedRunner()
    seeded_data, targets = runner.run(
        task=task,
        seed=seed,
        fake=FakeDataGenerator(seed),
        rng=random.Random(seed),
    )
    state = BookingState.model_validate(seeded_data)
    initial = state.model_copy(deep=True)
    return task, dict(targets), initial, state


def _cancel_reservation(state, reservation_id: str) -> None:
    preview = state.compute_cancel_fee(reservation_id)
    state.cancel_reservation(reservation_id, fee_accepted=preview["fee_amount"])


def _evaluate(task, initial, state, targets):
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _cancel_reservation(state, targets["reservation_id"])
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_reservation_fails():
    task, targets, initial, state = _setup_session(0)
    wrong = next(
        r for r in state.reservations
        if r.id != targets["reservation_id"]
        and r.status in ("confirmed", "upcoming", "modified")
    )
    _cancel_reservation(state, wrong.id)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False


def test_cancel_both_fails():
    task, targets, initial, state = _setup_session(0)
    _cancel_reservation(state, targets["reservation_id"])
    other = next(
        (r for r in state.reservations
         if r.id != targets["reservation_id"] and r.status not in ("cancelled", "completed", "no_show")),
        None,
    )
    if other is not None:
        _cancel_reservation(state, other.id)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
