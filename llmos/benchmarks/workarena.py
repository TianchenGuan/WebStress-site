"""
WorkArena benchmark adapter for LLMOS.

WorkArena is a benchmark for web agents on ServiceNow platform tasks.
This adapter supports two modes:

1. **LLM Simulator Mode** (default): Use LLMOS's LLM-based simulator with
   WorkArena task descriptions. Good for training without real ServiceNow access.

2. **Real Browser Mode**: Use BrowserGym's real Playwright-based environment.
   Requires ServiceNow instance access. Uses WorkArena's ground-truth validators.

Usage:
    # LLM Simulator mode (no ServiceNow needed)
    from llmos.benchmarks.workarena import WorkArenaBenchmark
    benchmark = WorkArenaBenchmark(use_real_browser=False)
    config = benchmark.get_config()

    # Real browser mode (requires ServiceNow)
    benchmark = WorkArenaBenchmark(use_real_browser=True)
    config = benchmark.get_config()
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

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
# Task Provider
# =============================================================================

class WorkArenaTaskProvider:
    """
    Task provider that loads tasks from WorkArena benchmark.

    Supports filtering by task category and difficulty.
    """

    def __init__(
        self,
        task_filter: Optional[list[str]] = None,
        split: str = "all",  # 'all', 'train', 'test' (WorkArena doesn't have official splits)
        shuffle: bool = True,
        seed: Optional[int] = None,
        max_tasks: Optional[int] = None,
    ):
        """
        Initialize WorkArena task provider.

        Args:
            task_filter: List of task class names to include (None = all).
            split: Dataset split (WorkArena doesn't have official splits, ignored).
            shuffle: Whether to shuffle tasks.
            seed: Random seed.
            max_tasks: Maximum number of tasks to load.
        """
        self.task_filter = task_filter
        self.split = split
        self.shuffle = shuffle
        self.seed = seed
        self.max_tasks = max_tasks

        self._tasks: list[Task] = []
        self._workarena_tasks: list[Any] = []  # Original WorkArena task classes
        self._index = 0
        self._loaded = False

    def _load_tasks(self) -> None:
        """Load tasks from WorkArena."""
        if self._loaded:
            return

        try:
            from browsergym.workarena import ATOMIC_TASKS
        except ImportError:
            raise ImportError(
                "WorkArena not installed. Install with: pip install browsergym-workarena"
            )

        # Get all atomic tasks
        task_classes = list(ATOMIC_TASKS)

        # Apply filter
        if self.task_filter:
            task_classes = [
                t for t in task_classes
                if t.__name__ in self.task_filter or any(f in t.__name__ for f in self.task_filter)
            ]

        # Shuffle
        if self.shuffle:
            if self.seed is not None:
                random.seed(self.seed)
            random.shuffle(task_classes)

        # Limit
        if self.max_tasks:
            task_classes = task_classes[:self.max_tasks]

        # Convert to Task objects
        self._workarena_tasks = task_classes
        self._tasks = [self._convert_task(tc, idx) for idx, tc in enumerate(task_classes)]
        self._loaded = True

    def _convert_task(self, task_class: Any, index: int) -> Task:
        """Convert a WorkArena task class to LLMOS Task."""
        # Extract metadata from task class
        task_name = task_class.__name__

        # Categorize based on class name patterns
        category = self._infer_category(task_name)
        difficulty = self._infer_difficulty(task_name)

        # Generate instruction from task name
        # WorkArena tasks have descriptive names like "FilterHardwareListTask"
        instruction = self._generate_instruction(task_name, task_class)

        return Task(
            task_id=f"workarena_{index:04d}_{task_name}",
            instruction=instruction,
            initial_state_template="browser",  # WorkArena is browser-based
            difficulty=difficulty,
            category=category,
            extra={
                "workarena_task_class": task_name,
                "workarena_task_index": index,
            },
        )

    def _infer_category(self, task_name: str) -> str:
        """Infer task category from name."""
        name_lower = task_name.lower()
        if "filter" in name_lower or "list" in name_lower:
            return "list_management"
        elif "create" in name_lower or "form" in name_lower:
            return "form_filling"
        elif "search" in name_lower or "knowledge" in name_lower:
            return "search"
        elif "order" in name_lower or "catalog" in name_lower:
            return "service_catalog"
        elif "dashboard" in name_lower or "chart" in name_lower:
            return "dashboard"
        elif "navigation" in name_lower:
            return "navigation"
        else:
            return "general"

    def _infer_difficulty(self, task_name: str) -> str:
        """Infer difficulty from task name."""
        name_lower = task_name.lower()
        if "multi" in name_lower or "complex" in name_lower:
            return "hard"
        elif "simple" in name_lower or "basic" in name_lower:
            return "easy"
        else:
            return "medium"

    def _generate_instruction(self, task_name: str, task_class: Any) -> str:
        """Generate natural language instruction from task class."""
        # Try to get docstring
        if task_class.__doc__:
            return task_class.__doc__.strip().split('\n')[0]

        # Convert class name to instruction
        # FilterHardwareListTask -> "Filter the hardware list"
        name = task_name.replace("Task", "").replace("_", " ")
        # CamelCase to spaces
        import re
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        return f"Complete the following task: {name}"

    @property
    def name(self) -> str:
        return "workarena"

    @property
    def total_tasks(self) -> int:
        self._load_tasks()
        return len(self._tasks)

    def get_task(self) -> Task:
        self._load_tasks()
        if not self._tasks:
            raise StopIteration("No tasks available")
        task = self._tasks[self._index % len(self._tasks)]
        self._index += 1
        return task

    def get_batch(self, n: int) -> list[Task]:
        return [self.get_task() for _ in range(n)]

    def get_metadata(self) -> dict:
        self._load_tasks()
        categories = set(t.category for t in self._tasks if t.category)
        difficulties = set(t.difficulty for t in self._tasks)
        return {
            "name": self.name,
            "version": "l1",  # WorkArena L1 (atomic tasks)
            "total_tasks": len(self._tasks),
            "categories": list(categories),
            "difficulties": list(difficulties),
            "task_classes": [t.__name__ for t in self._workarena_tasks],
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

    def get_workarena_task_class(self, task: Task) -> Any:
        """Get the original WorkArena task class for a task."""
        self._load_tasks()
        idx = task.extra.get("workarena_task_index")
        if idx is not None and 0 <= idx < len(self._workarena_tasks):
            return self._workarena_tasks[idx]
        return None


# =============================================================================
# State Builder
# =============================================================================

class WorkArenaStateBuilder:
    """
    State builder for WorkArena tasks.

    Two modes:
    1. Template mode: Use LLMOS browser template (for LLM simulator)
    2. Live mode: Build state from actual BrowserGym environment
    """

    def __init__(
        self,
        use_live_browser: bool = False,
        headless: bool = True,
        servicenow_instance: Any = None,
    ):
        """
        Initialize state builder.

        Args:
            use_live_browser: If True, create state from real browser.
            headless: Run browser in headless mode (for live mode).
            servicenow_instance: Shared ServiceNow instance (for live mode).
        """
        self.use_live_browser = use_live_browser
        self.headless = headless
        self.servicenow_instance = servicenow_instance
        self._env = None

    def build(self, task: Task) -> dict:
        """Build initial state for task."""
        if self.use_live_browser:
            return self._build_from_browser(task)
        else:
            return self._build_from_template(task)

    def _build_from_template(self, task: Task) -> dict:
        """Build state from LLMOS browser template."""
        from ..interfaces.state_builder import TemplateStateBuilder
        builder = TemplateStateBuilder()
        state = builder.build(task)

        # Customize for WorkArena
        state["meta"]["benchmark"] = "workarena"
        state["meta"]["task_class"] = task.extra.get("workarena_task_class", "unknown")

        return state

    def _build_from_browser(self, task: Task) -> dict:
        """Build state from live BrowserGym environment."""
        # This requires a running ServiceNow instance
        # We'll create the environment and get initial observation
        raise NotImplementedError(
            "Live browser mode requires additional setup. "
            "Use WorkArenaLiveEnvironment for real browser interaction."
        )

    def supports_task(self, task: Task) -> bool:
        return task.initial_state_template in ("browser", None)


# =============================================================================
# Evaluator
# =============================================================================

class WorkArenaEvaluator:
    """
    Evaluator using WorkArena's ground-truth validators.

    For LLM simulator mode, falls back to LLM-based evaluation.
    For real browser mode, uses WorkArena's validate() function.
    """

    def __init__(
        self,
        use_ground_truth: bool = True,
        fallback_to_llm: bool = True,
        config_path: Optional[str] = None,
    ):
        """
        Initialize evaluator.

        Args:
            use_ground_truth: Use WorkArena's validate() when available.
            fallback_to_llm: Fall back to LLM evaluation if ground truth unavailable.
            config_path: Config path for LLM-based fallback.
        """
        self.use_ground_truth = use_ground_truth
        self.fallback_to_llm = fallback_to_llm
        self.config_path = config_path
        self._llm_evaluator = None

    async def evaluate(
        self,
        task: Task,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict] = None,
        browser_env: Any = None,
        chat_messages: Optional[list] = None,
        **kwargs: Any,
    ) -> EvalResult:
        """
        Evaluate task completion.

        Args:
            task: The task.
            final_state: Final state.
            history: Action history.
            initial_state: Initial state.
            browser_env: BrowserGym environment (for ground-truth validation).
            chat_messages: Chat messages from episode (for WorkArena validation).
        """
        # Try ground-truth validation if browser environment available
        if self.use_ground_truth and browser_env is not None:
            try:
                result = self._ground_truth_evaluate(
                    task, browser_env, chat_messages or []
                )
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(f"Ground-truth evaluation failed: {e}")

        # Fall back to LLM evaluation
        if self.fallback_to_llm:
            return await self._llm_evaluate(task, final_state, history, initial_state)

        return EvalResult(
            score=0.0,
            success=False,
            reasoning="No evaluator available (ground-truth unavailable, LLM fallback disabled)",
        )

    def _ground_truth_evaluate(
        self,
        task: Task,
        browser_env: Any,
        chat_messages: list,
    ) -> Optional[EvalResult]:
        """Use WorkArena's validate() function."""
        if not hasattr(browser_env, 'task') or not hasattr(browser_env.task, 'validate'):
            return None

        try:
            reward, done, message, info = browser_env.task.validate(
                browser_env.page, chat_messages
            )

            # Convert WorkArena reward (0-1) to LLMOS scale (-1 to 1)
            # WorkArena: 0 = failure, 1 = success
            # LLMOS: -1 = failure, 1 = success
            score = (reward * 2) - 1

            return EvalResult(
                score=score,
                success=reward == 1,
                reasoning=message or f"Ground-truth validation: reward={reward}",
                extra={
                    "workarena_reward": reward,
                    "workarena_info": info,
                    "validation_source": "ground_truth",
                },
            )
        except Exception as e:
            logger.warning(f"WorkArena validate() failed: {e}")
            return None

    async def _llm_evaluate(
        self,
        task: Task,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict],
    ) -> EvalResult:
        """Fall back to LLM-based evaluation."""
        if self._llm_evaluator is None:
            from ..interfaces.evaluator import JudgeEvaluator
            self._llm_evaluator = JudgeEvaluator(config_path=self.config_path)

        return await self._llm_evaluator.evaluate(
            task, final_state, history, initial_state
        )

    def priority(self) -> int:
        return 0  # High priority - run first


# =============================================================================
# Observation Renderer
# =============================================================================

class WorkArenaObservationRenderer:
    """
    Observation renderer for WorkArena.

    Converts BrowserGym observations to LLMOS state format,
    or enhances LLMOS state with WorkArena-specific info.
    """

    def __init__(self, include_axtree: bool = True, include_html: bool = False):
        """
        Initialize renderer.

        Args:
            include_axtree: Include accessibility tree in observation.
            include_html: Include raw HTML (can be very large).
        """
        self.include_axtree = include_axtree
        self.include_html = include_html

    def render(self, state: dict, task: Optional[Task] = None) -> dict:
        """Render state to observation."""
        from ..utils.rendering import render_observation

        # Start with standard LLMOS rendering
        obs = render_observation(state)

        # Add WorkArena-specific context
        if task:
            obs["_workarena"] = {
                "task_class": task.extra.get("workarena_task_class"),
                "category": task.category,
            }

        return obs

    def render_from_browsergym(self, browsergym_obs: dict, task: Optional[Task] = None) -> dict:
        """
        Convert BrowserGym observation to LLMOS state format.

        This is used when running with real browser to create
        LLMOS-compatible states from BrowserGym observations.

        Args:
            browsergym_obs: Observation from BrowserGym environment.
            task: Optional task for context.

        Returns:
            LLMOS-compatible state dict.
        """
        # BrowserGym observation typically contains:
        # - 'axtree_txt': Accessibility tree as text
        # - 'dom_txt': DOM as text (if enabled)
        # - 'screenshot': Screenshot (if enabled)
        # - 'url': Current URL
        # - 'goal': Task goal
        # - etc.

        axtree = browsergym_obs.get("axtree_txt", "")
        url = browsergym_obs.get("url", "")
        goal = browsergym_obs.get("goal", "")

        # Convert to LLMOS state format
        state = {
            "meta": {
                "tick": 0,
                "status": "running",
                "benchmark": "workarena",
            },
            "hidden_state": {},
            "ui": self._axtree_to_ui(axtree),
            "filesystem": {},
            "tabs": [{"url": url, "title": goal, "active": True}],
        }

        if task:
            state["meta"]["task_class"] = task.extra.get("workarena_task_class")

        return state

    def _axtree_to_ui(self, axtree_txt: str) -> dict:
        """
        Convert accessibility tree text to LLMOS UI structure.

        This is a simplified conversion - a full implementation would
        parse the AXTree format properly.
        """
        # Basic structure
        ui = {
            "bid": "root",
            "tag": "browser",
            "children": [],
        }

        # Parse AXTree lines into UI nodes
        # AXTree format: "[bid] role 'name' [properties]"
        lines = axtree_txt.strip().split("\n") if axtree_txt else []

        for idx, line in enumerate(lines[:100]):  # Limit to avoid huge trees
            line = line.strip()
            if not line:
                continue

            # Try to extract bid and content
            # Format varies, do simple extraction
            node = {
                "bid": idx,
                "tag": "element",
                "text": line[:200],  # Truncate long lines
            }

            # Try to identify interactive elements
            line_lower = line.lower()
            if "button" in line_lower:
                node["tag"] = "button"
            elif "link" in line_lower or "href" in line_lower:
                node["tag"] = "a"
            elif "input" in line_lower or "textbox" in line_lower:
                node["tag"] = "input"
            elif "checkbox" in line_lower:
                node["tag"] = "input"
                node["type"] = "checkbox"

            ui["children"].append(node)

        return ui

    def supports_modality(self, modality: str) -> bool:
        return modality in ("dict", "text")


# =============================================================================
# Benchmark Adapter
# =============================================================================

class WorkArenaBenchmark(BenchmarkAdapter):
    """
    WorkArena benchmark adapter.

    Provides integration with the WorkArena benchmark for training
    and evaluating web agents on ServiceNow tasks.
    """

    name = "workarena"
    version = "l1"
    description = "WorkArena L1 benchmark for ServiceNow web agent tasks"

    def __init__(
        self,
        task_filter: Optional[list[str]] = None,
        shuffle: bool = True,
        seed: Optional[int] = None,
        max_tasks: Optional[int] = None,
        use_real_browser: bool = False,
        headless: bool = True,
        config_path: Optional[str] = None,
        **kwargs: Any,
    ):
        """
        Initialize WorkArena benchmark.

        Args:
            task_filter: Filter tasks by name patterns.
            shuffle: Shuffle task order.
            seed: Random seed.
            max_tasks: Maximum tasks to load.
            use_real_browser: Use real Playwright browser vs LLM simulator.
            headless: Run browser headless (if use_real_browser=True).
            config_path: LLMOS config path.
        """
        super().__init__(**kwargs)
        self.task_filter = task_filter
        self.shuffle = shuffle
        self.seed = seed
        self.max_tasks = max_tasks
        self.use_real_browser = use_real_browser
        self.headless = headless
        self.config_path = config_path

    def create_task_provider(self) -> TaskProvider:
        return WorkArenaTaskProvider(
            task_filter=self.task_filter,
            shuffle=self.shuffle,
            seed=self.seed,
            max_tasks=self.max_tasks,
        )

    def create_state_builder(self) -> StateBuilder:
        return WorkArenaStateBuilder(
            use_live_browser=self.use_real_browser,
            headless=self.headless,
        )

    def create_evaluator(self) -> Evaluator:
        return WorkArenaEvaluator(
            use_ground_truth=self.use_real_browser,
            fallback_to_llm=True,
            config_path=self.config_path,
        )

    def create_observation_renderer(self) -> ObservationRenderer:
        return WorkArenaObservationRenderer()

    def _get_config_kwargs(self) -> dict:
        return {
            "difficulty": "medium",
            "max_steps": 30,  # WorkArena tasks typically need fewer steps
            "use_llm_simulator": not self.use_real_browser,
            "extra": {
                "benchmark_source": "browsergym-workarena",
                "task_level": "l1",  # Atomic tasks
            },
        }


# =============================================================================
# Live Environment (for real browser mode)
# =============================================================================

class WorkArenaLiveEnvironment:
    """
    Live WorkArena environment using real browser.

    This wraps BrowserGym's BrowserEnv for integration with LLMOS training.
    Use this when you need ground-truth validation and real browser interaction.
    """

    def __init__(
        self,
        task: Task,
        task_provider: WorkArenaTaskProvider,
        headless: bool = True,
        servicenow_instance: Any = None,
    ):
        """
        Initialize live environment.

        Args:
            task: Task to run.
            task_provider: Provider to get original WorkArena task class.
            headless: Run browser headless.
            servicenow_instance: Shared ServiceNow instance.
        """
        self.task = task
        self.task_provider = task_provider
        self.headless = headless
        self.servicenow_instance = servicenow_instance
        self._env = None
        self._obs = None
        self._info = None
        self._chat_messages: list[dict] = []
        self._renderer = WorkArenaObservationRenderer()

    def reset(self, seed: Optional[int] = None) -> dict:
        """Reset environment and return initial state."""
        from browsergym.core.env import BrowserEnv

        # Get original WorkArena task class
        task_class = self.task_provider.get_workarena_task_class(self.task)
        if task_class is None:
            raise ValueError(f"Could not find WorkArena task class for {self.task.task_id}")

        # Build task kwargs
        task_kwargs = {}
        if self.servicenow_instance:
            task_kwargs["instance"] = self.servicenow_instance

        # Create BrowserGym environment
        self._env = BrowserEnv(
            task_entrypoint=task_class,
            task_kwargs=task_kwargs,
            headless=self.headless,
        )

        # Reset and get observation
        self._obs, self._info = self._env.reset(seed=seed)
        self._chat_messages = []

        # Convert to LLMOS state format
        return self._renderer.render_from_browsergym(self._obs, self.task)

    def step(self, action: dict) -> tuple[dict, float, bool, dict]:
        """
        Execute action and return (state, reward, done, info).

        Note: This translates LLMOS actions to BrowserGym actions.
        """
        if self._env is None:
            raise RuntimeError("Environment not initialized. Call reset() first.")

        # Translate LLMOS action to BrowserGym action
        browsergym_action = self._translate_action(action)

        # Execute in BrowserGym
        self._obs, reward, terminated, truncated, self._info = self._env.step(browsergym_action)

        # Convert observation to LLMOS state
        state = self._renderer.render_from_browsergym(self._obs, self.task)
        state["meta"]["tick"] = state["meta"].get("tick", 0) + 1

        done = terminated or truncated

        return state, reward, done, self._info

    def _translate_action(self, llmos_action: dict) -> str:
        """
        Translate LLMOS action to BrowserGym action string.

        BrowserGym uses string-based actions like:
        - click(bid)
        - fill(bid, "text")
        - press(bid, "key")
        """
        action_type = llmos_action.get("action_type", "noop")
        bid = llmos_action.get("bid", "")

        if action_type == "click":
            button = llmos_action.get("button", "left")
            if button == "right":
                return f"click('{bid}', button='right')"
            return f"click('{bid}')"
        elif action_type == "dblclick":
            return f"dblclick('{bid}')"
        elif action_type == "fill":
            text = llmos_action.get("text", "")
            # Escape quotes in text
            text = text.replace("'", "\\'")
            return f"fill('{bid}', '{text}')"
        elif action_type == "press":
            key = llmos_action.get("key", "Enter")
            return f"press('{bid}', '{key}')"
        elif action_type == "hover":
            return f"hover('{bid}')"
        elif action_type == "scroll":
            direction = llmos_action.get("direction", "down")
            return f"scroll('{bid}', '{direction}')"
        elif action_type == "goto":
            url = llmos_action.get("url", "")
            return f"goto('{url}')"
        elif action_type == "keyboard_type":
            text = llmos_action.get("text", "")
            text = text.replace("'", "\\'")
            return f"type('{text}')"
        elif action_type == "keyboard_press":
            key = llmos_action.get("key", "")
            return f"press('', '{key}')"
        elif action_type == "finish":
            return "send_msg_to_user('Task completed')"
        else:
            return "noop()"

    def validate(self) -> EvalResult:
        """Validate using WorkArena's ground-truth validator."""
        if self._env is None or not hasattr(self._env, 'task'):
            return EvalResult.failure_result("No environment to validate")

        try:
            reward, done, message, info = self._env.task.validate(
                self._env.page, self._chat_messages
            )

            score = (reward * 2) - 1
            return EvalResult(
                score=score,
                success=reward == 1,
                reasoning=message or f"WorkArena validation: reward={reward}",
                extra={"workarena_info": info},
            )
        except Exception as e:
            return EvalResult.failure_result(f"Validation error: {e}")

    def close(self) -> None:
        """Close the environment."""
        if self._env:
            try:
                self._env.close()
            except Exception:
                pass
            self._env = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
