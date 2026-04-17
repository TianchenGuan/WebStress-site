"""End-to-end tests for booking_frontier_social_reviewer canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import Review, SavedList
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_social_reviewer'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_reviews(targets):
    now = datetime.now(timezone.utc)
    return [
        Review(
            id="rev_1",
            property_id=targets['prop_id_1'],
            author_name="Jordan Parker",
            overall_score=9.5,
            title="Outstanding in every way",
            positive="The spa and breakfast were incredible, staff was wonderful",
            negative="",
            travel_purpose="leisure",
            traveled_with="family",
            created_at=now,
        ),
        Review(
            id="rev_2",
            property_id=targets['prop_id_2'],
            author_name="Jordan Parker",
            overall_score=8.0,
            title="Solid business choice",
            positive="Great conference facilities and wifi",
            negative="The restaurant was average",
            travel_purpose="business",
            traveled_with="solo",
            created_at=now,
        ),
        Review(
            id="rev_3",
            property_id=targets['prop_id_3'],
            author_name="Jordan Parker",
            overall_score=6.5,
            title="Below expectations",
            positive="Central location",
            negative="Renovation noise and not clean",
            travel_purpose="leisure",
            traveled_with="couple",
            created_at=now,
        ),
        Review(
            id="rev_4",
            property_id=targets['prop_id_4'],
            author_name="Jordan Parker",
            overall_score=7.5,
            title="Good value for money",
            positive="Comfortable bed and great price",
            negative="Thin walls",
            travel_purpose="leisure",
            traveled_with="friends",
            created_at=now,
        ),
    ]


def _make_saved_list(targets):
    now = datetime.now(timezone.utc)
    return SavedList(
        id="sl_top_stays",
        name="Top Stays",
        property_ids=[targets['prop_id_1'], targets['prop_id_2']],
        created_at=now,
        updated_at=now,
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        sm, sid, targets, initial, state = _setup_session(seed=seed)
        state.travel_preferences.preferred_room_type = 'suite'
        for rev in _make_reviews(targets):
            state.reviews.append(rev)
        state.saved_lists.append(_make_saved_list(targets))

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
    state.travel_preferences.preferred_room_type = 'suite'
    reviews = _make_reviews(targets)
    reviews[0] = Review(
        id="rev_1",
        property_id=targets['prop_id_1'],
        author_name="Jordan Parker",
        overall_score=8.0,  # wrong score (should be 9.5)
        title="Outstanding in every way",
        positive="Great spa",
        negative="",
        travel_purpose="leisure",
        traveled_with="family",
        created_at=datetime.now(timezone.utc),
    )
    for rev in reviews:
        state.reviews.append(rev)
    state.saved_lists.append(_make_saved_list(targets))

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    state.travel_preferences.preferred_room_type = 'suite'
    reviews = _make_reviews(targets)
    reviews[0] = Review(
        id="rev_1",
        property_id="prop_wrong_decoy",  # wrong property
        author_name="Jordan Parker",
        overall_score=9.5,
        title="Outstanding in every way",
        positive="Great spa",
        negative="",
        travel_purpose="leisure",
        traveled_with="family",
        created_at=datetime.now(timezone.utc),
    )
    for rev in reviews:
        state.reviews.append(rev)
    state.saved_lists.append(_make_saved_list(targets))

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
