"""End-to-end tests for gmail_data_compilation canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_data_compilation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send Q1 Budget Summary with all 3 numbers and dept CCs — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Q1 Budget Summary",
        body=(
            f"{targets['dept_a_dept']}: {targets['number_a']}\n"
            f"{targets['dept_b_dept']}: {targets['number_b']}\n"
            f"{targets['dept_c_dept']}: {targets['number_c']}"
        ),
        to=[targets["exec_email"]],
        cc=targets["dept_emails"],
    )

    task = get_task('gmail_data_compilation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_data_compilation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_number_fails():
    """Send email with only 2 of 3 numbers — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Q1 Budget Summary",
        body=f"{targets['number_a']}\n{targets['number_b']}",  # missing number_c
        to=[targets["exec_email"]],
        cc=targets["dept_emails"],
    )

    task = get_task('gmail_data_compilation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing department number should fail"


def test_missing_cc_fails():
    """Send email without CCs — CC check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Q1 Budget Summary",
        body=(
            f"{targets['dept_a_dept']}: {targets['number_a']}\n"
            f"{targets['dept_b_dept']}: {targets['number_b']}\n"
            f"{targets['dept_c_dept']}: {targets['number_c']}"
        ),
        to=[targets["exec_email"]],
        # No CC
    )

    task = get_task('gmail_data_compilation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing CC should fail"
