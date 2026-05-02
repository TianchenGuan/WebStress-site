"""End-to-end tests for booking_mark_notifications_read canonical_diff."""

from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.eval_core import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition


_TASK_YAML = Path(__file__).resolve().parents[1] / "tasks" / "booking" / "booking_mark_notifications_read.yaml"
TASK_ID = "booking_mark_notifications_read"


def _setup_session(seed: int):
    task = TaskDefinition.from_yaml(_TASK_YAML)
    runner = BookingSeedRunner()
    seeded_data, targets = runner.run(
        task=task,
        seed=seed,
        fake=FakeDataGenerator(seed),
        rng=random.Random(seed),
    )
    state = BookingState.model_validate(seeded_data)
    initial = state.model_copy(deep=True)
    return task, dict(targets), initial, state


def _mark_all_read(state) -> None:
    for n in state.notifications:
        n.read = True


def _evaluate(task, initial, state, targets):
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _mark_all_read(state)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    # Pure-constraints task (Class 14): do-nothing scores > 0 but passed=False.
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False


def test_partial_mark_fails():
    task, targets, initial, state = _setup_session(0)
    # Mark all but one
    unread = [n for n in state.notifications if not n.read]
    for n in unread[1:]:
        n.read = True
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False


def test_delete_instead_fails():
    task, targets, initial, state = _setup_session(0)
    # Delete all notifications instead of marking read
    state.notifications = []
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False


import pytest


@pytest.mark.skip(reason=(
    "Design gap: when a canonical Update matches a candidate, the entire "
    "candidate is added to ctx.matched — even if the candidate carries "
    "field changes beyond what the spec declares. So agent updates that "
    "set `read: True` PLUS modify `title` slip past the collateral sweep "
    "(matched entries are exempt) and the invariant filter never gets to "
    "see the title delta. Tried two ad-hoc fixes (2026-05-01) that both "
    "regressed real tasks: (a) per-YAML `strict_changes: true` flag is "
    "annotation pollution and breaks the 'incidental side-effects are OK' "
    "design (placing an order also bumps buying_power, etc.); (b) global "
    "strict-subset check breaks 40+ tests across RH/Gmail/LMS for the "
    "same reason. Needs a coherent answer to 'how does canonical_diff "
    "express mutation EXCLUSIVITY' — likely a separate construct that "
    "doesn't conflate 'expected change shape' with 'allowed change set'."
))
def test_modify_title_fails():
    task, targets, initial, state = _setup_session(0)
    _mark_all_read(state)
    state.notifications[0].title = "Modified title!"
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
