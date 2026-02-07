"""
Shared module types for LLMOS simulator configuration.

This package contains enums, protocols, and prompt building utilities
that are shared between core/ (production) and experiments/ (research).
"""

from .enums import (
    StateOutputMode,
    AbstractionLevel,
    MemoryMode,
    ReasoningMode,
    VerificationMode,
    TemporalMode,
    UncertaintyMode,
    GroundingStrategy,
    AdversarialMode,
)
from .protocols import (
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
from .prompt_blocks import (
    PromptBlockLibrary,
    build_simulator_prompt,
    get_prompt_block,
    get_base_prompt,
    compose_prompt,
)

__all__ = [
    # Enums
    "StateOutputMode",
    "AbstractionLevel",
    "MemoryMode",
    "ReasoningMode",
    "VerificationMode",
    "TemporalMode",
    "UncertaintyMode",
    "GroundingStrategy",
    "AdversarialMode",
    # Protocols
    "PromptBlock",
    "StatePreprocessor",
    "OutputParser",
    "Verifier",
    "HistoryManager",
    "Module",
    "ModuleConfig",
    # Base implementations
    "BasePromptBlock",
    "BaseStatePreprocessor",
    "BaseOutputParser",
    "BaseVerifier",
    "BaseHistoryManager",
    # Prompt blocks
    "PromptBlockLibrary",
    "build_simulator_prompt",
    "get_prompt_block",
    "get_base_prompt",
    "compose_prompt",
]
