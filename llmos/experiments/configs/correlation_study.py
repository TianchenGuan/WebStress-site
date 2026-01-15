"""
Configuration definitions for simulator correlation study.

This module defines all 20 configurations for the sequential ablation study
to find which simulator design choices correlate best with real benchmark scores.

Phases:
    1. Baseline: Default configuration
    2.1. State Output: full_state, delta_only, semantic_description
    2.2. Abstraction: full_dom, semantic_elements, task_relevant, viewport_only, interactive_only
    2.3. Memory: full_history, rolling_window (3, 5, 10), summarized
    2.4. Reasoning: direct, chain
    2.5. Verification: none, schema, constraint_check, backward
"""

from dataclasses import dataclass, field
from typing import Optional

from ...core.unified_simulator import (
    SimulatorConfig,
    StateOutputMode,
    AbstractionLevel,
    MemoryMode,
    ReasoningMode,
    VerificationMode,
    TemporalMode,
    UncertaintyMode,
    GroundingStrategy,
)


# =============================================================================
# Agent Definitions
# =============================================================================

@dataclass
class AgentConfig:
    """Configuration for an agent to test."""
    agent_id: str
    model_name: str
    provider: str = "openai"
    real_score: Optional[float] = None  # Real WorkArena-L2 score

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "model_name": self.model_name,
            "provider": self.provider,
            "real_score": self.real_score,
        }


# Target agents for correlation study
STUDY_AGENTS = [
    AgentConfig(
        agent_id="gpt-5-mini",
        model_name="gpt-5-mini",
        provider="openai",
        real_score=47.70,
    ),
    AgentConfig(
        agent_id="gpt-o1-mini",
        model_name="o1-mini",
        provider="openai",
        real_score=14.90,
    ),
    AgentConfig(
        agent_id="gpt-4o-mini",
        model_name="gpt-4o-mini",
        provider="openai",
        real_score=1.30,
    ),
]

# Real scores for correlation calculation
REAL_SCORES = {agent.agent_id: agent.real_score for agent in STUDY_AGENTS}


# =============================================================================
# Simulator LLM Configuration
# =============================================================================

SIMULATOR_LLM_CONFIG = {
    "provider": "gemini",
    "model": "gemini-3-flash-preview",
}


# =============================================================================
# Base Configuration (shared settings)
# =============================================================================

def get_base_config() -> dict:
    """Get base configuration settings shared across all experiments."""
    return {
        "llm_provider": SIMULATOR_LLM_CONFIG["provider"],
        "llm_model": SIMULATOR_LLM_CONFIG["model"],
        "max_tokens": 4096,
        "max_steps_per_episode": 50,
        "max_retries": 3,
        "domain": "servicenow",  # WorkArena is ServiceNow-based
        "temporal": TemporalMode.INSTANT,
        "uncertainty": UncertaintyMode.DETERMINISTIC,
        "grounding": GroundingStrategy.LLM_KNOWLEDGE,
    }


# =============================================================================
# Phase 1: Baseline Configuration
# =============================================================================

BASELINE_CONFIG = SimulatorConfig(
    state_output=StateOutputMode.DELTA_ONLY,
    abstraction=AbstractionLevel.FULL_DOM,
    memory=MemoryMode.ROLLING_WINDOW,
    memory_window=5,
    reasoning=ReasoningMode.DIRECT,
    verification=VerificationMode.SCHEMA,
    **get_base_config(),
)


# =============================================================================
# Phase 2.1: State Output Ablation
# =============================================================================

STATE_OUTPUT_CONFIGS = {
    "so_full": SimulatorConfig(
        state_output=StateOutputMode.FULL_STATE,
        abstraction=AbstractionLevel.FULL_DOM,
        memory=MemoryMode.ROLLING_WINDOW,
        memory_window=5,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.SCHEMA,
        **get_base_config(),
    ),
    "so_delta": SimulatorConfig(
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction=AbstractionLevel.FULL_DOM,
        memory=MemoryMode.ROLLING_WINDOW,
        memory_window=5,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.SCHEMA,
        **get_base_config(),
    ),
    "so_semantic": SimulatorConfig(
        state_output=StateOutputMode.SEMANTIC_DESCRIPTION,
        abstraction=AbstractionLevel.FULL_DOM,
        memory=MemoryMode.ROLLING_WINDOW,
        memory_window=5,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.SCHEMA,
        **get_base_config(),
    ),
}


# =============================================================================
# Phase 2.2: Abstraction Level Ablation
# (Uses best state_output from Phase 2.1 - will be updated at runtime)
# =============================================================================

def get_abstraction_configs(best_state_output: StateOutputMode = StateOutputMode.DELTA_ONLY) -> dict:
    """Get abstraction ablation configs with the best state output from Phase 2.1."""
    base = get_base_config()
    return {
        "abs_full": SimulatorConfig(
            state_output=best_state_output,
            abstraction=AbstractionLevel.FULL_DOM,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=5,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "abs_semantic": SimulatorConfig(
            state_output=best_state_output,
            abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=5,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "abs_task": SimulatorConfig(
            state_output=best_state_output,
            abstraction=AbstractionLevel.TASK_RELEVANT,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=5,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "abs_viewport": SimulatorConfig(
            state_output=best_state_output,
            abstraction=AbstractionLevel.VIEWPORT_ONLY,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=5,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "abs_interactive": SimulatorConfig(
            state_output=best_state_output,
            abstraction=AbstractionLevel.INTERACTIVE_ONLY,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=5,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
    }


# =============================================================================
# Phase 2.3: Memory/Context Ablation
# =============================================================================

def get_memory_configs(
    best_state_output: StateOutputMode = StateOutputMode.DELTA_ONLY,
    best_abstraction: AbstractionLevel = AbstractionLevel.FULL_DOM,
) -> dict:
    """Get memory ablation configs with best settings from previous phases."""
    base = get_base_config()
    return {
        "mem_full": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=MemoryMode.FULL_HISTORY,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "mem_roll3": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=3,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "mem_roll5": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=5,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "mem_roll10": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=10,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "mem_summary": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=MemoryMode.SUMMARIZED,
            memory_recent_steps=3,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
    }


# =============================================================================
# Phase 2.4: Reasoning Mode Ablation
# =============================================================================

def get_reasoning_configs(
    best_state_output: StateOutputMode = StateOutputMode.DELTA_ONLY,
    best_abstraction: AbstractionLevel = AbstractionLevel.FULL_DOM,
    best_memory: MemoryMode = MemoryMode.ROLLING_WINDOW,
    best_memory_window: int = 5,
) -> dict:
    """Get reasoning ablation configs with best settings from previous phases."""
    base = get_base_config()
    return {
        "reas_direct": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=best_memory,
            memory_window=best_memory_window,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "reas_chain": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=best_memory,
            memory_window=best_memory_window,
            reasoning=ReasoningMode.CHAIN,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
    }


# =============================================================================
# Phase 2.5: Verification Mode Ablation
# =============================================================================

def get_verification_configs(
    best_state_output: StateOutputMode = StateOutputMode.DELTA_ONLY,
    best_abstraction: AbstractionLevel = AbstractionLevel.FULL_DOM,
    best_memory: MemoryMode = MemoryMode.ROLLING_WINDOW,
    best_memory_window: int = 5,
    best_reasoning: ReasoningMode = ReasoningMode.DIRECT,
) -> dict:
    """Get verification ablation configs with best settings from previous phases."""
    base = get_base_config()
    return {
        "ver_none": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=best_memory,
            memory_window=best_memory_window,
            reasoning=best_reasoning,
            verification=VerificationMode.NONE,
            **base,
        ),
        "ver_schema": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=best_memory,
            memory_window=best_memory_window,
            reasoning=best_reasoning,
            verification=VerificationMode.SCHEMA,
            **base,
        ),
        "ver_constraint": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=best_memory,
            memory_window=best_memory_window,
            reasoning=best_reasoning,
            verification=VerificationMode.CONSTRAINT_CHECK,
            **base,
        ),
        "ver_backward": SimulatorConfig(
            state_output=best_state_output,
            abstraction=best_abstraction,
            memory=best_memory,
            memory_window=best_memory_window,
            reasoning=best_reasoning,
            verification=VerificationMode.BACKWARD,
            **base,
        ),
    }


# =============================================================================
# All Configurations (for reference)
# =============================================================================

# Initial configurations (before sequential selection)
ALL_INITIAL_CONFIGS = {
    "baseline": BASELINE_CONFIG,
    **STATE_OUTPUT_CONFIGS,
    **get_abstraction_configs(),
    **get_memory_configs(),
    **get_reasoning_configs(),
    **get_verification_configs(),
}


# =============================================================================
# Phase Management
# =============================================================================

@dataclass
class PhaseConfig:
    """Configuration for an experiment phase."""
    phase_id: str
    phase_name: str
    dimension: str
    config_ids: list[str]
    hypothesis: str


PHASES = [
    PhaseConfig(
        phase_id="baseline",
        phase_name="Phase 1: Baseline",
        dimension="baseline",
        config_ids=["baseline"],
        hypothesis="Establish baseline correlation.",
    ),
    PhaseConfig(
        phase_id="state_output",
        phase_name="Phase 2.1: State Output",
        dimension="state_output",
        config_ids=["so_full", "so_delta", "so_semantic"],
        hypothesis="Delta-based or semantic output reduces noise and improves correlation.",
    ),
    PhaseConfig(
        phase_id="abstraction",
        phase_name="Phase 2.2: Abstraction",
        dimension="abstraction",
        config_ids=["abs_full", "abs_semantic", "abs_task", "abs_viewport", "abs_interactive"],
        hypothesis="Semantic-level abstraction generalizes better than full DOM.",
    ),
    PhaseConfig(
        phase_id="memory",
        phase_name="Phase 2.3: Memory",
        dimension="memory",
        config_ids=["mem_full", "mem_roll3", "mem_roll5", "mem_roll10", "mem_summary"],
        hypothesis="Rolling window works best for L2 multi-step tasks.",
    ),
    PhaseConfig(
        phase_id="reasoning",
        phase_name="Phase 2.4: Reasoning",
        dimension="reasoning",
        config_ids=["reas_direct", "reas_chain"],
        hypothesis="Chain reasoning improves predictions for complex multi-step tasks.",
    ),
    PhaseConfig(
        phase_id="verification",
        phase_name="Phase 2.5: Verification",
        dimension="verification",
        config_ids=["ver_none", "ver_schema", "ver_constraint", "ver_backward"],
        hypothesis="Constraint checking catches errors and improves consistency.",
    ),
]


def get_phase(phase_id: str) -> PhaseConfig:
    """Get phase configuration by ID."""
    for phase in PHASES:
        if phase.phase_id == phase_id:
            return phase
    raise ValueError(f"Unknown phase: {phase_id}")


def get_configs_for_phase(
    phase_id: str,
    best_state_output: Optional[StateOutputMode] = None,
    best_abstraction: Optional[AbstractionLevel] = None,
    best_memory: Optional[MemoryMode] = None,
    best_memory_window: int = 5,
    best_reasoning: Optional[ReasoningMode] = None,
) -> dict[str, SimulatorConfig]:
    """
    Get configurations for a phase, using best settings from previous phases.

    Args:
        phase_id: Phase identifier.
        best_state_output: Best state output from Phase 2.1.
        best_abstraction: Best abstraction from Phase 2.2.
        best_memory: Best memory mode from Phase 2.3.
        best_memory_window: Best memory window from Phase 2.3.
        best_reasoning: Best reasoning mode from Phase 2.4.

    Returns:
        Dictionary mapping config IDs to SimulatorConfig objects.
    """
    # Use defaults if not specified
    best_state_output = best_state_output or StateOutputMode.DELTA_ONLY
    best_abstraction = best_abstraction or AbstractionLevel.FULL_DOM
    best_memory = best_memory or MemoryMode.ROLLING_WINDOW
    best_reasoning = best_reasoning or ReasoningMode.DIRECT

    if phase_id == "baseline":
        return {"baseline": BASELINE_CONFIG}

    elif phase_id == "state_output":
        return STATE_OUTPUT_CONFIGS

    elif phase_id == "abstraction":
        return get_abstraction_configs(best_state_output)

    elif phase_id == "memory":
        return get_memory_configs(best_state_output, best_abstraction)

    elif phase_id == "reasoning":
        return get_reasoning_configs(
            best_state_output, best_abstraction, best_memory, best_memory_window
        )

    elif phase_id == "verification":
        return get_verification_configs(
            best_state_output, best_abstraction, best_memory, best_memory_window, best_reasoning
        )

    else:
        raise ValueError(f"Unknown phase: {phase_id}")


def get_all_phase_ids() -> list[str]:
    """Get list of all phase IDs in order."""
    return [phase.phase_id for phase in PHASES]
