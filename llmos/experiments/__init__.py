"""
Experimental framework for studying simulator fidelity.

This module provides tools for:
1. Defining simulator design variants (SimulatorConfig)
2. Running systematic experiments across agents and simulators
3. Analyzing correlation between simulator and real benchmark scores
4. Conducting ablation studies on design choices

Research Question: How well does the LLM simulator predict agent performance
on real benchmarks?

Primary Metric: Correlation(Simulator Scores, Real Scores) across agents

Usage:
    # Run an ablation experiment
    python -m llmos.experiments.run_ablation --experiment llm_ablation --num-tasks 50

    # Analyze results
    python -m llmos.experiments.run_ablation --analyze results/exp.json --real-scores real.json

    # Programmatic usage
    from llmos.experiments import ExperimentRunner, SimulatorConfig
    runner = ExperimentRunner(benchmark_name="workarena")
    runner.register_agent(agent_spec)
    result = runner.run(simulator_configs=[...], num_tasks=50)
"""

from .simulator_config import (
    SimulatorConfig,
    PromptConfig,
    StateRepresentationConfig,
    LLMProvider,
    StateRepresentation,
    ActionFormat,
    HistoryMode,
    SIMULATOR_PRESETS,
    get_ablation_configs,
)
from .runner import (
    ExperimentRunner,
    ExperimentResult,
    AgentResult,
    TaskResult,
    AgentSpec,
    AgentProtocol,
)
from .analysis import CorrelationAnalyzer, AblationAnalyzer, CorrelationResult
from .design_space import (
    ExperimentalDesign,
    StateOutputMode,
    StateInputMode,
    PredictionTarget,
    AbstractionLevel,
    TemporalMode,
    CausalMode,
    UncertaintyMode,
    ErrorHandlingMode,
    ContextStrategy,
    MemoryType,
    VerificationMode,
    GroundingStrategy,
    DESIGN_EXPERIMENTS,
    get_experiment,
    get_experiment_configs,
    get_hypothesis,
    get_interaction_experiments,
)

__all__ = [
    # Config classes
    "SimulatorConfig",
    "PromptConfig",
    "StateRepresentationConfig",
    # Enums
    "LLMProvider",
    "StateRepresentation",
    "ActionFormat",
    "HistoryMode",
    # Presets and utilities
    "SIMULATOR_PRESETS",
    "get_ablation_configs",
    # Runner
    "ExperimentRunner",
    "ExperimentResult",
    "AgentResult",
    "TaskResult",
    "AgentSpec",
    "AgentProtocol",
    # Analysis
    "CorrelationAnalyzer",
    "AblationAnalyzer",
    "CorrelationResult",
    # Design space
    "ExperimentalDesign",
    "StateOutputMode",
    "StateInputMode",
    "PredictionTarget",
    "AbstractionLevel",
    "TemporalMode",
    "CausalMode",
    "UncertaintyMode",
    "ErrorHandlingMode",
    "ContextStrategy",
    "MemoryType",
    "VerificationMode",
    "GroundingStrategy",
    "DESIGN_EXPERIMENTS",
    "get_experiment",
    "get_experiment_configs",
    "get_hypothesis",
    "get_interaction_experiments",
]
