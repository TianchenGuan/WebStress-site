"""
Core components for LLMOS.
LLM-powered modules: Simulator, Agent, Judge, Proposer.
"""

from .simulator import Simulator, create_simulator
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
    "get_difficulty_from_dict",
    "build_difficulty_prompt",
    "DIFFICULTY_PRESETS",
]
