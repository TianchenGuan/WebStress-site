"""
Modular experiment components for simulator design space exploration.

These modules can be composed to create different simulator variants
without modifying the core Simulator class.

Architecture:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                      ExperimentalSimulator                               │
    │      (Wrapper that composes modules around base Simulator)               │
    ├─────────────────────────────────────────────────────────────────────────┤
    │                                                                          │
    │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
    │  │ Abstraction│  │   Memory   │  │ Reasoning  │  │  Grounding │        │
    │  │   Module   │  │   Module   │  │   Module   │  │   Module   │        │
    │  │            │  │            │  │            │  │            │        │
    │  │ Filters    │  │ Manages    │  │ Direct vs  │  │ Examples,  │        │
    │  │ state by   │  │ history    │  │ chain      │  │ docs, or   │        │
    │  │ abstraction│  │ context    │  │ reasoning  │  │ traces     │        │
    │  └────────────┘  └────────────┘  └────────────┘  └────────────┘        │
    │          │              │              │               │                │
    │          └──────────────┴──────────────┴───────────────┘                │
    │                                │                                         │
    │                                ▼                                         │
    │                      ┌──────────────┐                                   │
    │                      │    Prompt    │                                   │
    │                      │   Builder    │                                   │
    │                      └──────────────┘                                   │
    │                                │                                         │
    │                                ▼                                         │
    │                      ┌──────────────┐                                   │
    │                      │  Base LLM    │                                   │
    │                      │  Simulator   │                                   │
    │                      └──────────────┘                                   │
    │                                │                                         │
    │                                ▼                                         │
    │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
    │  │ StateOutput│  │ Temporal   │  │ Uncertainty│  │Verification│        │
    │  │   Module   │  │   Module   │  │   Module   │  │   Module   │        │
    │  │            │  │            │  │            │  │            │        │
    │  │ Full state │  │ Instant vs │  │ Confidence │  │ Schema,    │        │
    │  │ vs delta   │  │ async      │  │ or prob.   │  │ constraint │        │
    │  │ vs semantic│  │ vs events  │  │ outcomes   │  │ or backward│        │
    │  └────────────┘  └────────────┘  └────────────┘  └────────────┘        │
    │                                                                          │
    └─────────────────────────────────────────────────────────────────────────┘

Modules:
    - StateOutput: How state changes are represented (full/delta/semantic)
    - Abstraction: Level of detail in state (full/semantic/task-relevant/interactive)
    - Memory: History context strategy (full/rolling/summarized/checkpoints)
    - Reasoning: Reasoning approach (direct/chain)
    - Verification: Output validation (schema/constraint/backward)
    - Temporal: Async handling (instant/async-aware/event-driven)
    - Uncertainty: Confidence/probability (deterministic/confidence/probabilistic)
    - Grounding: Knowledge source (llm/examples/docs/traces)
    - Adversarial: Obstacle generation (none/subtle/deceptive/hostile)

Usage:
    from llmos.experiments.modules import (
        ExperimentalSimulator,
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

    sim = ExperimentalSimulator(
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
        memory=MemoryMode.ROLLING_WINDOW,
        memory_window=5,
        reasoning=ReasoningMode.CHAIN,
        verification=VerificationMode.CONSTRAINT_CHECK,
        temporal=TemporalMode.INSTANT,
        uncertainty=UncertaintyMode.DETERMINISTIC,
        grounding=GroundingStrategy.LLM_KNOWLEDGE,
        adversarial=AdversarialMode.SUBTLE,  # Add realistic obstacles
    )
"""

from .base import (
    Module,
    PromptBlock,
    StatePreprocessor,
    OutputParser,
    Verifier,
    HistoryManager,
    BasePromptBlock,
    BaseStatePreprocessor,
    BaseOutputParser,
    BaseVerifier,
    BaseHistoryManager,
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
    TaskRelevantPreprocessor,
    ViewportOnlyPreprocessor,
    InteractiveOnlyPreprocessor,
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
    CombinedVerifier,
)
from .temporal import (
    TemporalMode,
    TemporalModule,
    AsyncStateManager,
)
from .uncertainty import (
    UncertaintyMode,
    UncertaintyModule,
    UncertaintyAggregator,
)
from .grounding import (
    GroundingStrategy,
    GroundingModule,
    ExampleRetriever,
    DocumentationRetriever,
    TraceRetriever,
)
from .adversarial import (
    AdversarialMode,
    AdversarialModule,
    AdversarialTracker,
)
from .prompt_blocks import PromptBlockLibrary, build_simulator_prompt
from .experimental_simulator import (
    ExperimentalSimulator,
    ExperimentalConfig,
    create_experimental_simulator,
)

__all__ = [
    # Base
    "Module",
    "PromptBlock",
    "StatePreprocessor",
    "OutputParser",
    "Verifier",
    "HistoryManager",
    "BasePromptBlock",
    "BaseStatePreprocessor",
    "BaseOutputParser",
    "BaseVerifier",
    "BaseHistoryManager",
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
    "TaskRelevantPreprocessor",
    "ViewportOnlyPreprocessor",
    "InteractiveOnlyPreprocessor",
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
    "CombinedVerifier",
    # Temporal
    "TemporalMode",
    "TemporalModule",
    "AsyncStateManager",
    # Uncertainty
    "UncertaintyMode",
    "UncertaintyModule",
    "UncertaintyAggregator",
    # Grounding
    "GroundingStrategy",
    "GroundingModule",
    "ExampleRetriever",
    "DocumentationRetriever",
    "TraceRetriever",
    # Adversarial
    "AdversarialMode",
    "AdversarialModule",
    "AdversarialTracker",
    # Utilities
    "PromptBlockLibrary",
    "build_simulator_prompt",
    # Main
    "ExperimentalSimulator",
    "ExperimentalConfig",
    "create_experimental_simulator",
]
