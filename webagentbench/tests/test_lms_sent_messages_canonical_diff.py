"""Static guards for LMS sent-message canonical_diff coverage."""

from pathlib import Path

import yaml


LMS_TASK_DIR = Path(__file__).resolve().parents[1] / "tasks" / "lms"


def _canonical_blocks(task: dict):
    canonical = task["canonical_diff"]
    return canonical.get("oneof") or [canonical]


def test_no_message_invariants_have_executable_constraints():
    missing = []
    for path in sorted(LMS_TASK_DIR.glob("*.yaml")):
        task = yaml.safe_load(path.read_text())
        for index, block in enumerate(_canonical_blocks(task)):
            invariants = block.get("invariant") or []
            constraints = block.get("constraints") or []
            preserves_sent_messages = any(
                inv.get("collection") == "state.sent_messages" for inv in invariants
            )
            has_no_message_constraint = any(
                constraint.get("expr") == "len(state.sent_messages) == 0"
                for constraint in constraints
            )
            if preserves_sent_messages and not has_no_message_constraint:
                missing.append(f"{path.name}:block{index}")

    assert missing == []


def test_required_message_tasks_have_advisor_constraints():
    required_message_tasks = {
        "lms_academic_probation_recovery",
        "lms_academic_standing_optimization",
        "lms_advisor_meeting_prep",
        "lms_complete_account_audit",
        "lms_cross_course_prereq_orchestration",
        "lms_portfolio_assembly",
        "lms_scholarship_maintenance",
        "lms_semester_recovery_plan",
        "lms_waitlist_strategy",
    }
    missing = []
    for task_id in sorted(required_message_tasks):
        task = yaml.safe_load((LMS_TASK_DIR / f"{task_id}.yaml").read_text())
        for index, block in enumerate(_canonical_blocks(task)):
            constraints = block.get("constraints") or []
            has_advisor_constraint = any(
                "target['advisor_name']" in str(constraint.get("expr", ""))
                and "state.sent_messages" in str(constraint.get("expr", ""))
                and constraint.get("severity") == "critical"
                for constraint in constraints
            )
            if not has_advisor_constraint:
                missing.append(f"{task_id}:block{index}")

    assert missing == []
