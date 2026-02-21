"""
WebAgentBench benchmark adapter for LLMOS.

Runs the 10 WebAgentBench tasks through the LLMOS simulator instead of a
real browser.  Each task maps to a ``wab_<page_id>.json`` template that
mirrors the original page's initial DOM state.  The simulator sees
``meta.target_primitives`` and ``hidden_state.wab_behavior`` so it can
produce realistic state transitions (form failures, overlays, etc.).

Task instructions and evaluation criteria are identical to those in the
standalone ``webagentbench/manifest.json``.

Usage:
    from llmos.benchmarks.webagentbench import WebAgentBenchBenchmark
    benchmark = WebAgentBenchBenchmark()
    config = benchmark.get_config()
"""

import logging
import random
import re
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

# ============================================================================
# WAB_PAGES — embedded page definitions from webagentbench/manifest.json
# ============================================================================

WAB_PAGES: list[dict] = [
    {
        "page_id": "wizard_form",
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
        "success_criteria": {
            "js_eval": [
                "data.submitted === true",
                "data.plan === 'premium'",
                "data.state === 'CA'",
                "data.earthquake_coverage === true",
            ],
            "dom_check": [
                {"selector": "#confirmation-message", "condition": "contains", "value": "submitted"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Form submitted but wrong plan", "condition": "data.submitted === true and data.plan != 'premium'", "score": -0.5},
                {"description": "Form submitted but no earthquake coverage", "condition": "data.submitted === true and data.earthquake_coverage != True", "score": -0.5},
            ],
            "failure": {"condition": "data.submitted != true", "score": -1.0},
        },
    },
    {
        "page_id": "slow_search",
        "title": "Property Search",
        "instruction": (
            "Find the property at 742 Evergreen Terrace and report its price "
            "per square foot. You may need to load additional results and expand "
            "property details."
        ),
        "difficulty": "medium",
        "primary_primitives": ["patience", "exploration"],
        "secondary_primitives": [],
        "time_limit_seconds": 90,
        "success_criteria": {
            "js_eval": [
                "data.answer_submitted === true",
                "data.reported_price_per_sqft === 287",
            ],
            "dom_check": [
                {"selector": "#answer-display", "condition": "contains", "value": "287"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Answer submitted but wrong value", "condition": "data.answer_submitted === true and data.reported_price_per_sqft != 287", "score": -0.5},
            ],
            "failure": {"condition": "data.answer_submitted != true", "score": -1.0},
        },
    },
    {
        "page_id": "dark_checkout",
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
        "success_criteria": {
            "js_eval": [
                "data.order_placed === true",
                "data.warranty_checked === false",
                "data.insurance_checked === false",
                "data.newsletter_checked === false",
                "data.fake_button_clicked === false",
                "data.total === 1309.98",
            ],
            "dom_check": [
                {"selector": "#order-confirmation", "condition": "contains", "value": "Order Confirmed"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Order placed but extras not removed", "condition": "data.order_placed === true and (data.warranty_checked === true or data.insurance_checked === true)", "score": -0.5},
                {"description": "Clicked fake button (subscription trap)", "condition": "data.fake_button_clicked === true", "score": -1.0},
            ],
            "failure": {"condition": "data.order_placed != true", "score": -1.0},
        },
    },
    {
        "page_id": "popup_landing",
        "title": "Pop-up Landing Page",
        "instruction": (
            "Find the screen size specification for the UltraView Pro monitor. "
            "Dismiss any overlays or popups that block the content. Report the "
            "exact screen size value."
        ),
        "difficulty": "medium",
        "primary_primitives": ["attention", "spatial_reasoning"],
        "secondary_primitives": [],
        "time_limit_seconds": 90,
        "success_criteria": {
            "js_eval": [
                "data.answer_submitted === true",
                "String(data.reported_screen_size).indexOf('31.5') !== -1",
            ],
            "dom_check": [
                {"selector": "#answer-display", "condition": "contains", "value": "31.5"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Answer submitted but wrong value", "condition": "data.answer_submitted === true and String(data.reported_screen_size || '').indexOf('31.5') === -1", "score": -0.5},
            ],
            "failure": {"condition": "data.answer_submitted != true", "score": -1.0},
        },
    },
    {
        "page_id": "flaky_form",
        "title": "Flaky Form",
        "instruction": (
            "Submit the bug report form with title 'Memory leak in auth module', "
            "severity 'High', and description 'Auth tokens not cleared on logout'. "
            "The form may fail \u2014 persist until successful. Use the Save Draft "
            "feature to protect your progress."
        ),
        "difficulty": "hard",
        "primary_primitives": ["error_recovery"],
        "secondary_primitives": ["reflection"],
        "time_limit_seconds": 150,
        "success_criteria": {
            "js_eval": [
                "data.submission_successful === true",
                "data.title === 'Memory leak in auth module'",
                "data.severity === 'High'",
            ],
            "dom_check": [
                {"selector": "#status-message", "condition": "contains", "value": "successfully"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Submitted but wrong data", "condition": "data.submission_successful === true and (data.title != 'Memory leak in auth module' or data.severity != 'High')", "score": -0.5},
                {"description": "Gave up after errors", "condition": "data.attempt_count > 0 and data.submission_successful != true", "score": -0.5},
            ],
            "failure": {"condition": "data.attempt_count == 0 or data.attempt_count is None", "score": -1.0},
        },
    },
    {
        "page_id": "filter_dashboard",
        "title": "Filter Dashboard",
        "instruction": (
            "Find all Senior Engineers in the San Francisco office with salary "
            "above $150,000, sorted by name ascending. Report the total count "
            "of matching employees."
        ),
        "difficulty": "hard",
        "primary_primitives": ["constraint_satisfaction", "planning"],
        "secondary_primitives": [],
        "time_limit_seconds": 120,
        "success_criteria": {
            "js_eval": [
                "data.reported_count === 4",
            ],
            "dom_check": [
                {"selector": "#count-display", "condition": "equals", "value": "4"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Count reported but wrong", "condition": "data.reported_count !== undefined and data.reported_count !== null and data.reported_count !== 4", "score": -0.5},
            ],
            "failure": {"condition": "data.reported_count === undefined or data.reported_count === null", "score": -1.0},
        },
    },
    {
        "page_id": "scavenger_hunt",
        "title": "Scavenger Hunt",
        "instruction": (
            "Navigate between the three sections of this portal. Find the "
            "project coordinator's name in Section 1, the revised budget "
            "amount referenced in Section 2, and submit both values in the "
            "form in Section 1."
        ),
        "difficulty": "hard",
        "primary_primitives": ["memory", "exploration"],
        "secondary_primitives": ["planning"],
        "time_limit_seconds": 150,
        "success_criteria": {
            "js_eval": [
                "data.submission_complete === true",
                "data.coordinator_name === 'Sarah Chen'",
                "data.revised_budget === 245000",
            ],
            "dom_check": [
                {"selector": "#submission-result", "condition": "contains", "value": "submitted"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Submitted but one value wrong", "condition": "data.submission_complete === true and (data.coordinator_name !== 'Sarah Chen' or data.revised_budget !== 245000)", "score": 0.0},
                {"description": "Explored but didn't submit", "condition": "data.submission_complete !== true and len(data.get('sections_visited', [])) > 1", "score": -0.5},
            ],
            "failure": {"condition": "data.submission_complete != true", "score": -1.0},
        },
    },
    {
        "page_id": "fake_success",
        "title": "Fake Success Settings",
        "instruction": (
            "Change the notification preference to 'Email Only' and the "
            "timezone to 'Pacific (UTC-8)'. Make sure the changes are "
            "actually saved, not just displayed as saved."
        ),
        "difficulty": "medium",
        "primary_primitives": ["verification", "reflection"],
        "secondary_primitives": [],
        "time_limit_seconds": 90,
        "success_criteria": {
            "js_eval": [
                "data.actually_saved === true",
                "data.notification_pref === 'email_only'",
                "data.timezone === 'pacific'",
            ],
            "dom_check": [
                {"selector": "#current-notif-display", "condition": "contains", "value": "Email Only"},
                {"selector": "#current-tz-display", "condition": "contains", "value": "Pacific"},
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Clicked fake save only", "condition": "data.fake_save_clicked === true and data.actually_saved !== true", "score": -0.5},
            ],
            "failure": {"condition": "data.actually_saved != true", "score": -1.0},
        },
    },
    {
        "page_id": "broken_layout",
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
        "success_criteria": {
            "js_eval": [
                "data.submitted === true",
                "data.name === 'Alex Rivera'",
                "data.email === 'alex@example.com'",
                "data.department === 'Engineering'",
                "data.agreed_to_terms === true",
            ],
            "dom_check": [
                {"selector": "#confirmation-message", "condition": "contains", "value": "submitted"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Submitted but wrong fields", "condition": "data.submitted === true and (data.name !== 'Alex Rivera' or data.email !== 'alex@example.com')", "score": -0.5},
            ],
            "failure": {"condition": "data.submitted != true", "score": -1.0},
        },
    },
    {
        "page_id": "session_content",
        "title": "Session-Dependent Portal",
        "instruction": (
            "Complete the orientation: take the skill assessment quiz, "
            "study your assigned module, find the key code in your module, "
            "and enter it in the final assessment form."
        ),
        "difficulty": "hard",
        "primary_primitives": ["planning", "memory"],
        "secondary_primitives": [],
        "time_limit_seconds": 180,
        "success_criteria": {
            "js_eval": [
                "data.assessment_submitted === true",
                "data.key_code_correct === true",
            ],
            "dom_check": [
                {"selector": "#assessment-result", "condition": "contains", "value": "Correct"}
            ],
        },
        "scoring": {
            "full_success": {"conditions": "all js_eval pass", "score": 1.0},
            "partial": [
                {"description": "Assessment submitted but wrong key code", "condition": "data.assessment_submitted === true and data.key_code_correct !== true", "score": -0.5},
                {"description": "Completed quiz but didn't submit assessment", "condition": "data.quiz_completed === true and data.assessment_submitted !== true", "score": -0.5},
            ],
            "failure": {"condition": "data.assessment_submitted != true", "score": -1.0},
        },
    },
]

_WAB_PAGES_BY_ID: dict[str, dict] = {p["page_id"]: p for p in WAB_PAGES}


# ============================================================================
# Task Provider
# ============================================================================

class WebAgentBenchTaskProvider:
    """Task provider for WebAgentBench's 10 self-contained tasks."""

    def __init__(
        self,
        difficulty: str = "medium",
        pages_filter: Optional[list[str]] = None,
        shuffle: bool = False,
        seed: Optional[int] = None,
    ):
        self.difficulty = difficulty
        self.pages_filter = pages_filter
        self.shuffle = shuffle
        self.seed = seed

        pages = WAB_PAGES
        if pages_filter:
            pages = [p for p in pages if p["page_id"] in pages_filter]

        self._tasks = [self._page_to_task(p) for p in pages]

        if self.shuffle:
            rng = random.Random(self.seed)
            rng.shuffle(self._tasks)

        self._index = 0

    def _page_to_task(self, page: dict) -> Task:
        page_id = page["page_id"]
        return Task(
            task_id=f"wab_{page_id}",
            instruction=page["instruction"],
            initial_state_template=f"wab_{page_id}",
            difficulty=page.get("difficulty", self.difficulty),
            category=page_id,
            success_criteria=page["success_criteria"],
            time_limit_seconds=page.get("time_limit_seconds"),
            extra={
                "wab_page_id": page_id,
                "primary_primitives": page["primary_primitives"],
                "secondary_primitives": page.get("secondary_primitives", []),
                "scoring": page["scoring"],
            },
        )

    # -- TaskProvider protocol ------------------------------------------------

    @property
    def name(self) -> str:
        return "webagentbench"

    @property
    def total_tasks(self) -> int:
        return len(self._tasks)

    def get_task(self) -> Task:
        if not self._tasks:
            raise StopIteration("No tasks available")
        task = self._tasks[self._index % len(self._tasks)]
        self._index += 1
        return task

    def get_batch(self, n: int) -> list[Task]:
        return [self.get_task() for _ in range(n)]

    def get_metadata(self) -> dict:
        primitives: set[str] = set()
        for t in self._tasks:
            primitives.update(t.extra.get("primary_primitives", []))
            primitives.update(t.extra.get("secondary_primitives", []))
        return {
            "name": self.name,
            "total_tasks": len(self._tasks),
            "page_ids": [t.extra["wab_page_id"] for t in self._tasks],
            "primitives": sorted(primitives),
        }

    def reset(self) -> None:
        self._index = 0
        if self.shuffle:
            rng = random.Random(self.seed)
            rng.shuffle(self._tasks)

    def __iter__(self) -> Iterator[Task]:
        self._index = 0
        return self

    def __next__(self) -> Task:
        if self._index >= len(self._tasks):
            raise StopIteration
        return self.get_task()

    def __len__(self) -> int:
        return len(self._tasks)


# ============================================================================
# State Builder
# ============================================================================

class WebAgentBenchStateBuilder:
    """Loads ``wab_*.json`` templates and enriches ``meta`` for the simulator."""

    def build(self, task: Task) -> dict:
        from ..interfaces.state_builder import TemplateStateBuilder

        builder = TemplateStateBuilder()
        state = builder.build(task)

        # Enrich meta so the simulator is aware of the benchmark context
        state["meta"]["benchmark"] = "webagentbench"
        state["meta"]["wab_page_id"] = task.extra.get("wab_page_id", "")
        state["meta"]["target_primitives"] = (
            task.extra.get("primary_primitives", [])
            + task.extra.get("secondary_primitives", [])
        )
        return state

    def supports_task(self, task: Task) -> bool:
        tmpl = task.initial_state_template or ""
        return tmpl.startswith("wab_")


# ============================================================================
# Evaluation helpers (duplicated from webagentbench/evaluator.py)
# ============================================================================

_SAFE_BUILTINS = {"str": str, "int": int, "float": float, "len": len, "bool": bool}


class _DotDict(dict):
    """Dict subclass supporting attribute access (``data.field`` syntax)."""

    def __getattr__(self, key: str) -> Any:
        try:
            v = self[key]
            return _DotDict(v) if isinstance(v, dict) else v
        except KeyError:
            return None

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return dict.__eq__(self, other)
        return False


def _fuzzy_eq(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.01
    return False


def _js_to_py(expr: str) -> str:
    """Convert simple JS boolean expressions to Python-evaluable form."""
    expr = expr.replace("!==", "!=")
    expr = expr.replace("===", "==")
    expr = expr.replace("true", "True").replace("false", "False")
    expr = expr.replace("null", "None").replace("undefined", "None")
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = expr.replace("String(", "str(").replace(".indexOf(", ".find(")
    # Float == comparisons → _fuzzy_eq
    expr = re.sub(
        r"(\S+)\s*==\s*(-?\d+\.\d+)\b",
        r"_fuzzy_eq(\1, \2)",
        expr,
    )
    return expr


def _eval_js_criteria(data: dict, expressions: list[str]) -> list[dict]:
    """Evaluate ``js_eval`` expressions against the data dict."""
    results = []
    safe_globals = {"__builtins__": _SAFE_BUILTINS, "_fuzzy_eq": _fuzzy_eq}
    for expr in expressions:
        try:
            py_expr = _js_to_py(expr)
            passed = bool(eval(py_expr, safe_globals, {"data": _DotDict(data)}))  # noqa: S307
            results.append({"expression": expr, "passed": passed})
        except Exception as e:
            results.append({"expression": expr, "passed": False, "error": str(e)})
    return results


def _compute_score(
    data: dict,
    js_results: list[dict],
    scoring: dict,
) -> dict:
    """Compute the overall score from criteria results."""
    all_pass = all(r["passed"] for r in js_results) if js_results else False
    total = len(js_results)
    passed_count = sum(1 for r in js_results if r["passed"])

    if all_pass:
        return {
            "score": 1.0,
            "success": True,
            "reasoning": f"All {total} success criteria passed",
        }

    # Partial scoring rules
    for rule in scoring.get("partial", []):
        try:
            condition = _js_to_py(rule.get("condition", "False"))
            if eval(  # noqa: S307
                condition,
                {"__builtins__": _SAFE_BUILTINS, "len": len, "_fuzzy_eq": _fuzzy_eq},
                {"data": _DotDict(data)},
            ):
                return {
                    "score": rule.get("score", -0.5),
                    "success": False,
                    "reasoning": rule.get("description", "Partial completion"),
                }
        except Exception as e:
            logger.warning("Partial scoring rule failed (%s): %s", rule.get("condition"), e)

    failed = [r["expression"] for r in js_results if not r["passed"]]
    return {
        "score": -1.0,
        "success": False,
        "reasoning": f"Failed {len(failed)}/{total} criteria: {'; '.join(failed[:3])}",
    }


# ── Page-specific enrichers ─────────────────────────────────────────────


def _enrich_dark_checkout(data: dict) -> dict:
    traps = []
    if data.get("warranty_checked"):
        traps.append("warranty still checked ($149.99)")
    if data.get("insurance_checked"):
        traps.append("insurance still checked ($79.99)")
    if data.get("newsletter_checked"):
        traps.append("newsletter still checked")
    if data.get("fake_button_clicked"):
        traps.append("clicked fake 'Place Order' button (subscription trap)")
    return {
        "dark_patterns_avoided": len(traps) == 0,
        "traps_fallen_for": traps,
        "final_total": data.get("total"),
        "expected_total": 1309.98,
    }


def _enrich_flaky_form(data: dict) -> dict:
    return {
        "attempts_made": data.get("attempt_count", 0),
        "attempts_needed": 4,
        "draft_saved": data.get("draft_saved", False),
        "draft_restored": data.get("draft_restored", False),
    }


def _enrich_scavenger_hunt(data: dict) -> dict:
    return {
        "sections_visited": data.get("sections_visited", []),
        "coordinator_name_correct": data.get("coordinator_name") == "Sarah Chen",
        "budget_correct": data.get("revised_budget") == 245000,
    }


def _enrich_fake_success(data: dict) -> dict:
    return {
        "fake_save_clicked": data.get("fake_save_clicked", False),
        "real_save_used": data.get("actually_saved", False),
        "sidebar_checked": data.get("sidebar_verified", False),
    }


_PAGE_ENRICHERS = {
    "dark_checkout": _enrich_dark_checkout,
    "flaky_form": _enrich_flaky_form,
    "scavenger_hunt": _enrich_scavenger_hunt,
    "fake_success": _enrich_fake_success,
}


# ============================================================================
# Evaluator
# ============================================================================

class WebAgentBenchEvaluator:
    """
    Programmatic evaluator for WebAgentBench tasks.

    Extracts ``hidden_state.wab_data`` from the final simulator state,
    runs ``_eval_js_criteria`` / ``_compute_score``, and falls back to
    the LLM Judge for ambiguous cases.
    """

    def __init__(
        self,
        fallback_to_llm: bool = True,
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
        hidden = final_state.get("hidden_state", {})
        wab_data = hidden.get("wab_data", {})
        page_id = task.extra.get("wab_page_id", "")
        criteria = task.success_criteria or {}
        scoring = task.extra.get("scoring", {})

        # 1. Run js_eval criteria
        js_results = _eval_js_criteria(wab_data, criteria.get("js_eval", []))

        # 2. Score
        result = _compute_score(wab_data, js_results, scoring)

        # 3. Page-specific enrichment
        enricher = _PAGE_ENRICHERS.get(page_id)
        details = enricher(wab_data) if enricher else {}

        # Build EvalResult
        eval_result = EvalResult(
            score=result["score"],
            success=result["success"],
            reasoning=result["reasoning"],
            extra={
                "criteria_results": js_results,
                "page_id": page_id,
                "details": details,
            },
        )

        # 4. Fallback to LLM for ambiguous scores (neither clear pass nor fail)
        if (
            self.fallback_to_llm
            and not result["success"]
            and result["score"] > -1.0
        ):
            try:
                llm_result = await self._llm_evaluate(
                    task, final_state, history, initial_state
                )
                # Keep programmatic score but augment reasoning
                eval_result.extra["llm_reasoning"] = llm_result.reasoning
            except Exception as e:
                logger.debug("LLM fallback skipped: %s", e)

        return eval_result

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
        return 0  # Runs before LLM-only evaluators


# ============================================================================
# Benchmark Adapter
# ============================================================================

class WebAgentBenchBenchmark(BenchmarkAdapter):
    """Factory that wires task provider, state builder, and evaluator."""

    name = "webagentbench"
    description = "WebAgentBench — 10 self-contained web pages for cognitive primitive evaluation"

    def __init__(
        self,
        difficulty: str = "medium",
        pages_filter: Optional[list[str]] = None,
        shuffle: bool = False,
        seed: Optional[int] = None,
        fallback_to_llm: bool = True,
        config_path: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.difficulty = difficulty
        self.pages_filter = pages_filter
        self.shuffle = shuffle
        self.seed = seed
        self.fallback_to_llm = fallback_to_llm
        self.config_path = config_path

    @property
    def version(self) -> str:
        return "1.0.0"

    def create_task_provider(self) -> TaskProvider:
        return WebAgentBenchTaskProvider(
            difficulty=self.difficulty,
            pages_filter=self.pages_filter,
            shuffle=self.shuffle,
            seed=self.seed,
        )

    def create_state_builder(self) -> StateBuilder:
        return WebAgentBenchStateBuilder()

    def create_evaluator(self) -> Evaluator:
        return WebAgentBenchEvaluator(
            fallback_to_llm=self.fallback_to_llm,
            config_path=self.config_path,
        )

    def create_observation_renderer(self) -> Optional[ObservationRenderer]:
        return None  # Use default LLMOS renderer

    def _get_config_kwargs(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "max_steps": 30,
            "use_llm_simulator": True,
            "extra": {
                "benchmark_source": "webagentbench",
            },
        }
