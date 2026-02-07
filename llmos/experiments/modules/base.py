"""
Base interfaces for modular experiment components.

All modules follow a simple protocol that allows them to be composed.

Note: The canonical definitions live in llmos.core.modules.protocols.
This module re-exports them for backwards compatibility.
"""

# Re-export everything from core.modules.protocols
from ...core.modules.protocols import (  # noqa: F401
    PromptBlock,
    StatePreprocessor,
    OutputParser,
    Verifier,
    HistoryManager,
    Module,
    ModuleConfig,
    BasePromptBlock,
    BaseStatePreprocessor,
    BaseOutputParser,
    BaseVerifier,
    BaseHistoryManager,
)
