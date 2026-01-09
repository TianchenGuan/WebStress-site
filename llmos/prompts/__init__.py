"""
Prompts module for LLMOS.

Contains shared prompts used across llmos components and integrations.
The source of truth for prompts are the .md files in this directory.
"""

from .agent_prompt import AGENT_SYSTEM_PROMPT

__all__ = ["AGENT_SYSTEM_PROMPT"]
