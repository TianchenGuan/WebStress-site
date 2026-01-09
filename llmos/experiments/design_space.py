"""
Simulator Design Space: Meaningful experimental dimensions.

This module defines the key design choices that fundamentally affect
how an LLM-based simulator works. These go beyond trivial ablations
to explore core questions about world modeling with LLMs.

Research Questions:
1. How should state be communicated to/from the simulator?
2. What level of abstraction should the simulator operate at?
3. How should the simulator handle uncertainty and errors?
4. What temporal/causal structure should be modeled?
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


# =============================================================================
# Dimension 1: State Communication Strategy
# Question: How should we communicate state to/from the simulator LLM?
# =============================================================================

class StateOutputMode(str, Enum):
    """How the simulator outputs state changes."""

    # Output complete state every step (current approach)
    # + Ensures consistency, self-contained
    # - Token inefficient, may lose focus on changes
    FULL_STATE = "full_state"

    # Output only what changed (delta/diff)
    # + Token efficient, focuses on effects
    # - Errors accumulate, needs state reconstruction
    DELTA_ONLY = "delta_only"

    # Output delta + affected region context
    # + Balanced: efficient yet grounded
    # - More complex parsing
    DELTA_WITH_CONTEXT = "delta_with_context"

    # Output semantic description of changes
    # + Natural language, flexible
    # - Harder to verify, may drift
    SEMANTIC_DESCRIPTION = "semantic_description"


class StateInputMode(str, Enum):
    """How state is provided to the simulator."""

    # Full current state as input
    FULL_STATE = "full_state"

    # Current state + previous state (for comparison)
    CURRENT_AND_PREVIOUS = "current_and_previous"

    # Current state + diff from previous
    CURRENT_WITH_DIFF = "current_with_diff"

    # Summarized state (LLM-compressed)
    SUMMARIZED = "summarized"

    # Hierarchical: overview + details on demand
    HIERARCHICAL = "hierarchical"


# =============================================================================
# Dimension 2: Prediction Granularity
# Question: What should the simulator predict and at what granularity?
# =============================================================================

class PredictionTarget(str, Enum):
    """What the simulator predicts."""

    # Predict next state (standard)
    NEXT_STATE = "next_state"

    # Predict state + intermediate events/animations
    STATE_WITH_EVENTS = "state_with_events"

    # Predict multiple future states (trajectory)
    TRAJECTORY = "trajectory"

    # Predict until a "stable" state (after async ops complete)
    STABLE_STATE = "stable_state"

    # Predict possible outcomes (branching)
    OUTCOME_DISTRIBUTION = "outcome_distribution"


class AbstractionLevel(str, Enum):
    """Level of detail in state representation."""

    # Full DOM/UI tree with all attributes
    FULL_DETAIL = "full_detail"

    # Semantic elements only (buttons, inputs, text)
    SEMANTIC_ELEMENTS = "semantic_elements"

    # Task-relevant elements only
    TASK_RELEVANT = "task_relevant"

    # Abstract state machine (e.g., "logged_in", "form_filled")
    STATE_MACHINE = "state_machine"

    # Hybrid: abstract + detail where needed
    ADAPTIVE = "adaptive"


# =============================================================================
# Dimension 3: Temporal & Causal Modeling
# Question: How should the simulator model time and causality?
# =============================================================================

class TemporalMode(str, Enum):
    """How temporal aspects are handled."""

    # Instant: actions have immediate effects
    INSTANT = "instant"

    # Async-aware: model loading states, delays
    ASYNC_AWARE = "async_aware"

    # Event-driven: explicit event sequences
    EVENT_DRIVEN = "event_driven"


class CausalMode(str, Enum):
    """How causal relationships are modeled."""

    # Direct: action → immediate effects
    DIRECT = "direct"

    # Chain: reason about multi-step consequences
    CAUSAL_CHAIN = "causal_chain"

    # Counterfactual: consider what-if scenarios
    COUNTERFACTUAL = "counterfactual"


# =============================================================================
# Dimension 4: Uncertainty & Robustness
# Question: How should the simulator handle uncertainty?
# =============================================================================

class UncertaintyMode(str, Enum):
    """How the simulator expresses uncertainty."""

    # Point prediction (deterministic output)
    DETERMINISTIC = "deterministic"

    # Confidence score with prediction
    WITH_CONFIDENCE = "with_confidence"

    # Multiple possible outcomes with probabilities
    PROBABILISTIC = "probabilistic"

    # Explicit "I don't know" for edge cases
    ADMITS_UNCERTAINTY = "admits_uncertainty"


class ErrorHandlingMode(str, Enum):
    """How the simulator handles invalid/unexpected inputs."""

    # Strict: reject invalid actions
    STRICT = "strict"

    # Graceful: attempt reasonable interpretation
    GRACEFUL = "graceful"

    # Realistic: model real system error behaviors
    REALISTIC_ERRORS = "realistic_errors"

    # Robust: try to recover and continue
    ROBUST = "robust"


# =============================================================================
# Dimension 5: Context & Memory
# Question: How should the simulator use context/history?
# =============================================================================

class ContextStrategy(str, Enum):
    """How context window is utilized."""

    # Include full history up to context limit
    FULL_HISTORY = "full_history"

    # Rolling window of recent steps
    ROLLING_WINDOW = "rolling_window"

    # Summarized history (LLM-compressed past)
    SUMMARIZED_HISTORY = "summarized_history"

    # Key checkpoints only
    CHECKPOINTS = "checkpoints"

    # Retrieval-augmented (retrieve relevant past)
    RETRIEVAL_AUGMENTED = "retrieval_augmented"


class MemoryType(str, Enum):
    """What memory is maintained across steps."""

    # Stateless: each step is independent
    STATELESS = "stateless"

    # Episodic: remember this episode's events
    EPISODIC = "episodic"

    # Semantic: remember learned patterns
    SEMANTIC = "semantic"

    # Working memory: maintain task-relevant info
    WORKING_MEMORY = "working_memory"


# =============================================================================
# Dimension 6: Verification & Grounding
# Question: How does the simulator verify its predictions?
# =============================================================================

class VerificationMode(str, Enum):
    """How predictions are verified for consistency."""

    # No verification
    NONE = "none"

    # Self-consistency check (regenerate and compare)
    SELF_CONSISTENCY = "self_consistency"

    # Schema validation only
    SCHEMA_ONLY = "schema_only"

    # Constraint checking (element exists, values valid)
    CONSTRAINT_CHECK = "constraint_check"

    # Backward verification (is this state reachable?)
    BACKWARD_CHECK = "backward_check"


class GroundingStrategy(str, Enum):
    """How the simulator stays grounded to reality."""

    # Trust the LLM's world knowledge
    LLM_KNOWLEDGE = "llm_knowledge"

    # Ground to provided examples
    EXAMPLE_GROUNDED = "example_grounded"

    # Ground to retrieved documentation
    DOC_GROUNDED = "doc_grounded"

    # Ground to execution traces (few real executions)
    TRACE_GROUNDED = "trace_grounded"


# =============================================================================
# Experimental Configuration
# =============================================================================

@dataclass
class ExperimentalDesign:
    """
    A specific configuration in the design space.

    Each configuration represents a hypothesis about what makes
    a good LLM-based simulator.
    """
    name: str
    description: str

    # Core dimensions
    state_output: StateOutputMode = StateOutputMode.FULL_STATE
    state_input: StateInputMode = StateInputMode.FULL_STATE
    prediction_target: PredictionTarget = PredictionTarget.NEXT_STATE
    abstraction_level: AbstractionLevel = AbstractionLevel.FULL_DETAIL

    # Temporal & causal
    temporal_mode: TemporalMode = TemporalMode.INSTANT
    causal_mode: CausalMode = CausalMode.DIRECT

    # Uncertainty & robustness
    uncertainty_mode: UncertaintyMode = UncertaintyMode.DETERMINISTIC
    error_handling: ErrorHandlingMode = ErrorHandlingMode.STRICT

    # Context & memory
    context_strategy: ContextStrategy = ContextStrategy.ROLLING_WINDOW
    memory_type: MemoryType = MemoryType.STATELESS

    # Verification & grounding
    verification: VerificationMode = VerificationMode.SCHEMA_ONLY
    grounding: GroundingStrategy = GroundingStrategy.LLM_KNOWLEDGE

    # Implementation parameters
    context_window_steps: int = 5  # For rolling window
    num_verification_samples: int = 1  # For self-consistency
    confidence_threshold: float = 0.8  # For filtering uncertain predictions

    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "state_output": self.state_output.value,
            "state_input": self.state_input.value,
            "prediction_target": self.prediction_target.value,
            "abstraction_level": self.abstraction_level.value,
            "temporal_mode": self.temporal_mode.value,
            "causal_mode": self.causal_mode.value,
            "uncertainty_mode": self.uncertainty_mode.value,
            "error_handling": self.error_handling.value,
            "context_strategy": self.context_strategy.value,
            "memory_type": self.memory_type.value,
            "verification": self.verification.value,
            "grounding": self.grounding.value,
            "context_window_steps": self.context_window_steps,
            "num_verification_samples": self.num_verification_samples,
            "confidence_threshold": self.confidence_threshold,
            "tags": self.tags,
        }


# =============================================================================
# Hypothesis-Driven Experiments
# =============================================================================

DESIGN_EXPERIMENTS = {
    # ---------------------------------------------------------------------
    # Experiment A: State Output Strategy
    # Hypothesis: Delta-only output is more token-efficient but may
    # accumulate errors. Full state is safer but wasteful.
    # ---------------------------------------------------------------------
    "state_output": {
        "hypothesis": "Delta-based output improves efficiency without sacrificing accuracy if combined with periodic full-state anchoring",
        "configs": [
            ExperimentalDesign(
                name="full_state_baseline",
                description="Output complete state every step (current approach)",
                state_output=StateOutputMode.FULL_STATE,
                tags=["state_output", "baseline"],
            ),
            ExperimentalDesign(
                name="delta_only",
                description="Output only changes from previous state",
                state_output=StateOutputMode.DELTA_ONLY,
                tags=["state_output", "efficient"],
            ),
            ExperimentalDesign(
                name="delta_with_context",
                description="Output changes + surrounding context for grounding",
                state_output=StateOutputMode.DELTA_WITH_CONTEXT,
                tags=["state_output", "balanced"],
            ),
            ExperimentalDesign(
                name="semantic_changes",
                description="Describe changes in natural language",
                state_output=StateOutputMode.SEMANTIC_DESCRIPTION,
                tags=["state_output", "semantic"],
            ),
        ],
    },

    # ---------------------------------------------------------------------
    # Experiment B: Abstraction Level
    # Hypothesis: Operating at semantic level (not full DOM) improves
    # generalization while maintaining task-relevant accuracy.
    # ---------------------------------------------------------------------
    "abstraction": {
        "hypothesis": "Semantic-level abstraction generalizes better than full-detail while task-relevant abstraction maximizes efficiency",
        "configs": [
            ExperimentalDesign(
                name="full_detail",
                description="Full DOM/UI tree with all attributes",
                abstraction_level=AbstractionLevel.FULL_DETAIL,
                tags=["abstraction", "baseline"],
            ),
            ExperimentalDesign(
                name="semantic_only",
                description="Only semantic elements (buttons, inputs, text)",
                abstraction_level=AbstractionLevel.SEMANTIC_ELEMENTS,
                tags=["abstraction", "semantic"],
            ),
            ExperimentalDesign(
                name="task_relevant",
                description="Only elements relevant to current task",
                abstraction_level=AbstractionLevel.TASK_RELEVANT,
                tags=["abstraction", "focused"],
            ),
            ExperimentalDesign(
                name="state_machine",
                description="Abstract state machine representation",
                abstraction_level=AbstractionLevel.STATE_MACHINE,
                tags=["abstraction", "high_level"],
            ),
            ExperimentalDesign(
                name="adaptive",
                description="Hybrid: detail where needed, abstract elsewhere",
                abstraction_level=AbstractionLevel.ADAPTIVE,
                tags=["abstraction", "adaptive"],
            ),
        ],
    },

    # ---------------------------------------------------------------------
    # Experiment C: Uncertainty Handling
    # Hypothesis: Expressing uncertainty improves calibration and allows
    # downstream systems to handle edge cases appropriately.
    # ---------------------------------------------------------------------
    "uncertainty": {
        "hypothesis": "Simulators that express uncertainty have better calibrated predictions and enable safer agent training",
        "configs": [
            ExperimentalDesign(
                name="deterministic",
                description="Point predictions, no uncertainty",
                uncertainty_mode=UncertaintyMode.DETERMINISTIC,
                tags=["uncertainty", "baseline"],
            ),
            ExperimentalDesign(
                name="with_confidence",
                description="Predictions with confidence scores",
                uncertainty_mode=UncertaintyMode.WITH_CONFIDENCE,
                tags=["uncertainty", "calibrated"],
            ),
            ExperimentalDesign(
                name="probabilistic",
                description="Multiple outcomes with probabilities",
                uncertainty_mode=UncertaintyMode.PROBABILISTIC,
                num_verification_samples=3,
                tags=["uncertainty", "distribution"],
            ),
            ExperimentalDesign(
                name="admits_uncertainty",
                description="Explicit 'unknown' for edge cases",
                uncertainty_mode=UncertaintyMode.ADMITS_UNCERTAINTY,
                tags=["uncertainty", "honest"],
            ),
        ],
    },

    # ---------------------------------------------------------------------
    # Experiment D: Causal Reasoning
    # Hypothesis: Simulators with causal chain reasoning predict multi-step
    # consequences better, improving long-horizon task performance.
    # ---------------------------------------------------------------------
    "causality": {
        "hypothesis": "Causal chain reasoning improves prediction of delayed effects and multi-step consequences",
        "configs": [
            ExperimentalDesign(
                name="direct_effects",
                description="Only model immediate action effects",
                causal_mode=CausalMode.DIRECT,
                tags=["causality", "baseline"],
            ),
            ExperimentalDesign(
                name="causal_chain",
                description="Reason about multi-step causal chains",
                causal_mode=CausalMode.CAUSAL_CHAIN,
                tags=["causality", "chain"],
            ),
            ExperimentalDesign(
                name="counterfactual",
                description="Consider alternative action outcomes",
                causal_mode=CausalMode.COUNTERFACTUAL,
                tags=["causality", "counterfactual"],
            ),
        ],
    },

    # ---------------------------------------------------------------------
    # Experiment E: Context Strategy
    # Hypothesis: Smart context usage (summarization, retrieval) outperforms
    # naive full history when episodes are long.
    # ---------------------------------------------------------------------
    "context": {
        "hypothesis": "Summarized or retrieval-augmented context outperforms full history for long episodes",
        "configs": [
            ExperimentalDesign(
                name="full_history",
                description="Include complete episode history",
                context_strategy=ContextStrategy.FULL_HISTORY,
                tags=["context", "baseline"],
            ),
            ExperimentalDesign(
                name="rolling_5",
                description="Rolling window of 5 recent steps",
                context_strategy=ContextStrategy.ROLLING_WINDOW,
                context_window_steps=5,
                tags=["context", "window"],
            ),
            ExperimentalDesign(
                name="rolling_10",
                description="Rolling window of 10 recent steps",
                context_strategy=ContextStrategy.ROLLING_WINDOW,
                context_window_steps=10,
                tags=["context", "window"],
            ),
            ExperimentalDesign(
                name="summarized",
                description="LLM-summarized history",
                context_strategy=ContextStrategy.SUMMARIZED_HISTORY,
                tags=["context", "compressed"],
            ),
            ExperimentalDesign(
                name="checkpoints",
                description="Keep only key checkpoints",
                context_strategy=ContextStrategy.CHECKPOINTS,
                tags=["context", "sparse"],
            ),
            ExperimentalDesign(
                name="retrieval",
                description="Retrieve relevant past based on current state",
                context_strategy=ContextStrategy.RETRIEVAL_AUGMENTED,
                tags=["context", "retrieval"],
            ),
        ],
    },

    # ---------------------------------------------------------------------
    # Experiment F: Verification Strategy
    # Hypothesis: Self-consistency verification catches errors and improves
    # reliability, especially for edge cases.
    # ---------------------------------------------------------------------
    "verification": {
        "hypothesis": "Self-consistency verification improves prediction reliability with acceptable compute overhead",
        "configs": [
            ExperimentalDesign(
                name="no_verification",
                description="No verification, trust first prediction",
                verification=VerificationMode.NONE,
                tags=["verification", "baseline"],
            ),
            ExperimentalDesign(
                name="schema_only",
                description="Verify JSON schema compliance only",
                verification=VerificationMode.SCHEMA_ONLY,
                tags=["verification", "basic"],
            ),
            ExperimentalDesign(
                name="self_consistency_3",
                description="Generate 3 predictions, take majority",
                verification=VerificationMode.SELF_CONSISTENCY,
                num_verification_samples=3,
                tags=["verification", "ensemble"],
            ),
            ExperimentalDesign(
                name="constraint_check",
                description="Verify constraints (element exists, valid values)",
                verification=VerificationMode.CONSTRAINT_CHECK,
                tags=["verification", "constraints"],
            ),
            ExperimentalDesign(
                name="backward_check",
                description="Verify state is reachable from previous",
                verification=VerificationMode.BACKWARD_CHECK,
                tags=["verification", "bidirectional"],
            ),
        ],
    },

    # ---------------------------------------------------------------------
    # Experiment G: Grounding Strategy
    # Hypothesis: Grounding to real execution traces improves realism
    # compared to relying solely on LLM world knowledge.
    # ---------------------------------------------------------------------
    "grounding": {
        "hypothesis": "Trace-grounded simulators produce more realistic predictions than pure LLM knowledge",
        "configs": [
            ExperimentalDesign(
                name="llm_knowledge",
                description="Rely on LLM's learned world knowledge",
                grounding=GroundingStrategy.LLM_KNOWLEDGE,
                tags=["grounding", "baseline"],
            ),
            ExperimentalDesign(
                name="example_grounded",
                description="Ground to in-context examples",
                grounding=GroundingStrategy.EXAMPLE_GROUNDED,
                tags=["grounding", "icl"],
            ),
            ExperimentalDesign(
                name="doc_grounded",
                description="Ground to retrieved documentation",
                grounding=GroundingStrategy.DOC_GROUNDED,
                tags=["grounding", "rag"],
            ),
            ExperimentalDesign(
                name="trace_grounded",
                description="Ground to real execution traces",
                grounding=GroundingStrategy.TRACE_GROUNDED,
                tags=["grounding", "hybrid"],
            ),
        ],
    },

    # ---------------------------------------------------------------------
    # Experiment H: Temporal Modeling
    # Hypothesis: Async-aware modeling handles real-world UI behavior
    # (loading states, animations) better than instant mode.
    # ---------------------------------------------------------------------
    "temporal": {
        "hypothesis": "Async-aware temporal modeling better captures real UI behavior",
        "configs": [
            ExperimentalDesign(
                name="instant",
                description="All actions have instant effects",
                temporal_mode=TemporalMode.INSTANT,
                tags=["temporal", "baseline"],
            ),
            ExperimentalDesign(
                name="async_aware",
                description="Model loading states and delays",
                temporal_mode=TemporalMode.ASYNC_AWARE,
                tags=["temporal", "async"],
            ),
            ExperimentalDesign(
                name="event_driven",
                description="Model explicit event sequences",
                temporal_mode=TemporalMode.EVENT_DRIVEN,
                tags=["temporal", "events"],
            ),
        ],
    },
}


def get_experiment(name: str) -> dict:
    """Get a specific experiment configuration."""
    return DESIGN_EXPERIMENTS.get(name, {})


def get_all_experiments() -> dict:
    """Get all experiments."""
    return DESIGN_EXPERIMENTS


def get_experiment_configs(name: str) -> list[ExperimentalDesign]:
    """Get configs for a specific experiment."""
    exp = DESIGN_EXPERIMENTS.get(name, {})
    return exp.get("configs", [])


def get_hypothesis(name: str) -> str:
    """Get the hypothesis for an experiment."""
    exp = DESIGN_EXPERIMENTS.get(name, {})
    return exp.get("hypothesis", "")


# =============================================================================
# Combined Experiments: Testing Interactions
# =============================================================================

def get_interaction_experiments() -> list[ExperimentalDesign]:
    """
    Generate experiments testing interactions between design choices.

    These test whether certain combinations work better together.
    """
    configs = []

    # Hypothesis: Delta output + semantic abstraction is highly efficient
    configs.append(ExperimentalDesign(
        name="efficient_combo",
        description="Delta output + semantic abstraction for efficiency",
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction_level=AbstractionLevel.SEMANTIC_ELEMENTS,
        tags=["interaction", "efficiency"],
    ))

    # Hypothesis: Uncertainty + verification catches more errors
    configs.append(ExperimentalDesign(
        name="robust_combo",
        description="Uncertainty + self-consistency for robustness",
        uncertainty_mode=UncertaintyMode.WITH_CONFIDENCE,
        verification=VerificationMode.SELF_CONSISTENCY,
        num_verification_samples=3,
        tags=["interaction", "robustness"],
    ))

    # Hypothesis: Causal + trace grounding improves realism
    configs.append(ExperimentalDesign(
        name="realistic_combo",
        description="Causal reasoning + trace grounding for realism",
        causal_mode=CausalMode.CAUSAL_CHAIN,
        grounding=GroundingStrategy.TRACE_GROUNDED,
        tags=["interaction", "realism"],
    ))

    # Hypothesis: Summarized context + adaptive abstraction scales well
    configs.append(ExperimentalDesign(
        name="scalable_combo",
        description="Summarized history + adaptive abstraction for scale",
        context_strategy=ContextStrategy.SUMMARIZED_HISTORY,
        abstraction_level=AbstractionLevel.ADAPTIVE,
        tags=["interaction", "scalability"],
    ))

    # Hypothesis: Full verification + async-aware is most accurate
    configs.append(ExperimentalDesign(
        name="accurate_combo",
        description="Full verification + async-aware for accuracy",
        verification=VerificationMode.BACKWARD_CHECK,
        temporal_mode=TemporalMode.ASYNC_AWARE,
        tags=["interaction", "accuracy"],
    ))

    return configs
