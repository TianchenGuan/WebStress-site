"""
Modular experiment components for simulator design space exploration.

These modules can be composed to create different simulator variants
without modifying the core Simulator class.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                  ExperimentalSimulator                       │
    │  (Wrapper that composes modules around base Simulator)       │
    ├─────────────────────────────────────────────────────────────┤
    │                                                              │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
    │  │  Abstraction │  │    Memory    │  │  Reasoning   │       │
    │  │   Module     │  │   Module     │  │   Module     │       │
    │  │              │  │              │  │              │       │
    │  │ Preprocesses │  │  Manages     │  │ Adds CoT     │       │
    │  │ state before │  │  history     │  │ or chain     │       │
    │  │ LLM call     │  │  context     │  │ reasoning    │       │
    │  └──────────────┘  └──────────────┘  └──────────────┘       │
    │          │                │                │                 │
    │          └────────────────┼────────────────┘                 │
    │                           ▼                                  │
    │                  ┌──────────────┐                            │
    │                  │    Prompt    │                            │
    │                  │   Builder    │                            │
    │                  └──────────────┘                            │
    │                           │                                  │
    │                           ▼                                  │
    │                  ┌──────────────┐                            │
    │                  │  Base LLM    │                            │
    │                  │  Simulator   │                            │
    │                  └──────────────┘                            │
    │                           │                                  │
    │                           ▼                                  │
    │  ┌──────────────┐  ┌──────────────┐                         │
    │  │ StateOutput  │  │ Verification │                         │
    │  │   Module     │  │   Module     │                         │
    │  │              │  │              │                         │
    │  │ Parses LLM   │  │ Validates    │                         │
    │  │ output based │  │ output       │                         │
    │  │ on mode      │  │ correctness  │                         │
    │  └──────────────┘  └──────────────┘                         │
    │                                                              │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from llmos.experiments.modules import (
        ExperimentalSimulator,
        StateOutputMode,
        AbstractionLevel,
        MemoryMode,
        ReasoningMode,
        VerificationMode,
    )

    sim = ExperimentalSimulator(
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction=AbstractionLevel.SEMANTIC,
        memory=MemoryMode.ROLLING_WINDOW,
        memory_window=5,
        reasoning=ReasoningMode.CHAIN,
        verification=VerificationMode.CONSTRAINT_CHECK,
    )
"""

from .base import (
    Module,
    PromptBlock,
    StatePreprocessor,
    OutputParser,
    Verifier,
)
from .state_output import (
    StateOutputMode,
    StateOutputModule,
    FullStateParser,
    DeltaOnlyParser,
    SemanticDescriptionParser,
)
from .abstraction import (
    AbstractionLevel,
    AbstractionModule,
    FullDOMPreprocessor,
    SemanticElementsPreprocessor,
)
from .memory import (
    MemoryMode,
    MemoryModule,
    FullHistoryManager,
    RollingWindowManager,
    SummarizedHistoryManager,
    CheckpointManager,
)
from .reasoning import (
    ReasoningMode,
    ReasoningModule,
    DirectReasoningBlock,
    ChainReasoningBlock,
)
from .verification import (
    VerificationMode,
    VerificationModule,
    SchemaVerifier,
    ConstraintVerifier,
    BackwardVerifier,
)
from .prompt_blocks import PromptBlockLibrary
from .experimental_simulator import ExperimentalSimulator

__all__ = [
    # Base
    "Module",
    "PromptBlock",
    "StatePreprocessor",
    "OutputParser",
    "Verifier",
    # State Output
    "StateOutputMode",
    "StateOutputModule",
    "FullStateParser",
    "DeltaOnlyParser",
    "SemanticDescriptionParser",
    # Abstraction
    "AbstractionLevel",
    "AbstractionModule",
    "FullDOMPreprocessor",
    "SemanticElementsPreprocessor",
    # Memory
    "MemoryMode",
    "MemoryModule",
    "FullHistoryManager",
    "RollingWindowManager",
    "SummarizedHistoryManager",
    "CheckpointManager",
    # Reasoning
    "ReasoningMode",
    "ReasoningModule",
    "DirectReasoningBlock",
    "ChainReasoningBlock",
    # Verification
    "VerificationMode",
    "VerificationModule",
    "SchemaVerifier",
    "ConstraintVerifier",
    "BackwardVerifier",
    # Utilities
    "PromptBlockLibrary",
    # Main
    "ExperimentalSimulator",
]
