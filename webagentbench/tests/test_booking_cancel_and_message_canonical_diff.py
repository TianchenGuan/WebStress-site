"""End-to-end tests for booking_cancel_and_message canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Message
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_cancel_and_message.yaml"
)
TASK_ID = "booking_cancel_and_message"


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


def _cancel(state, reservation_id: str) -> None:
    preview = state.compute_cancel_fee(reservation_id)
    state.cancel_reservation(reservation_id, fee_accepted=preview["fee_amount"])


def _evaluate(task, initial, state, targets):
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets), initial=initial, final=state,
    )


def _apply_correct_actions(state, targets):
    _cancel(state, targets["reservation_id"])
    msg = Message(
        id=state._next_id("msg"),
        property_id=targets["property_id"],
        property_name=state.get_property(targets["property_id"]).name,
        reservation_id=targets["reservation_id"],
        subject="Cancellation - Change of Plans",
        body="I had to cancel due to a family emergency and hope to rebook in the future.",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    )
    state.messages.append(msg)


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


def test_cancel_without_message_fails():
    task, targets, initial, state = _setup_session(0)
    _cancel(state, targets["reservation_id"])
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "cancel without message should fail"


def test_message_without_cancel_fails():
    task, targets, initial, state = _setup_session(0)
    msg = Message(
        id=state._next_id("msg"),
        property_id=targets["property_id"],
        property_name=state.get_property(targets["property_id"]).name,
        reservation_id=targets["reservation_id"],
        subject="Cancellation - Change of Plans",
        body="I had to cancel due to a family emergency.",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    )
    state.messages.append(msg)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "message without cancel should fail"
