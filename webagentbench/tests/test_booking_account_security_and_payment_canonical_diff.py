"""End-to-end tests for booking_account_security_and_payment canonical_diff."""

from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, PaymentMethod
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_account_security_and_payment.yaml"
)
TASK_ID = "booking_account_security_and_payment"


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


def _apply_correct_mutations(state, targets):
    """Apply all required mutations for a correct trajectory."""
    # Enable 2FA
    state.settings.two_factor_enabled = True
    # Disable deal_alerts
    state.settings.deal_alerts = False
    # Enable SMS notifications
    state.settings.sms_notifications = True
    # Remove the seeded Mastercard 5555 (the one added by task seed step)
    state.remove_payment_method(targets["remove_pm_id"])
    # Add new Visa ending in 3333 as default (use a unique ID that won't collide)
    new_pm = PaymentMethod(
        id="pm_new_visa_3333",
        card_type="Visa",
        last_four="3333",
        expiry="06/30",
        holder_name="Jordan Parker",
        is_default=True,
    )
    state.add_payment_method(new_pm)


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _apply_correct_mutations(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    # Constraints-only component: assert passed=False (Class 14 — no score==0 guarantee)
    assert report.passed is False


def test_wrong_card_type_fails():
    task, targets, initial, state = _setup_session(0)
    state.settings.two_factor_enabled = True
    state.settings.deal_alerts = False
    state.settings.sms_notifications = True
    state.remove_payment_method(targets["remove_pm_id"])
    # Wrong card type (Mastercard instead of Visa)
    new_pm = PaymentMethod(
        id="pm_new_mc_3333",
        card_type="Mastercard",
        last_four="3333",
        expiry="06/30",
        holder_name="Jordan Parker",
        is_default=True,
    )
    state.add_payment_method(new_pm)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong card type should fail"


def test_missing_2fa_fails():
    task, targets, initial, state = _setup_session(0)
    # Don't enable 2FA, but do everything else
    state.settings.deal_alerts = False
    state.settings.sms_notifications = True
    state.remove_payment_method(targets["remove_pm_id"])
    new_pm = PaymentMethod(
        id="pm_new_visa_3333",
        card_type="Visa",
        last_four="3333",
        expiry="06/30",
        holder_name="Jordan Parker",
        is_default=True,
    )
    state.add_payment_method(new_pm)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "missing 2FA should fail"


def test_missing_default_payment_pointer_fails():
    task, targets, initial, state = _setup_session(0)
    _apply_correct_mutations(state, targets)
    state.settings.default_payment_id = next(pm.id for pm in initial.payment_methods if pm.is_default)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "new default card must also update settings.default_payment_id"
