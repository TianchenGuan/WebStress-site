"""End-to-end tests for booking_expert_cancel_chain canonical_diff."""

from datetime import datetime, timezone
from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState, Message, SavedList
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition

_TASK_YAML = (
    Path(__file__).resolve().parents[1]
    / "tasks" / "booking" / "booking_expert_cancel_chain.yaml"
)
TASK_ID = "booking_expert_cancel_chain"


def _setup_session(seed: int):
    task = TaskDefinition.from_yaml(_TASK_YAML)
    runner = BookingSeedRunner()
    seeded_data, targets = runner.run(
        task=task, seed=seed,
        fake=FakeDataGenerator(seed), rng=random.Random(seed),
    )
    state = BookingState.model_validate(seeded_data)
    initial = state.model_copy(deep=True)
    return task, dict(targets), initial, state


def _cancel(state, reservation_id: str) -> None:
    preview = state.compute_cancel_fee(reservation_id)
    state.cancel_reservation(reservation_id, fee_accepted=preview["fee_amount"])


def _evaluate(task, initial, state, targets):
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets), initial=initial, final=state,
    )


def _apply_correct_actions(state, targets):
    from datetime import datetime, timezone
    # Cancel all three
    _cancel(state, targets["cancel_res_id_1"])
    _cancel(state, targets["cancel_res_id_2"])
    _cancel(state, targets["cancel_res_id_3"])
    # Send messages
    for pid, subject, body in [
        (targets["cancel_id_1"], "Cancellation - Medical Emergency",
         "I must cancel due to a family medical emergency. I hope to visit in the future."),
        (targets["cancel_id_2"], "Cancellation - Work Conflict",
         "A mandatory work conference has been scheduled during my trip dates."),
        (targets["cancel_id_3"], "Cancellation - Travel Restrictions",
         "Travel restrictions have been imposed for the region."),
    ]:
        msg = Message(
            id=state._next_id("msg"),
            property_id=pid,
            property_name=state.get_property(pid).name,
            reservation_id="",
            subject=subject,
            body=body,
            sender="guest",
            read=False,
            created_at=datetime.now(timezone.utc),
        )
        state.messages.append(msg)
    # Create saved list with all three properties
    sl = state.create_saved_list("Cancelled Trips")
    for pid in [targets["cancel_id_1"], targets["cancel_id_2"], targets["cancel_id_3"]]:
        state.add_to_saved_list(sl.id, pid)


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        _apply_correct_actions(state, targets)
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_keep_reservation_also_cancelled_fails():
    task, targets, initial, state = _setup_session(0)
    _apply_correct_actions(state, targets)
    _cancel(state, targets["keep_res_id"])  # shouldn't cancel this
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "cancelling the keep reservation should fail"


def test_missing_one_cancel_fails():
    task, targets, initial, state = _setup_session(0)
    # Only cancel 2 of 3
    from datetime import datetime, timezone
    _cancel(state, targets["cancel_res_id_1"])
    _cancel(state, targets["cancel_res_id_2"])
    for pid, subject, body in [
        (targets["cancel_id_1"], "Cancellation - Medical Emergency", "Medical emergency."),
        (targets["cancel_id_2"], "Cancellation - Work Conflict", "Work conference."),
    ]:
        msg = Message(
            id=state._next_id("msg"),
            property_id=pid,
            property_name=state.get_property(pid).name,
            reservation_id="",
            subject=subject,
            body=body,
            sender="guest",
            read=False,
            created_at=datetime.now(timezone.utc),
        )
        state.messages.append(msg)
    sl = state.create_saved_list("Cancelled Trips")
    state.add_to_saved_list(sl.id, targets["cancel_id_1"])
    state.add_to_saved_list(sl.id, targets["cancel_id_2"])
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False, "missing one cancel should fail"
