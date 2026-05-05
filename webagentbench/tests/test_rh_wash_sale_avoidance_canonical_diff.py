"""End-to-end tests for rh_wash_sale_avoidance canonical_diff.

Task: Sell all loss positions, skipping any purchased within the last 30 days.

Verifies:
  - Correct harvest (sell eligible losses only) passes.
  - Wash sale violation (selling a recent-buy position) fails.
  - Selling a gain position fails.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from webagentbench.backend.state import SessionManager
from webagentbench.eval_core import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


REPO_ROOT = Path(__file__).resolve().parents[2]


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_wash_sale_avoidance",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_harvest(state, targets):
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]]
    for sym in eligible:
        pos = state.get_position(sym)
        if pos and pos.quantity > 0:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)


def _target_recent_loss_symbols(targets):
    return sorted(set(targets["loss_symbols"]) & set(targets["recent_buy_symbols"]))


def _actual_recent_loss_symbols(state, targets):
    return sorted(set(targets["loss_symbols"]) & state.recent_purchase_symbols(30))


def test_recent_buy_targets_match_actual_ledger_for_loss_positions():
    """Wash-sale targets must reflect the actual visible transaction ledger."""
    sm, sid, targets, initial, state = _setup_session()
    del sm, sid, initial

    assert _target_recent_loss_symbols(targets) == _actual_recent_loss_symbols(state, targets)
    assert len([s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]]) == 1


def test_recent_buy_targets_do_not_depend_on_python_hash_seed():
    """Regression for unordered set iteration changing which losses are safe to sell."""
    script = """
import json
from webagentbench.backend.state import SessionManager

sm = SessionManager()
sid, targets, _seed = sm.create_session("robinhood", "rh_wash_sale_avoidance", seed=42)
state = sm.get_state(sid)
payload = {
    "loss_symbols": targets["loss_symbols"],
    "recent_buy_symbols": targets["recent_buy_symbols"],
    "target_recent_losses": sorted(set(targets["loss_symbols"]) & set(targets["recent_buy_symbols"])),
    "actual_recent_losses": sorted(set(targets["loss_symbols"]) & state.recent_purchase_symbols(30)),
    "eligible_losses": [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]],
}
print(json.dumps(payload, sort_keys=True))
"""
    payloads = []
    for hash_seed in ("0", "9"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["target_recent_losses"] == payload["actual_recent_losses"]
        assert len(payload["eligible_losses"]) == 1
        payloads.append(payload)

    assert payloads[0] == payloads[1]


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_harvest(state, targets)

    task = get_task("rh_wash_sale_avoidance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wash_sale_violation_fails():
    """Agent sells a position bought within the last 30 days."""
    sm, sid, targets, initial, state = _setup_session()
    recent = targets["recent_buy_symbols"]
    if recent:
        pos = state.get_position(recent[0])
        if pos and pos.quantity > 0:
            state.place_order(symbol=recent[0], side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_wash_sale_avoidance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wash sale violation should fail"


def test_selling_gain_position_fails():
    """Agent sells a gain position (not a loss position)."""
    sm, sid, targets, initial, state = _setup_session()
    gains = targets["gain_symbols"]
    eligible_gain = next((s for s in gains if s not in targets["recent_buy_symbols"]), None)
    if eligible_gain:
        pos = state.get_position(eligible_gain)
        if pos and pos.quantity > 0:
            state.place_order(symbol=eligible_gain, side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_wash_sale_avoidance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling a gain position should fail"
