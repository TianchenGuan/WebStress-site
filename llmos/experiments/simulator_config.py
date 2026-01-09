"""
SimulatorConfig: Captures all design choices for the LLM simulator.

This module defines the configuration space for simulator ablation studies.
Each configuration represents a specific design choice that can be varied
to study its impact on simulator fidelity.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import json
import hashlib


class LLMProvider(str, Enum):
    """Supported LLM providers for the simulator."""
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    LOCAL = "local"  # For local models via vLLM/Ollama


class StateRepresentation(str, Enum):
    """How state is represented to the simulator LLM."""
    FULL_JSON = "full_json"           # Complete JSON state
    FILTERED_JSON = "filtered_json"   # Remove hidden_state, truncate
    TEXT_AXTREE = "text_axtree"       # Accessibility tree as text
    COMPRESSED = "compressed"          # LLM-summarized state
    HYBRID = "hybrid"                  # JSON structure + text description


class ActionFormat(str, Enum):
    """How actions are represented."""
    FULL = "full"                      # All 14 action types
    SIMPLIFIED = "simplified"          # Core 5 actions (click, fill, scroll, goto, finish)
    NATURAL_LANGUAGE = "natural_lang"  # Free-form action description


class HistoryMode(str, Enum):
    """How action history is included."""
    NONE = "none"                      # No history
    LAST_N = "last_n"                  # Last N actions
    FULL = "full"                      # Complete history
    SUMMARIZED = "summarized"          # LLM-summarized history


@dataclass
class PromptConfig:
    """Configuration for simulator prompt design."""

    # Prompt style
    use_chain_of_thought: bool = True
    include_examples: bool = True
    num_examples: int = 2

    # Instructions detail level
    detailed_instructions: bool = True
    include_error_handling: bool = True
    include_edge_cases: bool = True

    # Output format
    require_thought_field: bool = True
    require_events_field: bool = True
    strict_json_schema: bool = True

    # Custom prompt path (overrides defaults if set)
    custom_prompt_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "use_chain_of_thought": self.use_chain_of_thought,
            "include_examples": self.include_examples,
            "num_examples": self.num_examples,
            "detailed_instructions": self.detailed_instructions,
            "include_error_handling": self.include_error_handling,
            "include_edge_cases": self.include_edge_cases,
            "require_thought_field": self.require_thought_field,
            "require_events_field": self.require_events_field,
            "strict_json_schema": self.strict_json_schema,
            "custom_prompt_path": self.custom_prompt_path,
        }


@dataclass
class StateRepresentationConfig:
    """Configuration for state representation to simulator."""

    mode: StateRepresentation = StateRepresentation.FULL_JSON

    # Filtering options
    include_hidden_state: bool = True
    include_filesystem: bool = True
    include_tabs: bool = True

    # Truncation
    max_ui_depth: Optional[int] = None  # None = no limit
    max_children_per_node: Optional[int] = None
    max_text_length: int = 500
    max_file_content_length: int = 1000

    # Compression (for COMPRESSED mode)
    compression_model: Optional[str] = None  # Model for summarization

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "include_hidden_state": self.include_hidden_state,
            "include_filesystem": self.include_filesystem,
            "include_tabs": self.include_tabs,
            "max_ui_depth": self.max_ui_depth,
            "max_children_per_node": self.max_children_per_node,
            "max_text_length": self.max_text_length,
            "max_file_content_length": self.max_file_content_length,
            "compression_model": self.compression_model,
        }


@dataclass
class SimulatorConfig:
    """
    Complete configuration for a simulator variant.

    This captures all design choices that can be varied in ablation studies.
    Each unique configuration produces a different simulator behavior.

    Example usage:
        # Create a baseline config
        baseline = SimulatorConfig(
            name="baseline_gpt4o",
            llm_provider=LLMProvider.OPENAI,
            llm_model="gpt-4o",
        )

        # Create a variant with different LLM
        gemini_variant = baseline.with_changes(
            name="gemini_variant",
            llm_provider=LLMProvider.GEMINI,
            llm_model="gemini-1.5-pro",
        )
    """

    # Identifier
    name: str
    description: str = ""

    # LLM Configuration
    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_model: str = "gpt-4o"
    temperature: float = 0.0  # Deterministic by default for reproducibility
    max_tokens: int = 2048

    # Prompt Configuration
    prompt_config: PromptConfig = field(default_factory=PromptConfig)

    # State Representation
    state_config: StateRepresentationConfig = field(default_factory=StateRepresentationConfig)

    # Action Space
    action_format: ActionFormat = ActionFormat.FULL

    # History
    history_mode: HistoryMode = HistoryMode.LAST_N
    history_length: int = 5  # For LAST_N mode

    # Difficulty (maps to LLMOS difficulty settings)
    information_density: str = "rich"      # minimal, moderate, rich
    signal_noise_ratio: str = "clean"      # clean, moderate, noisy
    determinism: str = "deterministic"     # deterministic, moderate, stochastic

    # Retry/Error Handling
    max_retries: int = 3
    retry_on_invalid_json: bool = True

    # Metadata
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate configuration."""
        if self.history_mode == HistoryMode.LAST_N and self.history_length <= 0:
            raise ValueError("history_length must be > 0 when using LAST_N mode")

    @property
    def config_hash(self) -> str:
        """Generate a unique hash for this configuration."""
        config_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:12]

    @property
    def short_id(self) -> str:
        """Short identifier for this config."""
        return f"{self.name}_{self.config_hash}"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "llm_provider": self.llm_provider.value,
            "llm_model": self.llm_model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "prompt_config": self.prompt_config.to_dict(),
            "state_config": self.state_config.to_dict(),
            "action_format": self.action_format.value,
            "history_mode": self.history_mode.value,
            "history_length": self.history_length,
            "information_density": self.information_density,
            "signal_noise_ratio": self.signal_noise_ratio,
            "determinism": self.determinism,
            "max_retries": self.max_retries,
            "retry_on_invalid_json": self.retry_on_invalid_json,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimulatorConfig":
        """Create from dictionary."""
        prompt_config = PromptConfig(**data.pop("prompt_config", {}))

        state_config_data = data.pop("state_config", {})
        if "mode" in state_config_data:
            state_config_data["mode"] = StateRepresentation(state_config_data["mode"])
        state_config = StateRepresentationConfig(**state_config_data)

        if "llm_provider" in data:
            data["llm_provider"] = LLMProvider(data["llm_provider"])
        if "action_format" in data:
            data["action_format"] = ActionFormat(data["action_format"])
        if "history_mode" in data:
            data["history_mode"] = HistoryMode(data["history_mode"])

        return cls(
            prompt_config=prompt_config,
            state_config=state_config,
            **data,
        )

    def with_changes(self, **kwargs) -> "SimulatorConfig":
        """Create a new config with specified changes."""
        data = self.to_dict()

        # Handle nested configs specially
        if "prompt_config" in kwargs and isinstance(kwargs["prompt_config"], dict):
            data["prompt_config"].update(kwargs.pop("prompt_config"))
        if "state_config" in kwargs and isinstance(kwargs["state_config"], dict):
            data["state_config"].update(kwargs.pop("state_config"))

        data.update(kwargs)
        return SimulatorConfig.from_dict(data)

    def save(self, path: str) -> None:
        """Save configuration to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "SimulatorConfig":
        """Load configuration from JSON file."""
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))


# =============================================================================
# Preset Configurations for Common Ablation Studies
# =============================================================================

SIMULATOR_PRESETS: dict[str, SimulatorConfig] = {
    # Baseline: Full-featured simulator with GPT-4o
    "baseline_gpt4o": SimulatorConfig(
        name="baseline_gpt4o",
        description="Baseline simulator with GPT-4o and full features",
        llm_provider=LLMProvider.OPENAI,
        llm_model="gpt-4o",
        tags=["baseline", "gpt4o"],
    ),

    # LLM Provider Variants
    "gemini_pro": SimulatorConfig(
        name="gemini_pro",
        description="Gemini 1.5 Pro variant",
        llm_provider=LLMProvider.GEMINI,
        llm_model="gemini-1.5-pro",
        tags=["llm_ablation", "gemini"],
    ),

    "gpt4o_mini": SimulatorConfig(
        name="gpt4o_mini",
        description="GPT-4o-mini (smaller, faster)",
        llm_provider=LLMProvider.OPENAI,
        llm_model="gpt-4o-mini",
        tags=["llm_ablation", "gpt4o_mini"],
    ),

    # Prompt Design Variants
    "minimal_prompt": SimulatorConfig(
        name="minimal_prompt",
        description="Minimal prompt without examples or detailed instructions",
        prompt_config=PromptConfig(
            use_chain_of_thought=False,
            include_examples=False,
            detailed_instructions=False,
            include_error_handling=False,
            include_edge_cases=False,
        ),
        tags=["prompt_ablation", "minimal"],
    ),

    "no_cot": SimulatorConfig(
        name="no_cot",
        description="No chain-of-thought reasoning",
        prompt_config=PromptConfig(
            use_chain_of_thought=False,
            require_thought_field=False,
        ),
        tags=["prompt_ablation", "no_cot"],
    ),

    # State Representation Variants
    "text_only": SimulatorConfig(
        name="text_only",
        description="Text-only accessibility tree representation",
        state_config=StateRepresentationConfig(
            mode=StateRepresentation.TEXT_AXTREE,
        ),
        tags=["state_ablation", "text_only"],
    ),

    "filtered_state": SimulatorConfig(
        name="filtered_state",
        description="Filtered state without hidden_state",
        state_config=StateRepresentationConfig(
            mode=StateRepresentation.FILTERED_JSON,
            include_hidden_state=False,
        ),
        tags=["state_ablation", "filtered"],
    ),

    "truncated_state": SimulatorConfig(
        name="truncated_state",
        description="Truncated state with depth limits",
        state_config=StateRepresentationConfig(
            max_ui_depth=5,
            max_children_per_node=10,
            max_text_length=200,
        ),
        tags=["state_ablation", "truncated"],
    ),

    # History Variants
    "no_history": SimulatorConfig(
        name="no_history",
        description="No action history provided",
        history_mode=HistoryMode.NONE,
        tags=["history_ablation", "no_history"],
    ),

    "full_history": SimulatorConfig(
        name="full_history",
        description="Full action history",
        history_mode=HistoryMode.FULL,
        tags=["history_ablation", "full_history"],
    ),

    "short_history": SimulatorConfig(
        name="short_history",
        description="Only last 2 actions",
        history_mode=HistoryMode.LAST_N,
        history_length=2,
        tags=["history_ablation", "short_history"],
    ),

    # Action Space Variants
    "simplified_actions": SimulatorConfig(
        name="simplified_actions",
        description="Simplified action space (5 core actions)",
        action_format=ActionFormat.SIMPLIFIED,
        tags=["action_ablation", "simplified"],
    ),

    # Difficulty Variants
    "noisy": SimulatorConfig(
        name="noisy",
        description="Noisy state with stochastic behavior",
        signal_noise_ratio="noisy",
        determinism="stochastic",
        tags=["difficulty_ablation", "noisy"],
    ),

    "minimal_info": SimulatorConfig(
        name="minimal_info",
        description="Minimal information density",
        information_density="minimal",
        tags=["difficulty_ablation", "minimal_info"],
    ),
}


def get_ablation_configs(
    baseline: SimulatorConfig,
    variable: str,
    values: list[Any],
) -> list[SimulatorConfig]:
    """
    Generate configs for ablating a single variable.

    Args:
        baseline: Base configuration to modify.
        variable: Name of variable to ablate (e.g., "llm_model", "history_length").
        values: List of values to try for the variable.

    Returns:
        List of configs, one for each value.

    Example:
        configs = get_ablation_configs(
            baseline=SIMULATOR_PRESETS["baseline_gpt4o"],
            variable="history_length",
            values=[0, 2, 5, 10, 20],
        )
    """
    configs = []
    for value in values:
        config = baseline.with_changes(
            name=f"{baseline.name}_{variable}_{value}",
            tags=baseline.tags + [f"{variable}_ablation"],
            **{variable: value},
        )
        configs.append(config)
    return configs
