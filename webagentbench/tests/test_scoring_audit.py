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

import pytest
import yaml

pytestmark = pytest.mark.skip(
    reason="Legacy eval.checks schema is obsolete — all tasks migrated to canonical_diff. "
    "Rewrite against canonical_diff predicates if still needed."
)

TASKS_DIR = Path(__file__).parent.parent / "tasks" / "gmail"
TARGET_REF_RE = re.compile(r"\{target\.([^}]+)\}")
TEXT_TARGET_RE_PATTERNS = (
    re.compile(r"'\{target\.([^}]+)\}'\s+in\s+[me]\.(?:body|subject)"),
    re.compile(r"[me]\.(?:body|subject)[^\n]*startswith\('\{target\.([^}]+)\}'\)"),
    re.compile(r"[me]\.(?:body|subject)[^\n]*endswith\('\{target\.([^}]+)\}'\)"),
)


def _is_text_match_expr(expr: str) -> bool:
    return bool(
        re.search(r"in [me]\.(?:body|subject)", expr)
        or re.search(r"[me]\.(?:body|subject)[^\n]*startswith\(", expr)
        or re.search(r"[me]\.(?:body|subject)[^\n]*endswith\(", expr)
    )


def _hidden_target_refs_in_text_match(expr: str) -> set[str]:
    """Return target refs used specifically in body/subject text assertions."""
    refs: set[str] = set()
    for pattern in TEXT_TARGET_RE_PATTERNS:
        refs.update(pattern.findall(expr))
    return refs


def _classify_checks(task: dict[str, Any]) -> dict[str, int]:
    """Classify each check in a task's eval by scoring style."""
    ev = task.get("eval") or {}
    checks = (ev.get("checks") or []) + (ev.get("negative_checks") or [])
    instr = (task.get("instruction_template", "") or task.get("instruction", "")).lower()
    target_refs_in_instruction = set(TARGET_REF_RE.findall(instr))

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
        elif _is_text_match_expr(expr):
            # Substring check — only hidden target refs used in the actual text
            # assertion count as composed-text brittleness. Hidden targets used
            # only for routing or identity grounding are structural.
            hidden_target_refs = {
                ref for ref in _hidden_target_refs_in_text_match(expr)
                if ref not in target_refs_in_instruction
            }
            if hidden_target_refs:
                counts["composed"] += 1
                continue
            literals = re.findall(r"'([^']{8,})'", expr)
            any_composed = False
            for lit in literals:
                if "@" in lit or lit.startswith("*") or lit.startswith("{target."):
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
    """A large majority of all checks across the benchmark should be robust.

    Structural, count, keyword, and exact-given checks are robust to
    paraphrasing. The brittle category is composed-text matching against
    hidden target values. Keep that category small enough that the benchmark
    is still mostly testing task completion rather than exact phrasing.
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
    assert composed_ratio <= 0.15, (
        f"{composed_ratio:.1%} of checks require agent-composed text — "
        f"expected <= 15%. These checks fail correct paraphrases."
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


def test_composed_text_checks_do_not_stand_alone() -> None:
    """Tasks with hidden composed-text checks also need non-text grounding.

    This preserves acceptance for materially correct outputs with harmless
    formatting variation. A task may use composed-text checks, but they must not
    be the only grading signal.
    """
    violations: list[str] = []
    for f in sorted(TASKS_DIR.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        if not data or "eval" not in data:
            continue
        counts = _classify_checks(data)
        if counts["composed"] <= 0:
            continue
        grounded = counts["structural"] + counts["count"] + counts["exact_given"] + counts["keyword"]
        if grounded == 0:
            violations.append(
                f"[{data['task_id']}] has composed-text checks but no structural/count/"
                "keyword/exact-given grounding"
            )
    assert not violations, "\n".join(violations)


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
