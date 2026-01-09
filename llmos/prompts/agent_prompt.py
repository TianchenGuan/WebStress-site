"""
Shared Agent System Prompt for LLMOS.

This module provides the canonical agent system prompt used by both the llmos Agent
and the Tinker RL integration. The source of truth is agent.system.md.
"""

from pathlib import Path

_PROMPT_PATH = Path(__file__).parent / "agent.system.md"


def _load_agent_prompt() -> str:
    """Load the agent system prompt from the markdown file."""
    if _PROMPT_PATH.exists():
        with open(_PROMPT_PATH, "r") as f:
            return f.read()
    raise FileNotFoundError(f"Agent system prompt not found at {_PROMPT_PATH}")


# Load once at import time
AGENT_SYSTEM_PROMPT = _load_agent_prompt()
