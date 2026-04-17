"""End-to-end tests for booking_frontier_social_reviewer canonical_diff.

Mixed task: constraint (preferred_room_type=suite) + 4 reviews + 1 saved list.
"""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Review, ReviewBreakdown, SavedList
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_social_reviewer'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial_snap = sm.get_initial_snapshot(sid)
    initial_dict = initial_snap.model_dump()
    state = sm.get_state(sid)
    return dict(targets), initial_snap, initial_dict, state


def _run(targets, initial_snap, initial_dict, state):
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial_dict, state.model_dump())
    return match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial_snap, final=state)


def _apply_all_mutations(state, targets, suffix=""):
    # Constraint: update preferred_room_type to suite
    state.travel_preferences.preferred_room_type = "suite"

    # Review 1: Tokyo - score 9.5, Outstanding in every way, leisure/family
    state.reviews.append(Review(
        id=f"rev1{suffix}", property_id=targets['prop_id_1'], reservation_id="",
        author_name="Jordan Parker", author_country="US",
        overall_score=9.5, scores=ReviewBreakdown(),
        title="Outstanding in every way - best stay ever",
        positive="The spa was incredible and the breakfast was exceptional.",
        negative="",
        room_type="Suite", travel_purpose="leisure", traveled_with="family",
        stay_date="2026-01", created_at=datetime.now(timezone.utc),
    ))

    # Review 2: Frankfurt - score 8.0, Solid business choice, conference/wifi positive, restaurant negative
    state.reviews.append(Review(
        id=f"rev2{suffix}", property_id=targets['prop_id_2'], reservation_id="",
        author_name="Jordan Parker", author_country="US",
        overall_score=8.0, scores=ReviewBreakdown(),
        title="Solid business choice for work trips",
        positive="Great conference facilities and excellent wifi throughout the hotel.",
        negative="The restaurant was closed for renovation and room service was slow.",
        room_type="Business", travel_purpose="business", traveled_with="solo",
        stay_date="2026-02", created_at=datetime.now(timezone.utc),
    ))

    # Review 3: Rome - score 6.5, Below expectations, location positive, cleanliness negative
    state.reviews.append(Review(
        id=f"rev3{suffix}", property_id=targets['prop_id_3'], reservation_id="",
        author_name="Jordan Parker", author_country="US",
        overall_score=6.5, scores=ReviewBreakdown(),
        title="Below expectations for the price",
        positive="The location is central and convenient.",
        negative="The room was not clean upon arrival, quite dirty.",
        room_type="Standard", travel_purpose="leisure", traveled_with="couple",
        stay_date="2026-03", created_at=datetime.now(timezone.utc),
    ))

    # Review 4: Lisbon - score 7.5, Good value for money, comfortable bed positive, walls negative
    state.reviews.append(Review(
        id=f"rev4{suffix}", property_id=targets['prop_id_4'], reservation_id="",
        author_name="Jordan Parker", author_country="US",
        overall_score=7.5, scores=ReviewBreakdown(),
        title="Good value for money stay",
        positive="Comfortable bed and affordable pricing.",
        negative="Thin walls meant we heard everything from neighboring rooms.",
        room_type="Standard", travel_purpose="leisure", traveled_with="friends",
        stay_date="2026-04", created_at=datetime.now(timezone.utc),
    ))

    # Top Stays list with 2 highest-scored properties (prop_id_1=9.5, prop_id_2=8.0)
    state.saved_lists.append(SavedList(
        id=f"list_top{suffix}",
        name="Top Stays",
        property_ids=[targets['prop_id_1'], targets['prop_id_2']],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        _apply_all_mutations(state, targets, suffix=f"_{seed}")
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_missing_constraint_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_all_mutations(state, targets)
    state.travel_preferences.preferred_room_type = "deluxe"  # forgot to set suite
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing suite preference should fail"


def test_wrong_review_score_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_all_mutations(state, targets)
    # Change Tokyo review score
    state.reviews[-5].overall_score = 9.0  # wrong
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong Tokyo review score should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
    assert report.score < 1.0
