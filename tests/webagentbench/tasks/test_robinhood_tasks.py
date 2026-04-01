"""Tests for Robinhood task YAML loading and seeding."""

from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest

from webagentbench.backend.models.robinhood import RobinhoodState
from webagentbench.backend.seeders.robinhood import RobinhoodSeedRunner
from webagentbench.tasks._registry import load_all_tasks, get_task


EXPECTED_RH_TASKS = [
    "rh_buy_market_order",
    "rh_sell_shares",
    "rh_add_to_watchlist",
    "rh_cancel_pending_order",
    "rh_create_watchlist",
    "rh_set_price_alert",
    "rh_mark_notifications_read",
    "rh_check_buying_power",
    "rh_enable_extended_hours",
    "rh_deposit_funds",
]


def test_all_robinhood_tasks_load():
    """All rh_ tasks load with correct env_id and difficulty."""
    all_tasks = load_all_tasks()

    for task_id in EXPECTED_RH_TASKS:
        assert task_id in all_tasks, f"Task {task_id} not found in registry"
        task = all_tasks[task_id]
        assert task.env_id == "robinhood", f"{task_id} has wrong env_id: {task.env_id}"
        assert task.difficulty == "easy", f"{task_id} has wrong difficulty: {task.difficulty}"
        assert task.task_id == task_id
        assert len(task.primary_primitives) > 0, f"{task_id} has no primary primitives"


@pytest.mark.parametrize("task_id", EXPECTED_RH_TASKS)
def test_all_robinhood_tasks_seed(task_id: str):
    """Each rh_ task can be seeded with seed=42 and produces valid state."""
    runner = RobinhoodSeedRunner()
    task = get_task(task_id)
    seed = 42
    rng = random.Random(seed)
    fake = MagicMock()
    fake.name.return_value = "Jordan Baker"
    fake.domain_word.return_value = "example"

    base, targets = runner.run(task, seed, fake, rng)

    # Validate the base state against the Pydantic model
    state = RobinhoodState.model_validate(base)
    assert state.env_id == "robinhood"
    assert state.task_id == task_id

    # Verify eval config exists
    assert task.eval is not None, f"{task_id} has no eval config"
    assert len(task.eval.checks) > 0, f"{task_id} has no eval checks"
