"""Parametrized adversarial battery for every migrated task.

Replaces ~130 per-task ``test_<task_id>_adversarial.py`` files that were
byte-identical except for the task_id string. Tasks with bespoke
adversarial coverage keep their own file under the same name; this
battery runs in addition to (not instead of) those.

For every task that has a ``canonical_diff`` block:
- synthesize violating final states via ``synthesize_adversarial_cases``
- assert the matcher rejects every one

If this file fails with ``report.passed is True`` on a case, either the
matcher regressed or the canonical_diff admits states it shouldn't.
"""

from __future__ import annotations

import pytest

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import load_all_tasks
from webagentbench.tasks.adversarial import synthesize_adversarial_cases


def _migrated_task_ids() -> list[str]:
    return sorted(
        task_id
        for task_id, task in load_all_tasks().items()
        if task.canonical_diff is not None
    )


def _initial_state_as_dict(sm: SessionManager, sid: str) -> dict:
    snap = sm.get_initial_snapshot(sid)
    if hasattr(snap, "model_dump"):
        return snap.model_dump()
    return dict(snap) if snap else {}


@pytest.mark.parametrize("task_id", _migrated_task_ids())
def test_all_adversarial_cases_fail(task_id: str) -> None:
    task = load_all_tasks()[task_id]
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id=task.env_id, task_id=task_id, seed=42)
    initial = _initial_state_as_dict(sm, sid)

    cases = synthesize_adversarial_cases(
        task.canonical_diff,
        initial=initial,
        targets=dict(targets),
    )
    assert cases, (
        f"adversarial generator produced no cases for {task_id} — "
        "likely a canonical_diff with no negatable predicates."
    )

    leaked: list[str] = []
    for case in cases:
        final = case["final"]
        agent_diff = compute_diff(initial, final)
        report = match_diff(
            agent_diff,
            task.canonical_diff,
            targets=dict(targets),
            initial=initial,
            final=final,
        )
        if report.passed:
            leaked.append(f"{case['description']!r} passed but should have been rejected")

    assert not leaked, "Adversarial cases leaked through the matcher:\n  " + "\n  ".join(leaked)
