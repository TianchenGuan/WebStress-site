#!/usr/bin/env python
"""
Unified Experiment Runner for LLMOS.

Runs experiments with real benchmark tasks (WorkArena) using the
ExperimentalSimulator with modular configurations.

WorkArena Task Levels:
    - l1: Atomic tasks (single-step actions, ~33 tasks)
    - l2: Compositional tasks (multi-step, ~50+ tasks)
    - l3: Long-horizon tasks (complex workflows)
    - all: All available tasks (default)

Usage:
    # List available tasks from WorkArena (all levels)
    python -m llmos.experiments.run_experiment --list-tasks

    # List only L1 atomic tasks
    python -m llmos.experiments.run_experiment --list-tasks --task-level l1

    # Run with L1 tasks only
    python -m llmos.experiments.run_experiment \
        --num-tasks 50 \
        --task-level l1 \
        --preset default

    # Run with L2 compositional tasks
    python -m llmos.experiments.run_experiment \
        --num-tasks 50 \
        --task-level l2 \
        --preset default

    # Run with custom modular configuration
    python -m llmos.experiments.run_experiment \
        --num-tasks 50 \
        --task-level all \
        --state-output delta_only \
        --abstraction semantic \
        --memory rolling \
        --reasoning chain \
        --verification constraint

    # Compare multiple presets on L1 tasks
    python -m llmos.experiments.run_experiment \
        --num-tasks 50 \
        --task-level l1 \
        --compare default,efficient,thorough

    # Quick test to verify setup
    python -m llmos.experiments.run_experiment --quick-test
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Task Loading
# =============================================================================

def load_workarena_tasks(
    max_tasks: Optional[int] = None,
    task_filter: Optional[list[str]] = None,
    task_level: str = "all",  # 'l1', 'l2', 'l3', 'all'
    shuffle: bool = False,
    seed: Optional[int] = 42,
) -> list[dict]:
    """
    Load tasks from WorkArena benchmark.

    Args:
        max_tasks: Maximum number of tasks to load.
        task_filter: Filter tasks by name patterns.
        task_level: Task complexity level ('l1', 'l2', 'l3', 'all').
        shuffle: Whether to shuffle tasks.
        seed: Random seed for shuffling.

    Returns:
        List of task dictionaries.
    """
    try:
        from ..benchmarks.workarena import WorkArenaTaskProvider

        provider = WorkArenaTaskProvider(
            task_filter=task_filter,
            task_level=task_level,
            shuffle=shuffle,
            seed=seed,
            max_tasks=max_tasks,
        )

        tasks = []
        for task in provider:
            tasks.append({
                "task_id": task.task_id,
                "instruction": task.instruction,
                "initial_state_template": task.initial_state_template or "browser",
                "difficulty": task.difficulty,
                "category": task.category,
                "extra": task.extra,
            })

        # Log level distribution
        level_counts = {}
        for t in tasks:
            level = t["extra"].get("workarena_level", "unknown")
            level_counts[level] = level_counts.get(level, 0) + 1
        logger.info(f"Loaded tasks by level: {level_counts}")

        return tasks

    except ImportError as e:
        logger.warning(f"Could not load WorkArena: {e}")
        logger.info("Falling back to sample tasks")
        return create_sample_tasks(max_tasks or 10)


def create_sample_tasks(num_tasks: int = 10) -> list[dict]:
    """Create sample tasks for testing when WorkArena is not available."""
    task_templates = [
        {
            "instruction": "Click the Settings button",
            "initial_state_template": "desktop",
            "category": "navigation",
            "difficulty": "easy",
        },
        {
            "instruction": "Open the Documents folder",
            "initial_state_template": "desktop",
            "category": "navigation",
            "difficulty": "easy",
        },
        {
            "instruction": "Fill in the email field with 'test@example.com'",
            "initial_state_template": "form",
            "category": "form_filling",
            "difficulty": "easy",
        },
        {
            "instruction": "Navigate to the search page",
            "initial_state_template": "browser",
            "category": "navigation",
            "difficulty": "easy",
        },
        {
            "instruction": "Click the Submit button",
            "initial_state_template": "form",
            "category": "interaction",
            "difficulty": "easy",
        },
    ]

    tasks = []
    for i in range(num_tasks):
        template = task_templates[i % len(task_templates)].copy()
        template["task_id"] = f"sample_{i:03d}"
        template["extra"] = {"source": "sample"}
        tasks.append(template)

    return tasks


def list_tasks(max_display: int = 50, task_level: str = "all") -> None:
    """List available tasks."""
    tasks = load_workarena_tasks(max_tasks=max_display, task_level=task_level)

    print(f"\n{'='*70}")
    print(f"Available Tasks - Level: {task_level.upper()} (showing {len(tasks)})")
    print(f"{'='*70}")

    # Group by level first, then by category
    by_level = {}
    for task in tasks:
        level = task.get("extra", {}).get("workarena_level", "unknown")
        if level not in by_level:
            by_level[level] = []
        by_level[level].append(task)

    for level in ["l1", "l2", "l3"]:
        if level not in by_level:
            continue

        level_tasks = by_level[level]
        level_names = {"l1": "Atomic", "l2": "Compositional", "l3": "Long-Horizon"}
        print(f"\n{'='*70}")
        print(f"Level {level.upper()} - {level_names.get(level, 'Unknown')} ({len(level_tasks)} tasks)")
        print(f"{'='*70}")

        # Group by category within level
        by_category = {}
        for task in level_tasks:
            cat = task.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(task)

        for category, cat_tasks in sorted(by_category.items()):
            print(f"\n  {category} ({len(cat_tasks)} tasks):")
            print("  " + "-" * 38)
            for task in cat_tasks[:5]:  # Show fewer per category
                task_id = task["task_id"]
                instruction = task["instruction"]
                if len(instruction) > 55:
                    instruction = instruction[:55] + "..."
                print(f"    {task_id}")
                print(f"      {instruction}")
            if len(cat_tasks) > 5:
                print(f"      ... and {len(cat_tasks) - 5} more")

    print(f"\n{'='*70}")


# =============================================================================
# Results
# =============================================================================

@dataclass
class EpisodeResult:
    """Result from running a single episode."""
    task_id: str
    score: float
    success: bool
    steps: int
    total_time: float
    error: Optional[str] = None
    events: list[str] = field(default_factory=list)
    verification_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "score": self.score,
            "success": self.success,
            "steps": self.steps,
            "total_time": self.total_time,
            "error": self.error,
            "events": self.events,
            "verification_errors": self.verification_errors,
        }


@dataclass
class ExperimentResult:
    """Result from running an experiment with a configuration."""
    config_name: str
    config: dict
    num_tasks: int
    episode_results: list[EpisodeResult]
    total_time: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def mean_score(self) -> float:
        if not self.episode_results:
            return 0.0
        return sum(r.score for r in self.episode_results) / len(self.episode_results)

    @property
    def success_rate(self) -> float:
        if not self.episode_results:
            return 0.0
        return sum(1 for r in self.episode_results if r.success) / len(self.episode_results)

    @property
    def mean_steps(self) -> float:
        if not self.episode_results:
            return 0.0
        return sum(r.steps for r in self.episode_results) / len(self.episode_results)

    @property
    def error_rate(self) -> float:
        if not self.episode_results:
            return 0.0
        return sum(1 for r in self.episode_results if r.error) / len(self.episode_results)

    def to_dict(self) -> dict:
        return {
            "config_name": self.config_name,
            "config": self.config,
            "num_tasks": self.num_tasks,
            "timestamp": self.timestamp,
            "total_time": self.total_time,
            "metrics": {
                "mean_score": self.mean_score,
                "success_rate": self.success_rate,
                "mean_steps": self.mean_steps,
                "error_rate": self.error_rate,
            },
            "episode_results": [r.to_dict() for r in self.episode_results],
        }

    def save(self, path: str) -> None:
        """Save result to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ExperimentResult":
        """Load result from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)

        episode_results = [
            EpisodeResult(**r) for r in data.get("episode_results", [])
        ]

        return cls(
            config_name=data["config_name"],
            config=data["config"],
            num_tasks=data["num_tasks"],
            episode_results=episode_results,
            total_time=data["total_time"],
            timestamp=data.get("timestamp", ""),
        )


# =============================================================================
# Experiment Runner
# =============================================================================

class ExperimentRunner:
    """
    Unified experiment runner for LLMOS simulator experiments.

    Loads tasks from benchmarks and runs them with ExperimentalSimulator
    using different modular configurations.

    Usage:
        runner = ExperimentRunner(config_path="llmos/config.json")

        # Load tasks
        tasks = runner.load_tasks(max_tasks=50)

        # Run with preset
        result = runner.run(tasks, preset="efficient")

        # Run with custom config
        result = runner.run(
            tasks,
            state_output="delta_only",
            abstraction="semantic",
            memory="rolling",
            reasoning="chain",
        )

        # Compare multiple configurations
        results = runner.compare(
            tasks,
            presets=["default", "efficient", "thorough"],
        )
    """

    # Available presets (from unified Simulator)
    PRESETS = ["classic", "default", "efficient", "thorough", "robust", "grounded"]

    def __init__(
        self,
        config_path: Optional[str] = None,
        max_steps: int = 30,
        verbose: bool = True,
    ):
        """
        Initialize experiment runner.

        Args:
            config_path: Path to LLMOS config.json.
            max_steps: Maximum steps per episode.
            verbose: Print progress.
        """
        self.config_path = config_path
        self.max_steps = max_steps
        self.verbose = verbose

    def load_tasks(
        self,
        max_tasks: Optional[int] = None,
        task_filter: Optional[list[str]] = None,
        task_level: str = "all",
        shuffle: bool = False,
        seed: Optional[int] = 42,
        use_sample: bool = False,
    ) -> list[dict]:
        """
        Load tasks for experiments.

        Args:
            max_tasks: Maximum tasks to load.
            task_filter: Filter by name patterns.
            task_level: Task complexity level ('l1', 'l2', 'l3', 'all').
            shuffle: Shuffle task order.
            seed: Random seed.
            use_sample: Force use of sample tasks (for testing).

        Returns:
            List of task dictionaries.
        """
        if use_sample:
            return create_sample_tasks(max_tasks or 10)

        return load_workarena_tasks(
            max_tasks=max_tasks,
            task_filter=task_filter,
            task_level=task_level,
            shuffle=shuffle,
            seed=seed,
        )

    def run(
        self,
        tasks: list[dict],
        preset: Optional[str] = None,
        # Modular configuration options
        state_output: Optional[str] = None,
        abstraction: Optional[str] = None,
        memory: Optional[str] = None,
        memory_window: int = 5,
        reasoning: Optional[str] = None,
        verification: Optional[str] = None,
        domain: Optional[str] = None,
        # Agent
        agent: Optional[Any] = None,
        # Output
        output_dir: Optional[str] = None,
    ) -> ExperimentResult:
        """
        Run experiment with a configuration.

        Args:
            tasks: List of task dicts.
            preset: Preset name ("default", "efficient", "thorough", "robust").
            state_output: "full_state", "delta_only", "semantic_description".
            abstraction: "full_dom", "semantic_elements".
            memory: "full_history", "rolling_window", "summarized", "checkpoints".
            memory_window: Window size for rolling memory.
            reasoning: "direct", "chain".
            verification: "none", "schema", "constraint_check", "backward".
            domain: "web", "desktop", "servicenow".
            agent: Agent to run (None = random agent).
            output_dir: Directory to save results.

        Returns:
            ExperimentResult with all episode results.
        """
        from ..core import Simulator
        from .modules import (
            StateOutputMode,
            AbstractionLevel,
            MemoryMode,
            ReasoningMode,
            VerificationMode,
        )

        # Create simulator
        if preset:
            sim = Simulator.from_preset(
                preset,
                config_path=self.config_path,
            )
            config_name = preset
        else:
            # Map string options to enums
            state_output_mode = self._parse_enum(
                state_output, StateOutputMode, StateOutputMode.DELTA_ONLY
            )
            abstraction_level = self._parse_enum(
                abstraction, AbstractionLevel, AbstractionLevel.FULL_DOM
            )
            memory_mode = self._parse_enum(
                memory, MemoryMode, MemoryMode.ROLLING_WINDOW
            )
            reasoning_mode = self._parse_enum(
                reasoning, ReasoningMode, ReasoningMode.DIRECT
            )
            verification_mode = self._parse_enum(
                verification, VerificationMode, VerificationMode.SCHEMA
            )

            sim = Simulator(
                state_output=state_output_mode,
                abstraction=abstraction_level,
                memory=memory_mode,
                memory_window=memory_window,
                reasoning=reasoning_mode,
                verification=verification_mode,
                domain=domain,
                config_path=self.config_path,
            )

            config_name = f"custom_{state_output_mode.value}_{abstraction_level.value}"

        # Create agent if not provided
        if agent is None:
            agent = self._create_random_agent()

        # Run episodes
        episode_results = []
        start_time = time.time()

        for i, task in enumerate(tasks):
            if self.verbose:
                logger.info(f"Task {i+1}/{len(tasks)}: {task['task_id']}")

            result = self._run_episode(sim, agent, task)
            episode_results.append(result)

            if self.verbose and (i + 1) % 10 == 0:
                self._print_progress(episode_results)

        total_time = time.time() - start_time

        result = ExperimentResult(
            config_name=config_name,
            config=sim.get_config().to_dict(),
            num_tasks=len(tasks),
            episode_results=episode_results,
            total_time=total_time,
        )

        # Save if requested
        if output_dir:
            self._save_result(result, output_dir)

        return result

    def compare(
        self,
        tasks: list[dict],
        presets: Optional[list[str]] = None,
        configs: Optional[list[dict]] = None,
        agent: Optional[Any] = None,
        output_dir: Optional[str] = None,
    ) -> list[ExperimentResult]:
        """
        Compare multiple configurations on the same tasks.

        Args:
            tasks: List of task dicts.
            presets: List of preset names to compare.
            configs: List of custom config dicts (alternative to presets).
            agent: Agent to run.
            output_dir: Directory to save results.

        Returns:
            List of ExperimentResult for each configuration.
        """
        results = []

        if presets:
            for preset in presets:
                logger.info(f"\n{'='*50}")
                logger.info(f"Running preset: {preset}")
                logger.info(f"{'='*50}")

                result = self.run(
                    tasks=tasks,
                    preset=preset,
                    agent=agent,
                    output_dir=output_dir,
                )
                results.append(result)

                logger.info(
                    f"  Completed: score={result.mean_score:.3f}, "
                    f"success={result.success_rate:.1%}"
                )

        if configs:
            for i, config in enumerate(configs):
                config_name = config.pop("name", f"config_{i}")
                logger.info(f"\n{'='*50}")
                logger.info(f"Running config: {config_name}")
                logger.info(f"{'='*50}")

                result = self.run(
                    tasks=tasks,
                    agent=agent,
                    output_dir=output_dir,
                    **config,
                )
                results.append(result)

        return results

    def _parse_enum(self, value: Optional[str], enum_class, default):
        """Parse string to enum value."""
        if value is None:
            return default

        # Try direct match
        value_lower = value.lower().replace("-", "_")
        for member in enum_class:
            if member.value == value_lower or member.name.lower() == value_lower:
                return member

        logger.warning(f"Unknown value '{value}' for {enum_class.__name__}, using default")
        return default

    def _run_episode(
        self,
        sim,
        agent,
        task: dict,
    ) -> EpisodeResult:
        """Run a single episode."""
        start_time = time.time()
        events = []
        verification_errors = []

        try:
            # Reset simulator
            observation = sim.reset(
                template_name=task.get("initial_state_template", "browser"),
                instruction=task,
            )

            # Reset agent
            if hasattr(agent, "reset"):
                agent.reset(task.get("instruction", ""))

            # Run episode
            done = False
            step = 0
            while not done and step < self.max_steps:
                # Get action from agent
                action = agent.act(observation)

                # Step simulator
                observation, done, info = sim.step(action)
                step += 1

                # Collect events and verification info
                events.extend(info.get("events", []))
                exp_info = info.get("experimental", {})
                if not exp_info.get("verification_valid", True):
                    verification_errors.extend(exp_info.get("verification_errors", []))

            final_state = sim.get_state()
            history = sim.get_history()
            from ..core.judge import Judge
            judge = Judge(config_path=self.config_path)
            judge_result = judge.evaluate(
                instruction=task,
                final_state=final_state,
                history=history,
            )
            score = judge_result.get("score", 0.0)
            success = judge_result.get("success", False)

            return EpisodeResult(
                task_id=task["task_id"],
                score=score,
                success=success,
                steps=step,
                total_time=time.time() - start_time,
                events=events,
                verification_errors=verification_errors,
            )

        except Exception as e:
            logger.error(f"Episode error: {e}")
            return EpisodeResult(
                task_id=task["task_id"],
                score=-1.0,
                success=False,
                steps=0,
                total_time=time.time() - start_time,
                error=str(e),
            )

    def _create_random_agent(self):
        """Create a random agent for testing."""
        import random

        class RandomAgent:
            def reset(self, instruction: str):
                pass

            def act(self, observation: dict) -> dict:
                elements = []
                self._find_elements(observation.get("ui", {}), elements)

                if not elements or random.random() < 0.1:
                    return {
                        "thought": "Finishing",
                        "action_type": "finish",
                        "success": False,
                    }

                element = random.choice(elements)
                return {
                    "thought": f"Randomly clicking element {element.get('bid')}",
                    "action_type": "click",
                    "bid": element.get("bid"),
                }

            def _find_elements(self, node, elements):
                if isinstance(node, dict):
                    if "bid" in node:
                        elements.append(node)
                    for child in node.get("children", []):
                        self._find_elements(child, elements)

        return RandomAgent()

    def _print_progress(self, results: list[EpisodeResult]) -> None:
        """Print progress summary."""
        mean_score = sum(r.score for r in results) / len(results)
        success_rate = sum(1 for r in results if r.success) / len(results)
        logger.info(f"  Progress: score={mean_score:.3f}, success={success_rate:.1%}")

    def _save_result(self, result: ExperimentResult, output_dir: str) -> str:
        """Save result to file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"experiment_{result.config_name}_{timestamp}.json"
        filepath = output_path / filename

        result.save(str(filepath))
        logger.info(f"Saved result to: {filepath}")

        return str(filepath)


# =============================================================================
# Result Analysis
# =============================================================================

def print_result(result: ExperimentResult) -> None:
    """Print single result summary."""
    print(f"\n{'='*60}")
    print(f"RESULT: {result.config_name}")
    print(f"{'='*60}")
    print(f"Tasks:        {result.num_tasks}")
    print(f"Mean Score:   {result.mean_score:.3f}")
    print(f"Success Rate: {result.success_rate:.1%}")
    print(f"Mean Steps:   {result.mean_steps:.1f}")
    print(f"Error Rate:   {result.error_rate:.1%}")
    print(f"Total Time:   {result.total_time:.1f}s")
    print(f"{'='*60}")


def print_comparison(results: list[ExperimentResult]) -> None:
    """Print comparison table of results."""
    print("\n" + "=" * 80)
    print("EXPERIMENT COMPARISON")
    print("=" * 80)

    header = f"{'Config':<20} {'Score':<12} {'Success':<12} {'Steps':<12} {'Errors':<12} {'Time':<12}"
    print(f"\n{header}")
    print("-" * 80)

    for r in results:
        print(
            f"{r.config_name:<20} "
            f"{r.mean_score:>10.3f}  "
            f"{r.success_rate:>10.1%}  "
            f"{r.mean_steps:>10.1f}  "
            f"{r.error_rate:>10.1%}  "
            f"{r.total_time:>10.1f}s"
        )

    print("=" * 80)

    if results:
        best = max(results, key=lambda r: r.mean_score)
        print(f"\nBest configuration: {best.config_name} (score={best.mean_score:.3f})")


def analyze_by_category(results: list[ExperimentResult], tasks: list[dict]) -> None:
    """Analyze results by task category."""
    task_categories = {t["task_id"]: t.get("category", "unknown") for t in tasks}

    print("\n" + "=" * 80)
    print("RESULTS BY CATEGORY")
    print("=" * 80)

    for result in results:
        print(f"\n{result.config_name}:")
        print("-" * 40)

        by_category = {}
        for ep in result.episode_results:
            cat = task_categories.get(ep.task_id, "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(ep)

        for cat, episodes in sorted(by_category.items()):
            cat_score = sum(e.score for e in episodes) / len(episodes)
            cat_success = sum(1 for e in episodes if e.success) / len(episodes)
            print(
                f"  {cat:<20}: score={cat_score:>6.3f}, "
                f"success={cat_success:>6.1%} ({len(episodes)} tasks)"
            )


# =============================================================================
# Quick Test
# =============================================================================

def run_quick_test() -> None:
    """Run a quick test to verify the experiment framework works."""
    print("\n" + "=" * 70)
    print("QUICK TEST - Verifying experiment framework")
    print("=" * 70)

    runner = ExperimentRunner(verbose=False)

    # Create sample tasks
    tasks = runner.load_tasks(max_tasks=3, use_sample=True)
    print(f"\nCreated {len(tasks)} sample tasks")

    # Test with default preset
    print("\nRunning with 'default' preset...")
    result = runner.run(tasks, preset="default")

    print(f"\nResults:")
    print(f"  Score: {result.mean_score:.3f}")
    print(f"  Success: {result.success_rate:.1%}")
    print(f"  Config: {result.config}")

    print("\n✅ Quick test completed successfully!")
    print("The experiment framework is working.\n")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run LLMOS simulator experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Task options
    parser.add_argument(
        "--num-tasks", "-n",
        type=int,
        default=10,
        help="Number of tasks to run (default: 10)",
    )
    parser.add_argument(
        "--task-filter",
        type=str,
        help="Filter tasks by name pattern (comma-separated)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--use-sample",
        action="store_true",
        help="Use sample tasks instead of WorkArena",
    )
    parser.add_argument(
        "--task-level",
        type=str,
        choices=["l1", "l2", "l3", "all"],
        default="all",
        help="WorkArena task level: l1 (atomic), l2 (compositional), l3 (long-horizon), all (default: all)",
    )

    # Configuration options
    parser.add_argument(
        "--preset", "-p",
        type=str,
        choices=["classic", "default", "efficient", "thorough", "robust", "grounded"],
        help="Use a preset configuration",
    )
    parser.add_argument(
        "--compare",
        type=str,
        help="Compare presets (comma-separated, e.g., 'default,efficient,thorough')",
    )

    # Modular configuration
    parser.add_argument(
        "--state-output",
        type=str,
        choices=["full_state", "delta_only", "semantic_description"],
        help="State output mode",
    )
    parser.add_argument(
        "--abstraction",
        type=str,
        choices=["full_dom", "semantic_elements", "semantic"],
        help="Abstraction level",
    )
    parser.add_argument(
        "--memory",
        type=str,
        choices=["full_history", "rolling_window", "rolling", "summarized", "checkpoints"],
        help="Memory mode",
    )
    parser.add_argument(
        "--memory-window",
        type=int,
        default=5,
        help="Memory window size for rolling mode (default: 5)",
    )
    parser.add_argument(
        "--reasoning",
        type=str,
        choices=["direct", "chain"],
        help="Reasoning mode",
    )
    parser.add_argument(
        "--verification",
        type=str,
        choices=["none", "schema", "constraint_check", "constraint", "backward"],
        help="Verification mode",
    )
    parser.add_argument(
        "--domain",
        type=str,
        choices=["web", "desktop", "servicenow"],
        help="Domain knowledge to include",
    )

    # Output options
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./results",
        help="Output directory for results (default: ./results)",
    )
    parser.add_argument(
        "--llmos-config",
        type=str,
        help="Path to LLMOS config.json",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="Maximum steps per episode (default: 30)",
    )

    # Utility options
    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List available tasks and exit",
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="Run a quick test to verify framework",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce output verbosity",
    )

    args = parser.parse_args()

    # Utility commands
    if args.list_tasks:
        list_tasks(task_level=args.task_level)
        return 0

    if args.quick_test:
        run_quick_test()
        return 0

    # Parse task filter
    task_filter = None
    if args.task_filter:
        task_filter = [f.strip() for f in args.task_filter.split(",")]

    # Create runner
    runner = ExperimentRunner(
        config_path=args.llmos_config,
        max_steps=args.max_steps,
        verbose=not args.quiet,
    )

    # Load tasks
    logger.info(f"Loading tasks (level={args.task_level})...")
    tasks = runner.load_tasks(
        max_tasks=args.num_tasks,
        task_filter=task_filter,
        task_level=args.task_level,
        shuffle=True,
        seed=args.seed,
        use_sample=args.use_sample,
    )
    logger.info(f"Loaded {len(tasks)} tasks")

    # Run experiments
    if args.compare:
        # Compare multiple presets
        presets = [p.strip() for p in args.compare.split(",")]
        results = runner.compare(
            tasks=tasks,
            presets=presets,
            output_dir=args.output_dir,
        )
        print_comparison(results)
        analyze_by_category(results, tasks)

    elif args.preset:
        # Single preset
        result = runner.run(
            tasks=tasks,
            preset=args.preset,
            output_dir=args.output_dir,
        )
        print_result(result)

    elif any([args.state_output, args.abstraction, args.memory,
              args.reasoning, args.verification]):
        # Custom modular config
        result = runner.run(
            tasks=tasks,
            state_output=args.state_output,
            abstraction=args.abstraction,
            memory=args.memory,
            memory_window=args.memory_window,
            reasoning=args.reasoning,
            verification=args.verification,
            domain=args.domain,
            output_dir=args.output_dir,
        )
        print_result(result)

    else:
        # Default to default preset
        result = runner.run(
            tasks=tasks,
            preset="default",
            output_dir=args.output_dir,
        )
        print_result(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
