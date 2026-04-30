"""End-to-end tests for amazon_price_research canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_price_research",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _view_target_earbuds(state, targets):
    # Need ≥2 distinct brands. Seed has SoundCore, JLab, Jabra → all distinct.
    state.add_to_browsing_history(targets["earbud1_id"])
    state.add_to_browsing_history(targets["earbud2_id"])
    state.add_to_browsing_history(targets["earbud3_id"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _view_target_earbuds(state, targets)

    task = get_task("amazon_price_research")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_price_research")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_added_to_cart_fails():
    _, _, targets, initial, state = _setup_session()

    _view_target_earbuds(state, targets)
    # Agent wrongly adds to cart
    state.add_to_cart(targets["earbud1_id"], quantity=1)

    task = get_task("amazon_price_research")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False

def test_only_one_earbud_viewed_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_browsing_history(targets["earbud1_id"])

    task = get_task("amazon_price_research")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
