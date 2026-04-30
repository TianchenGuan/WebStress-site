"""End-to-end tests for booking_review_two_stays canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Review, ReviewBreakdown
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_review_two_stays'


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


def _make_review1(targets, suffix=""):
    return Review(
        id=f"rev1{suffix}",
        property_id=targets['prop_id_1'],
        reservation_id="",
        author_name="Test User",
        author_country="FR",
        overall_score=9.0,
        scores=ReviewBreakdown(),
        title="Exceptional experience - loved it",
        positive="The outstanding service was impeccable and the beautiful rooms were stunning.",
        negative="",
        room_type="Suite",
        travel_purpose="leisure",
        traveled_with="couple",
        stay_date="2026-02",
        created_at=datetime.now(timezone.utc),
        helpful_count=0,
        property_response="",
    )


def _make_review2(targets, suffix=""):
    return Review(
        id=f"rev2{suffix}",
        property_id=targets['prop_id_2'],
        reservation_id="",
        author_name="Test User",
        author_country="UK",
        overall_score=7.5,
        scores=ReviewBreakdown(),
        title="Good but could improve the noise levels",
        positive="The great location was convenient and the friendly staff were helpful.",
        negative="The rooms felt smaller than expected and the thin walls let in a lot of noise.",
        room_type="Standard",
        travel_purpose="business",
        traveled_with="solo",
        stay_date="2026-01",
        created_at=datetime.now(timezone.utc),
        helpful_count=0,
        property_response="",
    )


def _flip_rating_submitted(state, targets, key="reservation_id"):
    res_id = targets.get(key)
    if res_id:
        res = state.get_reservation(res_id)
        if res is not None:
            res.rating_submitted = True


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        state.reviews.append(_make_review1(targets, suffix=f"_{seed}"))
        state.reviews.append(_make_review2(targets, suffix=f"_{seed}"))
        _flip_rating_submitted(state, targets, "res_id_1")
        _flip_rating_submitted(state, targets, "res_id_2")
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_score_review1_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    rev1 = _make_review1(targets)
    rev1.overall_score = 8.0  # wrong
    state.reviews.append(rev1)
    state.reviews.append(_make_review2(targets))
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong score for review1 should fail"


def test_wrong_travel_purpose_review2_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.reviews.append(_make_review1(targets))
    rev2 = _make_review2(targets)
    rev2.travel_purpose = "leisure"  # wrong
    state.reviews.append(rev2)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong travel_purpose for review2 should fail"


def test_only_one_review_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.reviews.append(_make_review1(targets))
    # Missing review2
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing second review should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
