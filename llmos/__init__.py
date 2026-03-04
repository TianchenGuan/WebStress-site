"""
LLMOS - LLM-based Operating System Simulator

A pure-LLM environment simulator for training computer-use agents.
"""

__version__ = "0.2.0"

from .simulator import Simulator
from .agent import Agent, HumanAgent
from . import judge
from .utils.llm_client import LLMClient, create_client
from .utils.patching import apply_id_patch
from .utils.rendering import render_observation

__all__ = [
    "Simulator",
    "Agent",
    "HumanAgent",
    "judge",
    "LLMClient",
    "create_client",
    "render_observation",
    "apply_id_patch",
]
