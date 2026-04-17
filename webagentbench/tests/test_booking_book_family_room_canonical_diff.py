"""End-to-end tests for booking_book_family_room canonical_diff."""

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
    / "tasks" / "booking" / "booking_book_family_room.yaml"
)
TASK_ID = "booking_book_family_room"


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


def _book_family_room(state, targets):
    prop = state.get_property(targets["property_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Family Room")
    return state.create_reservation(
        property_id=targets["property_id"],
        room_type_id=room.id,
        check_in="2026-08-01",
        check_out="2026-08-06",
        guests=4,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(
            full_name=state.owner_name,
            email=state.owner_email,
        ),
        meals_included="breakfast",
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _book_family_room(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_room_fails():
    task, targets, initial, state = _setup_session(0)
    prop = state.get_property(targets["property_id"])
    other_room = next(rt for rt in prop.room_types if rt.name != "Family Room")
    state.create_reservation(
        property_id=targets["property_id"],
        room_type_id=other_room.id,
        check_in="2026-08-01",
        check_out="2026-08-06",
        guests=4,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong room type should fail"


def test_wrong_guests_fails():
    task, targets, initial, state = _setup_session(0)
    prop = state.get_property(targets["property_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Family Room")
    state.create_reservation(
        property_id=targets["property_id"],
        room_type_id=room.id,
        check_in="2026-08-01",
        check_out="2026-08-06",
        guests=2,  # wrong
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
        meals_included="breakfast",
    )
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong guest count should fail"
