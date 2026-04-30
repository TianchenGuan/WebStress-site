"""End-to-end tests for booking_write_simple_review canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Review, ReviewBreakdown
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_write_simple_review'


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


def _make_correct_review(targets, suffix=""):
    return Review(
        id=f"rev_correct{suffix}",
        property_id=targets['property_id'],
        reservation_id=targets['reservation_id'],
        author_name="Test User",
        author_country="US",
        overall_score=9,
        scores=ReviewBreakdown(),
        title="Wonderful experience - amazing stay",
        positive="The staff was incredibly friendly and the room was spotless.",
        negative="",
        room_type="Deluxe",
        travel_purpose="leisure",
        traveled_with="couple",
        stay_date="2026-03",
        created_at=datetime.now(timezone.utc),
        helpful_count=0,
        property_response="",
    )


def _flip_rating_submitted(state, targets):
    res_id = targets.get('reservation_id')
    if res_id:
        res = state.get_reservation(res_id)
        if res is not None:
            res.rating_submitted = True


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        state.reviews.append(_make_correct_review(targets, suffix=f"_{seed}"))
        _flip_rating_submitted(state, targets)
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_score_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    rev = _make_correct_review(targets)
    rev.overall_score = 7
    state.reviews.append(rev)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong score should fail"


def test_wrong_title_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    rev = _make_correct_review(targets)
    rev.title = "Nice stay"
    state.reviews.append(rev)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong title should fail"


def test_wrong_positive_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    rev = _make_correct_review(targets)
    rev.positive = "The location was great."
    state.reviews.append(rev)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing staff/spotless in positive should fail"


def test_excess_review_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.reviews.append(_make_correct_review(targets, suffix="_1"))
    state.reviews.append(_make_correct_review(targets, suffix="_2"))
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "excess review should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
