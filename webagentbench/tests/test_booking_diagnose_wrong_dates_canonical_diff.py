"""End-to-end tests for booking_diagnose_wrong_dates canonical_diff."""

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
    / "tasks" / "booking" / "booking_diagnose_wrong_dates.yaml"
)
TASK_ID = "booking_diagnose_wrong_dates"


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
    _cancel(state, targets["wrong_res_id"])
    prop = state.get_property(targets["target_prop_id"])
    room = next(rt for rt in prop.room_types if rt.id == targets["target_room_id"])
    state.create_reservation(
        property_id=targets["target_prop_id"],
        room_type_id=room.id,
        check_in="2026-07-15",
        check_out="2026-07-19",
        guests=2,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
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


def test_cancel_only_fails():
    task, targets, initial, state = _setup_session(0)
    _cancel(state, targets["wrong_res_id"])
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "cancel without rebook should fail"


def test_wrong_dates_rebook_fails():
    task, targets, initial, state = _setup_session(0)
    _cancel(state, targets["wrong_res_id"])
    prop = state.get_property(targets["target_prop_id"])
    room = next(rt for rt in prop.room_types if rt.id == targets["target_room_id"])
    state.create_reservation(
        property_id=targets["target_prop_id"],
        room_type_id=room.id,
        check_in="2026-07-10",  # wrong dates (original)
        check_out="2026-07-14",
        guests=2,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "rebooking with wrong dates should fail"
