"""Edge-case tests for the expression-based evaluation engine."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from webagentbench.backend.models.gmail import GmailSettings, GmailState
from webagentbench.tasks._evaluator import evaluate
from webagentbench.tasks._schema import Check, EvalConfig, NegativeCheck


def _empty_state() -> GmailState:
    return GmailState(
        env_id="gmail",
        task_id="test_task",
        owner_name="Test User",
        owner_email="test@example.com",
        settings=GmailSettings(id="settings_1"),
    )


def _task_with_checks(
    checks: list[Check] | None = None,
    negative_checks: list[NegativeCheck] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        eval=EvalConfig(
            source="server_state",
            checks=checks or [],
            negative_checks=negative_checks or [],
        )
    )


def test_empty_state_with_sent_check_fails_gracefully() -> None:
    """Checks referencing state.sent on empty state should fail, not crash."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="len(state.sent) > 0", desc="Has sent emails")]
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["success"] is False
    assert result["score"] == 0.0
    assert result["checks"][0]["passed"] is False
    assert result["checks"][0]["error"] is None  # len([]) > 0 is False, not an error


def test_missing_target_variable_returns_error() -> None:
    """Reference to undefined target should produce an error, not crash the process."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="any(e.id == '{target.nonexistent_id}' for e in state.sent)", desc="Missing target")]
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["success"] is False
    # The unresolved placeholder stays in the expression, which may cause
    # a NameError or simply evaluate to False — either way, check should not pass
    assert result["checks"][0]["passed"] is False


def test_malformed_expression_returns_error_string() -> None:
    """Syntax error in expression should be caught and reported."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="this is not valid python!!!", desc="Bad syntax")]
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["success"] is False
    assert result["checks"][0]["passed"] is False
    assert result["checks"][0]["error"] is not None
    assert "SyntaxError" in result["checks"][0]["error"]


def test_penalty_capped_at_095() -> None:
    """Total negative penalty must be capped at 0.95."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="True", desc="Always passes")],
        negative_checks=[
            NegativeCheck(expr="False", desc=f"Penalty {i}", penalty=0.5)
            for i in range(5)  # 5 * 0.5 = 2.5, should be capped
        ],
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    # base_score = 1.0, penalty capped at 0.95, score = 1.0 - 0.95 = 0.05
    assert result["score"] == pytest.approx(0.05)
    assert result["success"] is False  # score < 0.5


def test_score_exactly_05_is_success() -> None:
    """Score of exactly 0.5 with all checks passing should be success."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="True", desc="Passes")],
        negative_checks=[
            NegativeCheck(expr="False", desc="Half penalty", penalty=0.5)
        ],
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    # base_score = 1.0, penalty = 0.5, score = 0.5
    assert result["score"] == pytest.approx(0.5)
    assert result["success"] is True


def test_score_below_05_is_failure() -> None:
    """Score just below 0.5 with all checks passing should still fail."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="True", desc="Passes")],
        negative_checks=[
            NegativeCheck(expr="False", desc="Over half penalty", penalty=0.51)
        ],
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["score"] == pytest.approx(0.49)
    assert result["success"] is False


def test_all_checks_pass_no_negatives_gives_full_score() -> None:
    """Perfect run: all positive checks pass, no negatives → score 1.0."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[
            Check(expr="True", desc="Check 1"),
            Check(expr="True", desc="Check 2"),
        ],
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["score"] == pytest.approx(1.0)
    assert result["success"] is True
    assert result["final_score"] == pytest.approx(1.0)


def test_no_eval_config_returns_zero() -> None:
    """Task with no eval config should return score 0, success False."""
    state = _empty_state()
    task = SimpleNamespace(eval=None)
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["score"] == 0.0
    assert result["success"] is False


def test_negative_check_error_does_not_penalize() -> None:
    """A negative check that crashes (e.g. IndexError) should not apply penalty."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="True", desc="Passes")],
        negative_checks=[
            NegativeCheck(expr="state.sent[0].id == 'x'", desc="Crashes on empty sent", penalty=0.8)
        ],
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    # The negative check should error (IndexError), not penalize
    assert result["score"] == pytest.approx(1.0)
    assert result["success"] is True
    assert result["negative_checks"][0]["error"] is not None
