"""
Main Orchestrator for LLMOS.
Provides CLI interface and episode/curriculum loops.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .utils.llm_client import LLMClient
from .utils.rendering import summarize_state
from .core.simulator import Simulator
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
        benchmark: Optional["BenchmarkConfig"] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config_path: Path to config file.
            difficulty: Simulator difficulty preset ("easy", "medium", "hard", "expert").
            benchmark: Optional BenchmarkConfig for benchmark-specific behavior.
        """
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

        # Create components with difficulty setting
        self.simulator = Simulator(self.llm_client, config_path, difficulty=difficulty)
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
        **benchmark_kwargs,
    ) -> "Orchestrator":
        """
        Create an Orchestrator configured for a specific benchmark.

        Args:
            benchmark_name: Name of the benchmark ('workarena', 'webarena', etc.)
            config_path: Path to LLMOS config file.
            **benchmark_kwargs: Additional arguments passed to benchmark adapter.

        Returns:
            Configured Orchestrator instance.

        Example:
            orchestrator = Orchestrator.from_benchmark(
                "workarena",
                max_tasks=10,
                shuffle=True,
            )
        """
        from .benchmarks import get_benchmark
        benchmark_config = get_benchmark(benchmark_name, **benchmark_kwargs)
        return cls(config_path=config_path, benchmark=benchmark_config)

    def run_episode(
        self,
        instruction: dict,
        agent: Optional[Union[Agent, HumanAgent]] = None,
        save: bool = True,
        verbose: bool = True,
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
            agent = Agent(self.llm_client, self.config_path)

        # Get template and reset
        template_name = instruction.get("initial_state_template", "desktop")
        observation = self.simulator.reset(
            template_name=template_name,
            instruction=instruction
        )

        # Reset agent
        agent.reset(instruction.get("instruction", ""))

        if verbose:
            difficulty = self.simulator.get_difficulty()
            print(f"\n{'='*60}")
            print(f"Task: {instruction.get('instruction', 'Unknown')[:60]}...")
            print(f"Template: {template_name}")
            print(f"Difficulty: {difficulty.preset} (density={difficulty.information_density}, noise={difficulty.signal_noise_ratio}, determinism={difficulty.determinism})")
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
                    print(f"(bid: {action['bid']})")
                elif "text" in action:
                    print(f"(text: {action['text'][:30]}...)") 
                else:
                    print()

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

        if verbose:
            print(f"\n{'='*60}")
            print(f"Episode Complete!")
            print(f"Steps: {step}")
            print(f"Score: {judge_result.get('score', 0):.2f}")
            print(f"Success: {judge_result.get('success', False)}")
            print(f"Reasoning: {judge_result.get('reasoning', '')[:100]}...")
            print(f"{'='*60}\n")

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
        }

        # Save episode
        if save:
            self._save_episode(result)

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
            agent = Agent(self.llm_client, str(self.config_path))

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
            agent = Agent(self.llm_client, str(self.config_path))

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
                instruction = task.to_dict() if isinstance(task, Task) else task
            except StopIteration:
                if verbose:
                    print("No more tasks available from benchmark")
                break

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
                "benchmark": self.benchmark.name if self.benchmark else None,
            })

            # Auto-adjust simulator difficulty
            if auto_adjust_difficulty:
                self._maybe_adjust_difficulty(verbose)

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

    def _save_episode(self, result: dict):
        """Save an episode to disk and export HTML visualization."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_id = result["instruction"].get("task_id", "unknown")
        filename = f"episode_{timestamp}_{task_id}.json"

        path = self.runs_dir / filename

        # Don't save full state to reduce file size
        save_result = {
            "instruction": result["instruction"],
            "score": result["score"],
            "success": result["success"],
            "steps": result["steps"],
            "history": result["history"],
            "judge_result": result["judge_result"],
            "final_state_summary": summarize_state(result["final_state"]),
        }

        with open(path, "w") as f:
            json.dump(save_result, f, indent=2)

        logger.info(f"Episode saved to {path}")

        # Automatically export HTML visualization
        try:
            html_path = export_episode_to_html(str(path))
            logger.info(f"HTML visualization exported to {html_path}")

            index_path = export_runs_index(self.runs_dir)
            logger.info(f"Runs index exported to {index_path}")
        except Exception as e:
            logger.warning(f"Failed to export HTML visualization: {e}")

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

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a single episode")
    run_parser.add_argument("--task", "-t", type=str, help="Task instruction")
    run_parser.add_argument("--task-file", "-f", type=str, help="JSON file with task instruction")
    run_parser.add_argument("--template", type=str, default="desktop", help="Initial state template")
    run_parser.add_argument("--difficulty", "-d", type=str, choices=["easy", "medium", "hard", "expert"],
                           help="Simulator difficulty level")
    run_parser.add_argument(
        "--task-difficulty",
        type=str,
        choices=["easy", "medium", "hard", "expert"],
        help="Task metadata difficulty (defaults to the simulator difficulty)",
    )
    run_parser.add_argument("--human", action="store_true", help="Use human agent")
    run_parser.add_argument("--no-save", action="store_true", help="Don't save episode")
    run_parser.add_argument("--quiet", "-q", action="store_true", help="Less output")

    # Curriculum command
    curr_parser = subparsers.add_parser("curriculum", help="Run curriculum learning")
    curr_parser.add_argument("--episodes", "-n", type=int, default=10, help="Number of episodes")
    curr_parser.add_argument("--tasks-file", type=str, help="JSON file with initial tasks")
    curr_parser.add_argument("--difficulty", "-d", type=str, choices=["easy", "medium", "hard", "expert"],
                            help="Starting difficulty level")
    curr_parser.add_argument("--auto-adjust", action="store_true",
                            help="Auto-adjust difficulty based on performance")
    curr_parser.add_argument("--quiet", "-q", action="store_true", help="Less output")

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Run a benchmark evaluation")
    bench_parser.add_argument("name", type=str, help="Benchmark name (e.g., workarena, webarena)")
    bench_parser.add_argument("--episodes", "-n", type=int, help="Number of episodes (default: all tasks)")
    bench_parser.add_argument("--max-tasks", type=int, help="Maximum tasks to load from benchmark")
    bench_parser.add_argument("--shuffle", action="store_true", help="Shuffle task order")
    bench_parser.add_argument("--seed", type=int, help="Random seed for shuffling")
    bench_parser.add_argument("--filter", type=str, nargs="+", help="Filter tasks by name patterns")
    bench_parser.add_argument("--difficulty", "-d", type=str, choices=["easy", "medium", "hard", "expert"],
                             help="Simulator difficulty level")
    bench_parser.add_argument("--auto-adjust", action="store_true",
                             help="Auto-adjust difficulty based on performance")
    bench_parser.add_argument("--human", action="store_true", help="Use human agent")
    bench_parser.add_argument("--quiet", "-q", action="store_true", help="Less output")

    # Config command
    config_parser = subparsers.add_parser("config", help="Show or edit configuration")
    config_parser.add_argument("--show", action="store_true", help="Show current config")

    # List benchmarks command
    list_parser = subparsers.add_parser("list-benchmarks", help="List available benchmarks")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Get difficulty from args if available
    difficulty = getattr(args, "difficulty", None)

    # Initialize orchestrator with difficulty
    orchestrator = Orchestrator(difficulty=difficulty)
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

        # Create agent
        agent = HumanAgent() if args.human else None

        # Run benchmark
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
