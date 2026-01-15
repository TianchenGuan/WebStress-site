"""
Core components for LLMOS.
LLM-powered modules: Simulator, Agent, Judge, Proposer.

The Simulator is a unified, modular simulator that can be configured via:
- Presets: Simulator.from_preset("classic"), Simulator.from_preset("efficient")
- Config file: Simulator.from_config_file("config.json")
- Direct parameters: Simulator(state_output="delta_only", abstraction="semantic_elements")

Available presets:
- "classic": Original simulator behavior (full_state, full_dom, classic prompt)
- "default": Balanced configuration for general use
- "efficient": Optimized for speed and token efficiency
- "thorough": Maximum accuracy with full verification
- "robust": With constraint verification and uncertainty handling
- "grounded": Example-grounded predictions
"""

# Import unified simulator as the default Simulator
from .unified_simulator import (
    Simulator,
    SimulatorConfig,
    SimulatorError,
    SIMULATOR_PRESETS,
    create_simulator,
)

# Keep legacy simulator available for backward compatibility
from .simulator import Simulator as LegacySimulator

from .agent import Agent, HumanAgent, create_agent
from .judge import Judge, create_judge
from .proposer import Proposer, create_proposer
from .difficulty import (
    DifficultyConfig,
    get_difficulty_config,
    get_difficulty_from_dict,
    build_difficulty_prompt,
    DIFFICULTY_PRESETS,
)

__all__ = [
    # Unified Simulator (default)
    "Simulator",
    "SimulatorConfig",
    "SimulatorError",
    "SIMULATOR_PRESETS",
    "create_simulator",
    # Legacy Simulator (backward compatibility)
    "LegacySimulator",
    # Agent
    "Agent",
    "HumanAgent",
    "create_agent",
    # Judge
    "Judge",
    "create_judge",
    # Proposer
    "Proposer",
    "create_proposer",
    # Difficulty
    "DifficultyConfig",
    "get_difficulty_config",
    "get_difficulty_from_dict",
    "build_difficulty_prompt",
    "DIFFICULTY_PRESETS",
]
