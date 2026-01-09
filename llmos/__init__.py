"""
LLMOS - LLM-based Operating System Simulator

A pure-LLM environment simulator for training computer-use agents.
"""

__version__ = "0.1.0"

# Core components (LLM-powered)
from .core import (
    Simulator,
    create_simulator,
    Agent,
    HumanAgent,
    create_agent,
    Judge,
    create_judge,
    Proposer,
    create_proposer,
    DifficultyConfig,
    get_difficulty_config,
    DIFFICULTY_PRESETS,
)

# Utility modules (deterministic)
from .utils import (
    LLMClient,
    create_client,
    render_observation,
    apply_id_patch,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import Orchestrator as Orchestrator
    from .benchmarks.base import BenchmarkConfig as BenchmarkConfig
    from .interfaces import (
        Task as Task,
        TaskProvider as TaskProvider,
        StateBuilder as StateBuilder,
        Evaluator as Evaluator,
        EvalResult as EvalResult,
        ObservationRenderer as ObservationRenderer,
    )

__all__ = [
    # Core
    "Simulator",
    "create_simulator",
    "Agent",
    "HumanAgent",
    "create_agent",
    "Judge",
    "create_judge",
    "Proposer",
    "create_proposer",
    "DifficultyConfig",
    "get_difficulty_config",
    "DIFFICULTY_PRESETS",
    # Utils
    "LLMClient",
    "create_client",
    "render_observation",
    "apply_id_patch",
    # Orchestrator
    "Orchestrator",
    # Benchmarks
    "BenchmarkConfig",
    "get_benchmark",
    # Interfaces
    "Task",
    "TaskProvider",
    "StateBuilder",
    "Evaluator",
    "EvalResult",
    "ObservationRenderer",
]


def __getattr__(name: str):
    if name == "Orchestrator":
        from .main import Orchestrator
        return Orchestrator
    if name == "BenchmarkConfig":
        from .benchmarks.base import BenchmarkConfig
        return BenchmarkConfig
    if name == "get_benchmark":
        from .benchmarks import get_benchmark
        return get_benchmark
    if name in ("Task", "TaskProvider", "StateBuilder", "Evaluator", "EvalResult", "ObservationRenderer"):
        from . import interfaces
        return getattr(interfaces, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
