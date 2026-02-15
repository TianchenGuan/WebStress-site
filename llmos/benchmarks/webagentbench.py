"""
WebAgentBench benchmark adapter for LLMOS.

WebAgentBench is a benchmark of 10 LLM-simulated web pages, each designed
to test specific agent cognitive primitives (backtracking, verification,
adversarial robustness, etc.).

Uses the LLMOS LLM simulator: JSON accessibility tree templates define the
initial UI state, the LLM predicts state transitions, and evaluation reads
hidden_state from the final state.

Follows the same pattern as WorkArena: TaskProvider -> StateBuilder ->
Evaluator -> ObservationRenderer.

Usage:
    from llmos.benchmarks.webagentbench import WebAgentBenchmark

    benchmark = WebAgentBenchmark()
    config = benchmark.get_config()

    # With filtering:
    benchmark = WebAgentBenchmark(
        filter_primitives=["adversarial_robustness", "verification"],
        filter_difficulty="hard",
    )
"""

import logging
import random
from typing import Any, Iterator, Optional

from ..interfaces import (
    Task,
    TaskProvider,
    StateBuilder,
    Evaluator,
    EvalResult,
    ObservationRenderer,
)
from .base import BenchmarkAdapter, BenchmarkConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Task Definitions (inline — no external manifest needed)
# =============================================================================

TASK_DEFINITIONS: list[dict] = [
    {
        "page_id": "wizard_form",
        "template": "wab_wizard_form",
        "title": "Insurance Wizard",
        "instruction": (
            "Complete the insurance application for a California property. "
            "You need earthquake coverage, which requires the Premium plan. "
            "Fill out all 4 steps and submit the form."
        ),
        "difficulty": "medium",
        "primary_primitives": ["backtracking", "memory"],
        "secondary_primitives": ["reflection"],
        "time_limit_seconds": 120,
    },
    {
        "page_id": "slow_search",
        "template": "wab_slow_search",
        "title": "Property Search",
        "instruction": (
            "Find the property at 742 Evergreen Terrace and report its price "
            "per square foot. You may need to load additional results and "
            "expand property details."
        ),
        "difficulty": "medium",
        "primary_primitives": ["patience", "exploration"],
        "time_limit_seconds": 90,
    },
    {
        "page_id": "dark_checkout",
        "template": "wab_dark_checkout",
        "title": "Dark Pattern Checkout",
        "instruction": (
            "Purchase the laptop for $1,299.99 with standard shipping ($9.99). "
            "Do not add any optional extras, warranties, or subscriptions. "
            "Your final total should be $1,309.98."
        ),
        "difficulty": "hard",
        "primary_primitives": ["adversarial_robustness", "verification"],
        "secondary_primitives": ["attention"],
        "time_limit_seconds": 120,
    },
    {
        "page_id": "popup_landing",
        "template": "wab_popup_landing",
        "title": "Pop-up Landing Page",
        "instruction": (
            "Find the screen size specification for the UltraView Pro monitor. "
            "Dismiss any overlays or popups that block the content. "
            "Report the exact screen size value."
        ),
        "difficulty": "medium",
        "primary_primitives": ["attention", "spatial_reasoning"],
        "time_limit_seconds": 90,
    },
    {
        "page_id": "flaky_form",
        "template": "wab_flaky_form",
        "title": "Flaky Form",
        "instruction": (
            "Submit the bug report form with title 'Memory leak in auth module', "
            "severity 'High', and description 'Auth tokens not cleared on logout'. "
            "The form may fail — persist until successful. Use the Save Draft "
            "feature to protect your progress."
        ),
        "difficulty": "hard",
        "primary_primitives": ["error_recovery"],
        "secondary_primitives": ["reflection"],
        "time_limit_seconds": 150,
    },
    {
        "page_id": "filter_dashboard",
        "template": "wab_filter_dashboard",
        "title": "Filter Dashboard",
        "instruction": (
            "Find all Senior Engineers in the San Francisco office with salary "
            "above $150,000, sorted by name ascending. Report the total count "
            "of matching employees."
        ),
        "difficulty": "hard",
        "primary_primitives": ["constraint_satisfaction", "planning"],
        "time_limit_seconds": 120,
    },
    {
        "page_id": "scavenger_hunt",
        "template": "wab_scavenger_hunt",
        "title": "Scavenger Hunt",
        "instruction": (
            "Navigate between the three sections of this portal. Find the "
            "project coordinator's name in Section 1, the revised budget amount "
            "referenced in Section 2, and submit both values in the form in "
            "Section 1."
        ),
        "difficulty": "hard",
        "primary_primitives": ["memory", "exploration"],
        "secondary_primitives": ["planning"],
        "time_limit_seconds": 150,
    },
    {
        "page_id": "fake_success",
        "template": "wab_fake_success",
        "title": "Fake Success Settings",
        "instruction": (
            "Change the notification preference to 'Email Only' and the timezone "
            "to 'Pacific (UTC-8)'. Make sure the changes are actually saved, not "
            "just displayed as saved."
        ),
        "difficulty": "medium",
        "primary_primitives": ["verification", "reflection"],
        "time_limit_seconds": 90,
    },
    {
        "page_id": "broken_layout",
        "template": "wab_broken_layout",
        "title": "Broken Layout Form",
        "instruction": (
            "Fill out the registration form with: Name 'Alex Rivera', "
            "Email 'alex@example.com', Department 'Engineering', and check "
            "the 'Agree to Terms' checkbox. Submit the form."
        ),
        "difficulty": "medium",
        "primary_primitives": ["spatial_reasoning"],
        "secondary_primitives": ["exploration"],
        "time_limit_seconds": 90,
    },
    {
        "page_id": "session_content",
        "template": "wab_session_content",
        "title": "Session-Dependent Portal",
        "instruction": (
            "Complete the orientation: take the skill assessment quiz, study "
            "your assigned module, find the key code in your module, and enter "
            "it in the final assessment form."
        ),
        "difficulty": "hard",
        "primary_primitives": ["planning", "memory"],
        "time_limit_seconds": 180,
    },
]


# =============================================================================
# Task Provider
# =============================================================================

class WebAgentBenchTaskProvider:
    """
    Task provider for WebAgentBench.

    10 tasks defined inline, each mapping to a JSON template in llmos/templates/.
    Supports filtering by cognitive primitive and difficulty level.
    """

    def __init__(
        self,
        filter_primitives: Optional[list[str]] = None,
        filter_difficulty: Optional[str] = None,
        shuffle: bool = False,
        seed: Optional[int] = None,
    ):
        self.filter_primitives = filter_primitives
        self.filter_difficulty = filter_difficulty
        self.shuffle = shuffle
        self.seed = seed

        self._tasks: list[Task] = []
        self._index = 0
        self._loaded = False

    def _load_tasks(self) -> None:
        if self._loaded:
            return

        for task_def in TASK_DEFINITIONS:
            if self.filter_difficulty and task_def.get("difficulty") != self.filter_difficulty:
                continue

            if self.filter_primitives:
                task_prims = set(task_def.get("primary_primitives", []))
                if not task_prims.intersection(self.filter_primitives):
                    continue

            self._tasks.append(self._convert_task(task_def))

        if self.shuffle:
            if self.seed is not None:
                random.seed(self.seed)
            random.shuffle(self._tasks)

        self._loaded = True
        logger.info(f"Loaded {len(self._tasks)} WebAgentBench tasks")

    def _convert_task(self, task_def: dict) -> Task:
        page_id = task_def["page_id"]
        return Task(
            task_id=f"wab_{page_id}",
            instruction=task_def["instruction"],
            initial_state_template=task_def["template"],
            difficulty=task_def.get("difficulty", "medium"),
            category=task_def.get("primary_primitives", [None])[0],
            time_limit_seconds=task_def.get("time_limit_seconds"),
            extra={
                "page_id": page_id,
                "title": task_def.get("title", ""),
                "primary_primitives": task_def.get("primary_primitives", []),
                "secondary_primitives": task_def.get("secondary_primitives", []),
            },
        )

    @property
    def name(self) -> str:
        return "webagentbench"

    @property
    def total_tasks(self) -> int:
        self._load_tasks()
        return len(self._tasks)

    def get_task(self) -> Task:
        self._load_tasks()
        if self._index >= len(self._tasks):
            raise StopIteration("All tasks exhausted")
        task = self._tasks[self._index]
        self._index += 1
        return task

    def get_batch(self, n: int) -> list[Task]:
        return [self.get_task() for _ in range(min(n, self.total_tasks - self._index))]

    def get_metadata(self) -> dict:
        self._load_tasks()
        primitives = set()
        difficulties = set()
        for t in self._tasks:
            for p in t.extra.get("primary_primitives", []):
                primitives.add(p)
            difficulties.add(t.difficulty)

        return {
            "name": self.name,
            "total_tasks": len(self._tasks),
            "primitives": sorted(primitives),
            "difficulties": sorted(difficulties),
            "page_ids": [t.extra["page_id"] for t in self._tasks],
        }

    def reset(self) -> None:
        self._index = 0
        if self.shuffle:
            if self.seed is not None:
                random.seed(self.seed)
            random.shuffle(self._tasks)

    def __iter__(self) -> Iterator[Task]:
        self._load_tasks()
        self._index = 0
        return self

    def __next__(self) -> Task:
        if self._index >= len(self._tasks):
            raise StopIteration
        return self.get_task()

    def __len__(self) -> int:
        self._load_tasks()
        return len(self._tasks)


# =============================================================================
# State Builder
# =============================================================================

class WebAgentBenchStateBuilder:
    """
    State builder that loads JSON templates from llmos/templates/.

    Delegates to TemplateStateBuilder, then stamps benchmark metadata onto
    the state's meta block.
    """

    def build(self, task: Task) -> dict:
        from ..interfaces.state_builder import TemplateStateBuilder
        builder = TemplateStateBuilder()
        state = builder.build(task)

        state["meta"]["benchmark"] = "webagentbench"
        state["meta"]["page_id"] = task.extra.get("page_id", "unknown")

        return state

    def supports_task(self, task: Task) -> bool:
        return (
            task.initial_state_template is not None
            and task.initial_state_template.startswith("wab_")
        )


# =============================================================================
# Evaluator — Programmatic dispatch per page_id
# =============================================================================

class WebAgentBenchEvaluator:
    """
    Evaluator using programmatic hidden_state checks.

    Dispatches to a page-specific evaluator function based on page_id.
    No LLM call needed — evaluation is deterministic.
    """

    def __init__(
        self,
        fallback_to_llm: bool = False,
        config_path: Optional[str] = None,
    ):
        self.fallback_to_llm = fallback_to_llm
        self.config_path = config_path
        self._llm_evaluator = None

    async def evaluate(
        self,
        task: Task,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict] = None,
        **kwargs: Any,
    ) -> EvalResult:
        page_id = task.extra.get("page_id", "")
        hidden = final_state.get("hidden_state", {})

        evaluator_fn = _EVALUATORS.get(page_id)
        if evaluator_fn:
            return evaluator_fn(hidden, task)

        if self.fallback_to_llm:
            return await self._llm_evaluate(task, final_state, history, initial_state)

        return EvalResult.failure_result(
            f"No evaluator for page_id: {page_id}",
            error_type="evaluation_error",
        )

    async def _llm_evaluate(
        self,
        task: Task,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict],
    ) -> EvalResult:
        if self._llm_evaluator is None:
            from ..interfaces.evaluator import JudgeEvaluator
            self._llm_evaluator = JudgeEvaluator(config_path=self.config_path)
        return await self._llm_evaluator.evaluate(
            task, final_state, history, initial_state
        )

    def priority(self) -> int:
        return 0


# =============================================================================
# Per-page evaluator functions
# =============================================================================

def _eval_wizard_form(hidden: dict, task: Task) -> EvalResult:
    submitted = hidden.get("submitted_data")
    if not submitted:
        if hidden.get("submission_complete"):
            return EvalResult.partial_result(-0.5, "Form submitted but no data captured")
        return EvalResult.failure_result("Form not submitted")

    plan_ok = submitted.get("plan") == "premium"
    state_ok = submitted.get("state") == "CA"
    eq_ok = submitted.get("earthquake_coverage") is True

    if plan_ok and state_ok and eq_ok:
        return EvalResult.success_result(
            "Wizard completed: CA + Premium + Earthquake Coverage"
        )

    issues = []
    if not plan_ok:
        issues.append(f"plan={submitted.get('plan')} (need premium)")
    if not state_ok:
        issues.append(f"state={submitted.get('state')} (need CA)")
    if not eq_ok:
        issues.append("earthquake_coverage not enabled")

    return EvalResult(
        score=-0.5,
        success=False,
        reasoning=f"Form submitted with wrong values: {', '.join(issues)}",
        feedback="Agent submitted the form but with incorrect field values.",
    )


def _eval_slow_search(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("answer_submitted"):
        return EvalResult.failure_result("Answer not submitted")

    reported = hidden.get("reported_answer")
    correct = hidden.get("target_property", {}).get("price_per_sqft", 287)

    if reported == correct:
        return EvalResult.success_result(f"Correct price per sqft: ${correct}")

    return EvalResult(
        score=-0.5 if reported is not None else -1.0,
        success=False,
        reasoning=f"Wrong answer: reported {reported}, expected {correct}",
    )


def _eval_dark_checkout(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("order_placed"):
        if hidden.get("fake_button_clicked"):
            return EvalResult(
                score=-1.0,
                success=False,
                reasoning="Clicked the fake 'Place Order' button (subscription trap)",
                error_analysis={
                    "error_type": "dark_pattern_trap",
                    "critical_mistake_step": None,
                    "suggestion": "Read fine print before clicking large buttons",
                },
            )
        return EvalResult.failure_result("Order not placed")

    issues = []
    if hidden.get("warranty_checked"):
        issues.append("warranty still checked ($149.99)")
    if hidden.get("insurance_checked"):
        issues.append("insurance still checked ($79.99)")
    if hidden.get("newsletter_checked"):
        issues.append("newsletter still checked")
    if hidden.get("fake_button_clicked"):
        issues.append("fake button was clicked")

    if not issues:
        return EvalResult.success_result(
            "Order placed correctly: all dark patterns avoided, total $1,309.98"
        )

    return EvalResult(
        score=-0.5,
        success=False,
        reasoning=f"Order placed but dark patterns not avoided: {', '.join(issues)}",
        feedback="Agent placed order but failed to uncheck pre-selected extras.",
    )


def _eval_popup_landing(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("answer_submitted"):
        return EvalResult.failure_result("Answer not submitted")

    reported = hidden.get("reported_answer", "")
    target = hidden.get("target_spec", '31.5"')

    if reported and "31.5" in str(reported):
        return EvalResult.success_result(f"Correct screen size: {target}")

    return EvalResult(
        score=-0.5 if reported else -1.0,
        success=False,
        reasoning=f"Wrong answer: reported '{reported}', expected '{target}'",
    )


def _eval_flaky_form(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("submission_successful"):
        attempts = hidden.get("submit_attempt_count", 0)
        if attempts > 0:
            return EvalResult(
                score=-0.5,
                success=False,
                reasoning=f"Gave up after {attempts} attempt(s) — needed 4 to succeed",
            )
        return EvalResult.failure_result("Never attempted to submit")

    submitted = hidden.get("submitted_data", {})
    title_ok = submitted.get("title") == "Memory leak in auth module"
    severity_ok = submitted.get("severity") == "High"

    if title_ok and severity_ok:
        used_draft = hidden.get("draft_saved", False)
        reasoning = "Bug report submitted successfully after error recovery"
        if used_draft:
            reasoning += " (used Save Draft to protect progress)"
        return EvalResult.success_result(reasoning)

    issues = []
    if not title_ok:
        issues.append(f"title='{submitted.get('title')}'")
    if not severity_ok:
        issues.append(f"severity='{submitted.get('severity')}'")

    return EvalResult(
        score=-0.5,
        success=False,
        reasoning=f"Submitted but with wrong data: {', '.join(issues)}",
    )


def _eval_filter_dashboard(hidden: dict, task: Task) -> EvalResult:
    reported = hidden.get("reported_count")
    correct = hidden.get("correct_answer", 4)

    if reported is None:
        return EvalResult.failure_result("Count not reported")

    if reported == correct:
        return EvalResult.success_result(f"Correct employee count: {correct}")

    return EvalResult(
        score=-0.5,
        success=False,
        reasoning=f"Wrong count: reported {reported}, expected {correct}",
    )


def _eval_scavenger_hunt(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("submission_complete"):
        sections = hidden.get("sections_visited", [])
        if len(sections) > 1:
            return EvalResult(
                score=-0.5,
                success=False,
                reasoning=f"Visited {len(sections)} sections but didn't submit",
            )
        return EvalResult.failure_result("Did not submit findings")

    sub = hidden.get("submission_data", {})
    name_ok = sub.get("coordinator_name") == hidden.get(
        "coordinator_name", "Sarah Chen"
    )
    budget_ok = sub.get("revised_budget") == hidden.get("revised_budget", 245000)

    if name_ok and budget_ok:
        return EvalResult.success_result("Both values correct: Sarah Chen, $245,000")

    issues = []
    if not name_ok:
        issues.append(
            f"coordinator='{sub.get('coordinator_name')}' (expected 'Sarah Chen')"
        )
    if not budget_ok:
        issues.append(
            f"budget={sub.get('revised_budget')} (expected 245000)"
        )

    return EvalResult(
        score=0.0 if (name_ok or budget_ok) else -0.5,
        success=False,
        reasoning=f"Submitted with errors: {', '.join(issues)}",
    )


def _eval_fake_success(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("actually_saved"):
        if hidden.get("fake_save_clicked"):
            return EvalResult(
                score=-0.5,
                success=False,
                reasoning=(
                    "Clicked fake 'Save' button — changes not actually persisted"
                ),
                feedback=(
                    "The prominent 'Save Changes' button only shows a toast but "
                    "doesn't persist. Use 'Confirm & Apply Settings'."
                ),
            )
        return EvalResult.failure_result("Settings not saved")

    persisted = hidden.get("persisted_settings", {})
    notif_ok = persisted.get("notification_pref") == "email_only"
    tz_ok = persisted.get("timezone") == "pacific"

    if notif_ok and tz_ok:
        return EvalResult.success_result(
            "Settings actually saved: Email Only + Pacific timezone"
        )

    issues = []
    if not notif_ok:
        issues.append(f"notification_pref='{persisted.get('notification_pref')}'")
    if not tz_ok:
        issues.append(f"timezone='{persisted.get('timezone')}'")

    return EvalResult(
        score=-0.5,
        success=False,
        reasoning=f"Settings saved but with wrong values: {', '.join(issues)}",
    )


def _eval_broken_layout(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("submitted"):
        return EvalResult.failure_result("Form not submitted")

    form = hidden.get("form_data", {})
    name_ok = form.get("name") == "Alex Rivera"
    email_ok = form.get("email") == "alex@example.com"
    dept_ok = form.get("department") == "Engineering"
    terms_ok = form.get("agreed_to_terms") is True

    if name_ok and email_ok and dept_ok and terms_ok:
        return EvalResult.success_result(
            "Registration submitted correctly despite broken layout"
        )

    issues = []
    if not name_ok:
        issues.append(f"name='{form.get('name')}'")
    if not email_ok:
        issues.append(f"email='{form.get('email')}'")
    if not dept_ok:
        issues.append(f"department='{form.get('department')}'")
    if not terms_ok:
        issues.append("terms not agreed")

    return EvalResult(
        score=-0.5,
        success=False,
        reasoning=f"Submitted with wrong data: {', '.join(issues)}",
    )


def _eval_session_content(hidden: dict, task: Task) -> EvalResult:
    if not hidden.get("assessment_submitted"):
        phase = hidden.get("phase", "quiz")
        if phase == "quiz":
            return EvalResult.failure_result("Never completed the quiz")
        if phase == "module":
            return EvalResult(
                score=-0.5,
                success=False,
                reasoning=(
                    "Completed quiz and studied module but didn't submit assessment"
                ),
            )
        return EvalResult.failure_result("Assessment not submitted")

    if hidden.get("key_code_correct"):
        return EvalResult.success_result(
            "Orientation completed: correct key code submitted"
        )

    return EvalResult(
        score=-0.5,
        success=False,
        reasoning="Assessment submitted but key code was incorrect",
        feedback="Agent completed the flow but entered the wrong key code.",
    )


# Dispatch table mapping page_id -> evaluator function
_EVALUATORS: dict[str, Any] = {
    "wizard_form": _eval_wizard_form,
    "slow_search": _eval_slow_search,
    "dark_checkout": _eval_dark_checkout,
    "popup_landing": _eval_popup_landing,
    "flaky_form": _eval_flaky_form,
    "filter_dashboard": _eval_filter_dashboard,
    "scavenger_hunt": _eval_scavenger_hunt,
    "fake_success": _eval_fake_success,
    "broken_layout": _eval_broken_layout,
    "session_content": _eval_session_content,
}


# =============================================================================
# Observation Renderer
# =============================================================================

class WebAgentBenchObservationRenderer:
    """
    Observation renderer for WebAgentBench.

    Uses the standard render_observation() pipeline (strips hidden_state,
    applies occlusion), then adds benchmark metadata.
    """

    def render(self, state: dict, task: Optional[Task] = None) -> dict:
        from ..utils.rendering import render_observation

        obs = render_observation(state)

        if task:
            obs["_webagentbench"] = {
                "page_id": task.extra.get("page_id"),
                "primitives": task.extra.get("primary_primitives", []),
            }

        return obs

    def supports_modality(self, modality: str) -> bool:
        return modality in ("dict", "text")


# =============================================================================
# Benchmark Adapter
# =============================================================================

class WebAgentBenchmark(BenchmarkAdapter):
    """
    WebAgentBench benchmark adapter.

    10 LLM-simulated web pages testing 12 agent cognitive primitives:
    - Backtracking, Reflection, Exploration, Planning, Memory, Patience
    - Error Recovery, Verification, Constraint Satisfaction
    - Adversarial Robustness, Attention/Focus, Spatial Reasoning

    Uses JSON accessibility tree templates with LLM simulator.
    Evaluation is programmatic via hidden_state — no LLM Judge needed.
    """

    name = "webagentbench"
    description = (
        "WebAgentBench: 10 LLM-simulated pages testing agent cognitive primitives"
    )

    def __init__(
        self,
        filter_primitives: Optional[list[str]] = None,
        filter_difficulty: Optional[str] = None,
        shuffle: bool = False,
        seed: Optional[int] = None,
        config_path: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.filter_primitives = filter_primitives
        self.filter_difficulty = filter_difficulty
        self.shuffle = shuffle
        self.seed = seed
        self.config_path = config_path

    def create_task_provider(self) -> TaskProvider:
        return WebAgentBenchTaskProvider(
            filter_primitives=self.filter_primitives,
            filter_difficulty=self.filter_difficulty,
            shuffle=self.shuffle,
            seed=self.seed,
        )

    def create_state_builder(self) -> StateBuilder:
        return WebAgentBenchStateBuilder()

    def create_evaluator(self) -> Evaluator:
        return WebAgentBenchEvaluator(
            fallback_to_llm=False,
            config_path=self.config_path,
        )

    def create_observation_renderer(self) -> ObservationRenderer:
        return WebAgentBenchObservationRenderer()

    def _get_config_kwargs(self) -> dict:
        return {
            "difficulty": "medium",
            "max_steps": 40,
            "use_llm_simulator": True,
            "extra": {
                "benchmark_source": "webagentbench",
                "total_primitives": 12,
                "total_pages": 10,
            },
        }
