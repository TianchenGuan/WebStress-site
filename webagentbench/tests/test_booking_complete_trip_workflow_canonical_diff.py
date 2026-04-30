"""End-to-end tests for booking_complete_trip_workflow canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Reservation, ReservationGuest, Review, SavedList, ReviewBreakdown
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_complete_trip_workflow.yaml"
)
TASK_ID = "booking_complete_trip_workflow"


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
    # 1. Create saved list with property
    sl = state.create_saved_list("Barcelona 2026")
    state.add_to_saved_list(sl.id, targets["book_prop_id"])
    # 2. Book Deluxe Sea View Room
    prop = state.get_property(targets["book_prop_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Deluxe Sea View Room")
    state.create_reservation(
        property_id=targets["book_prop_id"],
        room_type_id=room.id,
        check_in="2026-09-10",
        check_out="2026-09-15",
        guests=2,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    # 3. Write review for completed property
    from datetime import datetime, timezone
    review = Review(
        id=state._next_id("review"),
        property_id=targets["review_prop_id"],
        overall_score=8.5,
        author_name=state.owner_name,
        title="Lovely Barcelona stay",
        positive="Perfect location near Las Ramblas with excellent tapas restaurant",
        negative="",
        travel_purpose="leisure",
        traveled_with="family",
        created_at=datetime.now(timezone.utc),
    )
    state.add_review(review)
    # Mirror route side-effect: flip rating_submitted on reviewed reservation
    review_res = state.get_reservation(targets["review_res_id"])
    if review_res:
        review_res.rating_submitted = True
    # 4. Update preferences
    state.travel_preferences.preferred_bed_type = "queen"
    state.travel_preferences.dietary_restrictions.append("halal")


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
    sl = state.create_saved_list("Barcelona 2026")
    state.add_to_saved_list(sl.id, targets["book_prop_id"])
    prop = state.get_property(targets["book_prop_id"])
    # Book wrong room
    room = next(rt for rt in prop.room_types if rt.name != "Deluxe Sea View Room")
    state.create_reservation(
        property_id=targets["book_prop_id"],
        room_type_id=room.id,
        check_in="2026-09-10",
        check_out="2026-09-15",
        guests=2,
        rooms=1,
        payment_method_id="pm_1",
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    from datetime import datetime, timezone
    review = Review(
        id=state._next_id("review"),
        property_id=targets["review_prop_id"],
        overall_score=8.5,
        author_name=state.owner_name,
        title="Lovely Barcelona stay",
        positive="Perfect location near Las Ramblas",
        travel_purpose="leisure",
        traveled_with="family",
        created_at=datetime.now(timezone.utc),
    )
    state.add_review(review)
    review_res = state.get_reservation(targets["review_res_id"])
    if review_res:
        review_res.rating_submitted = True
    state.travel_preferences.preferred_bed_type = "queen"
    state.travel_preferences.dietary_restrictions.append("halal")
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "booking wrong room should fail"
