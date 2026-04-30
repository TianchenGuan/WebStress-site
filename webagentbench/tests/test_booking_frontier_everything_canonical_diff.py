"""End-to-end tests for booking_frontier_everything canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Message, PaymentMethod, Reservation, ReservationGuest, Review, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_everything'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.owner_phone = '+1-415-555-0200'
    state.owner_address = '200 Market St, San Francisco, CA 94105'
    state.settings.currency = 'EUR'
    state.settings.two_factor_enabled = True
    state.travel_preferences.preferred_bed_type = 'king'
    state.travel_preferences.dietary_restrictions = ['gluten-free']
    for res in state.reservations:
        if res.id == targets['cancel_res_id']:
            res.status = 'cancelled'
        elif res.id == targets['modify_res_id']:
            res.check_in = '2026-07-20'
            res.check_out = '2026-07-25'
            res.guest_info.special_requests = 'late checkout'
    # Demote the previously-default card (mirrors add_payment_method side-effect
    # when a new is_default=True card is added).
    prev_pm = next((pm for pm in state.payment_methods if pm.id == targets['prev_default_pm_id']), None)
    if prev_pm:
        prev_pm.is_default = False
    state.payment_methods.append(PaymentMethod(
        id="pm_visa7777",
        card_type="Visa",
        last_four="7777",
        expiry="12/29",
        holder_name="Jordan Parker",
        is_default=True,
    ))
    state.reservations.append(Reservation(
        id="res_bcn",
        property_id=targets['book_id'],
        property_name="Barcelona Beachfront Palace",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-09-01",
        check_out="2026-09-04",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=200.0,
        total_price=600.0,
        taxes_and_fees=60.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_visa7777",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_BCN",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reviews.append(Review(
        id="rev_lisbon",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=8.5,
        title="Great location",
        positive="Wonderful breakfast",
        negative="The street was noisy",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=now,
    ))
    # Mirror route side-effect: flip rating_submitted on reviewed reservation
    review_res = state.get_reservation(targets['review_res_id'])
    if review_res:
        review_res.rating_submitted = True
    state.saved_lists.append(SavedList(
        id="sl_2026_fav",
        name="2026 Favorites",
        property_ids=[targets['book_id']],
        created_at=now,
        updated_at=now,
    ))
    state.messages.append(Message(
        id="msg_early",
        property_id=targets['book_id'],
        property_name="Barcelona Beachfront Palace",
        subject="Early check-in request",
        body="Could I have early check-in around 10am?",
        sender="guest",
        created_at=now,
    ))


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        sm, sid, targets, initial, state = _setup_session(seed=seed)
        _apply_correct_state(targets, state)

        task = get_task(TASK_ID)
        agent_diff = compute_diff(initial, state)
        report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_cancel_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    for res in state.reservations:
        if res.id == targets['cancel_res_id']:
            res.status = 'confirmed'
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_2fa_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.settings.two_factor_enabled = False

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
