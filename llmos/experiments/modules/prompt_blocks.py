"""
Prompt Blocks Library: Reusable prompt components.

Note: The canonical definitions live in llmos.core.modules.prompt_blocks.
This module re-exports them for backwards compatibility.
"""

# Re-export everything from core.modules.prompt_blocks
from ...core.modules.prompt_blocks import (  # noqa: F401
    load_base_prompt,
    PromptBlockLibrary,
    build_simulator_prompt,
    get_prompt_block,
    get_base_prompt,
    compose_prompt,
    # Block constants
    TASK_CONTEXT_BLOCK,
    ACTION_CONTEXT_BLOCK,
    JSON_OUTPUT_BLOCK,
    STRUCTURED_THOUGHT_BLOCK,
    WEB_UI_KNOWLEDGE_BLOCK,
    DESKTOP_UI_KNOWLEDGE_BLOCK,
    SERVICENOW_KNOWLEDGE_BLOCK,
    ERROR_HANDLING_BLOCK,
)

# Re-export base types that were previously imported here
from .base import BasePromptBlock, PromptBlock  # noqa: F401
