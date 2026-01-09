"""
ExperimentRunner: Systematic evaluation across agents and simulator variants.

This module provides tools for:
1. Running agents on simulator variants
2. Running agents on real benchmarks (for ground truth)
3. Collecting and storing results
4. Supporting parallel execution
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence
import traceback

from .simulator_config import SimulatorConfig

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of running a single task."""
    task_id: str
    score: float
    success: bool
    steps: int
    category: Optional[str] = None
    difficulty: Optional[str] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result of running an agent on a set of tasks."""
    agent_id: str
    simulator_config_id: str
    task_results: list[TaskResult]
    total_tasks: int
    successful_tasks: int
    mean_score: float
    std_score: float
    mean_steps: float
    total_time_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_task_results(
        cls,
        agent_id: str,
        simulator_config_id: str,
        task_results: list[TaskResult],
        total_time: float,
        metadata: Optional[dict] = None,
    ) -> "AgentResult":
        """Create from list of task results."""
        import numpy as np

        scores = [r.score for r in task_results]
        steps = [r.steps for r in task_results]

        return cls(
            agent_id=agent_id,
            simulator_config_id=simulator_config_id,
            task_results=task_results,
            total_tasks=len(task_results),
            successful_tasks=sum(1 for r in task_results if r.success),
            mean_score=float(np.mean(scores)) if scores else 0.0,
            std_score=float(np.std(scores)) if scores else 0.0,
            mean_steps=float(np.mean(steps)) if steps else 0.0,
            total_time_seconds=total_time,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "simulator_config_id": self.simulator_config_id,
            "task_results": [
                {
                    "task_id": r.task_id,
                    "score": r.score,
                    "success": r.success,
                    "steps": r.steps,
                    "category": r.category,
                    "difficulty": r.difficulty,
                    "error": r.error,
                    "metadata": r.metadata,
                }
                for r in self.task_results
            ],
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "mean_score": self.mean_score,
            "std_score": self.std_score,
            "mean_steps": self.mean_steps,
            "total_time_seconds": self.total_time_seconds,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ExperimentResult:
    """Result of a complete experiment (multiple agents × multiple simulators)."""
    experiment_id: str
    description: str
    agent_results: list[AgentResult]
    simulator_configs: list[dict]  # Serialized SimulatorConfigs
    benchmark_name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "description": self.description,
            "agent_results": [r.to_dict() for r in self.agent_results],
            "simulator_configs": self.simulator_configs,
            "benchmark_name": self.benchmark_name,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def save(self, path: str) -> None:
        """Save experiment results to JSON."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ExperimentResult":
        """Load experiment results from JSON."""
        with open(path, "r") as f:
            data = json.load(f)

        agent_results = []
        for ar_data in data["agent_results"]:
            task_results = [
                TaskResult(**tr) for tr in ar_data.pop("task_results")
            ]
            agent_results.append(AgentResult(task_results=task_results, **ar_data))

        return cls(
            experiment_id=data["experiment_id"],
            description=data["description"],
            agent_results=agent_results,
            simulator_configs=data["simulator_configs"],
            benchmark_name=data["benchmark_name"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
        )

    def get_score_matrix(self) -> tuple[list[str], list[str], list[list[float]]]:
        """
        Get scores as a matrix for correlation analysis.

        Returns:
            (agent_ids, simulator_ids, scores_matrix)
            where scores_matrix[i][j] is agent i's mean score on simulator j
        """
        agent_ids = sorted(set(r.agent_id for r in self.agent_results))
        simulator_ids = sorted(set(r.simulator_config_id for r in self.agent_results))

        # Build lookup
        score_lookup = {
            (r.agent_id, r.simulator_config_id): r.mean_score
            for r in self.agent_results
        }

        # Build matrix
        scores = []
        for agent_id in agent_ids:
            row = []
            for sim_id in simulator_ids:
                row.append(score_lookup.get((agent_id, sim_id), float('nan')))
            scores.append(row)

        return agent_ids, simulator_ids, scores


class AgentProtocol(Protocol):
    """Protocol for agents that can be evaluated."""

    @property
    def agent_id(self) -> str:
        """Unique identifier for this agent."""
        ...

    def reset(self, instruction: str) -> None:
        """Reset agent for new task."""
        ...

    def act(self, observation: dict) -> dict:
        """Generate action given observation."""
        ...


@dataclass
class AgentSpec:
    """Specification for an agent to evaluate."""
    agent_id: str
    agent_factory: Callable[[], AgentProtocol]
    description: str = ""
    metadata: dict = field(default_factory=dict)


class ExperimentRunner:
    """
    Runs systematic experiments across agents and simulator variants.

    Example:
        runner = ExperimentRunner(
            benchmark_name="workarena",
            results_dir="./results",
        )

        # Register agents
        runner.register_agent(AgentSpec(
            agent_id="qwen_8b",
            agent_factory=lambda: load_qwen_agent(),
        ))

        # Run experiment
        result = runner.run(
            simulator_configs=[config1, config2],
            num_tasks=50,
        )

        # Analyze
        analyzer = CorrelationAnalyzer()
        correlations = analyzer.compute_correlations(result, real_scores)
    """

    def __init__(
        self,
        benchmark_name: str = "workarena",
        results_dir: Optional[str] = None,
        llmos_config_path: Optional[str] = None,
        max_steps: int = 30,
        verbose: bool = True,
    ):
        """
        Initialize experiment runner.

        Args:
            benchmark_name: Name of benchmark to use.
            results_dir: Directory to save results.
            llmos_config_path: Path to LLMOS config.json.
            max_steps: Maximum steps per episode.
            verbose: Whether to print progress.
        """
        self.benchmark_name = benchmark_name
        self.results_dir = Path(results_dir) if results_dir else Path(__file__).parent / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.llmos_config_path = llmos_config_path
        self.max_steps = max_steps
        self.verbose = verbose

        self.agents: dict[str, AgentSpec] = {}

    def register_agent(self, spec: AgentSpec) -> None:
        """Register an agent for evaluation."""
        self.agents[spec.agent_id] = spec
        if self.verbose:
            logger.info(f"Registered agent: {spec.agent_id}")

    def register_agents(self, specs: Sequence[AgentSpec]) -> None:
        """Register multiple agents."""
        for spec in specs:
            self.register_agent(spec)

    def _create_simulator_from_config(
        self,
        config: SimulatorConfig,
    ):
        """Create a Simulator instance from SimulatorConfig."""
        from ..core.simulator import Simulator
        from ..core.difficulty import get_difficulty_config

        # Map config to difficulty settings
        difficulty_config = get_difficulty_config(
            information_density=config.information_density,
            signal_noise_ratio=config.signal_noise_ratio,
            determinism=config.determinism,
        )

        # Create simulator
        # Note: We'd need to extend Simulator to support all config options
        # For now, we use the basic parameters
        simulator = Simulator(
            config_path=self.llmos_config_path,
            difficulty_config=difficulty_config,
        )

        # Store config for reference
        simulator._experiment_config = config

        return simulator

    def _run_single_task(
        self,
        agent: AgentProtocol,
        simulator,
        task: dict,
    ) -> TaskResult:
        """Run a single task and return result."""
        try:
            # Reset simulator
            template = task.get("initial_state_template", "browser")
            observation = simulator.reset(
                template_name=template,
                instruction=task,
            )

            # Reset agent
            agent.reset(task.get("instruction", ""))

            # Run episode
            done = False
            step = 0
            while not done and step < self.max_steps:
                action = agent.act(observation)
                observation, done, info = simulator.step(action)
                step += 1

            # Get final state and evaluate
            final_state = simulator.get_state()
            history = simulator.get_history()

            # Use Judge for evaluation
            from ..core.judge import Judge
            judge = Judge(config_path=self.llmos_config_path)
            judge_result = judge.evaluate(
                instruction=task,
                final_state=final_state,
                history=history,
            )

            return TaskResult(
                task_id=task.get("task_id", "unknown"),
                score=judge_result.get("score", 0.0),
                success=judge_result.get("success", False),
                steps=step,
                category=task.get("category"),
                difficulty=task.get("difficulty"),
                metadata={"judge_reasoning": judge_result.get("reasoning", "")},
            )

        except Exception as e:
            logger.error(f"Error running task {task.get('task_id')}: {e}")
            traceback.print_exc()
            return TaskResult(
                task_id=task.get("task_id", "unknown"),
                score=-1.0,
                success=False,
                steps=0,
                category=task.get("category"),
                difficulty=task.get("difficulty"),
                error=str(e),
            )

    def _run_agent_on_simulator(
        self,
        agent_spec: AgentSpec,
        simulator_config: SimulatorConfig,
        tasks: list[dict],
    ) -> AgentResult:
        """Run an agent on a simulator config across all tasks."""
        if self.verbose:
            logger.info(f"Running {agent_spec.agent_id} on {simulator_config.name}")

        start_time = time.time()

        # Create agent and simulator
        agent = agent_spec.agent_factory()
        simulator = self._create_simulator_from_config(simulator_config)

        # Run all tasks
        task_results = []
        for i, task in enumerate(tasks):
            if self.verbose and (i + 1) % 10 == 0:
                logger.info(f"  Progress: {i + 1}/{len(tasks)}")

            result = self._run_single_task(agent, simulator, task)
            task_results.append(result)

        total_time = time.time() - start_time

        return AgentResult.from_task_results(
            agent_id=agent_spec.agent_id,
            simulator_config_id=simulator_config.short_id,
            task_results=task_results,
            total_time=total_time,
            metadata={
                "simulator_config": simulator_config.to_dict(),
                "agent_metadata": agent_spec.metadata,
            },
        )

    def run(
        self,
        simulator_configs: Sequence[SimulatorConfig],
        num_tasks: Optional[int] = None,
        task_filter: Optional[list[str]] = None,
        experiment_id: Optional[str] = None,
        description: str = "",
    ) -> ExperimentResult:
        """
        Run complete experiment across all agents and simulator configs.

        Args:
            simulator_configs: List of simulator configurations to test.
            num_tasks: Number of tasks to run (None = all).
            task_filter: Filter tasks by name patterns.
            experiment_id: Unique ID for this experiment.
            description: Description of the experiment.

        Returns:
            ExperimentResult with all agent results.
        """
        if not self.agents:
            raise ValueError("No agents registered. Call register_agent() first.")

        # Generate experiment ID
        if experiment_id is None:
            experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Load tasks from benchmark
        tasks = self._load_benchmark_tasks(num_tasks, task_filter)

        if self.verbose:
            logger.info(f"Starting experiment: {experiment_id}")
            logger.info(f"  Agents: {len(self.agents)}")
            logger.info(f"  Simulator configs: {len(simulator_configs)}")
            logger.info(f"  Tasks: {len(tasks)}")

        # Run all combinations
        all_results = []
        total_runs = len(self.agents) * len(simulator_configs)
        run_idx = 0

        for agent_id, agent_spec in self.agents.items():
            for sim_config in simulator_configs:
                run_idx += 1
                if self.verbose:
                    logger.info(f"\nRun {run_idx}/{total_runs}: {agent_id} × {sim_config.name}")

                result = self._run_agent_on_simulator(agent_spec, sim_config, tasks)
                all_results.append(result)

                if self.verbose:
                    logger.info(
                        f"  Result: score={result.mean_score:.3f}, "
                        f"success={result.successful_tasks}/{result.total_tasks}, "
                        f"time={result.total_time_seconds:.1f}s"
                    )

        # Create experiment result
        experiment = ExperimentResult(
            experiment_id=experiment_id,
            description=description,
            agent_results=all_results,
            simulator_configs=[c.to_dict() for c in simulator_configs],
            benchmark_name=self.benchmark_name,
            metadata={
                "num_tasks": len(tasks),
                "max_steps": self.max_steps,
                "agent_ids": list(self.agents.keys()),
            },
        )

        # Save results
        result_path = self.results_dir / f"{experiment_id}.json"
        experiment.save(str(result_path))

        if self.verbose:
            logger.info(f"\nExperiment complete. Results saved to: {result_path}")

        return experiment

    def _load_benchmark_tasks(
        self,
        num_tasks: Optional[int],
        task_filter: Optional[list[str]],
    ) -> list[dict]:
        """Load tasks from the benchmark."""
        from ..benchmarks import get_benchmark

        benchmark = get_benchmark(
            self.benchmark_name,
            max_tasks=num_tasks,
            task_filter=task_filter,
            shuffle=False,  # Consistent ordering for reproducibility
        )

        task_provider = benchmark.get_task_provider()
        tasks = []

        for task in task_provider:
            tasks.append(task.to_dict())
            if num_tasks and len(tasks) >= num_tasks:
                break

        return tasks

    async def run_async(
        self,
        simulator_configs: Sequence[SimulatorConfig],
        num_tasks: Optional[int] = None,
        task_filter: Optional[list[str]] = None,
        experiment_id: Optional[str] = None,
        description: str = "",
        max_concurrent: int = 4,
    ) -> ExperimentResult:
        """
        Run experiment with async parallelization.

        Args:
            ... (same as run())
            max_concurrent: Maximum concurrent agent-simulator runs.
        """
        # For now, delegate to sync version
        # TODO: Implement true async execution
        return self.run(
            simulator_configs=simulator_configs,
            num_tasks=num_tasks,
            task_filter=task_filter,
            experiment_id=experiment_id,
            description=description,
        )


class RealBenchmarkRunner:
    """
    Runner for obtaining ground-truth scores from real benchmarks.

    Used to compare simulator scores against actual benchmark performance.
    """

    def __init__(
        self,
        benchmark_name: str = "workarena",
        headless: bool = True,
        results_dir: Optional[str] = None,
    ):
        """
        Initialize real benchmark runner.

        Args:
            benchmark_name: Name of benchmark.
            headless: Run browser headless.
            results_dir: Directory to save results.
        """
        self.benchmark_name = benchmark_name
        self.headless = headless
        self.results_dir = Path(results_dir) if results_dir else Path(__file__).parent / "results"

    def run(
        self,
        agent_specs: Sequence[AgentSpec],
        num_tasks: Optional[int] = None,
        task_filter: Optional[list[str]] = None,
    ) -> dict[str, AgentResult]:
        """
        Run agents on real benchmark and collect ground-truth scores.

        Returns:
            Dict mapping agent_id to AgentResult.
        """
        # This would use WorkArenaLiveEnvironment for real execution
        # For now, return placeholder
        raise NotImplementedError(
            "Real benchmark execution requires ServiceNow instance. "
            "Use RealBenchmarkRunner only when you have benchmark access."
        )
