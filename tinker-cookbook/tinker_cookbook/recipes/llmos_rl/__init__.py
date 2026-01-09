"""
LLMOS RL Recipe - Train computer-use agents using the LLMOS simulator.

This recipe integrates the LLMOS (LLM-based OS Simulator) with Tinker's
RL training framework to train agents that can interact with simulated
computer environments.
"""

from tinker_cookbook.recipes.llmos_rl.llmos_env import (
    LLMOSEnv,
    LLMOSEnvGroupBuilder,
    LLMOSDataset,
    LLMOSDatasetBuilder,
)

__all__ = [
    "LLMOSEnv",
    "LLMOSEnvGroupBuilder",
    "LLMOSDataset",
    "LLMOSDatasetBuilder",
]
