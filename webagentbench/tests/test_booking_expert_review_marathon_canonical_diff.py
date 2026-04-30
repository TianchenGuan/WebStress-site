"""End-to-end tests for booking_expert_review_marathon canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_review_marathon'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _flip_rating_submitted(state, targets):
    for key in ('res_id_1', 'res_id_2', 'res_id_3'):
        res_id = targets.get(key)
        if res_id:
            res = state.get_reservation(res_id)
            if res is not None:
                res.rating_submitted = True


def _apply_correct_reviews(targets, state):
    now = datetime.now(timezone.utc)
    state.reviews.append(Review(
        id="rev_rome",
        property_id=targets['prop_id_1'],
        author_name="Jordan Parker",
        overall_score=9.5,
        title="Absolutely magnificent",
        positive="The rooftop terrace was incredible",
        negative="",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=now,
    ))
    state.reviews.append(Review(
        id="rev_berlin",
        property_id=targets['prop_id_2'],
        author_name="Jordan Parker",
        overall_score=7.0,
        title="Decent but disappointing",
        positive="Good location and transport links",
        negative="The bathroom was outdated and breakfast was poor",
        travel_purpose="business",
        traveled_with="solo",
        created_at=now,
    ))
    state.reviews.append(Review(
        id="rev_barcelona",
        property_id=targets['prop_id_3'],
        author_name="Jordan Parker",
        overall_score=8.0,
        title="Solid choice for families",
        positive="Great pool area for kids",
        negative="The restaurant was overpriced for the quality",
        travel_purpose="leisure",
        traveled_with="family",
        created_at=now,
    ))


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        sm, sid, targets, initial, state = _setup_session(seed=seed)
        _apply_correct_reviews(targets, state)
        _flip_rating_submitted(state, targets)

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


def test_wrong_score_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_reviews(targets, state)
    state.reviews[-3].overall_score = 8.0  # wrong score for Rome (should be 9.5)

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_travel_purpose_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_reviews(targets, state)
    state.reviews[-2].travel_purpose = "leisure"  # Berlin should be business

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
