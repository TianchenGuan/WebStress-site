"""Composable seed builder framework for the LMS environment.

Provides :class:`LMSSeedContext` and a registry of reusable builder
functions that generate deterministic academic test data for benchmark tasks.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

from webagentbench.backend.models.lms import (
    Announcement,
    Assignment,
    CalendarEvent,
    CategoryPolicy,
    ContentItem,
    Course,
    Discussion,
    DiscussionPost,
    Enrollment,
    Grade,
    LatePolicy,
    Module,
    PeerReview,
    RubricItem,
    Student,
    Syllabus,
)


# ---------------------------------------------------------------------------
# ResolvedActor (shared shape with Gmail / Robinhood)
# ---------------------------------------------------------------------------

@dataclass
class ResolvedActor:
    """A named person with a deterministically-generated email address."""

    name: str
    email: str
    first_name: str


# ---------------------------------------------------------------------------
# Hardcoded course catalog pool
# ---------------------------------------------------------------------------

_COURSE_CATALOG: list[dict[str, Any]] = [
    {"code": "CS101", "title": "Introduction to Computer Science", "dept": "Computer Science", "credits": 3},
    {"code": "CS201", "title": "Data Structures and Algorithms", "dept": "Computer Science", "credits": 3},
    {"code": "CS301", "title": "Operating Systems", "dept": "Computer Science", "credits": 3},
    {"code": "MATH201", "title": "Linear Algebra", "dept": "Mathematics", "credits": 4},
    {"code": "MATH301", "title": "Differential Equations", "dept": "Mathematics", "credits": 4},
    {"code": "ENG102", "title": "Academic Writing", "dept": "English", "credits": 3},
    {"code": "ENG201", "title": "Technical Communication", "dept": "English", "credits": 3},
    {"code": "PHYS201", "title": "Classical Mechanics", "dept": "Physics", "credits": 4},
    {"code": "CHEM101", "title": "General Chemistry", "dept": "Chemistry", "credits": 4},
    {"code": "BIO101", "title": "Introduction to Biology", "dept": "Biology", "credits": 3},
    {"code": "STAT301", "title": "Probability and Statistics", "dept": "Statistics", "credits": 3},
    {"code": "ECON101", "title": "Principles of Economics", "dept": "Economics", "credits": 3},
    {"code": "HIST101", "title": "World History", "dept": "History", "credits": 3},
    {"code": "PSYCH101", "title": "Introduction to Psychology", "dept": "Psychology", "credits": 3},
    {"code": "ART101", "title": "Art Appreciation", "dept": "Fine Arts", "credits": 3},
]

# Grading policy templates: each is a dict of category -> (weight, drop_lowest)
_GRADING_TEMPLATES: list[dict[str, tuple[str, int]]] = [
    {
        "homework": ("0.30", 1),
        "quizzes": ("0.10", 1),
        "midterm": ("0.20", 0),
        "project": ("0.15", 0),
        "final": ("0.25", 0),
    },
    {
        "homework": ("0.25", 2),
        "quizzes": ("0.15", 1),
        "midterm": ("0.25", 0),
        "final": ("0.35", 0),
    },
    {
        "homework": ("0.35", 1),
        "participation": ("0.05", 0),
        "midterm": ("0.20", 0),
        "project": ("0.20", 0),
        "final": ("0.20", 0),
    },
    {
        "homework": ("0.20", 0),
        "essays": ("0.20", 0),
        "quizzes": ("0.10", 0),
        "midterm": ("0.20", 0),
        "final": ("0.30", 0),
    },
]

# Late policy presets: (penalty_per_day, max_late_days, grace_period_hours)
_LATE_PRESETS: list[tuple[str, int, int]] = [
    ("0.05", 7, 6),   # lenient
    ("0.10", 5, 2),   # moderate
    ("0.15", 3, 0),   # strict
]

# Discussion prompts pool
_DISCUSSION_PROMPTS: list[str] = [
    "Discuss the key takeaways from this week's reading and how they relate to previous topics.",
    "What challenges did you encounter in the latest assignment? Share your approach.",
    "Analyze the trade-offs presented in the lecture material and argue for your preferred approach.",
    "How does this week's topic connect to real-world applications? Provide specific examples.",
    "Reflect on your learning process so far. What concepts have been most surprising?",
    "Compare and contrast the two main approaches discussed in class this week.",
]

# Announcement body templates
_ANNOUNCEMENT_BODIES: list[str] = [
    "Please review the updated syllabus before next week's class. Key changes are highlighted.",
    "Office hours have been moved to Thursday 2-4 PM for the remainder of the semester.",
    "The midterm exam will cover all material through Module {mod_num}. Study guide posted.",
    "Reminder: the project proposal is due by end of day Friday. No late submissions accepted.",
    "Guest speaker next Wednesday. Attendance is optional but strongly recommended.",
    "Grades for the latest assignment have been posted. Please review your feedback.",
    "Important: the final exam date has been confirmed. Check the calendar for details.",
    "Lab section is cancelled this week due to facility maintenance. Make-up session TBD.",
]

# Assignment title templates by type
_ASSIGNMENT_TITLES: dict[str, list[str]] = {
    "homework": [
        "Problem Set {n}",
        "Homework {n}: {topic}",
        "Weekly Assignment {n}",
        "Practice Problems {n}",
    ],
    "essay": [
        "Essay {n}: {topic}",
        "Analysis Paper {n}",
        "Reflection Paper {n}",
    ],
    "project": [
        "Course Project: Phase {n}",
        "Group Project Milestone {n}",
        "Final Project Submission",
    ],
    "quiz": [
        "Quiz {n}: {topic}",
        "Pop Quiz {n}",
        "Weekly Quiz {n}",
    ],
    "exam": [
        "Midterm Exam",
        "Final Exam",
        "Midterm Retake",
    ],
    "peer_review": [
        "Peer Review: {topic}",
        "Peer Review Assignment {n}",
    ],
    "participation": [
        "Class Participation: Week {n}",
        "Discussion Participation {n}",
    ],
}

# Topics pool for assignment title interpolation
_TOPICS: list[str] = [
    "Fundamentals",
    "Core Concepts",
    "Applications",
    "Advanced Topics",
    "Review",
    "Data Analysis",
    "Theory and Practice",
    "Integration",
    "Optimization",
    "Case Study",
]


# ---------------------------------------------------------------------------
# LMSSeedContext
# ---------------------------------------------------------------------------

class LMSSeedContext:
    """Mutable accumulator threaded through every seed builder step."""

    def __init__(
        self,
        seed: int,
        rng: random.Random,
        fake: Any,
        now: datetime,
        base: dict[str, Any],
    ) -> None:
        self.seed = seed
        self.rng = rng
        self.fake = fake
        self.now = now
        self.base = base
        self.actors: dict[str, ResolvedActor] = {}
        self.outputs: dict[str, Any] = {}
        self.counters: dict[str, int] = {}

    def next_id(self, prefix: str) -> str:
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]}"

    def email_for_name(self, name: str, domain: str | None = None) -> str:
        local = "".join(
            ch.lower() for ch in name if ch.isalnum() or ch == " "
        ).replace(" ", ".")
        local = ".".join(part for part in local.split(".") if part) or "contact"
        domain = domain or f"{self.fake.domain_word()}.com"
        return f"{local}@{domain}"

    def resolve_actor(self, key: str, domain: str = "thornton.com",
                      is_vip: bool = False, name: str | None = None) -> ResolvedActor:
        if key in self.actors:
            return self.actors[key]
        name = name or self.fake.name()
        actor = ResolvedActor(
            name=name,
            email=self.email_for_name(name, domain),
            first_name=name.split()[0],
        )
        self.actors[key] = actor
        return actor


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BuilderFn = Callable[["LMSSeedContext", dict[str, Any]], dict[str, Any]]

LMS_BUILDER_REGISTRY: dict[str, BuilderFn] = {}


def _register(name: str) -> Callable[[BuilderFn], BuilderFn]:
    def decorator(fn: BuilderFn) -> BuilderFn:
        LMS_BUILDER_REGISTRY[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# 1. student_profile
# ---------------------------------------------------------------------------

@_register("student_profile")
def _build_student_profile(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate student demographics, GPA, advisor assignment."""
    gpa = Decimal(str(params.get("gpa", str(round(ctx.rng.uniform(2.5, 3.8), 2)))))
    gpa = gpa.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    status = params.get("enrollment_status", "active")
    name = params.get("name") or ctx.fake.name()
    email = ctx.email_for_name(name, "thornton.com")
    student_id_num = f"S-{ctx.rng.randint(20240000, 20269999)}"
    advisor_name = f"Dr. {ctx.fake.name().split()[-1]}"

    student = Student(
        id=ctx.next_id("student"),
        name=name,
        email=email,
        student_id=student_id_num,
        enrollment_status=status,
        gpa=gpa,
        advisor_id=ctx.next_id("advisor"),
        advisor_name=advisor_name,
    )
    ctx.base["student"] = student.model_dump()
    return {
        "student_id": student.id,
        "student_name": name,
        "student_email": email,
        "gpa": str(gpa),
        "advisor_name": advisor_name,
    }


# ---------------------------------------------------------------------------
# 2. course_catalog
# ---------------------------------------------------------------------------

@_register("course_catalog")
def _build_course_catalog(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate N courses with syllabi, instructors, and varied grading/late policies.

    Params
    ------
    count : int               -- number of courses (default 4)
    must_include : list[str]  -- course codes that MUST be present
    vary_late_policies : bool -- assign varied late policies across courses (default False)
    semester : str            -- semester label (default "Spring 2026")
    """
    count = params.get("count", 4)
    must_include = set(params.get("must_include", []))
    vary_late = params.get("vary_late_policies", False)
    semester = params.get("semester", "Spring 2026")

    # Select courses: must_include first, then random fill
    available = list(_COURSE_CATALOG)
    selected = [c for c in available if c["code"] in must_include]
    remaining = [c for c in available if c["code"] not in must_include]
    ctx.rng.shuffle(remaining)
    selected.extend(remaining[: max(0, count - len(selected))])

    if "courses" not in ctx.base:
        ctx.base["courses"] = []

    course_ids: list[str] = []
    course_codes: list[str] = []
    strictest_id: str | None = None
    most_lenient_id: str | None = None
    strictest_penalty = Decimal("0")
    most_lenient_penalty = Decimal("1")
    first_instructor_name: str | None = None
    first_course_code: str | None = None
    first_course_title: str | None = None
    first_course_id: str | None = None

    for i, cd in enumerate(selected):
        course_id = ctx.next_id("course")
        instructor_name = f"Prof. {ctx.fake.name().split()[-1]}"

        # Pick grading policy
        template = _GRADING_TEMPLATES[ctx.rng.randint(0, len(_GRADING_TEMPLATES) - 1)]
        grading_policy: dict[str, CategoryPolicy] = {}
        for cat_name, (weight_str, drop_low) in template.items():
            grading_policy[cat_name] = CategoryPolicy(
                weight=Decimal(weight_str),
                drop_lowest=drop_low,
            )

        # Pick late policy
        if vary_late:
            preset = _LATE_PRESETS[i % len(_LATE_PRESETS)]
        else:
            preset = _LATE_PRESETS[1]  # moderate default
        late_policy = LatePolicy(
            penalty_per_day=Decimal(preset[0]),
            max_late_days=preset[1],
            grace_period_hours=preset[2],
        )

        # Track strictest/most lenient
        if late_policy.penalty_per_day > strictest_penalty:
            strictest_penalty = late_policy.penalty_per_day
            strictest_id = course_id
        if late_policy.penalty_per_day < most_lenient_penalty:
            most_lenient_penalty = late_policy.penalty_per_day
            most_lenient_id = course_id

        semester_start = ctx.now - timedelta(days=45)
        drop_deadline = semester_start + timedelta(days=30)
        final_exam_date = ctx.now + timedelta(days=60)

        course = Course(
            id=course_id,
            course_code=cd["code"],
            title=cd["title"],
            instructor_id=ctx.next_id("instructor"),
            instructor_name=instructor_name,
            semester=semester,
            credits=cd["credits"],
            syllabus=Syllabus(
                grading_policy=grading_policy,
                late_policy=late_policy,
            ),
            drop_deadline=drop_deadline,
            final_exam_date=final_exam_date,
        )
        ctx.base["courses"].append(course.model_dump())

        course_ids.append(course_id)
        course_codes.append(cd["code"])

        if i == 0:
            first_instructor_name = instructor_name
            first_course_code = cd["code"]
            first_course_title = cd["title"]
            first_course_id = course_id

    return {
        "course_ids": course_ids,
        "course_codes": course_codes,
        "strictest_late_policy_course_id": strictest_id or (course_ids[0] if course_ids else ""),
        "most_lenient_late_policy_course_id": most_lenient_id or (course_ids[0] if course_ids else ""),
        "instructor_name": first_instructor_name or "",
        "course_code": first_course_code or "",
        "course_title": first_course_title or "",
        "target_course_id": first_course_id or "",
    }


# ---------------------------------------------------------------------------
# 3. enrollment_set
# ---------------------------------------------------------------------------

@_register("enrollment_set")
def _build_enrollment_set(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Enroll student in all courses from course_catalog.

    Params
    ------
    roles : dict[str, str]      -- course_id -> role override ("ta")
    include_waitlisted : bool   -- add a waitlisted enrollment (default False)
    """
    roles: dict[str, str] = params.get("roles", {})
    include_waitlisted = params.get("include_waitlisted", False)

    student_id = ctx.base.get("student", {}).get("id", "student_1")
    courses = ctx.base.get("courses", [])

    if "enrollments" not in ctx.base:
        ctx.base["enrollments"] = []

    enrollment_ids: list[str] = []
    ta_course_id: str | None = None

    for i, course_data in enumerate(courses):
        course_id = course_data["id"]
        role = roles.get(course_id, "student")
        status = "enrolled"
        if include_waitlisted and i == len(courses) - 1:
            status = "waitlisted"

        enrollment = Enrollment(
            id=ctx.next_id("enrollment"),
            student_id=student_id,
            course_id=course_id,
            role=role,
            status=status,
        )
        ctx.base["enrollments"].append(enrollment.model_dump())
        enrollment_ids.append(enrollment.id)

        if role == "ta":
            ta_course_id = course_id

    return {
        "enrollment_ids": enrollment_ids,
        "ta_course_id": ta_course_id or "",
    }


# ---------------------------------------------------------------------------
# 4. assignment_battery
# ---------------------------------------------------------------------------

def _pick_assignment_title(
    rng: random.Random, atype: str, n: int, topic: str,
) -> str:
    """Deterministically pick a title template and interpolate."""
    templates = _ASSIGNMENT_TITLES.get(atype, _ASSIGNMENT_TITLES["homework"])
    tmpl = rng.choice(templates)
    return tmpl.replace("{n}", str(n)).replace("{topic}", topic)


@_register("assignment_battery")
def _build_assignment_battery(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate assignments across courses with varying statuses.

    Params
    ------
    per_course_count : int     -- assignments per course (default 6)
    graded_fraction : float    -- fraction that are graded (default 0.5)
    late_count : int           -- how many assignments are late (default 1)
    missing_count : int        -- how many are not_submitted past due (default 1)
    resubmit_count : int       -- how many request resubmission (default 0)
    target_assignment_status : str -- filter target selection by status
    """
    per_course = params.get("per_course_count", 6)
    graded_frac = params.get("graded_fraction", 0.5)
    late_count = params.get("late_count", 1)
    missing_count = params.get("missing_count", 1)
    resubmit_count = params.get("resubmit_count", 0)
    target_status = params.get("target_assignment_status", None)

    courses = ctx.base.get("courses", [])
    if "assignments" not in ctx.base:
        ctx.base["assignments"] = []

    all_assignment_ids: list[str] = []
    missing_ids: list[str] = []
    late_ids: list[str] = []
    resubmit_ids: list[str] = []
    lowest_homework_id: str | None = None
    lowest_homework_score: Decimal | None = None
    exam_assignment_id: str | None = None
    file_name: str = "submission.pdf"

    # Category -> assignment type mapping
    _cat_to_type: dict[str, str] = {
        "homework": "homework",
        "quizzes": "quiz",
        "midterm": "exam",
        "final": "exam",
        "project": "project",
        "participation": "participation",
        "essays": "essay",
    }

    late_budget = late_count
    missing_budget = missing_count
    resubmit_budget = resubmit_count

    for course_data in courses:
        course_id = course_data["id"]
        grading_policy = course_data["syllabus"]["grading_policy"]
        categories = list(grading_policy.keys())

        for n in range(1, per_course + 1):
            assignment_id = ctx.next_id("assignment")
            cat = categories[(n - 1) % len(categories)]
            atype = _cat_to_type.get(cat, "homework")
            topic = ctx.rng.choice(_TOPICS)
            title = _pick_assignment_title(ctx.rng, atype, n, topic)

            points_possible = Decimal(str(ctx.rng.choice([10, 20, 25, 50, 100])))
            due_offset_days = ctx.rng.randint(-30, 30)
            due_at = ctx.now + timedelta(days=due_offset_days)

            # Determine status
            graded_count = int(per_course * graded_frac)
            is_past_due = due_offset_days < 0

            if missing_budget > 0 and is_past_due and n == per_course:
                status = "not_submitted"
                score = None
                submitted_at = None
                missing_budget -= 1
                missing_ids.append(assignment_id)
            elif late_budget > 0 and is_past_due and n == per_course - 1:
                status = "late"
                score = Decimal(str(round(ctx.rng.uniform(
                    float(points_possible) * 0.4,
                    float(points_possible) * 0.85,
                ), 1)))
                submitted_at = due_at + timedelta(days=ctx.rng.randint(1, 3))
                late_budget -= 1
                late_ids.append(assignment_id)
            elif resubmit_budget > 0 and n == per_course - 2 and is_past_due:
                status = "resubmit_requested"
                score = Decimal(str(round(ctx.rng.uniform(
                    float(points_possible) * 0.3,
                    float(points_possible) * 0.6,
                ), 1)))
                submitted_at = due_at - timedelta(hours=ctx.rng.randint(1, 12))
                resubmit_budget -= 1
                resubmit_ids.append(assignment_id)
            elif n <= graded_count and is_past_due:
                status = "graded"
                score = Decimal(str(round(ctx.rng.uniform(
                    float(points_possible) * 0.5,
                    float(points_possible) * 1.0,
                ), 1)))
                submitted_at = due_at - timedelta(hours=ctx.rng.randint(1, 48))
            elif is_past_due:
                status = "submitted"
                score = None
                submitted_at = due_at - timedelta(hours=ctx.rng.randint(1, 24))
            else:
                status = "not_submitted"
                score = None
                submitted_at = None

            attempt_count = 1 if status in ("submitted", "graded", "late", "resubmit_requested") else 0

            assignment = Assignment(
                id=assignment_id,
                course_id=course_id,
                title=title,
                type=atype,
                due_at=due_at,
                points_possible=points_possible,
                submission_status=status,
                score=score,
                feedback="Good work." if status == "graded" else None,
                attempt_count=attempt_count,
                max_attempts=2 if atype in ("homework", "quiz") else 1,
                rubric=[],
                weight_category=cat,
                submitted_at=submitted_at,
                file_name=file_name if status != "not_submitted" else None,
            )
            ctx.base["assignments"].append(assignment.model_dump())
            all_assignment_ids.append(assignment_id)

            # Track lowest homework score for drop-lowest
            if cat == "homework" and score is not None:
                pct = score / points_possible
                if lowest_homework_score is None or pct < lowest_homework_score:
                    lowest_homework_score = pct
                    lowest_homework_id = assignment_id

            # Track an exam assignment
            if atype == "exam" and exam_assignment_id is None:
                exam_assignment_id = assignment_id

    # Select target and decoy assignments
    target_assignment_id: str | None = None
    target_assignment_title: str = ""
    target_course_id: str = ""
    target_course_code: str = ""
    decoy_assignment_id: str | None = None

    all_assignments = ctx.base.get("assignments", [])
    candidates = all_assignments
    if target_status:
        candidates = [a for a in all_assignments if a["submission_status"] == target_status]
    if not candidates:
        candidates = all_assignments

    if candidates:
        target = ctx.rng.choice(candidates)
        target_assignment_id = target["id"]
        target_assignment_title = target["title"]
        target_course_id = target["course_id"]
        # Find course code
        for c in courses:
            if c["id"] == target_course_id:
                target_course_code = c["course_code"]
                break

        # Find a decoy in a different course with a similar title word
        decoy_candidates = [
            a for a in all_assignments
            if a["course_id"] != target_course_id and a["id"] != target_assignment_id
        ]
        if decoy_candidates:
            decoy_assignment_id = ctx.rng.choice(decoy_candidates)["id"]

    return {
        "assignment_ids": all_assignment_ids,
        "missing_assignment_ids": missing_ids,
        "late_assignment_ids": late_ids,
        "lowest_homework_id": lowest_homework_id or "",
        "exam_assignment_id": exam_assignment_id or "",
        "resubmit_assignment_ids": resubmit_ids,
        "target_assignment_id": target_assignment_id or "",
        "target_assignment_title": target_assignment_title,
        "target_course_id": target_course_id,
        "target_course_code": target_course_code,
        "decoy_assignment_id": decoy_assignment_id or "",
        "file_name": file_name,
    }


# ---------------------------------------------------------------------------
# 5. grade_book
# ---------------------------------------------------------------------------

@_register("grade_book")
def _build_grade_book(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create Grade records for all graded assignments.

    Applies drop-lowest logic, computes current weighted scores per course,
    and solves for minimum_final_score_for_b.

    Params
    ------
    (no params -- operates on existing assignments in ctx.base)
    """
    assignments = ctx.base.get("assignments", [])
    courses = ctx.base.get("courses", [])
    enrollments = ctx.base.get("enrollments", [])

    if "grades" not in ctx.base:
        ctx.base["grades"] = []

    grade_ids: list[str] = []
    dropped_grade_ids: list[str] = []

    # Build enrollment lookup: course_id -> enrollment_id
    enrollment_by_course: dict[str, str] = {}
    for e in enrollments:
        enrollment_by_course[e["course_id"]] = e["id"]

    # Create grade records for graded/late assignments
    for a in assignments:
        if a["score"] is None:
            continue
        if a["submission_status"] not in ("graded", "late", "resubmit_requested"):
            continue

        enrollment_id = enrollment_by_course.get(a["course_id"], "")
        if not enrollment_id:
            continue

        # Compute late penalty
        late_penalty = Decimal("0")
        if a["submission_status"] == "late" and a.get("submitted_at"):
            # Find course late policy
            for c in courses:
                if c["id"] == a["course_id"]:
                    lp = c["syllabus"]["late_policy"]
                    due_at = datetime.fromisoformat(a["due_at"]) if isinstance(a["due_at"], str) else a["due_at"]
                    sub_at = datetime.fromisoformat(a["submitted_at"]) if isinstance(a["submitted_at"], str) else a["submitted_at"]
                    elapsed = sub_at - due_at
                    elapsed_hours = Decimal(str(elapsed.total_seconds())) / Decimal("3600")
                    grace = Decimal(str(lp["grace_period_hours"]))
                    if elapsed_hours > grace:
                        hours_past = elapsed_hours - grace
                        days_late = math.ceil(float(hours_past) / 24)
                        if days_late > lp["max_late_days"]:
                            late_penalty = Decimal("1")
                        else:
                            late_penalty = min(
                                Decimal(str(days_late)) * Decimal(str(lp["penalty_per_day"])),
                                Decimal("1"),
                            )
                    break

        grade = Grade(
            id=ctx.next_id("grade"),
            enrollment_id=enrollment_id,
            course_id=a["course_id"],
            assignment_id=a["id"],
            score=Decimal(str(a["score"])),
            points_possible=Decimal(str(a["points_possible"])),
            weight_category=a["weight_category"],
            is_dropped=False,
            late_penalty_applied=late_penalty,
        )
        ctx.base["grades"].append(grade.model_dump())
        grade_ids.append(grade.id)

    # Apply drop-lowest logic per course/category
    for c in courses:
        course_id = c["id"]
        grading_policy = c["syllabus"]["grading_policy"]
        for cat_name, cat_policy_raw in grading_policy.items():
            drop_lowest = cat_policy_raw["drop_lowest"] if isinstance(cat_policy_raw, dict) else cat_policy_raw.drop_lowest
            if drop_lowest == 0:
                continue

            cat_grades = [
                g for g in ctx.base["grades"]
                if g["course_id"] == course_id
                and g["weight_category"] == cat_name
                and g["score"] is not None
            ]
            if not cat_grades:
                continue

            effective_drop = drop_lowest
            if len(cat_grades) <= effective_drop:
                effective_drop = max(0, len(cat_grades) - 1)

            sorted_grades = sorted(
                cat_grades,
                key=lambda g: Decimal(str(g["score"])) / Decimal(str(g["points_possible"]))
                if Decimal(str(g["points_possible"])) != 0 else Decimal("0"),
            )
            for g in sorted_grades[:effective_drop]:
                g["is_dropped"] = True
                dropped_grade_ids.append(g["id"])

    # Compute current weighted scores per course
    current_weighted_scores: dict[str, str] = {}
    minimum_final_score_for_b: str | None = None

    for c in courses:
        course_id = c["id"]
        grading_policy = c["syllabus"]["grading_policy"]
        graded_weight = Decimal("0")
        weighted_sum = Decimal("0")

        for cat_name, cat_policy_raw in grading_policy.items():
            weight = Decimal(str(cat_policy_raw["weight"] if isinstance(cat_policy_raw, dict) else cat_policy_raw.weight))

            cat_grades = [
                g for g in ctx.base["grades"]
                if g["course_id"] == course_id
                and g["weight_category"] == cat_name
                and g["score"] is not None
                and not g["is_dropped"]
            ]
            if not cat_grades:
                continue

            total = Decimal("0")
            for g in cat_grades:
                effective_score = Decimal(str(g["score"])) * (Decimal("1") - Decimal(str(g["late_penalty_applied"])))
                total += (effective_score / Decimal(str(g["points_possible"]))) * Decimal("100")

            cat_avg = (total / Decimal(str(len(cat_grades)))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )
            graded_weight += weight
            weighted_sum += cat_avg * weight

        if graded_weight > Decimal("0"):
            course_score = (weighted_sum / graded_weight).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )
            current_weighted_scores[course_id] = str(course_score)

    # Compute minimum score for B (80%) on the first course with ungraded assignments
    for c in courses:
        course_id = c["id"]
        remaining = [
            {"weight_category": a["weight_category"], "points_possible": Decimal(str(a["points_possible"]))}
            for a in assignments
            if a["course_id"] == course_id and a["score"] is None
        ]
        if not remaining:
            continue

        # Use the LMSState model's computation by constructing a temporary state
        # Instead, replicate the logic inline to avoid full state construction
        grading_policy = c["syllabus"]["grading_policy"]
        target_pct = Decimal("80")  # B

        total_weight = Decimal("0")
        fixed_part = Decimal("0")
        x_coefficient = Decimal("0")

        for cat_name, cat_policy_raw in grading_policy.items():
            weight = Decimal(str(cat_policy_raw["weight"] if isinstance(cat_policy_raw, dict) else cat_policy_raw.weight))
            active_grades = [
                g for g in ctx.base["grades"]
                if g["course_id"] == course_id
                and g["weight_category"] == cat_name
                and g["score"] is not None
                and not g["is_dropped"]
            ]
            remaining_in_cat = [r for r in remaining if r["weight_category"] == cat_name]

            current_count = len(active_grades)
            remaining_count = len(remaining_in_cat)
            n = current_count + remaining_count
            if n == 0:
                continue

            score_sum = Decimal("0")
            for g in active_grades:
                effective = Decimal(str(g["score"])) * (Decimal("1") - Decimal(str(g["late_penalty_applied"])))
                score_sum += (effective / Decimal(str(g["points_possible"]))) * Decimal("100")

            total_weight += weight
            denom = Decimal(str(n))
            fixed_part += weight * score_sum / denom
            x_coefficient += weight * Decimal(str(remaining_count)) / denom

        if total_weight > Decimal("0") and x_coefficient > Decimal("0"):
            needed = (target_pct * total_weight - fixed_part) / x_coefficient
            if needed <= Decimal("100") and needed >= Decimal("0"):
                minimum_final_score_for_b = str(
                    needed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                )
            elif needed < Decimal("0"):
                minimum_final_score_for_b = "0.00"
            break  # Use first course with remaining assignments

    return {
        "grade_ids": grade_ids,
        "dropped_grade_ids": dropped_grade_ids,
        "current_weighted_scores": current_weighted_scores,
        "minimum_final_score_for_b": minimum_final_score_for_b or "",
    }


# ---------------------------------------------------------------------------
# 6. module_sequence
# ---------------------------------------------------------------------------

@_register("module_sequence")
def _build_module_sequence(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate modules with prerequisite chains.

    Params
    ------
    course_id : str          -- which course to attach modules to
    count : int              -- number of modules (default 5)
    chain_type : str         -- "linear", "branching", or "mixed" (default "linear")
    completed_count : int    -- how many modules are already completed (default 2)
    """
    course_id = params.get("course_id", "")
    count = params.get("count", 5)
    chain_type = params.get("chain_type", "linear")
    completed_count = params.get("completed_count", 2)

    if not course_id:
        courses = ctx.base.get("courses", [])
        if courses:
            course_id = courses[0]["id"]

    if "modules" not in ctx.base:
        ctx.base["modules"] = []

    module_ids: list[str] = []
    first_locked_id: str | None = None
    next_available_id: str | None = None

    for i in range(count):
        module_id = ctx.next_id("module")
        module_ids.append(module_id)

        # Determine unlock condition based on chain type
        if i == 0:
            unlock_condition = "none"
            unlock_value: list[str] = []
        elif chain_type == "linear":
            unlock_condition = "prerequisite"
            unlock_value = [module_ids[i - 1]]
        elif chain_type == "branching":
            if i <= 1:
                unlock_condition = "prerequisite"
                unlock_value = [module_ids[0]]
            else:
                unlock_condition = "prerequisite"
                # Any one of the previous modules
                unlock_value = [module_ids[i - 1]]
        else:  # mixed
            if i == 1:
                unlock_condition = "prerequisite"
                unlock_value = [module_ids[0]]
            elif i > 1 and i % 2 == 0:
                unlock_condition = "min_score"
                unlock_value = [f"{module_ids[i - 1]}:70"]
            else:
                unlock_condition = "prerequisite"
                unlock_value = [module_ids[i - 1]]

        # Status
        if i < completed_count:
            status = "completed"
        elif i == completed_count:
            status = "available"
        else:
            status = "locked"

        # Content items
        content_items = [
            ContentItem(
                title=f"Reading: Chapter {i + 1}",
                type="reading",
                completed=i < completed_count,
            ),
            ContentItem(
                title=f"Video Lecture {i + 1}",
                type="video",
                completed=i < completed_count,
            ),
        ]

        module = Module(
            id=module_id,
            course_id=course_id,
            title=f"Module {i + 1}: {ctx.rng.choice(_TOPICS)}",
            position=i,
            unlock_condition=unlock_condition,
            unlock_value=unlock_value,
            status=status,
            content_items=content_items,
        )
        ctx.base["modules"].append(module.model_dump())

        if status == "locked" and first_locked_id is None:
            first_locked_id = module_id
        if status == "available" and next_available_id is None:
            next_available_id = module_id

    return {
        "module_ids": module_ids,
        "first_locked_module_id": first_locked_id or "",
        "next_available_module_id": next_available_id or "",
    }


# ---------------------------------------------------------------------------
# 7. discussion_forums
# ---------------------------------------------------------------------------

@_register("discussion_forums")
def _build_discussion_forums(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate discussions with existing classmate posts.

    Params
    ------
    course_id : str          -- which course (default first)
    count : int              -- number of discussions (default 2)
    posts_per : int          -- classmate posts per discussion (default 3)
    """
    course_id = params.get("course_id", "")
    count = params.get("count", 2)
    posts_per = params.get("posts_per", 3)

    if not course_id:
        courses = ctx.base.get("courses", [])
        if courses:
            course_id = courses[0]["id"]

    if "discussions" not in ctx.base:
        ctx.base["discussions"] = []
    if "discussion_posts" not in ctx.base:
        ctx.base["discussion_posts"] = []

    discussion_ids: list[str] = []
    target_discussion_id: str | None = None
    target_discussion_title: str = ""

    for d in range(count):
        disc_id = ctx.next_id("discussion")
        discussion_ids.append(disc_id)

        prompt = ctx.rng.choice(_DISCUSSION_PROMPTS)
        due_offset = ctx.rng.randint(3, 14)
        disc_title = f"Discussion {d + 1}: {ctx.rng.choice(_TOPICS)}"

        discussion = Discussion(
            id=disc_id,
            course_id=course_id,
            title=disc_title,
            prompt=prompt,
            due_at=ctx.now + timedelta(days=due_offset),
            min_posts=1,
            min_replies=1,
            points_possible=Decimal("10"),
            weight_category="participation",
        )
        ctx.base["discussions"].append(discussion.model_dump())

        if d == 0:
            target_discussion_id = disc_id
            target_discussion_title = disc_title

        # Generate classmate posts
        for p in range(posts_per):
            classmate_name = ctx.fake.name()
            post_id = ctx.next_id("post")
            post = DiscussionPost(
                id=post_id,
                discussion_id=disc_id,
                author_id=ctx.next_id("classmate"),
                author_name=classmate_name,
                body=ctx.fake.paragraph(nb_sentences=2),
                timestamp=ctx.now - timedelta(hours=ctx.rng.randint(1, 72)),
            )
            ctx.base["discussion_posts"].append(post.model_dump())

            # Add a reply to the first post sometimes
            if p == 0 and posts_per > 1:
                reply_name = ctx.fake.name()
                reply = DiscussionPost(
                    id=ctx.next_id("post"),
                    discussion_id=disc_id,
                    author_id=ctx.next_id("classmate"),
                    author_name=reply_name,
                    body=ctx.fake.paragraph(nb_sentences=1),
                    parent_post_id=post_id,
                    timestamp=ctx.now - timedelta(hours=ctx.rng.randint(1, 24)),
                )
                ctx.base["discussion_posts"].append(reply.model_dump())

    # Look up course code for the target discussion
    target_course_code = ""
    if course_id:
        for c in ctx.base.get("courses", []):
            if c["id"] == course_id:
                target_course_code = c["course_code"]
                break

    return {
        "discussion_ids": discussion_ids,
        "target_discussion_id": target_discussion_id or "",
        "target_discussion_title": target_discussion_title,
        "target_course_code": target_course_code,
    }


# ---------------------------------------------------------------------------
# 8. announcements_feed
# ---------------------------------------------------------------------------

@_register("announcements_feed")
def _build_announcements_feed(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate announcements distributed across courses.

    Params
    ------
    count : int        -- total announcements (default 6)
    unread_count : int -- how many are unread (default 2)
    urgent_count : int -- how many are urgent priority (default 1)
    """
    count = params.get("count", 6)
    unread_count = params.get("unread_count", 2)
    urgent_count = params.get("urgent_count", 1)

    courses = ctx.base.get("courses", [])
    if "announcements" not in ctx.base:
        ctx.base["announcements"] = []

    announcement_ids: list[str] = []
    unread_ids: list[str] = []
    urgent_announcement_id: str | None = None

    for i in range(count):
        ann_id = ctx.next_id("announcement")
        course_data = courses[i % len(courses)] if courses else {"id": "course_1"}
        course_id = course_data["id"]

        body = ctx.rng.choice(_ANNOUNCEMENT_BODIES).replace(
            "{mod_num}", str(ctx.rng.randint(1, 5)),
        )
        is_read = i >= unread_count
        is_urgent = i < urgent_count

        announcement = Announcement(
            id=ann_id,
            course_id=course_id,
            title=f"{'URGENT: ' if is_urgent else ''}Announcement {i + 1}",
            body=body,
            posted_at=ctx.now - timedelta(days=ctx.rng.randint(0, 14)),
            is_read=is_read,
            priority="urgent" if is_urgent else "normal",
        )
        ctx.base["announcements"].append(announcement.model_dump())
        announcement_ids.append(ann_id)

        if not is_read:
            unread_ids.append(ann_id)
        if is_urgent and urgent_announcement_id is None:
            urgent_announcement_id = ann_id

    return {
        "announcement_ids": announcement_ids,
        "unread_announcement_ids": unread_ids,
        "urgent_announcement_id": urgent_announcement_id or "",
    }


# ---------------------------------------------------------------------------
# 9. calendar_events
# ---------------------------------------------------------------------------

@_register("calendar_events")
def _build_calendar_events(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate calendar events (lectures, office hours, exams, deadlines).

    Params
    ------
    include_recurring : bool -- expand weekly recurrences (default True)
    weeks : int              -- how many weeks of recurrences (default 4)
    """
    include_recurring = params.get("include_recurring", True)
    weeks = params.get("weeks", 4)

    courses = ctx.base.get("courses", [])
    if "calendar_events" not in ctx.base:
        ctx.base["calendar_events"] = []

    event_ids: list[str] = []
    next_exam_id: str | None = None
    next_deadline_id: str | None = None

    # For each course, create lecture and office hours recurrences + one-off events
    for ci, course_data in enumerate(courses):
        course_id = course_data["id"]

        # Weekly lecture
        lecture_day_offset = ci % 5  # Mon-Fri
        lecture_hour = 9 + ci  # stagger start times

        if include_recurring:
            semester_start = ctx.now - timedelta(days=45)
            for w in range(weeks):
                week_start = semester_start + timedelta(weeks=w)
                lecture_start = week_start + timedelta(
                    days=lecture_day_offset,
                    hours=lecture_hour - week_start.hour,
                )
                lecture_start = lecture_start.replace(
                    hour=lecture_hour, minute=0, second=0,
                )
                event_id = ctx.next_id("event")
                event = CalendarEvent(
                    id=event_id,
                    course_id=course_id,
                    title=f"{course_data['course_code']} Lecture",
                    event_type="lecture",
                    start_datetime=lecture_start,
                    end_datetime=lecture_start + timedelta(hours=1, minutes=15),
                    location=f"Room {100 + ci * 10 + ctx.rng.randint(1, 9)}",
                    recurrence="none",
                )
                ctx.base["calendar_events"].append(event.model_dump())
                event_ids.append(event_id)

            # Weekly office hours
            oh_day_offset = (lecture_day_offset + 2) % 5
            for w in range(weeks):
                week_start = semester_start + timedelta(weeks=w)
                oh_start = week_start + timedelta(days=oh_day_offset)
                oh_start = oh_start.replace(hour=14, minute=0, second=0)
                event_id = ctx.next_id("event")
                event = CalendarEvent(
                    id=event_id,
                    course_id=course_id,
                    title=f"{course_data['course_code']} Office Hours",
                    event_type="office_hours",
                    start_datetime=oh_start,
                    end_datetime=oh_start + timedelta(hours=2),
                    location=f"Office {200 + ci}",
                    recurrence="none",
                )
                ctx.base["calendar_events"].append(event.model_dump())
                event_ids.append(event_id)
        else:
            # Just add template events
            event_id = ctx.next_id("event")
            lecture_start = ctx.now.replace(hour=lecture_hour, minute=0, second=0)
            recurrence_end = ctx.now + timedelta(weeks=weeks)
            event = CalendarEvent(
                id=event_id,
                course_id=course_id,
                title=f"{course_data['course_code']} Lecture",
                event_type="lecture",
                start_datetime=lecture_start,
                end_datetime=lecture_start + timedelta(hours=1, minutes=15),
                location=f"Room {100 + ci * 10}",
                recurrence="weekly",
                recurrence_end_date=recurrence_end,
            )
            ctx.base["calendar_events"].append(event.model_dump())
            event_ids.append(event_id)

        # Exam event (from course data)
        exam_date_raw = course_data.get("final_exam_date")
        if exam_date_raw:
            exam_dt = datetime.fromisoformat(exam_date_raw) if isinstance(exam_date_raw, str) else exam_date_raw
            event_id = ctx.next_id("event")
            event = CalendarEvent(
                id=event_id,
                course_id=course_id,
                title=f"{course_data['course_code']} Final Exam",
                event_type="exam",
                start_datetime=exam_dt,
                end_datetime=exam_dt + timedelta(hours=3),
                location=f"Exam Hall {ctx.rng.choice(['A', 'B', 'C'])}",
            )
            ctx.base["calendar_events"].append(event.model_dump())
            event_ids.append(event_id)
            if next_exam_id is None and exam_dt > ctx.now:
                next_exam_id = event_id

    # Add deadline events from assignments due in the future
    assignments = ctx.base.get("assignments", [])
    for a in assignments:
        due_at = datetime.fromisoformat(a["due_at"]) if isinstance(a["due_at"], str) else a["due_at"]
        if due_at > ctx.now and a["submission_status"] == "not_submitted":
            event_id = ctx.next_id("event")
            event = CalendarEvent(
                id=event_id,
                course_id=a["course_id"],
                title=f"Due: {a['title']}",
                event_type="deadline",
                start_datetime=due_at,
                end_datetime=due_at + timedelta(minutes=1),
            )
            ctx.base["calendar_events"].append(event.model_dump())
            event_ids.append(event_id)
            if next_deadline_id is None:
                next_deadline_id = event_id

    return {
        "event_ids": event_ids,
        "next_exam_event_id": next_exam_id or "",
        "next_deadline_event_id": next_deadline_id or "",
    }


# ---------------------------------------------------------------------------
# 10. peer_review_assignments
# ---------------------------------------------------------------------------

@_register("peer_review_assignments")
def _build_peer_review_assignments(ctx: LMSSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create peer review records in various states.

    Params
    ------
    count : int                   -- number of peer reviews (default 3)
    assignment_id : str           -- which assignment the reviews are for
    statuses : list[str]          -- status distribution (default mixed)
    """
    count = params.get("count", 3)
    assignment_id = params.get("assignment_id", "")
    statuses = params.get("statuses", ["assigned", "in_progress", "submitted"])

    if not assignment_id:
        # Find a peer_review type assignment, or fallback to first assignment
        assignments = ctx.base.get("assignments", [])
        pr_assignments = [a for a in assignments if a["type"] == "peer_review"]
        if pr_assignments:
            assignment_id = pr_assignments[0]["id"]
        elif assignments:
            assignment_id = assignments[0]["id"]

    student_id = ctx.base.get("student", {}).get("id", "student_1")

    if "peer_reviews" not in ctx.base:
        ctx.base["peer_reviews"] = []

    review_ids: list[str] = []
    pending_review_ids: list[str] = []
    completed_review_ids: list[str] = []

    for i in range(count):
        review_id = ctx.next_id("review")
        status = statuses[i % len(statuses)]
        reviewee_name = ctx.fake.name()
        reviewee_id = ctx.next_id("reviewee")

        rubric_scores: dict[str, int] = {}
        comments = ""
        if status == "submitted":
            rubric_scores = {
                "clarity": ctx.rng.randint(3, 5),
                "depth": ctx.rng.randint(2, 5),
                "originality": ctx.rng.randint(2, 5),
            }
            comments = ctx.fake.paragraph(nb_sentences=2)
        elif status == "in_progress":
            rubric_scores = {"clarity": ctx.rng.randint(3, 5)}

        review = PeerReview(
            id=review_id,
            assignment_id=assignment_id,
            reviewer_student_id=student_id,
            reviewee_student_id=reviewee_id,
            rubric_scores=rubric_scores,
            comments=comments,
            status=status,
            due_at=ctx.now + timedelta(days=ctx.rng.randint(3, 10)),
        )
        ctx.base["peer_reviews"].append(review.model_dump())
        review_ids.append(review_id)

        if status in ("assigned", "in_progress"):
            pending_review_ids.append(review_id)
        else:
            completed_review_ids.append(review_id)

    return {
        "review_ids": review_ids,
        "pending_review_ids": pending_review_ids,
        "completed_review_ids": completed_review_ids,
    }
