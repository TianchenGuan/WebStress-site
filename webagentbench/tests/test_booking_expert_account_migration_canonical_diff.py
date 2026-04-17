"""End-to-end tests for booking_expert_account_migration canonical_diff."""

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
    / "tasks" / "booking" / "booking_expert_account_migration.yaml"
)
TASK_ID = "booking_expert_account_migration"


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
    state.owner_name = "Jordan A. Parker"
    state.owner_address = "100 Lake Shore Dr, Chicago, IL 60611"
    state.owner_phone = "+1-312-555-0199"
    # Remove Alex's Mastercard (the seeded one, not the base pm_5)
    state.remove_payment_method(targets["alex_pm_id"])
    # Add Amex 4444 (use unique IDs to avoid collision with seeded pm_6)
    pm_amex = PaymentMethod(
        id="pm_new_amex_4444",
        card_type="American Express",
        last_four="4444",
        expiry="09/29",
        holder_name="Jordan A. Parker",
        is_default=False,
    )
    state.add_payment_method(pm_amex)
    # Add Visa 6666 as default
    pm_visa = PaymentMethod(
        id="pm_new_visa_6666",
        card_type="Visa",
        last_four="6666",
        expiry="03/30",
        holder_name="Jordan A. Parker",
        is_default=True,
    )
    state.add_payment_method(pm_visa)


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


def test_missing_visa_fails():
    task, targets, initial, state = _setup_session(0)
    state.owner_name = "Jordan A. Parker"
    state.owner_address = "100 Lake Shore Dr, Chicago, IL 60611"
    state.owner_phone = "+1-312-555-0199"
    state.remove_payment_method(targets["alex_pm_id"])
    # Add only Amex, not Visa
    pm_amex = PaymentMethod(
        id="pm_new_amex_4444",
        card_type="American Express",
        last_four="4444",
        expiry="09/29",
        holder_name="Jordan A. Parker",
        is_default=True,  # amex as default, not visa
    )
    state.add_payment_method(pm_amex)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "missing Visa 6666 should fail"
