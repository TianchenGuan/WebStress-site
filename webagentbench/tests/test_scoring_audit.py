"""Scoring style audit — categorizes eval checks and flags brittleness.

Each eval check falls into one of these categories:

  structural   — checks state fields (is_starred, in_reply_to, settings, labels, filters)
  exact_given  — checks for exact text that IS given verbatim in the instruction
  keyword      — checks for short keywords / email addresses in body
  count        — checks length/count constraints (len, sum, <=, >=)
  composed     — checks for exact text NOT given in the instruction (agent must compose it)

The "composed" category is the one that can be brittle: a correct paraphrase
would fail. This test documents which tasks use composed-text checks so the
benchmark author can make an explicit decision per task.

Design rule: If a task requires the agent to write free-form text, use
structural checks (did a reply exist? was it in the right thread?) rather
than exact-substring checks, unless the instruction gives the exact text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

TASKS_DIR = Path(__file__).parent.parent / "tasks" / "gmail"


def _classify_checks(task: dict[str, Any]) -> dict[str, int]:
    """Classify each check in a task's eval by scoring style."""
    ev = task.get("eval") or {}
    checks = (ev.get("checks") or []) + (ev.get("negative_checks") or [])
    instr = (task.get("instruction_template", "") or task.get("instruction", "")).lower()

    counts = {"structural": 0, "exact_given": 0, "keyword": 0, "count": 0, "composed": 0}

    for check in checks:
        expr = check["expr"] if isinstance(check, dict) else str(check)

        if re.search(r"state\.settings\.", expr):
            counts["structural"] += 1
        elif re.search(r"len\(|sum\(|<= \d|>= \d", expr):
            counts["count"] += 1
        elif re.search(
            r"is_starred|is_read|in_reply_to|forwarded_from_id|\.archived|\.deleted|thread_id",
            expr,
        ) and "in m.body" not in expr and "in e.body" not in expr:
            counts["structural"] += 1
        elif re.search(r"in m\.body|in e\.body|in m\.subject|in e\.subject", expr):
            # Substring check — is the string given in the instruction?
            literals = re.findall(r"'([^']{8,})'", expr)
            any_composed = False
            for lit in literals:
                if "@" in lit or lit.startswith("*") or "target." in lit:
                    continue
                if lit.lower() not in instr:
                    any_composed = True
            if any_composed:
                counts["composed"] += 1
            else:
                counts["exact_given"] += 1
        elif re.search(r"'[^']{3,}' in", expr):
            counts["keyword"] += 1
        else:
            counts["structural"] += 1

    return counts


def test_majority_of_checks_are_structural() -> None:
    """At least 70% of all checks across the benchmark should be structural.

    Structural checks (is_starred, in_reply_to, settings values, filter
    existence, label creation) are robust to paraphrasing. A benchmark
    that relies mostly on exact-text matching is fragile.
    """
    total = 0
    robust = 0  # structural + count + exact_given (text from instruction)
    composed = 0
    for f in sorted(TASKS_DIR.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        if not data or "eval" not in data:
            continue
        counts = _classify_checks(data)
        total += sum(counts.values())
        robust += counts["structural"] + counts["count"] + counts["exact_given"] + counts["keyword"]
        composed += counts["composed"]
    assert total > 0
    composed_ratio = composed / total
    assert composed_ratio <= 0.10, (
        f"{composed_ratio:.1%} of checks require agent-composed text — "
        f"expected <= 10%. These checks fail correct paraphrases."
    )


def test_composed_text_checks_are_documented() -> None:
    """Every task with composed-text checks should be hard/expert/frontier.

    Easy/medium tasks should not require the agent to compose exact phrasing
    that isn't given in the instruction — that makes simple tasks fragile.
    """
    violations: list[str] = []
    for f in sorted(TASKS_DIR.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        if not data or "eval" not in data:
            continue
        counts = _classify_checks(data)
        if counts["composed"] > 0:
            diff = data.get("difficulty", "medium")
            if diff in ("easy",):
                violations.append(
                    f"[{data['task_id']}] difficulty={diff} but has "
                    f"{counts['composed']} composed-text checks"
                )
    # reply_simple is easy with 1 composed check but the instruction says
    # "reply with exactly: ..." so it's intentional. Allow 1 easy task.
    assert len(violations) <= 1, (
        "Easy tasks should not have composed-text checks:\n"
        + "\n".join(violations)
    )


def test_print_scoring_summary() -> None:
    """Advisory: print scoring style breakdown per task (always passes)."""
    rows: list[tuple[str, str, dict[str, int]]] = []
    for f in sorted(TASKS_DIR.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        if not data or "eval" not in data:
            continue
        counts = _classify_checks(data)
        rows.append((data["task_id"], data.get("difficulty", "?"), counts))

    # Print summary (visible with pytest -s)
    composed_tasks = [(tid, diff, c) for tid, diff, c in rows if c["composed"] > 0]
    total_checks = sum(sum(c.values()) for _, _, c in rows)
    total_composed = sum(c["composed"] for _, _, c in rows)

    print(f"\n  Scoring summary: {total_checks} total checks, "
          f"{total_composed} composed-text ({total_composed/total_checks:.0%})")
    print(f"  {len(composed_tasks)}/{len(rows)} tasks have composed-text checks:")
    for tid, diff, c in composed_tasks:
        print(f"    {tid:50s} [{diff:8s}] {c['composed']}/{sum(c.values())} composed")
