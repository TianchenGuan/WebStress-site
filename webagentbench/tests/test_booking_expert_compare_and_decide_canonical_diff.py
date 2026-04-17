"""End-to-end tests for booking_expert_compare_and_decide canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Reservation, ReservationGuest, Review, SavedList
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_expert_compare_and_decide.yaml"
)
TASK_ID = "booking_expert_compare_and_decide"


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
    # 1. Book Rosewood London Deluxe Room using Visa 9876 (pm_4)
    prop = state.get_property(targets["target_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Deluxe Room")
    state.create_reservation(
        property_id=targets["target_id"],
        room_type_id=room.id,
        check_in="2026-10-15",
        check_out="2026-10-19",
        guests=2,
        rooms=1,
        payment_method_id="pm_4",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    # 2. Create London Shortlist with all four
    sl = state.create_saved_list("London Shortlist")
    for pid in [targets["prop_id_1"], targets["prop_id_2"], targets["prop_id_3"], targets["prop_id_4"]]:
        state.add_to_saved_list(sl.id, pid)
    # 3. Write review for The Savoy
    review = Review(
        id=state._next_id("review"),
        property_id=targets["completed_id"],
        overall_score=8.5,
        author_name=state.owner_name,
        title="Pleasant London stay",
        positive="Excellent afternoon tea service and prime West End location",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=datetime.now(timezone.utc),
    )
    state.add_review(review)


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


def test_wrong_payment_fails():
    task, targets, initial, state = _setup_session(0)
    from datetime import datetime, timezone
    prop = state.get_property(targets["target_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Deluxe Room")
    state.create_reservation(
        property_id=targets["target_id"],
        room_type_id=room.id,
        check_in="2026-10-15",
        check_out="2026-10-19",
        guests=2,
        rooms=1,
        payment_method_id="pm_1",  # wrong payment
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    sl = state.create_saved_list("London Shortlist")
    for pid in [targets["prop_id_1"], targets["prop_id_2"], targets["prop_id_3"], targets["prop_id_4"]]:
        state.add_to_saved_list(sl.id, pid)
    review = Review(
        id=state._next_id("review"),
        property_id=targets["completed_id"],
        overall_score=8.5,
        author_name=state.owner_name,
        title="Pleasant London stay",
        positive="Excellent afternoon tea service",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=datetime.now(timezone.utc),
    )
    state.add_review(review)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong payment method should fail"
