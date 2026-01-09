#!/usr/bin/env python
"""
Run ablation experiments to study simulator fidelity.

Usage:
    # Run a specific ablation experiment
    python -m llmos.experiments.run_ablation --experiment llm_ablation --num-tasks 50

    # Run factorial experiment
    python -m llmos.experiments.run_ablation --experiment factorial --num-tasks 100

    # Run all ablation experiments
    python -m llmos.experiments.run_ablation --all --num-tasks 50

    # Analyze existing results
    python -m llmos.experiments.run_ablation --analyze results/exp_20240115_123456.json
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .runner import ExperimentRunner, AgentSpec
from .analysis import CorrelationAnalyzer, AblationAnalyzer, ExperimentResult
from .configs import (
    LLM_ABLATION_CONFIGS,
    PROMPT_ABLATION_CONFIGS,
    STATE_ABLATION_CONFIGS,
    HISTORY_ABLATION_CONFIGS,
    DIFFICULTY_ABLATION_CONFIGS,
    ALL_EXPERIMENTS,
    get_factorial_configs,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_dummy_agents() -> list[AgentSpec]:
    """
    Create dummy agents for testing the experiment framework.

    In practice, replace these with real agent implementations.
    """
    # Placeholder - users should replace with actual agent factories
    class DummyAgent:
        def __init__(self, agent_id: str):
            self._agent_id = agent_id

        @property
        def agent_id(self) -> str:
            return self._agent_id

        def reset(self, instruction: str) -> None:
            pass

        def act(self, observation: dict) -> dict:
            # Return a dummy action
            return {"action_type": "finish"}

    return [
        AgentSpec(
            agent_id="dummy_agent_1",
            agent_factory=lambda: DummyAgent("dummy_agent_1"),
            description="Placeholder agent 1",
        ),
        AgentSpec(
            agent_id="dummy_agent_2",
            agent_factory=lambda: DummyAgent("dummy_agent_2"),
            description="Placeholder agent 2",
        ),
    ]


def load_real_agents() -> list[AgentSpec]:
    """
    Load real agent implementations.

    Override this function to add your actual agents.
    """
    agents = []

    # Example: Load a Qwen agent
    try:
        from ..core.agent import Agent

        def create_qwen_agent():
            return Agent(
                config_path=None,  # Uses default config
                model_name="qwen-7b-instruct",
            )

        agents.append(AgentSpec(
            agent_id="qwen_7b",
            agent_factory=create_qwen_agent,
            description="Qwen 7B Instruct",
            metadata={"model_size": "7B"},
        ))
    except Exception as e:
        logger.warning(f"Could not load Qwen agent: {e}")

    # Example: Load GPT-4o agent
    try:
        from ..core.agent import Agent

        def create_gpt4o_agent():
            return Agent(
                config_path=None,
                model_name="gpt-4o",
            )

        agents.append(AgentSpec(
            agent_id="gpt4o",
            agent_factory=create_gpt4o_agent,
            description="GPT-4o Agent",
            metadata={"model_size": "large"},
        ))
    except Exception as e:
        logger.warning(f"Could not load GPT-4o agent: {e}")

    return agents


def run_experiment(
    experiment_name: str,
    num_tasks: int = 50,
    results_dir: str = "./results",
    use_dummy_agents: bool = False,
) -> Optional[ExperimentResult]:
    """Run a single ablation experiment."""
    logger.info(f"Running experiment: {experiment_name}")

    # Get configs for this experiment
    if experiment_name == "factorial":
        configs = get_factorial_configs()
    elif experiment_name in ALL_EXPERIMENTS:
        configs = ALL_EXPERIMENTS[experiment_name]
    else:
        logger.error(f"Unknown experiment: {experiment_name}")
        logger.info(f"Available experiments: {list(ALL_EXPERIMENTS.keys()) + ['factorial']}")
        return None

    logger.info(f"Experiment has {len(configs)} simulator configurations")

    # Create runner
    runner = ExperimentRunner(
        benchmark_name="workarena",
        results_dir=results_dir,
        max_steps=30,
        verbose=True,
    )

    # Register agents
    agents = create_dummy_agents() if use_dummy_agents else load_real_agents()
    if not agents:
        logger.warning("No agents loaded. Using dummy agents.")
        agents = create_dummy_agents()

    runner.register_agents(agents)
    logger.info(f"Registered {len(agents)} agents")

    # Run experiment
    result = runner.run(
        simulator_configs=configs,
        num_tasks=num_tasks,
        experiment_id=f"{experiment_name}_ablation",
        description=f"Ablation study: {experiment_name}",
    )

    return result


def analyze_results(
    result_path: str,
    real_scores_path: Optional[str] = None,
) -> None:
    """Analyze experiment results."""
    logger.info(f"Analyzing results from: {result_path}")

    # Load experiment results
    result = ExperimentResult.load(result_path)

    # Print summary
    print("\n" + "=" * 60)
    print(f"Experiment: {result.experiment_id}")
    print(f"Description: {result.description}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Benchmark: {result.benchmark_name}")
    print("=" * 60)

    # Get score matrix
    agent_ids, sim_ids, scores = result.get_score_matrix()

    print(f"\nAgents ({len(agent_ids)}): {agent_ids}")
    print(f"Simulator configs ({len(sim_ids)}): {sim_ids[:5]}...")

    # Print per-agent scores
    print("\n--- Agent Performance Summary ---")
    for i, agent_id in enumerate(agent_ids):
        agent_scores = [s for s in scores[i] if s == s]  # Filter NaN
        if agent_scores:
            avg_score = sum(agent_scores) / len(agent_scores)
            print(f"{agent_id}: avg_score={avg_score:.3f}")

    # If real scores provided, compute correlations
    if real_scores_path:
        import json
        with open(real_scores_path, "r") as f:
            real_scores = json.load(f)

        analyzer = CorrelationAnalyzer()
        correlations = analyzer.compute_correlations(result, real_scores)

        print("\n--- Correlation Analysis ---")
        for corr in correlations:
            print(f"\n{corr.simulator_config_id}:")
            print(f"  Pearson r: {corr.pearson_r:.3f} (p={corr.pearson_p:.3f})")
            print(f"  Spearman ρ: {corr.spearman_rho:.3f} (p={corr.spearman_p:.3f})")
            print(f"  Kendall τ: {corr.kendall_tau:.3f} (p={corr.kendall_p:.3f})")

        # Ablation analysis
        ablation_analyzer = AblationAnalyzer()
        ablation_results = ablation_analyzer.analyze(result, real_scores)

        print("\n--- Ablation Impact Analysis ---")
        for group_name, metrics in ablation_results.items():
            print(f"\n{group_name}:")
            print(f"  Best config: {metrics.get('best_config')}")
            print(f"  Best correlation: {metrics.get('best_correlation', 0):.3f}")
    else:
        print("\nNote: Provide --real-scores to compute correlation with ground truth")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Run simulator fidelity ablation experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Experiment selection
    exp_group = parser.add_mutually_exclusive_group()
    exp_group.add_argument(
        "--experiment", "-e",
        type=str,
        choices=list(ALL_EXPERIMENTS.keys()) + ["factorial"],
        help="Specific experiment to run",
    )
    exp_group.add_argument(
        "--all",
        action="store_true",
        help="Run all ablation experiments",
    )
    exp_group.add_argument(
        "--analyze",
        type=str,
        metavar="RESULT_FILE",
        help="Analyze existing results file",
    )

    # Configuration
    parser.add_argument(
        "--num-tasks", "-n",
        type=int,
        default=50,
        help="Number of tasks per experiment (default: 50)",
    )
    parser.add_argument(
        "--results-dir", "-o",
        type=str,
        default="./results",
        help="Directory to save results (default: ./results)",
    )
    parser.add_argument(
        "--real-scores",
        type=str,
        help="Path to real benchmark scores JSON for correlation analysis",
    )
    parser.add_argument(
        "--dummy-agents",
        action="store_true",
        help="Use dummy agents (for testing framework)",
    )
    parser.add_argument(
        "--list-experiments",
        action="store_true",
        help="List available experiments and exit",
    )

    args = parser.parse_args()

    # List experiments
    if args.list_experiments:
        print("Available experiments:")
        for name, configs in ALL_EXPERIMENTS.items():
            print(f"  {name}: {len(configs)} configurations")
        print(f"  factorial: {len(get_factorial_configs())} configurations")
        return 0

    # Analyze existing results
    if args.analyze:
        analyze_results(args.analyze, args.real_scores)
        return 0

    # Run experiments
    if args.all:
        experiments = list(ALL_EXPERIMENTS.keys())
    elif args.experiment:
        experiments = [args.experiment]
    else:
        parser.print_help()
        return 1

    results = []
    for exp_name in experiments:
        result = run_experiment(
            experiment_name=exp_name,
            num_tasks=args.num_tasks,
            results_dir=args.results_dir,
            use_dummy_agents=args.dummy_agents,
        )
        if result:
            results.append(result)
            logger.info(f"Completed {exp_name}: {len(result.agent_results)} results")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Completed {len(results)} experiments")
    print(f"Results saved to: {args.results_dir}")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
