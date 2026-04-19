"""End-to-end tests for amazon_add_new_address canonical_diff."""

from webagentbench.backend.models.amazon import Address
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_add_new_address",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _correct_address(state, targets):
    return Address(
        id=state._next_id("addr"),
        full_name=targets["full_name"],
        street_address=targets["street"],
        city=targets["city"],
        state=targets["state_code"],
        zip_code=targets["zip"],
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    state.add_address(_correct_address(state, targets))

    task = get_task("amazon_add_new_address")
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

    task = get_task("amazon_add_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_city_fails():
    _, _, targets, initial, state = _setup_session()

    wrong = _correct_address(state, targets)
    wrong.city = "Seattle"
    state.add_address(wrong)

    task = get_task("amazon_add_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_zip_fails():
    _, _, targets, initial, state = _setup_session()

    wrong = _correct_address(state, targets)
    wrong.zip_code = "99999"
    state.add_address(wrong)

    task = get_task("amazon_add_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_order_placed_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_address(_correct_address(state, targets))
    # Stray action — place an order
    pm = state.payment_methods[0]
    state.place_order(
        shipping_address_id=state.addresses[-1].id,
        payment_method_id=pm.id,
    )

    task = get_task("amazon_add_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
