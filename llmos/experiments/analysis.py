"""
Analysis tools for simulator fidelity experiments.

This module provides:
1. CorrelationAnalyzer: Compare simulator scores with real benchmark scores
2. AblationAnalyzer: Analyze impact of individual design choices
3. Visualization utilities: Generate plots and reports
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence
import numpy as np

from .runner import ExperimentResult, AgentResult

logger = logging.getLogger(__name__)


@dataclass
class CorrelationResult:
    """Result of correlation analysis between simulator and real scores."""
    simulator_id: str
    pearson_r: float
    pearson_p: float
    spearman_rho: float
    spearman_p: float
    kendall_tau: float
    kendall_p: float
    mean_absolute_error: float
    root_mean_squared_error: float
    num_agents: int
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "simulator_id": self.simulator_id,
            "pearson_r": self.pearson_r,
            "pearson_p": self.pearson_p,
            "spearman_rho": self.spearman_rho,
            "spearman_p": self.spearman_p,
            "kendall_tau": self.kendall_tau,
            "kendall_p": self.kendall_p,
            "mean_absolute_error": self.mean_absolute_error,
            "root_mean_squared_error": self.root_mean_squared_error,
            "num_agents": self.num_agents,
            "metadata": self.metadata,
        }

    @property
    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"{self.simulator_id}: "
            f"Pearson r={self.pearson_r:.3f} (p={self.pearson_p:.3f}), "
            f"Spearman ρ={self.spearman_rho:.3f} (p={self.spearman_p:.3f}), "
            f"MAE={self.mean_absolute_error:.3f}"
        )


@dataclass
class AblationResult:
    """Result of ablation study on a single variable."""
    variable_name: str
    baseline_value: Any
    baseline_correlation: float
    ablation_results: list[dict]  # [{value, correlation, delta}, ...]
    best_value: Any
    best_correlation: float
    worst_value: Any
    worst_correlation: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "variable_name": self.variable_name,
            "baseline_value": self.baseline_value,
            "baseline_correlation": self.baseline_correlation,
            "ablation_results": self.ablation_results,
            "best_value": self.best_value,
            "best_correlation": self.best_correlation,
            "worst_value": self.worst_value,
            "worst_correlation": self.worst_correlation,
            "metadata": self.metadata,
        }


class CorrelationAnalyzer:
    """
    Analyzes correlation between simulator and real benchmark scores.

    The primary metric for simulator fidelity is how well simulator scores
    predict real benchmark performance across different agents.

    Example:
        analyzer = CorrelationAnalyzer()

        # Load experiment results
        sim_results = ExperimentResult.load("sim_experiment.json")

        # Set ground truth scores (from real benchmark)
        real_scores = {
            "agent_a": 0.75,
            "agent_b": 0.62,
            "agent_c": 0.83,
        }

        # Compute correlations
        correlations = analyzer.compute_correlations(sim_results, real_scores)

        # Print report
        analyzer.print_report(correlations)
    """

    def __init__(self):
        self.results: list[CorrelationResult] = []

    def compute_correlations(
        self,
        experiment: ExperimentResult,
        real_scores: dict[str, float],
        metric: str = "mean_score",
    ) -> list[CorrelationResult]:
        """
        Compute correlations between simulator and real scores.

        Args:
            experiment: Experiment results with simulator scores.
            real_scores: Dict mapping agent_id to real benchmark score.
            metric: Which metric to use ("mean_score", "success_rate").

        Returns:
            List of CorrelationResult, one per simulator config.
        """
        from scipy import stats

        # Get unique simulator configs
        simulator_ids = sorted(set(r.simulator_config_id for r in experiment.agent_results))

        results = []
        for sim_id in simulator_ids:
            # Get simulator scores for this config
            sim_scores = {}
            for result in experiment.agent_results:
                if result.simulator_config_id == sim_id:
                    if metric == "mean_score":
                        sim_scores[result.agent_id] = result.mean_score
                    elif metric == "success_rate":
                        sim_scores[result.agent_id] = result.successful_tasks / result.total_tasks

            # Match with real scores
            agents = sorted(set(sim_scores.keys()) & set(real_scores.keys()))
            if len(agents) < 2:
                logger.warning(f"Not enough matching agents for {sim_id}")
                continue

            sim_arr = np.array([sim_scores[a] for a in agents])
            real_arr = np.array([real_scores[a] for a in agents])

            # Compute correlations
            pearson_r, pearson_p = stats.pearsonr(sim_arr, real_arr)
            spearman_rho, spearman_p = stats.spearmanr(sim_arr, real_arr)
            kendall_tau, kendall_p = stats.kendalltau(sim_arr, real_arr)

            # Compute errors
            mae = np.mean(np.abs(sim_arr - real_arr))
            rmse = np.sqrt(np.mean((sim_arr - real_arr) ** 2))

            result = CorrelationResult(
                simulator_id=sim_id,
                pearson_r=float(pearson_r),
                pearson_p=float(pearson_p),
                spearman_rho=float(spearman_rho),
                spearman_p=float(spearman_p),
                kendall_tau=float(kendall_tau),
                kendall_p=float(kendall_p),
                mean_absolute_error=float(mae),
                root_mean_squared_error=float(rmse),
                num_agents=len(agents),
                metadata={
                    "agents": agents,
                    "sim_scores": {a: sim_scores[a] for a in agents},
                    "real_scores": {a: real_scores[a] for a in agents},
                },
            )
            results.append(result)

        self.results = results
        return results

    def rank_simulators(
        self,
        results: Optional[list[CorrelationResult]] = None,
        by: str = "spearman_rho",
    ) -> list[CorrelationResult]:
        """
        Rank simulators by correlation metric.

        Args:
            results: Correlation results (uses self.results if None).
            by: Metric to rank by ("pearson_r", "spearman_rho", "kendall_tau").

        Returns:
            Sorted list of results (best first).
        """
        results = results or self.results
        return sorted(results, key=lambda r: getattr(r, by), reverse=True)

    def print_report(
        self,
        results: Optional[list[CorrelationResult]] = None,
        top_k: Optional[int] = None,
    ) -> None:
        """Print a formatted report of correlation results."""
        results = results or self.results
        ranked = self.rank_simulators(results)

        if top_k:
            ranked = ranked[:top_k]

        print("\n" + "=" * 80)
        print("SIMULATOR FIDELITY REPORT")
        print("=" * 80)
        print(f"\nRanked by Spearman correlation (higher = better):\n")
        print(f"{'Rank':<6}{'Simulator':<30}{'Spearman ρ':<12}{'Pearson r':<12}{'MAE':<10}{'N':<6}")
        print("-" * 80)

        for i, result in enumerate(ranked, 1):
            print(
                f"{i:<6}"
                f"{result.simulator_id[:28]:<30}"
                f"{result.spearman_rho:>10.3f}  "
                f"{result.pearson_r:>10.3f}  "
                f"{result.mean_absolute_error:>8.3f}  "
                f"{result.num_agents:<6}"
            )

        print("=" * 80)

        # Statistical significance
        print("\nStatistical Significance (p < 0.05 marked with *):")
        for result in ranked[:5]:
            sig_s = "*" if result.spearman_p < 0.05 else " "
            sig_p = "*" if result.pearson_p < 0.05 else " "
            print(f"  {result.simulator_id}: Spearman p={result.spearman_p:.4f}{sig_s}, Pearson p={result.pearson_p:.4f}{sig_p}")

    def save_report(
        self,
        path: str,
        results: Optional[list[CorrelationResult]] = None,
    ) -> None:
        """Save correlation results to JSON."""
        results = results or self.results
        data = {
            "results": [r.to_dict() for r in results],
            "ranking": [r.simulator_id for r in self.rank_simulators(results)],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def plot_correlation(
        self,
        result: CorrelationResult,
        save_path: Optional[str] = None,
    ) -> None:
        """
        Plot simulator vs real scores with regression line.

        Requires matplotlib.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not installed, skipping plot")
            return

        sim_scores = list(result.metadata["sim_scores"].values())
        real_scores = list(result.metadata["real_scores"].values())
        agents = result.metadata["agents"]

        fig, ax = plt.subplots(figsize=(8, 6))

        # Scatter plot
        ax.scatter(real_scores, sim_scores, s=100, alpha=0.7)

        # Label points
        for i, agent in enumerate(agents):
            ax.annotate(agent, (real_scores[i], sim_scores[i]), fontsize=8)

        # Regression line
        z = np.polyfit(real_scores, sim_scores, 1)
        p = np.poly1d(z)
        x_line = np.linspace(min(real_scores), max(real_scores), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.8, label=f"ρ={result.spearman_rho:.3f}")

        # Perfect correlation line
        lim = [min(min(real_scores), min(sim_scores)), max(max(real_scores), max(sim_scores))]
        ax.plot(lim, lim, "k:", alpha=0.5, label="Perfect correlation")

        ax.set_xlabel("Real Benchmark Score")
        ax.set_ylabel("Simulator Score")
        ax.set_title(f"Simulator Fidelity: {result.simulator_id}")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150)
            logger.info(f"Plot saved to {save_path}")
        else:
            plt.show()


class AblationAnalyzer:
    """
    Analyzes the impact of individual design choices through ablation.

    Compares correlation deltas when varying a single factor while
    holding others constant.

    Example:
        analyzer = AblationAnalyzer()

        # Analyze impact of history length
        result = analyzer.analyze_variable(
            experiment=experiment,
            real_scores=real_scores,
            variable_name="history_length",
            baseline_config=SIMULATOR_PRESETS["baseline_gpt4o"],
        )

        print(f"Best history length: {result.best_value}")
        print(f"Correlation improvement: {result.best_correlation - result.baseline_correlation:.3f}")
    """

    def __init__(self):
        self.correlation_analyzer = CorrelationAnalyzer()

    def analyze_variable(
        self,
        experiment: ExperimentResult,
        real_scores: dict[str, float],
        variable_name: str,
        baseline_config_id: Optional[str] = None,
    ) -> AblationResult:
        """
        Analyze impact of a single variable.

        Args:
            experiment: Experiment results.
            real_scores: Ground truth scores.
            variable_name: Name of variable being ablated.
            baseline_config_id: ID of baseline config (uses first if None).

        Returns:
            AblationResult with analysis.
        """
        # Compute correlations for all configs
        correlations = self.correlation_analyzer.compute_correlations(
            experiment, real_scores
        )

        if not correlations:
            raise ValueError("No correlation results computed")

        # Find baseline
        if baseline_config_id:
            baseline = next(
                (c for c in correlations if c.simulator_id == baseline_config_id),
                None
            )
        else:
            baseline = correlations[0]

        if baseline is None:
            raise ValueError(f"Baseline config not found: {baseline_config_id}")

        # Extract variable values from config metadata
        ablation_results = []
        for corr in correlations:
            # Find the config
            config_data = next(
                (c for c in experiment.simulator_configs if c.get("name") in corr.simulator_id),
                {}
            )

            value = config_data.get(variable_name, "unknown")
            delta = corr.spearman_rho - baseline.spearman_rho

            ablation_results.append({
                "simulator_id": corr.simulator_id,
                "value": value,
                "correlation": corr.spearman_rho,
                "delta": delta,
            })

        # Find best and worst
        sorted_results = sorted(ablation_results, key=lambda x: x["correlation"], reverse=True)
        best = sorted_results[0]
        worst = sorted_results[-1]

        return AblationResult(
            variable_name=variable_name,
            baseline_value=ablation_results[0]["value"] if ablation_results else None,
            baseline_correlation=baseline.spearman_rho,
            ablation_results=ablation_results,
            best_value=best["value"],
            best_correlation=best["correlation"],
            worst_value=worst["value"],
            worst_correlation=worst["correlation"],
        )

    def analyze_all_variables(
        self,
        experiment: ExperimentResult,
        real_scores: dict[str, float],
        variables: list[str],
    ) -> dict[str, AblationResult]:
        """
        Analyze multiple variables.

        Returns:
            Dict mapping variable name to AblationResult.
        """
        results = {}
        for var in variables:
            try:
                results[var] = self.analyze_variable(experiment, real_scores, var)
            except Exception as e:
                logger.warning(f"Failed to analyze {var}: {e}")
        return results

    def rank_variable_importance(
        self,
        ablation_results: dict[str, AblationResult],
    ) -> list[tuple[str, float]]:
        """
        Rank variables by their impact on correlation.

        Returns:
            List of (variable_name, impact_score) sorted by impact.
        """
        impacts = []
        for var_name, result in ablation_results.items():
            # Impact = range of correlations across values
            correlations = [r["correlation"] for r in result.ablation_results]
            impact = max(correlations) - min(correlations) if correlations else 0
            impacts.append((var_name, impact))

        return sorted(impacts, key=lambda x: x[1], reverse=True)

    def print_ablation_report(
        self,
        ablation_results: dict[str, AblationResult],
    ) -> None:
        """Print formatted ablation report."""
        print("\n" + "=" * 80)
        print("ABLATION STUDY REPORT")
        print("=" * 80)

        # Rank by importance
        rankings = self.rank_variable_importance(ablation_results)

        print("\nVariable Importance (by correlation range):\n")
        print(f"{'Rank':<6}{'Variable':<25}{'Impact':<10}{'Best Value':<20}{'Best ρ':<10}")
        print("-" * 80)

        for i, (var_name, impact) in enumerate(rankings, 1):
            result = ablation_results[var_name]
            print(
                f"{i:<6}"
                f"{var_name:<25}"
                f"{impact:>8.3f}  "
                f"{str(result.best_value)[:18]:<20}"
                f"{result.best_correlation:>8.3f}"
            )

        print("\n" + "-" * 80)
        print("\nDetailed Results per Variable:\n")

        for var_name, result in ablation_results.items():
            print(f"\n{var_name}:")
            print(f"  Baseline: {result.baseline_value} (ρ={result.baseline_correlation:.3f})")
            print(f"  Best: {result.best_value} (ρ={result.best_correlation:.3f})")
            print(f"  Worst: {result.worst_value} (ρ={result.worst_correlation:.3f})")
            print(f"  All values tested:")
            for r in sorted(result.ablation_results, key=lambda x: x["correlation"], reverse=True):
                delta_str = f"+{r['delta']:.3f}" if r['delta'] >= 0 else f"{r['delta']:.3f}"
                print(f"    {r['value']}: ρ={r['correlation']:.3f} ({delta_str})")

        print("=" * 80)


def compare_experiments(
    experiment1: ExperimentResult,
    experiment2: ExperimentResult,
    real_scores: dict[str, float],
) -> dict:
    """
    Compare two experiments (e.g., before/after a change).

    Returns:
        Dict with comparison metrics.
    """
    analyzer = CorrelationAnalyzer()

    corr1 = analyzer.compute_correlations(experiment1, real_scores)
    corr2 = analyzer.compute_correlations(experiment2, real_scores)

    # Match by simulator ID
    comparison = []
    for c1 in corr1:
        c2 = next((c for c in corr2 if c.simulator_id == c1.simulator_id), None)
        if c2:
            comparison.append({
                "simulator_id": c1.simulator_id,
                "exp1_spearman": c1.spearman_rho,
                "exp2_spearman": c2.spearman_rho,
                "delta": c2.spearman_rho - c1.spearman_rho,
            })

    return {
        "comparisons": comparison,
        "avg_delta": np.mean([c["delta"] for c in comparison]) if comparison else 0,
        "improved": sum(1 for c in comparison if c["delta"] > 0),
        "degraded": sum(1 for c in comparison if c["delta"] < 0),
    }
