"""End-to-end tests for booking_add_payment canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, PaymentMethod
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_add_payment.yaml"
)
TASK_ID = "booking_add_payment"


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


def _add_correct_card(state):
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Discover",
        last_four="7777",
        expiry="09/28",
        holder_name="Jordan Parker",
        is_default=False,
    )
    state.add_payment_method(pm)
    return pm


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _add_correct_card(state)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_card_type_fails():
    task, targets, initial, state = _setup_session(0)
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Mastercard",
        last_four="7777",
        expiry="09/28",
        holder_name="Jordan Parker",
        is_default=False,
    )
    state.add_payment_method(pm)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong card type should fail"


def test_extra_card_fails():
    task, targets, initial, state = _setup_session(0)
    _add_correct_card(state)
    _add_correct_card(state)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "extra payment method should fail"
