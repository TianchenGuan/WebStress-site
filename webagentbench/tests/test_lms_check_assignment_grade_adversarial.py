"""Adversarial regression battery for lms_check_assignment_grade.

Auto-generated — no manual TODO. The generator synthesizes violating
final-states per predicate and asserts the matcher rejects every one.

If this test FAILS, either:
  (a) the matcher regressed and is accepting an obviously-wrong state, or
  (b) the canonical_diff got looser and admits states it shouldn't.
Both are regressions that must be fixed before the PR merges.
"""

from pathlib import Path
import random

from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.lms import LMSSeedRunner
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks.adversarial import synthesize_adversarial_cases
from webagentbench.tasks._schema import TaskDefinition


_TASK_YAML = Path(__file__).resolve().parents[1] / "tasks" / "lms" / "lms_check_assignment_grade.yaml"
TASK_ID = "lms_check_assignment_grade"


def _seed_task(seed: int):
    task = TaskDefinition.from_yaml(_TASK_YAML)
    runner = LMSSeedRunner()
    seeded_data, targets = runner.run(
        task=task,
        seed=seed,
        fake=FakeDataGenerator(seed),
        rng=random.Random(seed),
    )
    return task, dict(targets), seeded_data


def test_all_adversarial_cases_fail():
    task, targets, initial = _seed_task(42)
    assert task.canonical_diff is not None, (
        "canonical_diff missing — migrate the task first or run Tool B "
        "to scaffold the authoring context."
    )

    cases = synthesize_adversarial_cases(
        task.canonical_diff,
        initial=initial,
        targets=dict(targets),
    )
    assert len(cases) >= 1, (
        "adversarial generator produced no cases for lms_check_assignment_grade — "
        "likely a canonical_diff with no negatable predicates."
    )

    unexpectedly_passed: list[str] = []
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
            unexpectedly_passed.append(
                f"case {case['description']!r} passed when it should have been rejected"
            )

    assert not unexpectedly_passed, (
        "Adversarial cases leaked through the matcher:\n  "
        + "\n  ".join(unexpectedly_passed)
    )
