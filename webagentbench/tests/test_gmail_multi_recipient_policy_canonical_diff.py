"""End-to-end tests for gmail_multi_recipient_policy canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_multi_recipient_policy',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Reply only to sender on Board Strategy Review (not reply-all)
    state.send_email(
        subject="Re: Board Strategy Review",
        body="Acknowledged, will prepare the revised deck by Friday.",
        to=[targets["sender_email"]],
        in_reply_to=targets["thread_a_msg_id"],
    )
    # Reply-all to Sprint 14 Retro
    state.send_email(
        subject="Re: Sprint 14 Retro Action Items",
        body="Adding capacity planning to next sprint scope.",
        to=[targets["sender_email"]],
        cc=targets["eng_cc_emails"],
        in_reply_to=targets["thread_b_msg_id"],
    )
    # Forward vendor contract to delegate
    state.forward_email(
        targets["thread_c_msg_id"],
        to=[targets["delegate_email"]],
        body="Please review and sign by EOD Wednesday.",
    )


def test_correct_trajectory_passes():
    """All three outbound emails sent correctly — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_multi_recipient_policy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_multi_recipient_policy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_phrase_on_board_reply_fails():
    """Send wrong phrase on Board Strategy reply — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Board Strategy Review",
        body="Got it, will update the deck.",  # wrong phrase
        to=[targets["sender_email"]],
        in_reply_to=targets["thread_a_msg_id"],
    )
    state.send_email(
        subject="Re: Sprint 14 Retro",
        body="Adding capacity planning to next sprint scope.",
        to=[targets["sender_email"]],
        cc=targets["eng_cc_emails"],
        in_reply_to=targets["thread_b_msg_id"],
    )
    state.forward_email(
        targets["thread_c_msg_id"],
        to=[targets["delegate_email"]],
        body="Please review and sign by EOD Wednesday.",
    )

    task = get_task('gmail_multi_recipient_policy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong phrase on board reply should fail"


def test_reply_all_requires_exact_engineering_ccs():
    """Omitting the engineering CC list on the reply-all message fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Board Strategy Review",
        body="Acknowledged, will prepare the revised deck by Friday.",
        to=[targets["sender_email"]],
        in_reply_to=targets["thread_a_msg_id"],
    )
    state.send_email(
        subject="Re: Sprint 14 Retro",
        body="Adding capacity planning to next sprint scope.",
        to=[targets["sender_email"]],
        cc=[],
        in_reply_to=targets["thread_b_msg_id"],
    )
    state.forward_email(
        targets["thread_c_msg_id"],
        to=[targets["delegate_email"]],
        body="Please review and sign by EOD Wednesday.",
    )

    task = get_task('gmail_multi_recipient_policy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing reply-all CCs should fail"


def test_exact_reply_phrase_rejects_extra_text():
    """Exact phrase replies should not pass with appended prose."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Board Strategy Review",
        body="Acknowledged, will prepare the revised deck by Friday. Extra note.",
        to=[targets["sender_email"]],
        in_reply_to=targets["thread_a_msg_id"],
    )
    state.send_email(
        subject="Re: Sprint 14 Retro",
        body="Adding capacity planning to next sprint scope.",
        to=[targets["sender_email"]],
        cc=targets["eng_cc_emails"],
        in_reply_to=targets["thread_b_msg_id"],
    )
    state.forward_email(
        targets["thread_c_msg_id"],
        to=[targets["delegate_email"]],
        body="Please review and sign by EOD Wednesday.",
    )

    task = get_task('gmail_multi_recipient_policy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "extra text on exact reply should fail"
