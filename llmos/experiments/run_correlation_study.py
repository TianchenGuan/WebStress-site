#!/usr/bin/env python
"""
Correlation Study Experiment Runner.

Runs sequential ablation experiments to find which simulator design choices
correlate best with real WorkArena L2 benchmark scores.

Usage:
    # Run smoke test to verify setup
    python -m llmos.experiments.run_correlation_study --smoke-test

    # Run a specific phase
    python -m llmos.experiments.run_correlation_study --phase baseline

    # Run all phases sequentially
    python -m llmos.experiments.run_correlation_study --all

    # Run specific config
    python -m llmos.experiments.run_correlation_study --config so_delta --agent gpt-4o-mini

    # Limit number of tasks for testing
    python -m llmos.experiments.run_correlation_study --phase baseline --num-tasks 5
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Result Data Classes
# =============================================================================

@dataclass
class TaskResult:
    """Result from running a single task."""
    task_id: str
    config_id: str
    agent_id: str
    score: float
    success: bool
    steps: int
    instruction: str = ""  # Task instruction
    state_history: list[dict] = field(default_factory=list)
    action_trace: list[dict] = field(default_factory=list)
    simulator_trace: list[dict] = field(default_factory=list)  # Simulator LLM data per step
    events: list[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str) -> None:
        """Save task result to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def load(cls, path: str) -> "TaskResult":
        """Load task result from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(**data)


@dataclass
class PhaseResult:
    """Result from running a phase of experiments."""
    phase_id: str
    config_results: dict[str, dict[str, list[TaskResult]]]  # config_id -> agent_id -> results
    best_config_id: Optional[str] = None
    best_correlation: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "config_results": {
                config_id: {
                    agent_id: [r.to_dict() for r in results]
                    for agent_id, results in agent_results.items()
                }
                for config_id, agent_results in self.config_results.items()
            },
            "best_config_id": self.best_config_id,
            "best_correlation": self.best_correlation,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Task Loading
# =============================================================================

def load_workarena_l2_tasks(
    max_tasks: Optional[int] = None,
    shuffle: bool = False,
    seed: int = 42,
) -> list[dict]:
    """Load WorkArena L2 tasks."""
    try:
        from ..benchmarks.workarena import WorkArenaTaskProvider

        provider = WorkArenaTaskProvider(
            task_level="l2",
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

        logger.info(f"Loaded {len(tasks)} WorkArena L2 tasks")
        return tasks

    except ImportError as e:
        logger.warning(f"Could not load WorkArena: {e}")
        logger.info("Using sample tasks instead")
        return create_sample_tasks(max_tasks or 10)


def create_sample_tasks(num_tasks: int = 10) -> list[dict]:
    """Create sample tasks for testing."""
    templates = [
        {"instruction": "Click the Settings button", "category": "navigation"},
        {"instruction": "Fill in the email field", "category": "form_filling"},
        {"instruction": "Submit the form", "category": "interaction"},
        {"instruction": "Navigate to the dashboard", "category": "navigation"},
        {"instruction": "Select the first item in the list", "category": "selection"},
    ]

    tasks = []
    for i in range(num_tasks):
        template = templates[i % len(templates)].copy()
        template["task_id"] = f"sample_l2_{i:03d}"
        template["initial_state_template"] = "browser"
        template["difficulty"] = "medium"
        template["extra"] = {"source": "sample", "workarena_level": "l2"}
        tasks.append(template)

    return tasks


# =============================================================================
# Experiment Runner
# =============================================================================

class CorrelationStudyRunner:
    """
    Runner for correlation study experiments.

    Runs tasks with different simulator configurations and saves results
    for later correlation analysis.
    """

    def __init__(
        self,
        output_dir: str = "./results/correlation_study",
        config_path: Optional[str] = None,
        max_steps: int = 50,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = config_path
        self.max_steps = max_steps

        # Track best settings from each phase
        self.best_settings: dict[str, Any] = {}

    def run_phase(
        self,
        phase_id: str,
        tasks: list[dict],
        agent_ids: list[str],
        verbose: bool = True,
    ) -> PhaseResult:
        """
        Run all configurations for a phase.

        Args:
            phase_id: Phase identifier.
            tasks: List of task dictionaries.
            agent_ids: List of agent IDs to test.
            verbose: Print progress.

        Returns:
            PhaseResult with all results.
        """
        from .configs.correlation_study import get_configs_for_phase, get_phase

        phase = get_phase(phase_id)
        if verbose:
            logger.info(f"\n{'='*60}")
            logger.info(f"{phase.phase_name}")
            logger.info(f"Hypothesis: {phase.hypothesis}")
            logger.info(f"{'='*60}")

        # Get configs with best settings from previous phases
        configs = get_configs_for_phase(
            phase_id,
            best_state_output=self.best_settings.get("state_output"),
            best_abstraction=self.best_settings.get("abstraction"),
            best_memory=self.best_settings.get("memory"),
            best_memory_window=self.best_settings.get("memory_window", 5),
            best_reasoning=self.best_settings.get("reasoning"),
        )

        config_results = {}

        for config_id, config in configs.items():
            if verbose:
                logger.info(f"\n--- Config: {config_id} ---")

            agent_results = {}
            for agent_id in agent_ids:
                if verbose:
                    logger.info(f"  Agent: {agent_id}")

                results = self.run_config_agent(
                    config_id=config_id,
                    config=config,
                    agent_id=agent_id,
                    tasks=tasks,
                    verbose=verbose,
                )
                agent_results[agent_id] = results

            config_results[config_id] = agent_results

        # Compute correlations and find best
        from .utils.leaderboard import get_workarena_l2_scores
        real_scores = get_workarena_l2_scores(agent_ids=agent_ids)

        best_config, best_corr = self._find_best_config(config_results, real_scores)

        if verbose:
            logger.info(f"\nPhase {phase_id} best config: {best_config} (corr={best_corr:.3f})")

        # Update best settings for next phase
        self._update_best_settings(phase_id, best_config, configs)

        return PhaseResult(
            phase_id=phase_id,
            config_results=config_results,
            best_config_id=best_config,
            best_correlation=best_corr,
        )

    def run_config_agent(
        self,
        config_id: str,
        config,
        agent_id: str,
        tasks: list[dict],
        verbose: bool = True,
    ) -> list[TaskResult]:
        """Run all tasks for a config-agent pair."""
        from ..core import Simulator
        from ..core.agent import Agent
        from ..utils.llm_client import LLMClient

        # Create simulator with config
        sim = Simulator(config=config, config_path=self.config_path)

        # Create agent
        llm_client = LLMClient(self.config_path)
        agent = self._create_agent(agent_id, llm_client)

        results = []
        for i, task in enumerate(tasks):
            if verbose and (i + 1) % 10 == 0:
                logger.info(f"    Task {i+1}/{len(tasks)}")

            result = self._run_task(sim, agent, task, config_id, agent_id)
            results.append(result)

            # Save individual task result
            self._save_task_result(result)

        return results

    def _run_task(
        self,
        sim,
        agent,
        task: dict,
        config_id: str,
        agent_id: str,
    ) -> TaskResult:
        """Run a single task and return result."""
        start_time = time.time()
        state_history = []
        action_trace = []
        simulator_trace = []
        events = []
        instruction = task.get("instruction", "")

        try:
            # Reset simulator
            observation = sim.reset(
                template_name=task.get("initial_state_template", "browser"),
                instruction=task,
            )
            state_history.append({
                "tick": 0,
                "observation": observation,
                "instruction": instruction,
            })

            # Reset agent
            if hasattr(agent, "reset"):
                agent.reset(instruction)

            # Run episode
            done = False
            step = 0
            while not done and step < self.max_steps:
                # Get action from agent
                action = agent.act(observation)
                action_trace.append({"step": step, "action": action})

                # Step simulator
                observation, done, info = sim.step(action)
                step += 1

                # Get simulator LLM data from simulator history
                sim_history_entry = sim.history[-1] if hasattr(sim, 'history') and sim.history else {}
                simulator_llm_data = sim_history_entry.get("simulator_llm_data", {})
                simulator_trace.append({
                    "step": step,
                    "thought": sim_history_entry.get("thought", ""),
                    "state_ops": sim_history_entry.get("state_ops", []),
                    "llm_data": simulator_llm_data,
                })

                state_history.append({
                    "tick": step,
                    "observation": observation,
                    "info": info,
                })
                events.extend(info.get("events", []))

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

            return TaskResult(
                task_id=task["task_id"],
                config_id=config_id,
                agent_id=agent_id,
                score=score,
                success=success,
                steps=step,
                instruction=instruction,
                state_history=state_history,
                action_trace=action_trace,
                simulator_trace=simulator_trace,
                events=events,
                metadata={
                    "timestamp": datetime.now().isoformat(),
                    "total_time_seconds": time.time() - start_time,
                    "task_category": task.get("category"),
                    "task_difficulty": task.get("difficulty"),
                },
            )

        except Exception as e:
            logger.error(f"Task {task['task_id']} error: {e}")
            return TaskResult(
                task_id=task["task_id"],
                config_id=config_id,
                agent_id=agent_id,
                score=-1.0,
                success=False,
                steps=0,
                instruction=instruction,
                error=str(e),
                metadata={
                    "timestamp": datetime.now().isoformat(),
                    "total_time_seconds": time.time() - start_time,
                },
            )

    def _create_agent(self, agent_id: str, llm_client):
        """Create an agent by ID."""
        from ..core.agent import Agent

        # Map agent IDs to (provider, model_name)
        agent_mapping = {
            "gpt-5-mini": ("openai", "gpt-5-mini"),
            "gpt-4o-mini": ("openai", "gpt-4o-mini"),
            "gpt-o4-mini": ("openai", "o4-mini"),  # o4-mini doesn't support system messages
        }

        provider, model_name = agent_mapping.get(agent_id, ("openai", agent_id))

        # Create agent with specific provider and model
        return Agent(
            llm_client=llm_client,
            config_path=self.config_path,
            model_name=model_name,
            provider=provider,
        )

    def _save_task_result(self, result: TaskResult) -> str:
        """Save task result to file and generate HTML visualization."""
        result_dir = self.output_dir / result.config_id / result.agent_id
        result_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        filepath = result_dir / f"{result.task_id}.json"
        result.save(str(filepath))

        # Auto-generate HTML visualization and update index
        try:
            from ..tools.visualize_correlation import export_result_to_html, create_index_html
            html_dir = self.output_dir / "html" / result.config_id / result.agent_id
            html_dir.mkdir(parents=True, exist_ok=True)
            html_path = html_dir / f"{result.task_id}.html"
            export_result_to_html(str(filepath), str(html_path))
            # Update index after each result
            create_index_html(str(self.output_dir))
        except Exception as e:
            logger.warning(f"Could not generate HTML for {result.task_id}: {e}")

        return str(filepath)

    def _find_best_config(
        self,
        config_results: dict,
        real_scores: dict,
    ) -> tuple[str, float]:
        """Find config with best correlation to real scores."""
        from scipy.stats import spearmanr

        best_config = None
        best_corr = -2.0

        for config_id, agent_results in config_results.items():
            # Compute mean scores per agent
            sim_scores = {}
            for agent_id, results in agent_results.items():
                if results:
                    sim_scores[agent_id] = sum(r.score for r in results) / len(results)

            # Compute correlation if we have matching agents
            common_agents = set(sim_scores.keys()) & set(real_scores.keys())
            if len(common_agents) >= 2:
                sim_values = [sim_scores[a] for a in common_agents]
                real_values = [real_scores[a] for a in common_agents]

                corr, _ = spearmanr(sim_values, real_values)
                if corr > best_corr:
                    best_corr = corr
                    best_config = config_id

        return best_config or list(config_results.keys())[0], best_corr

    def _update_best_settings(self, phase_id: str, best_config: str, configs: dict):
        """Update best settings based on phase results."""
        if best_config not in configs:
            return

        config = configs[best_config]

        if phase_id == "state_output":
            self.best_settings["state_output"] = config.state_output
        elif phase_id == "abstraction":
            self.best_settings["abstraction"] = config.abstraction
        elif phase_id == "memory":
            self.best_settings["memory"] = config.memory
            self.best_settings["memory_window"] = getattr(config, "memory_window", 5)
        elif phase_id == "reasoning":
            self.best_settings["reasoning"] = config.reasoning

    def run_all_phases(
        self,
        tasks: list[dict],
        agent_ids: list[str],
        verbose: bool = True,
    ) -> list[PhaseResult]:
        """Run all phases sequentially."""
        from .configs.correlation_study import get_all_phase_ids

        results = []
        for phase_id in get_all_phase_ids():
            result = self.run_phase(phase_id, tasks, agent_ids, verbose)
            results.append(result)

            # Save phase result
            phase_path = self.output_dir / f"phase_{phase_id}_result.json"
            with open(phase_path, "w") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)

        return results


# =============================================================================
# Smoke Test
# =============================================================================

def run_smoke_test(output_dir: str = "./results/smoke_test") -> bool:
    """Run a quick smoke test to verify the pipeline works."""
    logger.info("\n" + "=" * 60)
    logger.info("SMOKE TEST - Verifying correlation study pipeline")
    logger.info("=" * 60)

    try:
        # Test 1: Import configs
        logger.info("\n1. Testing config imports...")
        from .configs.correlation_study import (
            BASELINE_CONFIG, STUDY_AGENTS, get_configs_for_phase
        )
        logger.info(f"   Baseline config: {BASELINE_CONFIG.state_output}")
        logger.info(f"   Study agents: {[a.agent_id for a in STUDY_AGENTS]}")
        logger.info("   OK")

        # Test 2: Load leaderboard
        logger.info("\n2. Testing leaderboard parser...")
        from .utils.leaderboard import get_workarena_l2_scores
        scores = get_workarena_l2_scores()
        logger.info(f"   Found {len(scores)} agents with L2 scores")
        for agent_id in ["gpt-5-mini", "gpt-o4-mini", "gpt-4o-mini"]:
            if agent_id in scores:
                logger.info(f"   {agent_id}: {scores[agent_id]}%")
        logger.info("   OK")

        # Test 3: Create simulator
        logger.info("\n3. Testing simulator creation...")
        from ..core import Simulator
        sim = Simulator(config=BASELINE_CONFIG)
        logger.info(f"   Simulator created with config: {sim.get_config().state_output}")
        logger.info("   OK")

        # Test 4: Load tasks
        logger.info("\n4. Testing task loading...")
        tasks = create_sample_tasks(3)
        logger.info(f"   Loaded {len(tasks)} sample tasks")
        logger.info("   OK")

        # Test 5: Run single task (without agent to avoid API calls)
        logger.info("\n5. Testing result saving...")
        result = TaskResult(
            task_id="test_001",
            config_id="baseline",
            agent_id="test_agent",
            score=0.5,
            success=False,
            steps=5,
            state_history=[{"tick": 0}],
            action_trace=[{"step": 0, "action": {"action_type": "click"}}],
        )
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        result_path = output_path / "baseline" / "test_agent" / "test_001.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(result_path))
        logger.info(f"   Saved result to: {result_path}")

        # Verify it can be loaded
        loaded = TaskResult.load(str(result_path))
        assert loaded.task_id == result.task_id
        logger.info("   OK")

        logger.info("\n" + "=" * 60)
        logger.info("SMOKE TEST PASSED")
        logger.info("=" * 60 + "\n")
        return True

    except Exception as e:
        logger.error(f"\nSMOKE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run correlation study experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Phase/config selection
    parser.add_argument(
        "--phase",
        type=str,
        choices=["baseline", "state_output", "abstraction", "memory", "reasoning", "verification"],
        help="Run a specific phase",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Run a specific config ID",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all phases sequentially",
    )

    # Agent selection
    parser.add_argument(
        "--agent",
        type=str,
        help="Run with specific agent only",
    )
    parser.add_argument(
        "--agents",
        type=str,
        default="gpt-5-mini,gpt-o4-mini,gpt-4o-mini",
        help="Comma-separated list of agent IDs (default: all study agents)",
    )

    # Task options
    parser.add_argument(
        "--num-tasks",
        type=int,
        help="Limit number of tasks (for testing)",
    )
    parser.add_argument(
        "--use-sample",
        action="store_true",
        help="Use sample tasks instead of WorkArena",
    )

    # Output options
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./results/correlation_study",
        help="Output directory (default: ./results/correlation_study)",
    )
    parser.add_argument(
        "--llmos-config",
        type=str,
        help="Path to LLMOS config.json",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=50,
        help="Maximum steps per episode (default: 50)",
    )

    # Utility options
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run smoke test to verify setup",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce output verbosity",
    )

    args = parser.parse_args()

    # Run smoke test
    if args.smoke_test:
        success = run_smoke_test(args.output_dir)
        sys.exit(0 if success else 1)

    # Parse agent list
    if args.agent:
        agent_ids = [args.agent]
    else:
        agent_ids = [a.strip() for a in args.agents.split(",")]

    # Load tasks
    if args.use_sample:
        tasks = create_sample_tasks(args.num_tasks or 10)
    else:
        tasks = load_workarena_l2_tasks(max_tasks=args.num_tasks)

    if not tasks:
        logger.error("No tasks loaded")
        sys.exit(1)

    logger.info(f"Loaded {len(tasks)} tasks")
    logger.info(f"Agents: {agent_ids}")

    # Create runner
    runner = CorrelationStudyRunner(
        output_dir=args.output_dir,
        config_path=args.llmos_config,
        max_steps=args.max_steps,
    )

    # Run experiments
    if args.all:
        results = runner.run_all_phases(tasks, agent_ids, verbose=not args.quiet)
        logger.info(f"\nCompleted {len(results)} phases")

    elif args.phase:
        result = runner.run_phase(args.phase, tasks, agent_ids, verbose=not args.quiet)
        logger.info(f"\nPhase {args.phase} completed")
        logger.info(f"Best config: {result.best_config_id}")
        logger.info(f"Best correlation: {result.best_correlation:.3f}")

    else:
        # Default: run baseline phase
        result = runner.run_phase("baseline", tasks, agent_ids, verbose=not args.quiet)
        logger.info(f"\nBaseline completed")

    logger.info(f"\nResults saved to: {args.output_dir}")
    sys.exit(0)


if __name__ == "__main__":
    main()
