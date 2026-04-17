"""End-to-end tests for booking_review_completed_stay canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Review, ReviewBreakdown
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_review_completed_stay'


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
        overall_score=8.5,
        scores=ReviewBreakdown(),
        title="Wonderful experience - great stay",
        positive="The staff was amazing and the location was perfect.",
        negative="The room could have been bigger.",
        room_type="Deluxe",
        travel_purpose="leisure",
        traveled_with="couple",
        stay_date="2026-03",
        created_at=datetime.now(timezone.utc),
        helpful_count=0,
        property_response="",
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        state.reviews.append(_make_correct_review(targets, suffix=f"_{seed}"))
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_score_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    rev = _make_correct_review(targets)
    rev.overall_score = 6.0
    state.reviews.append(rev)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong score should fail"


def test_wrong_positive_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    rev = _make_correct_review(targets)
    rev.positive = "Nice place."
    state.reviews.append(rev)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing staff/location in positive should fail"


def test_wrong_negative_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    rev = _make_correct_review(targets)
    rev.negative = "Nothing to complain."
    state.reviews.append(rev)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing room in negative should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
