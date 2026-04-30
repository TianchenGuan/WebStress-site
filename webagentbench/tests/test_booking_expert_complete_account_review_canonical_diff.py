"""End-to-end tests for booking_expert_complete_account_review canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Reservation, ReservationGuest, Review, PaymentMethod
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_expert_complete_account_review.yaml"
)
TASK_ID = "booking_expert_complete_account_review"


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
    state.owner_phone = "+1-415-555-0234"
    state.owner_address = "500 Market Street, San Francisco, CA 94105"
    state.settings.currency = "EUR"
    state.settings.newsletter = True
    state.settings.deal_alerts = False
    state.travel_preferences.preferred_bed_type = "queen"
    state.travel_preferences.floor_preference = "high"
    state.travel_preferences.dietary_restrictions.append("vegan")
    # Add Mastercard 2222
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Mastercard",
        last_four="2222",
        expiry="05/30",
        holder_name="Jordan Parker",
        is_default=False,
    )
    new_pm = state.add_payment_method(pm)
    # Book Deluxe Room using new Mastercard
    prop = state.get_property(targets["prop_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Deluxe Room")
    state.create_reservation(
        property_id=targets["prop_id"],
        room_type_id=room.id,
        check_in="2026-10-20",
        check_out="2026-10-24",
        guests=2,
        rooms=1,
        payment_method_id=new_pm.id,
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    # Write review for The Fairmont Chicago
    review = Review(
        id=state._next_id("review"),
        property_id=targets["review_id"],
        overall_score=9.0,
        author_name=state.owner_name,
        title="Outstanding hospitality",
        positive="The staff went above and beyond and the rooftop bar had stunning city views",
        negative="Parking was limited and expensive",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=datetime.now(timezone.utc),
    )
    state.add_review(review)
    # Mirror route side-effect: flip rating_submitted on reviewed reservation
    review_res = state.get_reservation(targets["review_res_id"])
    if review_res:
        review_res.rating_submitted = True


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


def test_wrong_review_score_fails():
    task, targets, initial, state = _setup_session(0)
    from datetime import datetime, timezone
    state.owner_phone = "+1-415-555-0234"
    state.owner_address = "500 Market Street, San Francisco, CA 94105"
    state.settings.currency = "EUR"
    state.settings.newsletter = True
    state.settings.deal_alerts = False
    state.travel_preferences.preferred_bed_type = "queen"
    state.travel_preferences.floor_preference = "high"
    state.travel_preferences.dietary_restrictions.append("vegan")
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Mastercard",
        last_four="2222",
        expiry="05/30",
        holder_name="Jordan Parker",
        is_default=False,
    )
    new_pm = state.add_payment_method(pm)
    prop = state.get_property(targets["prop_id"])
    room = next(rt for rt in prop.room_types if rt.name == "Deluxe Room")
    state.create_reservation(
        property_id=targets["prop_id"],
        room_type_id=room.id,
        check_in="2026-10-20",
        check_out="2026-10-24",
        guests=2,
        rooms=1,
        payment_method_id=new_pm.id,
        guest_info=ReservationGuest(full_name=state.owner_name, email=state.owner_email),
    )
    review = Review(
        id=state._next_id("review"),
        property_id=targets["review_id"],
        overall_score=7.5,  # wrong score
        author_name=state.owner_name,
        title="Outstanding hospitality",
        positive="Rooftop bar had stunning city views",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=datetime.now(timezone.utc),
    )
    state.add_review(review)
    review_res = state.get_reservation(targets["review_res_id"])
    if review_res:
        review_res.rating_submitted = True
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "wrong review score should fail"
