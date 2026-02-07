"""
Shared enums for simulator module configuration.

These enums define the configuration options for each simulator module.
They live in core/ so that both production code (core/unified_simulator.py)
and experimental code (experiments/modules/) can import them without
creating a circular dependency.
"""

from enum import Enum


class StateOutputMode(str, Enum):
    """Available state output modes."""
    FULL_STATE = "full_state"
    DELTA_ONLY = "delta_only"
    SEMANTIC_DESCRIPTION = "semantic_description"


class AbstractionLevel(str, Enum):
    """Available abstraction levels."""
    FULL_DOM = "full_dom"
    SEMANTIC_ELEMENTS = "semantic_elements"
    TASK_RELEVANT = "task_relevant"
    VIEWPORT_ONLY = "viewport_only"
    INTERACTIVE_ONLY = "interactive_only"


class MemoryMode(str, Enum):
    """Available memory modes."""
    FULL_HISTORY = "full_history"
    ROLLING_WINDOW = "rolling_window"
    SUMMARIZED = "summarized"
    CHECKPOINTS = "checkpoints"


class ReasoningMode(str, Enum):
    """Available reasoning modes."""
    DIRECT = "direct"
    CHAIN = "chain"


class VerificationMode(str, Enum):
    """Available verification modes."""
    NONE = "none"
    SCHEMA = "schema"
    CONSTRAINT_CHECK = "constraint_check"
    BACKWARD = "backward"


class TemporalMode(str, Enum):
    """Available temporal modes."""
    INSTANT = "instant"
    ASYNC_AWARE = "async_aware"
    EVENT_DRIVEN = "event_driven"


class UncertaintyMode(str, Enum):
    """Available uncertainty modes."""
    DETERMINISTIC = "deterministic"
    WITH_CONFIDENCE = "with_confidence"
    PROBABILISTIC = "probabilistic"
    ADMITS_UNCERTAINTY = "admits_uncertainty"


class GroundingStrategy(str, Enum):
    """Available grounding strategies."""
    LLM_KNOWLEDGE = "llm_knowledge"
    EXAMPLE_GROUNDED = "example_grounded"
    DOC_GROUNDED = "doc_grounded"
    TRACE_GROUNDED = "trace_grounded"


class AdversarialMode(str, Enum):
    """Available adversarial modes."""
    NONE = "none"
    SUBTLE = "subtle"
    DECEPTIVE = "deceptive"
    HOSTILE = "hostile"
