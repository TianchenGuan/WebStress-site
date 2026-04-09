"""Booking environment seed stability and integrity tests.

Verifies that seeded state is deterministic, builders produce expected
outputs, evaluation expressions are error-free, and the task pipeline
is end-to-end functional.
"""
from __future__ import annotations

import random
import subprocess
import sys

import pytest

from webagentbench.backend.models.booking import BookingState, ReservationGuest
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.backend.state import materialize_task_state
from webagentbench.tasks._evaluator import evaluate as unified_evaluate
from webagentbench.tasks._registry import env_tasks, get_task, load_all_tasks
from webagentbench.tasks._seed_builders_booking import BOOKING_BUILDER_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_seed(task_id: str, seed: int = 42):
    task = get_task(task_id)
    rng = random.Random(seed)
    fake = FakeDataGenerator(seed)
    return BookingSeedRunner().run(task, seed, fake, rng)


def _materialize(task_id: str, seed: int = 42):
    return materialize_task_state("booking", task_id, seed=seed)


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------


def test_booking_builder_registry_is_populated() -> None:
    assert len(BOOKING_BUILDER_REGISTRY) >= 10


def test_booking_builders_import_without_circular_import() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from webagentbench.tasks._seed_builders_booking import BOOKING_BUILDER_REGISTRY; print(len(BOOKING_BUILDER_REGISTRY))",
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) >= 10


# ---------------------------------------------------------------------------
# Seed stability
# ---------------------------------------------------------------------------


def test_seed_determinism() -> None:
    """Same (task_id, seed) pair produces identical state."""
    base_a, targets_a = _run_seed("booking_cancel_upcoming")
    base_b, targets_b = _run_seed("booking_cancel_upcoming")
    assert targets_a == targets_b
    assert len(base_a["properties"]) == len(base_b["properties"])
    assert len(base_a["reservations"]) == len(base_b["reservations"])


def test_different_seeds_produce_different_targets() -> None:
    _, targets_42 = _run_seed("booking_cancel_upcoming", seed=42)
    _, targets_99 = _run_seed("booking_cancel_upcoming", seed=99)
    # Confirmation numbers should differ
    assert targets_42.get("confirmation_number") != targets_99.get("confirmation_number")


# ---------------------------------------------------------------------------
# State richness
# ---------------------------------------------------------------------------


def test_seeded_state_has_rich_account() -> None:
    """Verify the seeded account has realistic lived-in data."""
    _, state, _, _ = _materialize("booking_cancel_upcoming")
    assert len(state.properties) >= 100
    assert len(state.reservations) >= 10
    assert len(state.reviews) >= 50
    assert len(state.saved_lists) >= 3
    assert len(state.payment_methods) >= 4
    assert len(state.messages) >= 5
    assert len(state.notifications) >= 5
    assert len(state.search_history) >= 5
    assert state.genius.level >= 2
    assert state.wallet.balance > 0


def test_seeded_properties_span_multiple_cities() -> None:
    _, state, _, _ = _materialize("booking_cancel_upcoming")
    cities = {p.city for p in state.properties}
    assert len(cities) >= 6


def test_seeded_reservations_span_multiple_statuses() -> None:
    _, state, _, _ = _materialize("booking_cancel_upcoming")
    statuses = {r.status for r in state.reservations}
    assert "completed" in statuses
    assert "confirmed" in statuses


def test_id_counters_prevent_collisions() -> None:
    """After seeding, id_counters should be high enough to avoid collisions."""
    _, state, _, _ = _materialize("booking_cancel_upcoming")
    existing_review_ids = {r.id for r in state.reviews}
    new_id = state._next_id("review")
    assert new_id not in existing_review_ids


# ---------------------------------------------------------------------------
# All tasks materialize
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def booking_tasks():
    load_all_tasks.cache_clear()
    return [t for t in load_all_tasks().values() if t.env_id == "booking"]


def test_all_booking_tasks_materialize(booking_tasks) -> None:
    failures = []
    for task in booking_tasks:
        try:
            materialize_task_state("booking", task.task_id, seed=42)
        except Exception as exc:
            failures.append(f"{task.task_id}: {exc}")
    assert not failures, f"{len(failures)} tasks failed:\n" + "\n".join(failures)


def test_all_booking_tasks_have_error_free_eval(booking_tasks) -> None:
    """Every eval expression must parse and execute without errors."""
    failures = []
    for task in booking_tasks:
        try:
            _, state, targets, _ = materialize_task_state("booking", task.task_id, seed=42)
            state._initial_snapshot = state.state_snapshot()
            result = unified_evaluate(task, server_state=state, targets=targets, trajectory=[])
            for check in result.get("checks", []):
                if check.get("error"):
                    failures.append(f"{task.task_id} check '{check['desc']}': {check['error']}")
            for neg in result.get("negative_checks", []):
                if neg.get("error"):
                    failures.append(f"{task.task_id} neg '{neg['desc']}': {neg['error']}")
        except Exception as exc:
            failures.append(f"{task.task_id}: {exc}")
    assert not failures, f"{len(failures)} eval errors:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Difficulty distribution
# ---------------------------------------------------------------------------


def test_booking_has_all_difficulty_levels(booking_tasks) -> None:
    difficulties = {t.difficulty for t in booking_tasks}
    for d in ("easy", "medium", "hard", "expert", "frontier"):
        assert d in difficulties, f"Missing difficulty level: {d}"


def test_booking_has_at_least_10_per_difficulty(booking_tasks) -> None:
    counts: dict[str, int] = {}
    for t in booking_tasks:
        counts[t.difficulty] = counts.get(t.difficulty, 0) + 1
    for d, c in counts.items():
        assert c >= 10, f"Difficulty '{d}' has only {c} tasks (need >= 10)"


# ---------------------------------------------------------------------------
# Evaluation correctness (smoke tests)
# ---------------------------------------------------------------------------


def test_cancel_task_scores_perfectly_when_target_cancelled() -> None:
    _, state, targets, _ = _materialize("booking_cancel_upcoming")
    state._initial_snapshot = state.state_snapshot()
    state.cancel_reservation(targets["reservation_id"])
    task = get_task("booking_cancel_upcoming")
    result = unified_evaluate(task, server_state=state, targets=targets, trajectory=[])
    assert result["success"] is True
    assert result["score"] >= 0.9


def test_cancel_task_fails_when_nothing_done() -> None:
    _, state, targets, _ = _materialize("booking_cancel_upcoming")
    state._initial_snapshot = state.state_snapshot()
    task = get_task("booking_cancel_upcoming")
    result = unified_evaluate(task, server_state=state, targets=targets, trajectory=[])
    assert result["success"] is False


def test_enable_2fa_scores_perfectly() -> None:
    _, state, targets, _ = _materialize("booking_enable_2fa")
    state._initial_snapshot = state.state_snapshot()
    state.settings.two_factor_enabled = True
    task = get_task("booking_enable_2fa")
    result = unified_evaluate(task, server_state=state, targets=targets, trajectory=[])
    assert result["success"] is True
    assert result["score"] >= 0.9


def test_view_reservation_needs_audit_entry() -> None:
    """booking_view_reservation requires a reservation.view audit entry."""
    _, state, targets, _ = _materialize("booking_view_reservation")
    state._initial_snapshot = state.state_snapshot()
    task = get_task("booking_view_reservation")
    # Without the audit entry, should fail
    result = unified_evaluate(task, server_state=state, targets=targets, trajectory=[])
    assert result["success"] is False
    # With the audit entry, should pass
    from webagentbench.backend.models.base import AuditEntry
    state.audit_log.append(AuditEntry(
        action="reservation.view",
        payload={"reservation_id": targets["reservation_id"]},
    ))
    result2 = unified_evaluate(task, server_state=state, targets=targets, trajectory=[])
    assert result2["success"] is True
