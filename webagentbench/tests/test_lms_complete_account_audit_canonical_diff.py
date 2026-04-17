"""End-to-end tests for lms_complete_account_audit canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_complete_account_audit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _read_unread_announcements(state, targets: dict[str, str]) -> None:
    for announcement_id in _ids(targets["unread_announcement_ids"]):
        announcement = state.get_announcement(announcement_id)
        if announcement is None:
            raise ValueError(f"announcement {announcement_id!r} not found")
        announcement.is_read = True


def _send_message(state, *, to: str) -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": "LMS account audit summary",
            "body": "I reviewed my account and completed the audit checks.",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "from": state.student.email,
        }
    )


def _match(initial, state, targets):
    task = get_task("lms_complete_account_audit")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _apply_correct_trajectory(state, targets):
    _read_unread_announcements(state, targets)
    _send_message(state, to=targets["advisor_name"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)

    report = _match(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _match(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_announcement_field_fails():
    _, _, targets, initial, state = _setup_session()

    unread_ids = _ids(targets["unread_announcement_ids"])
    assert unread_ids, "seed must include at least one unread announcement"
    announcement = state.get_announcement(unread_ids[0])
    if announcement is None:
        raise ValueError(f"announcement {unread_ids[0]!r} not found")
    announcement.title = announcement.title + " (edited)"
    _send_message(state, to=targets["advisor_name"])

    report = _match(initial, state, targets)
    assert report.passed is False, "editing the target announcement's wrong field should fail"


def test_wrong_announcement_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)
    unread_ids = set(_ids(targets["unread_announcement_ids"]))
    wrong = None
    for announcement in state.announcements:
        if announcement.id not in unread_ids:
            wrong = announcement
            break
    assert wrong is not None, "seed must include already-read announcements"
    wrong.title = wrong.title + " (edited)"

    report = _match(initial, state, targets)
    assert report.passed is False, (
        "mutating an announcement outside the unread target set should fail"
    )


def test_wrong_recipient_fails():
    _, _, targets, initial, state = _setup_session()

    _read_unread_announcements(state, targets)
    _send_message(state, to="not-the-advisor@example.com")

    report = _match(initial, state, targets)
    assert report.passed is False, "sending the audit summary to the wrong recipient should fail"


def test_excess_messages_fails():
    _, _, targets, initial, state = _setup_session()

    _read_unread_announcements(state, targets)
    for index in range(5):
        _send_message(state, to=targets["advisor_name"] if index == 0 else f"advisor-{index}@example.com")

    report = _match(initial, state, targets)
    assert report.passed is False, "sending excessive messages should fail the message constraint"


def test_collateral_collection_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)
    state.modules[0].title = state.modules[0].title + " (edited)"

    report = _match(initial, state, targets)
    assert report.passed is False, "mutating modules during the audit should fail"
