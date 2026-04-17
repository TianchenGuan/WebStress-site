"""End-to-end tests for booking_expert_deal_hunter canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Reservation, ReservationGuest, SavedList, Message
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_expert_deal_hunter.yaml"
)
TASK_ID = "booking_expert_deal_hunter"


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
    from datetime import datetime, timezone
    prop = state.get_property(targets["deal_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Deluxe King with Breakfast")
    state.create_reservation(
        property_id=targets["deal_id"],
        room_type_id=room.id,
        check_in="2026-07-20",
        check_out="2026-07-25",
        guests=2,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    sl = state.create_saved_list("Amsterdam Deals")
    for pid in [targets["prop_id_1"], targets["prop_id_2"], targets["prop_id_3"]]:
        state.add_to_saved_list(sl.id, pid)
    msg = Message(
        id=state._next_id("msg"),
        property_id=targets["deal_id"],
        property_name=prop.name,
        reservation_id="",
        subject="Pre-arrival inquiry",
        body="Could you arrange an early check-in around 11am? We are arriving on an early flight.",
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


def test_wrong_property_fails():
    task, targets, initial, state = _setup_session(0)
    from datetime import datetime, timezone
    prop = state.get_property(targets["prop_id_1"])  # not the deal
    room = prop.room_types[0]
    state.create_reservation(
        property_id=targets["prop_id_1"],
        room_type_id=room.id,
        check_in="2026-07-20",
        check_out="2026-07-25",
        guests=2,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "booking wrong property should fail"
