"""
Main Orchestrator for LLMOS.
Provides CLI interface and episode/curriculum loops.
"""

import argparse
import asyncio
import copy
import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .utils.llm_client import LLMClient
from .utils.rendering import summarize_state
from .core import Simulator  # Unified Simulator from core/__init__.py
from .core.agent import Agent, HumanAgent
from .core.judge import Judge
from .core.proposer import Proposer
from .tools.export_html import export_episode_to_html
from .tools.export_runs_index import export_runs_index

# Import benchmark types (lazy to avoid heavy dependencies)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .benchmarks.base import BenchmarkConfig
    from .interfaces import TaskProvider, StateBuilder, Evaluator, Task

logger = logging.getLogger(__name__)


def _configure_logging(
    level: str = "INFO",
    *,
    third_party_level: str = "WARNING",
    silence_loggers: Optional[list[str]] = None,
) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    noisy_default = [
        "httpx",
        "google_genai",
        "google_genai.models",
    ]
    for name in (silence_loggers or noisy_default):
        logging.getLogger(name).setLevel(getattr(logging, third_party_level.upper(), logging.WARNING))


class Orchestrator:
    """
    Main orchestrator for running episodes and curriculum loops.

    Supports two modes:
    1. Standard mode: Use built-in components (Simulator, Judge, Proposer)
    2. Benchmark mode: Use benchmark-provided interfaces (TaskProvider, Evaluator, etc.)
    """

    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        difficulty: Optional[str] = None,
        strictness: Optional[str] = None,
        action_space: Optional[str] = None,
        # Simulator module parameters
        preset: Optional[str] = None,
        state_output: Optional[str] = None,
        abstraction: Optional[str] = None,
        memory: Optional[str] = None,
        reasoning: Optional[str] = None,
        verification: Optional[str] = None,
        temporal: Optional[str] = None,
        uncertainty: Optional[str] = None,
        grounding: Optional[str] = None,
        adversarial: Optional[str] = None,
        # Simulator model parameters
        sim_model: Optional[str] = None,
        sim_provider: Optional[str] = None,
        # Agent parameters
        agent_model: Optional[str] = None,
        agent_provider: Optional[str] = None,
        benchmark: Optional["BenchmarkConfig"] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config_path: Path to config file.
            difficulty: Simulator difficulty preset ("easy", "medium", "hard", "expert").
            strictness: Simulator strictness level ("lenient", "moderate", "strict").
            action_space: Agent action space preset ("minimal", "full").
            preset: Simulator preset ("classic", "default", "efficient", "thorough").
            state_output: State output mode.
            abstraction: Abstraction level.
            memory: Memory mode.
            reasoning: Reasoning mode.
            verification: Verification mode.
            temporal: Temporal mode.
            uncertainty: Uncertainty mode.
            grounding: Grounding strategy.
            adversarial: Adversarial mode ("none", "subtle", "deceptive", "hostile").
            sim_model: Simulator LLM model name.
            sim_provider: Simulator LLM provider.
            agent_model: Agent model name.
            agent_provider: Agent LLM provider.
            benchmark: Optional BenchmarkConfig for benchmark-specific behavior.
        """
        self.action_space = action_space
        self.agent_model = agent_model
        self.agent_provider = agent_provider
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        self.config_path: Union[str, Path] = config_path

        with open(self.config_path, "r") as f:
            self.config = json.load(f)

        # Create shared LLM client
        self.llm_client = LLMClient(config_path)

        # Store benchmark config
        self.benchmark = benchmark

        # Override difficulty from benchmark if provided
        if benchmark and difficulty is None:
            difficulty = benchmark.difficulty

        # Create simulator with configurable modules
        simulator_preset = preset or "classic"
        self.simulator = Simulator.from_preset(
            simulator_preset,
            llm_client=self.llm_client,
            config_path=str(config_path),
            difficulty=difficulty,
            strictness=strictness,
            state_output=state_output,
            abstraction=abstraction,
            memory=memory,
            reasoning=reasoning,
            verification=verification,
            temporal=temporal,
            uncertainty=uncertainty,
            grounding=grounding,
            adversarial=adversarial,
            llm_model=sim_model,
            llm_provider=sim_provider,
        )
        self.judge = Judge(self.llm_client, config_path)
        self.proposer = Proposer(self.llm_client, config_path)

        # Set up benchmark interfaces if provided
        self._task_provider: Optional["TaskProvider"] = None
        self._state_builder: Optional["StateBuilder"] = None
        self._evaluator: Optional["Evaluator"] = None

        if benchmark:
            self._task_provider = benchmark.get_task_provider()
            self._state_builder = benchmark.get_state_builder()
            self._evaluator = benchmark.get_evaluator(str(config_path))
            logger.info(f"Initialized with benchmark: {benchmark.name}")

        # Runs directory
        self.runs_dir = Path(__file__).parent / self.config.get("logging", {}).get("runs_dir", "runs")
        self.runs_dir.mkdir(exist_ok=True)

        # Performance history for curriculum
        self.performance_history: list[dict] = []

        # Curriculum settings
        self.curriculum_config = self.config.get("simulator", {}).get("curriculum", {})
        self.difficulty_progression = self.curriculum_config.get(
            "progression", ["easy", "medium", "hard", "expert"]
        )

        # Align curriculum index with the simulator's starting difficulty
        starting_preset = self.simulator.get_difficulty().preset
        if starting_preset in self.difficulty_progression:
            self.current_difficulty_idx = self.difficulty_progression.index(starting_preset)
        else:
            self.current_difficulty_idx = 0

    @classmethod
    def from_benchmark(
        cls,
        benchmark_name: str,
        config_path: Optional[Union[str, Path]] = None,
        difficulty: Optional[str] = None,
        strictness: Optional[str] = None,
        action_space: Optional[str] = None,
        # Simulator module parameters
        preset: Optional[str] = None,
        state_output: Optional[str] = None,
        abstraction: Optional[str] = None,
        memory: Optional[str] = None,
        reasoning: Optional[str] = None,
        verification: Optional[str] = None,
        temporal: Optional[str] = None,
        uncertainty: Optional[str] = None,
        grounding: Optional[str] = None,
        adversarial: Optional[str] = None,
        # Simulator model parameters
        sim_model: Optional[str] = None,
        sim_provider: Optional[str] = None,
        # Agent parameters
        agent_model: Optional[str] = None,
        agent_provider: Optional[str] = None,
        **benchmark_kwargs,
    ) -> "Orchestrator":
        """
        Create an Orchestrator configured for a specific benchmark.

        Args:
            benchmark_name: Name of the benchmark ('workarena', 'webarena', etc.)
            config_path: Path to LLMOS config file.
            difficulty: Simulator difficulty preset.
            strictness: Simulator strictness level.
            action_space: Agent action space preset.
            preset: Simulator preset.
            state_output, abstraction, memory, reasoning, verification,
            temporal, uncertainty, grounding: Simulator module parameters.
            sim_model: Simulator LLM model name.
            sim_provider: Simulator LLM provider.
            agent_model: Agent model name.
            agent_provider: Agent LLM provider.
            **benchmark_kwargs: Additional arguments passed to benchmark adapter.

        Returns:
            Configured Orchestrator instance.
        """
        from .benchmarks import get_benchmark
        benchmark_config = get_benchmark(benchmark_name, **benchmark_kwargs)
        return cls(
            config_path=config_path,
            difficulty=difficulty,
            strictness=strictness,
            action_space=action_space,
            preset=preset,
            state_output=state_output,
            abstraction=abstraction,
            memory=memory,
            reasoning=reasoning,
            verification=verification,
            temporal=temporal,
            uncertainty=uncertainty,
            grounding=grounding,
            adversarial=adversarial,
            sim_model=sim_model,
            sim_provider=sim_provider,
            agent_model=agent_model,
            agent_provider=agent_provider,
            benchmark=benchmark_config,
        )

    def run_episode(
        self,
        instruction: dict,
        agent: Optional[Union[Agent, HumanAgent]] = None,
        save: bool = True,
        verbose: bool = True,
        initial_state: Optional[dict] = None,
    ) -> dict:
        """
        Run a single episode.

        Args:
            instruction: Task instruction dict.
            agent: Agent to use. If None, creates new LLM agent.
            save: Whether to save the episode.
            verbose: Whether to print progress.

        Returns:
            Episode result dict with score, success, history.
        """
        if agent is None:
            agent = Agent(
                llm_client=self.llm_client,
                config_path=str(self.config_path),
                action_space=self.action_space,
                model_name=self.agent_model,
                provider=self.agent_provider,
            )

        # Get template and reset
        template_name = instruction.get("initial_state_template", "desktop")
        if initial_state is not None:
            observation = self.simulator.reset(
                initial_state=initial_state,
                instruction=instruction,
            )
        else:
            observation = self.simulator.reset(
                template_name=template_name,
                instruction=instruction,
            )

        # Reset agent
        agent.reset(instruction.get("instruction", ""))

        if verbose:
            settings = self.simulator.get_settings_dict()
            difficulty = self.simulator.get_difficulty()
            print(f"\n{'='*60}")
            print(f"Task: {instruction.get('instruction', 'Unknown')[:60]}...")
            print(f"Template: {template_name}")
            print(f"{'='*60}")
            print(f"Simulator Settings:")
            print(f"  Preset: {settings['preset']}")
            # Skip difficulty/strictness display when adversarial is active
            if settings.get('adversarial') and settings['adversarial'] != 'none':
                print(f"  Adversarial: {settings['adversarial']} (difficulty/strictness disabled)")
            else:
                print(f"  Difficulty: {difficulty.preset} (density={difficulty.information_density}, noise={difficulty.signal_noise_ratio}, determinism={difficulty.determinism})")
                print(f"  Strictness: {settings['strictness']}")
            print(f"  State Output: {settings['state_output']}")
            print(f"  Model: {settings['model']} ({settings['provider']})")
            print(f"Agent Settings:")
            print(f"  Action Space: {self.action_space or 'minimal'}")
            print(f"  Model: {getattr(agent, 'model_name', None) or 'default'} ({getattr(agent, 'provider', None) or 'default'})")
            print(f"{'='*60}\n")

        # Episode loop
        max_steps = self.config.get("simulator", {}).get("max_steps_per_episode", 50)
        done = False
        step = 0

        while not done and step < max_steps:
            # Get action from agent
            action = agent.act(observation)

            if verbose:
                print(f"Step {step + 1}: {action.get('action_type', '?')} ", end="")
                if "bid" in action:
                    print(f"(bid: {action['bid']})", end="")
                if action.get("text"):
                    text_preview = action['text'][:30]
                    print(f" text=\"{text_preview}...\"" if len(action['text']) > 30 else f" text=\"{text_preview}\"", end="")
                if action.get("url"):
                    print(f" url=\"{action['url'][:40]}...\"" if len(action['url']) > 40 else f" url=\"{action['url']}\"", end="")
                print()  # End line
                # Show agent's thought (truncated)
                thought = action.get("thought", "")
                if thought:
                    thought_preview = thought[:80].replace("\n", " ")
                    print(f"  Thought: {thought_preview}{'...' if len(thought) > 80 else ''}")

            # Execute action
            observation, done, info = self.simulator.step(action)

            if verbose and info.get("events"):
                print(f"  Events: {info['events']}")

            step += 1

        # Get final state and evaluate
        final_state = self.simulator.get_state()
        history = self.simulator.get_history()

        # Judge the episode
        judge_result = self.judge.evaluate(
            instruction=instruction,
            final_state=final_state,
            history=history,
        )

        # Build result
        result = {
            "instruction": instruction,
            "score": judge_result.get("score", 0),
            "success": judge_result.get("success", False),
            "steps": step,
            "history": history,
            "judge_result": judge_result,
            "final_state": final_state,
            "category": instruction.get("category", "unknown"),
            "difficulty": instruction.get("difficulty", "unknown"),
            "feedback": judge_result.get("feedback", ""),
            "_agent_settings": {
                "action_space": self.action_space or "minimal",
                "model": getattr(agent, "model_name", None) or "default",
                "provider": getattr(agent, "provider", None) or "default",
            },
        }

        # Save episode
        saved_path = None
        if save:
            saved_path = self._save_episode(result)

        if verbose:
            print(f"\n{'='*60}")
            print(f"Episode Complete!")
            print(f"{'='*60}")
            print(f"Steps: {step}")
            print(f"Score: {judge_result.get('score', 0):.2f}")
            print(f"Success: {judge_result.get('success', False)}")
            if judge_result.get("reasoning"):
                print(f"Reasoning: {judge_result.get('reasoning', '')[:100]}...")
            if saved_path:
                print(f"{'='*60}")
                print(f"Saved to: {saved_path}")
                print(f"HTML:     {saved_path.replace('.json', '.html')}")
            print(f"{'='*60}\n")

        return result

    def run_curriculum(
        self,
        num_episodes: int = 10,
        agent: Optional[Union[Agent, HumanAgent]] = None,
        initial_tasks: Optional[list[dict]] = None,
        verbose: bool = True,
        auto_adjust_difficulty: Optional[bool] = None,
    ) -> list[dict]:
        """
        Run a curriculum learning loop.

        Args:
            num_episodes: Number of episodes to run.
            agent: Agent to use.
            initial_tasks: Optional list of initial tasks. If None, proposer generates.
            verbose: Whether to print progress.
            auto_adjust_difficulty: Whether to auto-adjust simulator difficulty.
                                    If None, uses config setting.

        Returns:
            List of episode results.
        """
        if agent is None:
            agent = Agent(
                llm_client=self.llm_client,
                config_path=str(self.config_path),
                action_space=self.action_space,
                model_name=self.agent_model,
                provider=self.agent_provider,
            )

        # Determine if we should auto-adjust difficulty
        if auto_adjust_difficulty is None:
            auto_adjust_difficulty = self.curriculum_config.get("auto_adjust", False)

        results = []

        for episode_num in range(num_episodes):
            if verbose:
                print(f"\n{'#'*60}")
                print(f"# Episode {episode_num + 1}/{num_episodes}")
                print(f"{'#'*60}")

            # Get next task
            if initial_tasks and episode_num < len(initial_tasks):
                instruction = initial_tasks[episode_num]
            else:
                instruction = self.proposer.propose_next_task(self.performance_history)

            # Run episode
            result = self.run_episode(instruction, agent, save=True, verbose=verbose)
            results.append(result)

            # Update performance history
            self.performance_history.append({
                "task_id": instruction.get("task_id"),
                "instruction": instruction.get("instruction"),
                "score": result["score"],
                "success": result["success"],
                "category": result["category"],
                "difficulty": result["difficulty"],
                "simulator_difficulty": self.simulator.get_difficulty().preset,
                "feedback": result["feedback"],
            })

            # Auto-adjust simulator difficulty based on recent performance
            if auto_adjust_difficulty:
                self._maybe_adjust_difficulty(verbose)

        # Print summary
        if verbose:
            self._print_curriculum_summary(results)

        return results

    def _maybe_adjust_difficulty(self, verbose: bool = True):
        """
        Adjust simulator difficulty based on recent performance.

        Uses a sliding window of recent episodes to determine if we should
        increase or decrease difficulty.
        """
        window_size = self.curriculum_config.get("window_size", 5)
        success_threshold = self.curriculum_config.get("success_threshold", 0.8)
        failure_threshold = self.curriculum_config.get("failure_threshold", 0.3)

        if len(self.performance_history) < window_size:
            return

        # Calculate recent success rate
        recent = self.performance_history[-window_size:]
        recent_success_rate = sum(1 for r in recent if r["success"]) / window_size

        old_difficulty = self.simulator.get_difficulty().preset

        # Increase difficulty if doing well
        if recent_success_rate >= success_threshold:
            if self.current_difficulty_idx < len(self.difficulty_progression) - 1:
                self.current_difficulty_idx += 1
                new_difficulty = self.difficulty_progression[self.current_difficulty_idx]
                self.simulator.set_difficulty(preset=new_difficulty)
                if verbose:
                    print(f"\n>>> Difficulty INCREASED: {old_difficulty} -> {new_difficulty} (success rate: {recent_success_rate:.0%})")

        # Decrease difficulty if struggling
        elif recent_success_rate <= failure_threshold:
            if self.current_difficulty_idx > 0:
                self.current_difficulty_idx -= 1
                new_difficulty = self.difficulty_progression[self.current_difficulty_idx]
                self.simulator.set_difficulty(preset=new_difficulty)
                if verbose:
                    print(f"\n>>> Difficulty DECREASED: {old_difficulty} -> {new_difficulty} (success rate: {recent_success_rate:.0%})")

    def run_benchmark(
        self,
        num_episodes: Optional[int] = None,
        agent: Optional[Union[Agent, HumanAgent]] = None,
        verbose: bool = True,
        auto_adjust_difficulty: bool = False,
    ) -> list[dict]:
        """
        Run episodes using the configured benchmark's task provider.

        This is the primary method for running benchmark evaluations.
        Tasks are sourced from the benchmark's TaskProvider.

        Args:
            num_episodes: Number of episodes to run. If None, runs all tasks.
            agent: Agent to use. If None, creates new LLM agent.
            verbose: Whether to print progress.
            auto_adjust_difficulty: Whether to auto-adjust simulator difficulty.

        Returns:
            List of episode results.

        Raises:
            ValueError: If no benchmark is configured.

        Example:
            orchestrator = Orchestrator.from_benchmark("workarena", max_tasks=10)
            results = orchestrator.run_benchmark()
        """
        if self._task_provider is None:
            raise ValueError(
                "No benchmark configured. Use Orchestrator.from_benchmark() or pass "
                "a BenchmarkConfig to __init__."
            )

        if agent is None:
            agent = Agent(
                llm_client=self.llm_client,
                config_path=str(self.config_path),
                action_space=self.action_space,
                model_name=self.agent_model,
                provider=self.agent_provider,
            )

        # Determine number of episodes
        total_tasks = self._task_provider.total_tasks
        if num_episodes is None:
            num_episodes = total_tasks if total_tasks else 10

        if verbose:
            metadata = self._task_provider.get_metadata()
            print(f"\n{'='*60}")
            print(f"Benchmark: {metadata.get('name', 'unknown')}")
            print(f"Version: {metadata.get('version', 'unknown')}")
            print(f"Total tasks available: {total_tasks or 'unknown'}")
            print(f"Episodes to run: {num_episodes}")
            print(f"Categories: {metadata.get('categories', [])}")
            print(f"{'='*60}\n")

        results = []
        self._task_provider.reset()

        for episode_num in range(num_episodes):
            if verbose:
                print(f"\n{'#'*60}")
                print(f"# Episode {episode_num + 1}/{num_episodes}")
                print(f"{'#'*60}")

            # Get next task from benchmark
            try:
                from .interfaces import Task
                task = self._task_provider.get_task()
                task_obj = task if isinstance(task, Task) else Task.from_dict(task)
                instruction = task_obj.to_dict()
            except StopIteration:
                if verbose:
                    print("No more tasks available from benchmark")
                break

            # Run episode
            initial_state = None
            if self._state_builder is not None:
                if hasattr(self._state_builder, "supports_task"):
                    if self._state_builder.supports_task(task_obj):
                        initial_state = self._state_builder.build(task_obj)
                else:
                    initial_state = self._state_builder.build(task_obj)

            result = self.run_episode(
                instruction,
                agent,
                save=self._evaluator is None,
                verbose=verbose,
                initial_state=initial_state,
            )

            if self._evaluator is not None:
                from .utils import run_async
                eval_result = run_async(self._evaluator.evaluate(
                    task_obj,
                    result["final_state"],
                    result["history"],
                ))
                eval_dict = eval_result.to_dict() if hasattr(eval_result, "to_dict") else eval_result
                result["judge_result"] = eval_dict
                result["score"] = eval_dict.get("score", result["score"])
                result["success"] = eval_dict.get("success", result["success"])
                result["feedback"] = eval_dict.get("feedback", result.get("feedback", ""))
                self._save_episode(result)
            results.append(result)

            # Update performance history
            self.performance_history.append({
                "task_id": instruction.get("task_id"),
                "instruction": instruction.get("instruction"),
                "score": result["score"],
                "success": result["success"],
                "category": result["category"],
                "difficulty": result["difficulty"],
                "simulator_difficulty": self.simulator.get_difficulty().preset,
                "feedback": result["feedback"],
                "benchmark": self.benchmark.name if self.benchmark else None,
            })

            # Auto-adjust simulator difficulty
            if auto_adjust_difficulty:
                self._maybe_adjust_difficulty(verbose)

        # Print summary
        if verbose:
            self._print_benchmark_summary(results)

        return results

    def run_benchmark_parallel(
        self,
        num_episodes: Optional[int] = None,
        num_workers: int = 4,
        verbose: bool = True,
    ) -> list[dict]:
        """
        Run benchmark episodes in parallel using multiple workers.

        Each worker gets its own Orchestrator instance with separate
        Simulator, Agent, and LLM client to avoid state conflicts.

        Args:
            num_episodes: Number of episodes to run. If None, runs all tasks.
            num_workers: Number of parallel workers (default: 4).
            verbose: Whether to print progress.

        Returns:
            List of episode results.

        Raises:
            ValueError: If no benchmark is configured.

        Example:
            orchestrator = Orchestrator.from_benchmark("workarena", max_tasks=20)
            results = orchestrator.run_benchmark_parallel(num_workers=4)
        """
        if self._task_provider is None:
            raise ValueError(
                "No benchmark configured. Use Orchestrator.from_benchmark() or pass "
                "a BenchmarkConfig to __init__."
            )

        # Collect all tasks first
        total_tasks = self._task_provider.total_tasks
        if num_episodes is None:
            num_episodes = total_tasks if total_tasks else 10

        if verbose:
            metadata = self._task_provider.get_metadata()
            print(f"\n{'='*60}")
            print(f"Benchmark: {metadata.get('name', 'unknown')} (PARALLEL)")
            print(f"Workers: {num_workers}")
            print(f"Total tasks available: {total_tasks or 'unknown'}")
            print(f"Episodes to run: {num_episodes}")
            print(f"{'='*60}\n")

        # Collect tasks into a list
        self._task_provider.reset()
        tasks_to_run = []
        from .interfaces import Task
        for _ in range(num_episodes):
            try:
                task = self._task_provider.get_task()
                task_obj = task if isinstance(task, Task) else Task.from_dict(task)
                tasks_to_run.append(task_obj)
            except StopIteration:
                break

        if not tasks_to_run:
            if verbose:
                print("No tasks available")
            return []

        # Create config dict for workers
        worker_config = {
            "config_path": str(self.config_path),
            "difficulty": self.simulator.get_difficulty().preset,
            "strictness": self.simulator.sim_config.strictness,
            "action_space": self.action_space,
            "preset": getattr(self.simulator, "_preset_name", "classic"),
            "sim_model": self.simulator.sim_config.llm_model,
            "sim_provider": self.simulator.sim_config.llm_provider,
            "agent_model": self.agent_model,
            "agent_provider": self.agent_provider,
            "benchmark_name": self.benchmark.name if self.benchmark else None,
            "runs_dir": str(self.runs_dir),
        }

        # Thread-safe results collection
        results = []
        results_lock = threading.Lock()
        completed_count = [0]  # Use list for mutable counter in closure

        def run_single_episode(task_obj: "Task") -> dict:
            """Worker function to run a single episode."""
            # Create fresh orchestrator for this worker
            worker_orchestrator = Orchestrator(
                config_path=worker_config["config_path"],
                difficulty=worker_config["difficulty"],
                strictness=worker_config["strictness"],
                action_space=worker_config["action_space"],
                preset=worker_config["preset"],
                sim_model=worker_config["sim_model"],
                sim_provider=worker_config["sim_provider"],
                agent_model=worker_config["agent_model"],
                agent_provider=worker_config["agent_provider"],
            )
            worker_orchestrator.runs_dir = Path(worker_config["runs_dir"])

            # Create agent for this worker
            agent = Agent(
                llm_client=worker_orchestrator.llm_client,
                config_path=worker_config["config_path"],
                action_space=worker_config["action_space"],
                model_name=worker_config["agent_model"],
                provider=worker_config["agent_provider"],
            )

            instruction = task_obj.to_dict()

            # Run episode
            result = worker_orchestrator.run_episode(
                instruction,
                agent,
                save=True,
                verbose=False,  # Suppress per-episode output in parallel
            )

            # Update counter
            with results_lock:
                completed_count[0] += 1
                if verbose:
                    task_id = instruction.get("task_id", "unknown")
                    status = "✓" if result["success"] else "✗"
                    print(f"[{completed_count[0]}/{len(tasks_to_run)}] {task_id}: {status} (score: {result['score']:.2f})")

            return result

        # Run episodes in parallel
        if verbose:
            print(f"Starting {len(tasks_to_run)} episodes with {num_workers} workers...\n")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(run_single_episode, task): task
                for task in tasks_to_run
            }

            # Collect results as they complete
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    with results_lock:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Episode failed for task {task.task_id}: {e}")
                    with results_lock:
                        results.append({
                            "instruction": task.to_dict(),
                            "score": 0.0,
                            "success": False,
                            "steps": 0,
                            "history": [],
                            "judge_result": {"error": str(e)},
                            "final_state": {},
                            "category": task.category or "unknown",
                            "difficulty": task.difficulty or "unknown",
                            "feedback": f"Error: {e}",
                        })

        # Sort results by task order (optional, for consistent output)
        task_id_order = {t.task_id: i for i, t in enumerate(tasks_to_run)}
        results.sort(key=lambda r: task_id_order.get(r["instruction"].get("task_id"), float("inf")))

        # Print summary
        if verbose:
            self._print_benchmark_summary(results)

        return results

    def _print_benchmark_summary(self, results: list[dict]):
        """Print benchmark results summary."""
        print(f"\n{'='*60}")
        print(f"Benchmark Results: {self.benchmark.name if self.benchmark else 'custom'}")
        print(f"{'='*60}")

        total = len(results)
        if total == 0:
            print("No episodes completed")
            return

        successes = sum(1 for r in results if r["success"])
        avg_score = sum(r["score"] for r in results) / total
        avg_steps = sum(r["steps"] for r in results) / total

        print(f"Total Episodes: {total}")
        print(f"Successes: {successes} ({100*successes/total:.1f}%)")
        print(f"Average Score: {avg_score:.2f}")
        print(f"Average Steps: {avg_steps:.1f}")

        # Category breakdown
        categories: dict[str, dict] = {}
        for r in results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "success": 0, "score_sum": 0}
            categories[cat]["total"] += 1
            categories[cat]["success"] += 1 if r["success"] else 0
            categories[cat]["score_sum"] += r["score"]

        if categories:
            print("\nBy Category:")
            for cat, stats in sorted(categories.items()):
                cat_avg = stats["score_sum"] / stats["total"]
                success_pct = 100 * stats["success"] / stats["total"]
                print(f"  {cat}: {stats['success']}/{stats['total']} ({success_pct:.0f}%) success, avg score {cat_avg:.2f}")

        print(f"{'='*60}\n")

    def _save_episode(self, result: dict) -> str:
        """Save an episode to disk and export HTML visualization.

        Returns:
            Path to saved JSON file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_id = result["instruction"].get("task_id", "unknown")
        filename = f"episode_{timestamp}_{task_id}.json"

        path = self.runs_dir / filename

        # Get simulator and agent settings
        sim_settings = self.simulator.get_settings_dict()
        # Use agent settings from result if available (has resolved model/provider)
        agent_settings = result.get("_agent_settings", {
            "action_space": self.action_space or "minimal",
            "model": self.agent_model or "default",
            "provider": self.agent_provider or "default",
        })

        # Don't save full state to reduce file size
        save_result = {
            "instruction": result["instruction"],
            "score": result["score"],
            "success": result["success"],
            "steps": result["steps"],
            "history": result["history"],
            "judge_result": result["judge_result"],
            "final_state_summary": summarize_state(result["final_state"]),
            "settings": {
                "simulator": sim_settings,
                "agent": agent_settings,
                "benchmark": self.benchmark.name if self.benchmark else None,
            },
            "timestamp": timestamp,
        }

        with open(path, "w") as f:
            json.dump(save_result, f, indent=2)

        logger.info(f"Episode saved to {path}")

        # Automatically export HTML visualization
        html_path = export_episode_to_html(str(path))
        logger.info(f"HTML visualization exported to {html_path}")

        index_path = export_runs_index(self.runs_dir)
        logger.info(f"Runs index exported to {index_path}")

        return str(path)

    def _print_curriculum_summary(self, results: list[dict]):
        """Print curriculum summary."""
        print(f"\n{'='*60}")
        print("Curriculum Summary")
        print(f"{'='*60}")

        total = len(results)
        successes = sum(1 for r in results if r["success"])
        avg_score = sum(r["score"] for r in results) / total if total > 0 else 0
        avg_steps = sum(r["steps"] for r in results) / total if total > 0 else 0

        print(f"Total Episodes: {total}")
        print(f"Successes: {successes} ({100*successes/total:.1f}%)")
        print(f"Average Score: {avg_score:.2f}")
        print(f"Average Steps: {avg_steps:.1f}")

        # Category breakdown
        categories = {}
        for r in results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "success": 0, "score_sum": 0}
            categories[cat]["total"] += 1
            categories[cat]["success"] += 1 if r["success"] else 0
            categories[cat]["score_sum"] += r["score"]

        if categories:
            print("\nBy Category:")
            for cat, stats in categories.items():
                cat_avg = stats["score_sum"] / stats["total"]
                print(f"  {cat}: {stats['success']}/{stats['total']} success, avg score {cat_avg:.2f}")

        print(f"{'='*60}\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="LLMOS - LLM-based Operating System Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a single episode with a custom task
  python -m llmos.main run --task "Click the Settings button"

  # Run with specific simulator difficulty
  python -m llmos.main run --task "Click Settings" --difficulty hard

  # Run curriculum learning
  python -m llmos.main curriculum --episodes 10

  # Run curriculum with auto-adjusting difficulty
  python -m llmos.main curriculum --episodes 20 --auto-adjust

  # Run with human agent for debugging
  python -m llmos.main run --task "Navigate to Documents" --human

  # Use a specific template
  python -m llmos.main run --task "Fill out the form" --template form

  # Run a benchmark
  python -m llmos.main benchmark workarena --episodes 10

  # Run benchmark with specific options
  python -m llmos.main benchmark workarena --episodes 5 --max-tasks 20 --shuffle
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Shared parent parser for common arguments (simulator, agent, model settings)
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--difficulty", "-d", type=str, choices=["easy", "medium", "hard", "expert"],
                               help="Simulator difficulty level")
    common_parser.add_argument("--strictness", "-s", type=str, choices=["lenient", "moderate", "strict"],
                               default="strict", help="Simulator strictness level")
    common_parser.add_argument("--action-space", type=str, choices=["minimal", "full"],
                               default="minimal", help="Agent action space")
    common_parser.add_argument("--quiet", "-q", action="store_true", help="Less output")
    # Simulator module arguments
    common_parser.add_argument("--preset", type=str, choices=["classic", "default", "efficient", "thorough"],
                               help="Simulator preset")
    common_parser.add_argument("--state-output", type=str,
                               choices=["full_state", "delta_only", "semantic_description"],
                               help="State output mode")
    common_parser.add_argument("--abstraction", type=str,
                               choices=["full_dom", "semantic_elements", "task_relevant", "viewport_only", "interactive_only"],
                               help="Abstraction level")
    common_parser.add_argument("--memory", type=str,
                               choices=["full_history", "rolling_window", "summarized", "checkpoints"],
                               help="Memory mode")
    common_parser.add_argument("--reasoning", type=str, choices=["direct", "chain"],
                               help="Reasoning mode")
    common_parser.add_argument("--verification", type=str,
                               choices=["none", "schema", "constraint_check", "backward"],
                               help="Verification mode")
    common_parser.add_argument("--temporal", type=str,
                               choices=["instant", "async_aware", "event_driven"],
                               help="Temporal mode")
    common_parser.add_argument("--uncertainty", type=str,
                               choices=["deterministic", "with_confidence", "probabilistic", "admits_uncertainty"],
                               help="Uncertainty mode")
    common_parser.add_argument("--grounding", type=str,
                               choices=["llm_knowledge", "example_grounded", "doc_grounded", "trace_grounded"],
                               help="Grounding strategy")
    common_parser.add_argument("--adversarial", type=str,
                               choices=["none", "subtle", "deceptive", "hostile"],
                               help="Adversarial mode (creates realistic obstacles)")
    # Simulator model arguments
    common_parser.add_argument("--sim-model", type=str,
                               help="Simulator model name (e.g., gpt-4o, gemini-1.5-pro)")
    common_parser.add_argument("--sim-provider", type=str, choices=["openai", "gemini"],
                               help="Simulator LLM provider")
    # Agent model arguments
    common_parser.add_argument("--agent-model", type=str,
                               help="Agent model name (e.g., gpt-4o, gemini-1.5-pro)")
    common_parser.add_argument("--agent-provider", type=str, choices=["openai", "gemini"],
                               help="Agent LLM provider")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a single episode", parents=[common_parser])
    run_parser.add_argument("--task", "-t", type=str, help="Task instruction")
    run_parser.add_argument("--task-file", "-f", type=str, help="JSON file with task instruction")
    run_parser.add_argument("--template", type=str, default="desktop", help="Initial state template")
    run_parser.add_argument("--task-difficulty", type=str, choices=["easy", "medium", "hard", "expert"],
                            help="Task metadata difficulty (defaults to the simulator difficulty)")
    run_parser.add_argument("--human", action="store_true", help="Use human agent")
    run_parser.add_argument("--no-save", action="store_true", help="Don't save episode")

    # Curriculum command
    curr_parser = subparsers.add_parser("curriculum", help="Run curriculum learning", parents=[common_parser])
    curr_parser.add_argument("--episodes", "-n", type=int, default=10, help="Number of episodes")
    curr_parser.add_argument("--tasks-file", type=str, help="JSON file with initial tasks")
    curr_parser.add_argument("--auto-adjust", action="store_true",
                             help="Auto-adjust difficulty based on performance")

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Run a benchmark evaluation", parents=[common_parser])
    bench_parser.add_argument("name", type=str, help="Benchmark name (e.g., workarena, webarena)")
    bench_parser.add_argument("--episodes", "-n", type=int, help="Number of episodes (default: all tasks)")
    bench_parser.add_argument("--max-tasks", type=int, help="Maximum tasks to load from benchmark")
    bench_parser.add_argument("--shuffle", action="store_true", help="Shuffle task order")
    bench_parser.add_argument("--seed", type=int, help="Random seed for shuffling")
    bench_parser.add_argument("--filter", type=str, nargs="+", help="Filter tasks by name patterns")
    bench_parser.add_argument("--auto-adjust", action="store_true",
                              help="Auto-adjust difficulty based on performance")
    bench_parser.add_argument("--parallel", "-p", action="store_true",
                              help="Run episodes in parallel")
    bench_parser.add_argument("--workers", "-w", type=int, default=4,
                              help="Number of parallel workers (default: 4)")
    bench_parser.add_argument("--human", action="store_true", help="Use human agent")

    # Config command
    config_parser = subparsers.add_parser("config", help="Show or edit configuration")
    config_parser.add_argument("--show", action="store_true", help="Show current config")

    # List benchmarks command
    list_parser = subparsers.add_parser("list-benchmarks", help="List available benchmarks")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Get settings from args if available
    difficulty = getattr(args, "difficulty", None)
    strictness = getattr(args, "strictness", "strict")
    action_space = getattr(args, "action_space", "minimal")
    # Simulator module settings
    preset = getattr(args, "preset", None)
    state_output = getattr(args, "state_output", None)
    abstraction = getattr(args, "abstraction", None)
    memory = getattr(args, "memory", None)
    reasoning = getattr(args, "reasoning", None)
    verification = getattr(args, "verification", None)
    temporal = getattr(args, "temporal", None)
    uncertainty = getattr(args, "uncertainty", None)
    grounding = getattr(args, "grounding", None)
    adversarial = getattr(args, "adversarial", None)
    # Simulator model settings
    sim_model = getattr(args, "sim_model", None)
    sim_provider = getattr(args, "sim_provider", None)
    # Agent settings
    agent_model = getattr(args, "agent_model", None)
    agent_provider = getattr(args, "agent_provider", None)

    # Initialize orchestrator
    orchestrator = Orchestrator(
        difficulty=difficulty,
        strictness=strictness,
        action_space=action_space,
        preset=preset,
        state_output=state_output,
        abstraction=abstraction,
        memory=memory,
        reasoning=reasoning,
        verification=verification,
        temporal=temporal,
        uncertainty=uncertainty,
        grounding=grounding,
        adversarial=adversarial,
        sim_model=sim_model,
        sim_provider=sim_provider,
        agent_model=agent_model,
        agent_provider=agent_provider,
    )
    logging_cfg = orchestrator.config.get("logging", {})
    _configure_logging(
        logging_cfg.get("level", "INFO"),
        third_party_level=logging_cfg.get("third_party_level", "WARNING"),
        silence_loggers=logging_cfg.get("silence_loggers"),
    )

    if args.command == "run":
        # Build instruction
        if args.task_file:
            with open(args.task_file, "r") as f:
                instruction = json.load(f)
        elif args.task:
            task_difficulty = args.task_difficulty or orchestrator.simulator.get_difficulty().preset
            instruction = {
                "task_id": f"cli_task_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "instruction": args.task,
                "initial_state_template": args.template,
                "difficulty": task_difficulty,
                "category": "general",
            }
        else:
            print("Error: Must specify --task or --task-file")
            sys.exit(1)

        # Create agent
        agent = HumanAgent() if args.human else None

        # Run
        result = orchestrator.run_episode(
            instruction=instruction,
            agent=agent,
            save=not args.no_save,
            verbose=not args.quiet,
        )

        # Exit with appropriate code
        sys.exit(0 if result["success"] else 1)

    elif args.command == "curriculum":
        # Load initial tasks if provided
        initial_tasks = None
        if args.tasks_file:
            with open(args.tasks_file, "r") as f:
                initial_tasks = json.load(f)

        # Run curriculum
        results = orchestrator.run_curriculum(
            num_episodes=args.episodes,
            initial_tasks=initial_tasks,
            verbose=not args.quiet,
            auto_adjust_difficulty=args.auto_adjust,
        )

        # Exit with success rate
        success_rate = sum(1 for r in results if r["success"]) / len(results) if results else 0
        sys.exit(0 if success_rate >= 0.5 else 1)

    elif args.command == "benchmark":
        # Build benchmark kwargs from args
        benchmark_kwargs = {
            "shuffle": args.shuffle,
        }
        if args.max_tasks:
            benchmark_kwargs["max_tasks"] = args.max_tasks
        if args.seed:
            benchmark_kwargs["seed"] = args.seed
        if args.filter:
            benchmark_kwargs["task_filter"] = args.filter

        # Create orchestrator with benchmark
        try:
            orchestrator = Orchestrator.from_benchmark(
                args.name,
                difficulty=args.difficulty,
                strictness=args.strictness,
                action_space=args.action_space,
                preset=args.preset,
                state_output=args.state_output,
                abstraction=args.abstraction,
                memory=args.memory,
                reasoning=args.reasoning,
                verification=args.verification,
                temporal=args.temporal,
                uncertainty=args.uncertainty,
                grounding=args.grounding,
                adversarial=args.adversarial,
                sim_model=args.sim_model,
                sim_provider=args.sim_provider,
                agent_model=args.agent_model,
                agent_provider=args.agent_provider,
                **benchmark_kwargs,
            )
        except (ValueError, NotImplementedError) as e:
            print(f"Error: {e}")
            sys.exit(1)

        # Configure logging
        logging_cfg = orchestrator.config.get("logging", {})
        _configure_logging(
            logging_cfg.get("level", "INFO"),
            third_party_level=logging_cfg.get("third_party_level", "WARNING"),
            silence_loggers=logging_cfg.get("silence_loggers"),
        )

        # Run benchmark (parallel or sequential)
        if args.parallel:
            if args.human:
                print("Error: --human mode not supported with --parallel")
                sys.exit(1)
            results = orchestrator.run_benchmark_parallel(
                num_episodes=args.episodes,
                num_workers=args.workers,
                verbose=not args.quiet,
            )
        else:
            # Create agent
            agent = HumanAgent() if args.human else None
            results = orchestrator.run_benchmark(
                num_episodes=args.episodes,
                agent=agent,
                verbose=not args.quiet,
                auto_adjust_difficulty=args.auto_adjust,
            )

        # Exit with success rate
        success_rate = sum(1 for r in results if r["success"]) / len(results) if results else 0
        sys.exit(0 if success_rate >= 0.5 else 1)

    elif args.command == "list-benchmarks":
        print("Available benchmarks:")
        print("  workarena    - WorkArena L1 benchmark for ServiceNow web agent tasks")
        print("  webarena     - (not yet implemented)")
        print("  osworld      - (not yet implemented)")
        print("  miniwob      - (not yet implemented)")
        sys.exit(0)

    elif args.command == "config":
        if args.show:
            print(json.dumps(orchestrator.config, indent=2))


if __name__ == "__main__":
    main()
