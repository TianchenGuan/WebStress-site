"""End-to-end tests for gmail_annual_vendor_review canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_annual_vendor_review',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    """Apply all required mutations for the annual vendor review."""
    # Create labels
    state.ensure_label("Vendor-Renew")
    state.ensure_label("Vendor-Renegotiate")
    state.ensure_label("Vendor-Terminate")
    # Create 6 vendor filters
    vendor_filters = [
        FilterRule(id='f_alpha', name='AlphaServ', from_addresses=['*@alphaserv.io'], add_labels=['Vendor-Renew']),
        FilterRule(id='f_beta', name='BetaLogic', from_addresses=['*@betalogic.com'], add_labels=['Vendor-Renegotiate']),
        FilterRule(id='f_gamma', name='GammaTech', from_addresses=['*@gammatech.co'], add_labels=['Vendor-Terminate']),
        FilterRule(id='f_delta', name='DeltaWare', from_addresses=['*@deltaware.net'], add_labels=['Vendor-Terminate']),
        FilterRule(id='f_epsilon', name='EpsilonAI', from_addresses=['*@epsilonai.com'], add_labels=['Vendor-Renegotiate']),
        FilterRule(id='f_zeta', name='ZetaCloud', from_addresses=['*@zetacloud.org'], add_labels=['Vendor-Renew']),
    ]
    for f in vendor_filters:
        state.create_filter(f)
    # Send recommendation email
    state.send_email(
        subject="Annual Vendor Review - Recommendations",
        body=(
            "AlphaServ: RENEW\nBetaLogic: RENEGOTIATE\nGammaTech: TERMINATE\n"
            "DeltaWare: TERMINATE\nEpsilonAI: RENEGOTIATE\nZetaCloud: RENEW"
        ),
        to=["vp-operations@company.com"],
    )


def test_correct_trajectory_passes():
    """Complete vendor review workflow — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_annual_vendor_review')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_annual_vendor_review')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_categorization_fails():
    """Send email with wrong vendor categorization — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("Vendor-Renew")
    state.ensure_label("Vendor-Renegotiate")
    state.ensure_label("Vendor-Terminate")
    # Wrong: GammaTech listed as RENEGOTIATE instead of TERMINATE
    state.send_email(
        subject="Annual Vendor Review - Recommendations",
        body="AlphaServ: RENEW\nGammaTech: RENEGOTIATE\nDeltaWare: TERMINATE",
        to=["vp-operations@company.com"],
    )

    task = get_task('gmail_annual_vendor_review')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong categorization should fail"
