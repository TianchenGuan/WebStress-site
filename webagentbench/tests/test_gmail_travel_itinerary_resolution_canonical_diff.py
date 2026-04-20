"""End-to-end tests for gmail_travel_itinerary_resolution canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_travel_itinerary_resolution',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward rebooked flight to travel assistant
    state.forward_email(
        targets["flight_rebooked_email_id"],
        to=["travel.assistant@ops.thornton.com"],
    )
    # Forward Denver hotel to travel assistant
    state.forward_email(
        targets["hotel_denver_email_id"],
        to=["travel.assistant@ops.thornton.com"],
    )
    # Create filter for airline sender with Travel label
    state.create_filter(FilterRule(
        id='f_travel', name='airline filter',
        from_addresses=[targets["airline_sender"]],
        add_labels=["Travel"],
    ))


def test_correct_trajectory_passes():
    """Forward correct itinerary items and create filter — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_travel_itinerary_resolution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_travel_itinerary_resolution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_flight_forwarded_fails():
    """Forward superseded (original) flight instead of rebooked — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.forward_email(
        targets["flight_original_email_id"],  # wrong flight
        to=["travel.assistant@ops.thornton.com"],
    )
    state.forward_email(
        targets["hotel_denver_email_id"],
        to=["travel.assistant@ops.thornton.com"],
    )
    state.create_filter(FilterRule(
        id='f_travel', name='airline filter',
        from_addresses=[targets["airline_sender"]],
        add_labels=["Travel"],
    ))

    task = get_task('gmail_travel_itinerary_resolution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "forwarding wrong flight should fail"
