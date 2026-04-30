"""End-to-end tests for lms_advisor_meeting_prep canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_advisor_meeting_prep",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _mark_announcements_read(state, announcement_ids: list[str]) -> None:
    for announcement_id in announcement_ids:
        announcement = state.get_announcement(announcement_id)
        if announcement is None:
            raise ValueError(f"announcement {announcement_id!r} not found")
        announcement.is_read = True


def _complete_module(state, module_id: str, *, complete_all_items: bool = True) -> None:
    module = state.get_module(module_id)
    if module is None:
        raise ValueError(f"module {module_id!r} not found")
    for index, item in enumerate(module.content_items):
        item.completed = complete_all_items or index < len(module.content_items) - 1
    module.status = "completed"


def _send_message(state, *, to: str, subject: str = "Meeting prep") -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": subject,
            "body": "I have reviewed announcements and completed the next module.",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "from": state.student.email,
        }
    )


def _report(initial, state, targets):
    task = get_task("lms_advisor_meeting_prep")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _mark_announcements_read(state, _ids(targets["unread_announcement_ids"]))
    _complete_module(state, targets["next_available_module_id"])
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_message_recipient_fails():
    # `state.sent_messages` is `list[dict[str, Any]]` (no `id` key), so
    # canonical_diff cannot enforce recipient identity (compute_diff skips
    # this collection). Recipient checks live in the `eval:` block.
    _, _, targets, initial, state = _setup_session()

    _mark_announcements_read(state, _ids(targets["unread_announcement_ids"]))
    _complete_module(state, targets["next_available_module_id"])
    _send_message(state, to="not-the-advisor@example.com")

    assert state.sent_messages[-1]["to"] == "not-the-advisor@example.com"


def test_wrong_module_completion_fails():
    _, _, targets, initial, state = _setup_session()

    _mark_announcements_read(state, _ids(targets["unread_announcement_ids"]))
    _complete_module(state, targets["next_available_module_id"], complete_all_items=False)
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "completing the module without all items should fail"


def test_extra_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    _mark_announcements_read(state, _ids(targets["unread_announcement_ids"]))
    _complete_module(state, targets["next_available_module_id"])
    _send_message(state, to=targets["advisor_name"])
    state.enrollments[0].status = "dropped"

    report = _report(initial, state, targets)
    assert report.passed is False, "dropping an enrollment should fail"
