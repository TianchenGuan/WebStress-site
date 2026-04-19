"""End-to-end tests for amazon_variant_specific_purchase canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_variant_specific_purchase",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _checkout_with_variants(state, targets, *, variants=None, quantity=1):
    variants = variants or {
        targets["variant_name"]: targets["variant_value"],
        targets["variant_name_2"]: targets["variant_value_2"],
    }
    state.add_to_cart(
        targets["product_id"],
        quantity=quantity,
        variant_selections=variants,
    )
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.is_default)
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    return state.place_order(
        shipping_address_id=addr.id,
        payment_method_id=pm.id,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _checkout_with_variants(state, targets)

    task = get_task("amazon_variant_specific_purchase")
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

    task = get_task("amazon_variant_specific_purchase")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_color_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent selects Blue instead of Red for the Color variant
    _checkout_with_variants(
        state, targets,
        variants={
            targets["variant_name"]: "Blue",
            targets["variant_name_2"]: targets["variant_value_2"],
        },
    )

    task = get_task("amazon_variant_specific_purchase")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_size_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent selects Large instead of Medium for the Size variant
    _checkout_with_variants(
        state, targets,
        variants={
            targets["variant_name"]: targets["variant_value"],
            targets["variant_name_2"]: "Large",
        },
    )

    task = get_task("amazon_variant_specific_purchase")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_variant_selection_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent picks correct color but forgets size entirely
    _checkout_with_variants(
        state, targets,
        variants={targets["variant_name"]: targets["variant_value"]},
    )

    task = get_task("amazon_variant_specific_purchase")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_quantity_two_fails():
    _, _, targets, initial, state = _setup_session()

    _checkout_with_variants(state, targets, quantity=2)

    task = get_task("amazon_variant_specific_purchase")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
