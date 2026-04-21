"""Edge-case tests for the expression-based evaluation engine."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from webagentbench.backend.models.gmail import (
    Contact,
    Email,
    GmailSettings,
    GmailState,
    Label,
)
from webagentbench.tasks._evaluator import _compute_collateral, evaluate
from webagentbench.tasks._registry import get_task
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


def test_recipient_checks_accept_display_name_wrapped_addresses() -> None:
    """Recipient equality checks should pass after canonicalizing Name <email> inputs."""
    state = _empty_state()
    state.send_email(
        to=["Ravi Menon <SOFIA.BROOKS@ATLAS.DEV>"],
        subject="Atlas decision",
        body="Forwarding the final decision on Project Atlas.",
    )
    task = _task_with_checks(
        checks=[
            Check(
                expr="any(m.to == ['sofia.brooks@atlas.dev'] for m in state.sent)",
                desc="Exact recipient match survives display-name formatting",
            )
        ],
    )

    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["success"] is True
    assert result["checks"][0]["passed"] is True


def test_thread_detective_blank_reply_does_not_pass_via_quoted_history() -> None:
    result = evaluate(
        get_task("gmail_thread_detective"),
        server_state=SimpleNamespace(
            sent=[
                SimpleNamespace(
                    to=["sofia.rivera@vertexlab.io"],
                    body=(
                        "\n\nOn 3/2/2026, 3:20:00 AM, Sofia Rivera wrote:\n"
                        "11:00 AM still works for me if the calendar is clear."
                    ),
                    in_reply_to="email_123",
                    thread_id="thread_456",
                )
            ]
        ),
        targets={
            "sender_email": "sofia.rivera@vertexlab.io",
            "correct_time": "11:00 AM",
            "wrong_times": ["4:00 PM", "2:30 PM"],
            "most_recent_thread_id": "thread_456",
        },
        trajectory=[],
    )

    assert result["success"] is False
    # Task migrated to canonical_diff; the originality/authored-text rule is
    # still enforced (the reply with only quoted history fails the positive
    # create check). Assertion updated to match the current check desc.
    assert any(
        check["desc"] == "Reply to sender confirming the non-conflicting meeting time"
        and check["passed"] is False
        for check in result["checks"]
    )


def test_data_compilation_requires_one_consolidated_summary_email() -> None:
    result = evaluate(
        get_task("gmail_data_compilation"),
        server_state=SimpleNamespace(
            sent=[
                SimpleNamespace(
                    to=["cfo@example.com"],
                    cc=["a@example.com", "b@example.com", "c@example.com"],
                    subject="Q1 Budget Summary",
                    body="Ops 100, Sales 200",
                ),
                SimpleNamespace(
                    to=["cfo@example.com"],
                    cc=["a@example.com", "b@example.com", "c@example.com"],
                    subject="Q1 Budget Summary",
                    body="Finance 300",
                ),
            ]
        ),
        targets={
            "exec_email": "cfo@example.com",
            "dept_emails": ["a@example.com", "b@example.com", "c@example.com"],
            "number_a": "100",
            "number_b": "200",
            "number_c": "300",
            "dept_a_dept": "Ops",
            "dept_b_dept": "Sales",
            "dept_c_dept": "Finance",
            "wrong_numbers": ["999", "888"],
        },
        trajectory=[],
    )

    assert result["success"] is False
    assert any(
        check["desc"] == "Compose Q1 Budget Summary email to exec with all dept numbers"
        and check["passed"] is False
        for check in result["checks"]
    )


def test_meeting_negotiation_requires_one_confirmation_email() -> None:
    result = evaluate(
        get_task("gmail_meeting_negotiation"),
        server_state=SimpleNamespace(
            sent=[
                SimpleNamespace(
                    to=["organizer@example.com"],
                    cc=["a@example.com", "b@example.com", "c@example.com", "d@example.com", "e@example.com"],
                    body="Everyone is included here.",
                    in_reply_to=None,
                ),
                SimpleNamespace(
                    to=["organizer@example.com"],
                    cc=[],
                    body="Let's use Tuesday 2 PM in Cedar Room.",
                    in_reply_to=None,
                ),
            ]
        ),
        targets={
            "organizer_email": "organizer@example.com",
            "attendee_emails": [
                "a@example.com",
                "b@example.com",
                "c@example.com",
                "d@example.com",
                "e@example.com",
            ],
            "correct_time": "Tuesday 2 PM",
            "room_name": "Cedar Room",
        },
        trajectory=[],
    )

    assert result["success"] is False
    assert any(
        check["desc"] == "Compose confirmation email to organizer with correct time, room and all attendees CC'd"
        and check["passed"] is False
        for check in result["checks"]
    )


def test_budget_reconciliation_requires_both_corrections_in_one_reply() -> None:
    emails = {
        "dept_1": SimpleNamespace(is_starred=True, labels=["Budget Verified"]),
        "dept_2": SimpleNamespace(is_starred=True, labels=["Budget Verified"]),
        "dept_3": SimpleNamespace(is_starred=True, labels=["Budget Verified"]),
        "summary": SimpleNamespace(is_starred=False, labels=["Budget Verified"]),
    }
    result = evaluate(
        get_task("gmail_budget_reconciliation"),
        server_state=SimpleNamespace(
            sent=[
                SimpleNamespace(
                    to=["author@example.com"],
                    body="The correct first number is 120.",
                    in_reply_to="summary",
                ),
                SimpleNamespace(
                    to=["author@example.com"],
                    body="The correct second number is 340.",
                    in_reply_to="summary",
                ),
            ],
            get_email=lambda eid: emails[eid],
        ),
        targets={
            "summary_author_email": "author@example.com",
            "summary_id": "summary",
            "dept_ids": ["dept_1", "dept_2", "dept_3"],
            "all_budget_ids": ["dept_1", "dept_2", "dept_3", "summary"],
            "correct_value_1": "120",
            "correct_value_2": "340",
        },
        trajectory=[],
    )

    assert result["success"] is False
    assert any(
        check["desc"] == "Reply to summary author with the two corrections"
        and check["passed"] is False
        for check in result["checks"]
    )


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


# ------------------------------------------------------------------
# Collateral-damage detection tests
# ------------------------------------------------------------------

def _seeded_state() -> GmailState:
    """Build a state with one email, one contact, one label, and take a snapshot."""
    state = GmailState(
        env_id="gmail",
        task_id="test_task",
        owner_name="Test User",
        owner_email="test@example.com",
        emails=[
            Email(
                id="e001",
                from_addr="alice@example.com",
                from_name="Alice",
                to=["test@example.com"],
                subject="Hello",
                body="Hi there",
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                thread_id="t001",
            ),
        ],
        contacts=[
            Contact(id="c001", name="Alice", email="alice@example.com"),
        ],
        labels=[
            Label(id="label_inbox", name="inbox", system=True),
        ],
        settings=GmailSettings(id="settings_1", signature="--Test"),
    )
    state._initial_snapshot = state.state_snapshot()
    return state


def test_collateral_no_changes_returns_empty() -> None:
    """When nothing changes, collateral report should be empty."""
    state = _seeded_state()
    report = _compute_collateral(state.initial_snapshot, state)
    assert report == {}


def test_collateral_detects_unintended_star() -> None:
    """Starring an email that wasn't required should show in collateral."""
    state = _seeded_state()
    state.toggle_star("e001", is_starred=True)

    report = _compute_collateral(state.initial_snapshot, state)
    assert "emails_modified" in report
    assert len(report["emails_modified"]) == 1
    mod = report["emails_modified"][0]
    assert mod["email_id"] == "e001"
    assert "is_starred" in mod["changes"]
    assert mod["changes"]["is_starred"] == {"before": False, "after": True}


def test_collateral_detects_settings_change() -> None:
    """Changing a setting should appear in collateral.settings_changed."""
    state = _seeded_state()
    state.settings.signature = "--New Signature"

    report = _compute_collateral(state.initial_snapshot, state)
    assert "settings_changed" in report
    assert "signature" in report["settings_changed"]
    assert report["settings_changed"]["signature"]["before"] == "--Test"
    assert report["settings_changed"]["signature"]["after"] == "--New Signature"


def test_collateral_detects_email_deletion() -> None:
    """Deleting an email should appear in collateral.emails_deleted."""
    state = _seeded_state()
    state.delete_email("e001")

    report = _compute_collateral(state.initial_snapshot, state)
    assert "emails_deleted" in report
    assert "e001" in report["emails_deleted"]


def test_collateral_detects_sent_email() -> None:
    """Sending an email should appear in collateral.emails_sent."""
    state = _seeded_state()
    state.send_email(to=["bob@example.com"], subject="Test", body="Body")

    report = _compute_collateral(state.initial_snapshot, state)
    assert "emails_sent" in report
    assert report["emails_sent"] == 1


def test_collateral_detects_label_creation() -> None:
    """Creating a new label should appear in collateral.labels_added."""
    state = _seeded_state()
    state.ensure_label("Work")

    report = _compute_collateral(state.initial_snapshot, state)
    assert "labels_added" in report


def test_collateral_detects_contact_modification() -> None:
    """Modifying a contact should appear in collateral.contacts_modified."""
    state = _seeded_state()
    state.update_contact("c001", note="Updated note")

    report = _compute_collateral(state.initial_snapshot, state)
    assert "contacts_modified" in report
    mod = report["contacts_modified"][0]
    assert mod["contact_id"] == "c001"
    assert mod["changes"]["note"] == {"before": None, "after": "Updated note"}


def test_collateral_does_not_affect_score() -> None:
    """Collateral mutations must NOT change the score — analytics only."""
    state = _seeded_state()
    state._initial_snapshot = state.state_snapshot()

    # Perform collateral damage: star an email + change a setting
    state.toggle_star("e001", is_starred=True)
    state.settings.display_density = "compact"

    task = _task_with_checks(
        checks=[Check(expr="True", desc="Always passes")],
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    # Score should be perfect despite collateral
    assert result["score"] == pytest.approx(1.0)
    assert result["success"] is True
    # But collateral should be reported
    assert "collateral" in result
    assert "emails_modified" in result["collateral"]
    assert "settings_changed" in result["collateral"]


def test_collateral_absent_when_no_snapshot() -> None:
    """When no initial snapshot exists, collateral key should be absent."""
    state = _empty_state()
    task = _task_with_checks(
        checks=[Check(expr="True", desc="Passes")],
    )
    result = evaluate(task, server_state=state, targets={}, trajectory=[])

    assert result["score"] == pytest.approx(1.0)
    assert "collateral" not in result
