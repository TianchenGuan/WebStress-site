"""End-to-end tests for gmail_weekly_digest_preparation canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_weekly_digest_preparation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Compose and send weekly digest email to team-all
    state.send_email(
        subject=f"Weekly Digest -- Week of {targets['current_monday']}",
        body=(
            f"Week of {targets['current_monday']}\n\n"
            f"Engineering: 5 emails\n- {targets['starred_a_subject']}\n\n"
            f"Business: 6 emails\n- {targets['starred_b_subject']}\n\n"
            f"External: 4 emails\n- {targets['starred_c_subject']}\n\n"
            f"Operations: 4 emails\nNone starred\n\n"
            f"Uncategorized: 3 emails"
        ),
        to=["team-all@team.thornton.com"],
    )
    # Archive bucket A, B, C, D emails
    for eid in targets["bucket_a_ids"]:
        state.archive_email(eid)
    for eid in targets["bucket_b_ids"]:
        state.archive_email(eid)
    for eid in targets["bucket_c_ids"]:
        state.archive_email(eid)
    for eid in targets["bucket_d_ids"]:
        state.archive_email(eid)
    # Create filter 1: engineering domains -> Engineering label, skip inbox
    state.create_filter(FilterRule(
        id='f_eng', name='engineering filter',
        from_addresses=["*@eng.thornton.com", "*@devops.thornton.com"],
        add_labels=["Engineering"],
        archive=True,
    ))
    # Create filter 2: external domains -> External label, star
    state.create_filter(FilterRule(
        id='f_ext', name='external filter',
        from_addresses=["*@northstarco.com", "*@evergreenind.com"],
        add_labels=["External"],
        star=True,
    ))


def test_correct_trajectory_passes():
    """Apply all weekly digest actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_weekly_digest_preparation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_weekly_digest_preparation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_filter_fails():
    """Send digest and archive emails but skip filters — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=f"Weekly Digest -- Week of {targets['current_monday']}",
        body=(
            f"Week of {targets['current_monday']}\n\n"
            f"Engineering: 5 emails\nBusiness: 6 emails\n"
            f"External: 4 emails\nOperations: 4 emails\nNone starred\n"
            f"Uncategorized: 3 emails"
        ),
        to=["team-all@team.thornton.com"],
    )
    for eid in targets["bucket_a_ids"]:
        state.archive_email(eid)
    for eid in targets["bucket_b_ids"]:
        state.archive_email(eid)
    for eid in targets["bucket_c_ids"]:
        state.archive_email(eid)
    for eid in targets["bucket_d_ids"]:
        state.archive_email(eid)
    # Skip filters

    task = get_task('gmail_weekly_digest_preparation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing filters should fail"
