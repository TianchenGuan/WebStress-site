"""End-to-end tests for booking_expert_family_vacation canonical_diff."""

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
    / "tasks" / "booking" / "booking_expert_family_vacation.yaml"
)
TASK_ID = "booking_expert_family_vacation"


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
    # 1. Book Family Room at main hotel
    prop = state.get_property(targets["prop_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Family Room")
    state.create_reservation(
        property_id=targets["prop_id"],
        room_type_id=room.id,
        check_in="2026-08-01",
        check_out="2026-08-08",
        guests=4,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
        meals_included="breakfast",
    )
    # 2. Create Family Trips list with both hotels
    sl = state.create_saved_list("Family Trips")
    state.add_to_saved_list(sl.id, targets["prop_id"])
    state.add_to_saved_list(sl.id, targets["alt_id"])
    # 3. Send family requirements message
    msg = Message(
        id=state._next_id("msg"),
        property_id=targets["prop_id"],
        property_name=prop.name,
        reservation_id="",
        subject="Family requirements",
        body="We are traveling with two children ages 5 and 8. Could you please arrange a crib?",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    )
    state.messages.append(msg)
    # 4. Update preferences
    state.travel_preferences.preferred_room_type = "family"
    state.travel_preferences.accessibility_needs = True


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


def test_wrong_room_fails():
    task, targets, initial, state = _setup_session(0)
    from datetime import datetime, timezone
    prop = state.get_property(targets["prop_id"])
    room = next(rt for rt in prop.room_types if rt.name != "Family Room")
    state.create_reservation(
        property_id=targets["prop_id"],
        room_type_id=room.id,
        check_in="2026-08-01",
        check_out="2026-08-08",
        guests=4,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    sl = state.create_saved_list("Family Trips")
    state.add_to_saved_list(sl.id, targets["prop_id"])
    state.add_to_saved_list(sl.id, targets["alt_id"])
    msg = Message(
        id=state._next_id("msg"),
        property_id=targets["prop_id"],
        property_name=prop.name,
        reservation_id="",
        subject="Family requirements",
        body="We are traveling with children ages 5 and 8.",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    )
    state.messages.append(msg)
    state.travel_preferences.preferred_room_type = "family"
    state.travel_preferences.accessibility_needs = True
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong room type should fail"
