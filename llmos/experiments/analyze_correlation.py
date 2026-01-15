#!/usr/bin/env python
"""
Correlation Analysis for Simulator Design Study.

Analyzes experiment results to compute correlations between simulated
agent scores and real WorkArena L2 benchmark scores.

Usage:
    # Analyze results from a correlation study
    python -m llmos.experiments.analyze_correlation \
        --results ./results/correlation_study/ \
        --real-scores llmos/experiments/workarena-official-leaderboard.csv

    # Generate detailed report
    python -m llmos.experiments.analyze_correlation \
        --results ./results/correlation_study/ \
        --output ./results/correlation_study/analysis_report.json
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Result Data Classes
# =============================================================================

@dataclass
class CorrelationMetrics:
    """Correlation metrics between simulated and real scores."""
    spearman_rho: float
    spearman_pvalue: float
    pearson_r: float
    pearson_pvalue: float
    kendall_tau: float
    kendall_pvalue: float
    mae: float
    rmse: float
    num_agents: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConfigAnalysis:
    """Analysis result for a single configuration."""
    config_id: str
    agent_scores: dict[str, float]  # agent_id -> mean score
    agent_success_rates: dict[str, float]
    correlation: Optional[CorrelationMetrics] = None

    def to_dict(self) -> dict:
        return {
            "config_id": self.config_id,
            "agent_scores": self.agent_scores,
            "agent_success_rates": self.agent_success_rates,
            "correlation": self.correlation.to_dict() if self.correlation else None,
        }


@dataclass
class PhaseAnalysis:
    """Analysis result for a phase."""
    phase_id: str
    config_analyses: list[ConfigAnalysis]
    best_config_id: str
    best_correlation: float
    hypothesis: str

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "config_analyses": [c.to_dict() for c in self.config_analyses],
            "best_config_id": self.best_config_id,
            "best_correlation": self.best_correlation,
            "hypothesis": self.hypothesis,
        }


@dataclass
class StudyAnalysis:
    """Complete analysis of the correlation study."""
    phases: list[PhaseAnalysis]
    overall_best_config: str
    overall_best_correlation: float
    conclusions: list[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "phases": [p.to_dict() for p in self.phases],
            "overall_best_config": self.overall_best_config,
            "overall_best_correlation": self.overall_best_correlation,
            "conclusions": self.conclusions,
            "timestamp": self.timestamp,
        }

    def save(self, path: str) -> None:
        """Save analysis to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


# =============================================================================
# Analysis Functions
# =============================================================================

def compute_correlation(
    sim_scores: dict[str, float],
    real_scores: dict[str, float],
) -> Optional[CorrelationMetrics]:
    """
    Compute correlation metrics between simulated and real scores.

    Args:
        sim_scores: Dictionary mapping agent_id to simulated mean score.
        real_scores: Dictionary mapping agent_id to real benchmark score.

    Returns:
        CorrelationMetrics or None if insufficient data.
    """
    # Find common agents
    common_agents = set(sim_scores.keys()) & set(real_scores.keys())

    if len(common_agents) < 2:
        logger.warning(f"Insufficient common agents ({len(common_agents)}) for correlation")
        return None

    # Extract aligned values
    agents = sorted(common_agents)
    sim_values = np.array([sim_scores[a] for a in agents])
    real_values = np.array([real_scores[a] for a in agents])

    # Compute correlations
    spearman_rho, spearman_p = stats.spearmanr(sim_values, real_values)
    pearson_r, pearson_p = stats.pearsonr(sim_values, real_values)
    kendall_tau, kendall_p = stats.kendalltau(sim_values, real_values)

    # Compute error metrics (normalize real scores to [0, 1] for comparison)
    # Real scores are percentages, sim scores are typically [-1, 1]
    # Normalize both to [0, 1] for MAE/RMSE
    sim_norm = (sim_values + 1) / 2  # [-1, 1] -> [0, 1]
    real_norm = real_values / 100  # [0, 100] -> [0, 1]

    mae = np.mean(np.abs(sim_norm - real_norm))
    rmse = np.sqrt(np.mean((sim_norm - real_norm) ** 2))

    return CorrelationMetrics(
        spearman_rho=float(spearman_rho),
        spearman_pvalue=float(spearman_p),
        pearson_r=float(pearson_r),
        pearson_pvalue=float(pearson_p),
        kendall_tau=float(kendall_tau),
        kendall_pvalue=float(kendall_p),
        mae=float(mae),
        rmse=float(rmse),
        num_agents=len(agents),
    )


def load_task_results(results_dir: Path) -> dict[str, dict[str, list[dict]]]:
    """
    Load task results from directory structure.

    Expected structure:
        results_dir/
        ├── config_id/
        │   ├── agent_id/
        │   │   ├── task_001.json
        │   │   └── task_002.json
        │   └── ...
        └── ...

    Returns:
        Nested dict: config_id -> agent_id -> list of task result dicts
    """
    results = {}

    if not results_dir.exists():
        logger.error(f"Results directory not found: {results_dir}")
        return results

    for config_dir in results_dir.iterdir():
        if not config_dir.is_dir() or config_dir.name.startswith("."):
            continue

        config_id = config_dir.name
        results[config_id] = {}

        for agent_dir in config_dir.iterdir():
            if not agent_dir.is_dir():
                continue

            agent_id = agent_dir.name
            agent_results = []

            for task_file in agent_dir.glob("*.json"):
                try:
                    with open(task_file, "r") as f:
                        task_result = json.load(f)
                        agent_results.append(task_result)
                except Exception as e:
                    logger.warning(f"Failed to load {task_file}: {e}")

            if agent_results:
                results[config_id][agent_id] = agent_results

    return results


def analyze_config(
    config_id: str,
    agent_results: dict[str, list[dict]],
    real_scores: dict[str, float],
) -> ConfigAnalysis:
    """Analyze results for a single configuration."""
    agent_scores = {}
    agent_success_rates = {}

    for agent_id, results in agent_results.items():
        if results:
            agent_scores[agent_id] = sum(r["score"] for r in results) / len(results)
            agent_success_rates[agent_id] = sum(1 for r in results if r["success"]) / len(results)

    correlation = compute_correlation(agent_scores, real_scores)

    return ConfigAnalysis(
        config_id=config_id,
        agent_scores=agent_scores,
        agent_success_rates=agent_success_rates,
        correlation=correlation,
    )


def analyze_phase(
    phase_id: str,
    all_results: dict[str, dict[str, list[dict]]],
    real_scores: dict[str, float],
) -> PhaseAnalysis:
    """Analyze results for a phase."""
    from .configs.correlation_study import get_phase

    phase = get_phase(phase_id)
    config_ids = phase.config_ids

    config_analyses = []
    best_config = None
    best_corr = -2.0

    for config_id in config_ids:
        if config_id not in all_results:
            logger.warning(f"Config {config_id} not found in results")
            continue

        analysis = analyze_config(config_id, all_results[config_id], real_scores)
        config_analyses.append(analysis)

        if analysis.correlation and analysis.correlation.spearman_rho > best_corr:
            best_corr = analysis.correlation.spearman_rho
            best_config = config_id

    return PhaseAnalysis(
        phase_id=phase_id,
        config_analyses=config_analyses,
        best_config_id=best_config or config_ids[0],
        best_correlation=best_corr,
        hypothesis=phase.hypothesis,
    )


def analyze_study(
    results_dir: Path,
    real_scores: dict[str, float],
) -> StudyAnalysis:
    """Analyze complete correlation study."""
    from .configs.correlation_study import PHASES

    all_results = load_task_results(results_dir)

    if not all_results:
        raise ValueError(f"No results found in {results_dir}")

    phases = []
    overall_best_config = None
    overall_best_corr = -2.0

    for phase_config in PHASES:
        # Check if we have any results for this phase
        has_results = any(cid in all_results for cid in phase_config.config_ids)
        if not has_results:
            continue

        phase_analysis = analyze_phase(phase_config.phase_id, all_results, real_scores)
        phases.append(phase_analysis)

        if phase_analysis.best_correlation > overall_best_corr:
            overall_best_corr = phase_analysis.best_correlation
            overall_best_config = phase_analysis.best_config_id

    # Generate conclusions
    conclusions = generate_conclusions(phases)

    return StudyAnalysis(
        phases=phases,
        overall_best_config=overall_best_config or "unknown",
        overall_best_correlation=overall_best_corr,
        conclusions=conclusions,
    )


def generate_conclusions(phases: list[PhaseAnalysis]) -> list[str]:
    """Generate conclusions from phase analyses."""
    conclusions = []

    for phase in phases:
        if phase.best_correlation > 0.5:
            conclusions.append(
                f"{phase.phase_id}: Strong positive correlation ({phase.best_correlation:.3f}) "
                f"with config '{phase.best_config_id}'. Hypothesis supported."
            )
        elif phase.best_correlation > 0:
            conclusions.append(
                f"{phase.phase_id}: Weak positive correlation ({phase.best_correlation:.3f}) "
                f"with config '{phase.best_config_id}'. Hypothesis partially supported."
            )
        elif phase.best_correlation > -0.3:
            conclusions.append(
                f"{phase.phase_id}: No significant correlation ({phase.best_correlation:.3f}). "
                f"Hypothesis not supported."
            )
        else:
            conclusions.append(
                f"{phase.phase_id}: Negative correlation ({phase.best_correlation:.3f}). "
                f"Hypothesis contradicted."
            )

    return conclusions


# =============================================================================
# Report Generation
# =============================================================================

def print_report(analysis: StudyAnalysis) -> None:
    """Print formatted report to console."""
    print("\n" + "=" * 70)
    print("CORRELATION STUDY ANALYSIS REPORT")
    print("=" * 70)

    for phase in analysis.phases:
        print(f"\n{'─' * 70}")
        print(f"Phase: {phase.phase_id}")
        print(f"Hypothesis: {phase.hypothesis}")
        print(f"{'─' * 70}")

        print(f"\n{'Config':<20} {'Spearman ρ':<12} {'p-value':<12} {'Agents':<8}")
        print("-" * 52)

        for config in phase.config_analyses:
            if config.correlation:
                print(
                    f"{config.config_id:<20} "
                    f"{config.correlation.spearman_rho:>10.3f}  "
                    f"{config.correlation.spearman_pvalue:>10.4f}  "
                    f"{config.correlation.num_agents:>6}"
                )
            else:
                print(f"{config.config_id:<20} {'N/A':>10}  {'N/A':>10}  {'N/A':>6}")

        print(f"\n  Best config: {phase.best_config_id} (ρ = {phase.best_correlation:.3f})")

    print("\n" + "=" * 70)
    print("OVERALL RESULTS")
    print("=" * 70)
    print(f"\nBest configuration: {analysis.overall_best_config}")
    print(f"Best correlation: {analysis.overall_best_correlation:.3f}")

    print("\n" + "-" * 70)
    print("CONCLUSIONS")
    print("-" * 70)
    for conclusion in analysis.conclusions:
        print(f"  • {conclusion}")

    print("\n" + "=" * 70 + "\n")


def print_agent_comparison(analysis: StudyAnalysis, real_scores: dict[str, float]) -> None:
    """Print agent score comparison table."""
    print("\n" + "=" * 70)
    print("AGENT SCORE COMPARISON")
    print("=" * 70)

    # Collect all agent scores across configs
    all_agents = set(real_scores.keys())
    for phase in analysis.phases:
        for config in phase.config_analyses:
            all_agents.update(config.agent_scores.keys())

    agents = sorted(all_agents)

    # Print header
    print(f"\n{'Agent':<20} {'Real Score':<12} ", end="")
    for phase in analysis.phases:
        if phase.config_analyses:
            print(f"{phase.best_config_id:<15} ", end="")
    print()
    print("-" * 80)

    # Print rows
    for agent in agents:
        real = real_scores.get(agent, float("nan"))
        print(f"{agent:<20} {real:>10.2f}%  ", end="")

        for phase in analysis.phases:
            if phase.config_analyses:
                # Find best config's score for this agent
                for config in phase.config_analyses:
                    if config.config_id == phase.best_config_id:
                        score = config.agent_scores.get(agent, float("nan"))
                        print(f"{score:>13.3f}  ", end="")
                        break
        print()

    print("=" * 70 + "\n")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Analyze correlation study results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--results", "-r",
        type=str,
        required=True,
        help="Path to results directory",
    )
    parser.add_argument(
        "--real-scores",
        type=str,
        help="Path to leaderboard CSV (default: auto-detect)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output path for analysis JSON",
    )
    parser.add_argument(
        "--agents",
        type=str,
        default="gpt-5-mini,gpt-o1-mini,gpt-4o-mini",
        help="Comma-separated list of agent IDs to analyze",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress detailed output",
    )

    args = parser.parse_args()

    # Load real scores
    agent_ids = [a.strip() for a in args.agents.split(",")]

    from .utils.leaderboard import get_workarena_l2_scores
    real_scores = get_workarena_l2_scores(args.real_scores, agent_ids)

    if not real_scores:
        logger.error("No real scores found for specified agents")
        sys.exit(1)

    logger.info(f"Real scores: {real_scores}")

    # Run analysis
    results_dir = Path(args.results)
    analysis = analyze_study(results_dir, real_scores)

    # Print report
    if not args.quiet:
        print_report(analysis)
        print_agent_comparison(analysis, real_scores)

    # Save output
    if args.output:
        analysis.save(args.output)
        logger.info(f"Analysis saved to: {args.output}")

    sys.exit(0)


if __name__ == "__main__":
    main()
