"""End-to-end tests for booking_book_with_specific_payment canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Reservation, ReservationGuest
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_book_with_specific_payment.yaml"
)
TASK_ID = "booking_book_with_specific_payment"


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


def _book_superior_double(state, targets, payment_method_id="pm_2"):
    prop = state.get_property(targets["property_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Superior Double")
    return state.create_reservation(
        property_id=targets["property_id"],
        room_type_id=room.id,
        check_in="2026-07-10",
        check_out="2026-07-12",
        guests=2,
        rooms=1,
        payment_method_id=payment_method_id,
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _book_superior_double(state, targets, payment_method_id="pm_2")
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_payment_fails():
    task, targets, initial, state = _setup_session(0)
    _book_superior_double(state, targets, payment_method_id="pm_1")  # default Visa, wrong
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "using default Visa (pm_1) should fail"
