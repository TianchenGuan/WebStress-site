"""
Unified Simulator for LLMOS.

A fully modular, configurable simulator that can be used for both production
training and experimental analysis. Configured via config file or programmatically.

Key Features:
- 8 composable modules (state_output, abstraction, memory, reasoning,
  verification, temporal, uncertainty, grounding)
- Difficulty configuration (easy, medium, hard, expert)
- Presets for common configurations including "classic" for original behavior
- Robust error handling and history tracking
- Configuration file support

Usage:
    # From config file
    sim = Simulator.from_config("config.json")

    # With preset
    sim = Simulator.from_preset("classic")  # Original behavior
    sim = Simulator.from_preset("efficient")  # Optimized for speed

    # Programmatic
    sim = Simulator(
        state_output="delta_only",
        abstraction="semantic_elements",
        uncertainty="with_confidence",
    )
"""

import copy
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Union

from ..utils.llm_client import LLMClient
from ..utils.patching import apply_id_patch, validate_ops
from ..utils.rendering import render_observation
from ..utils.validation import validate_action_complete
from .difficulty import (
    DifficultyConfig,
    get_difficulty_config,
    get_difficulty_from_dict,
    build_difficulty_prompt,
)

# Import module components
from ..experiments.modules.state_output import (
    StateOutputMode,
    StateOutputModule,
)
from ..experiments.modules.abstraction import (
    AbstractionLevel,
    AbstractionModule,
)
from ..experiments.modules.memory import (
    MemoryMode,
    MemoryModule,
)
from ..experiments.modules.reasoning import (
    ReasoningMode,
    ReasoningModule,
)
from ..experiments.modules.verification import (
    VerificationMode,
    VerificationModule,
)
from ..experiments.modules.temporal import (
    TemporalMode,
    TemporalModule,
)
from ..experiments.modules.uncertainty import (
    UncertaintyMode,
    UncertaintyModule,
)
from ..experiments.modules.grounding import (
    GroundingStrategy,
    GroundingModule,
)
from ..experiments.modules.prompt_blocks import build_simulator_prompt

logger = logging.getLogger(__name__)


class SimulatorError(Exception):
    """Exception raised for simulator errors."""
    pass


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SimulatorConfig:
    """
    Complete simulator configuration.

    This dataclass defines all configurable aspects of the simulator,
    from module choices to LLM settings to difficulty.
    """

    # Module configurations
    state_output: StateOutputMode = StateOutputMode.DELTA_ONLY
    abstraction: AbstractionLevel = AbstractionLevel.FULL_DOM
    memory: MemoryMode = MemoryMode.ROLLING_WINDOW
    reasoning: ReasoningMode = ReasoningMode.DIRECT
    verification: VerificationMode = VerificationMode.SCHEMA
    temporal: TemporalMode = TemporalMode.INSTANT
    uncertainty: UncertaintyMode = UncertaintyMode.DETERMINISTIC
    grounding: GroundingStrategy = GroundingStrategy.LLM_KNOWLEDGE

    # Module parameters
    memory_window: int = 5
    memory_recent_steps: int = 3
    memory_max_checkpoints: int = 10
    include_hidden_elements: bool = False
    reasoning_include_examples: bool = True
    verification_strict: bool = False
    uncertainty_min_confidence: float = 0.0
    uncertainty_selection_strategy: str = "most_likely"

    # LLM configuration
    llm_provider: Optional[str] = None  # None = use default from config
    llm_model: Optional[str] = None
    max_tokens: int = 4096

    # Difficulty configuration
    difficulty_preset: Optional[str] = None  # "easy", "medium", "hard", "expert"
    difficulty_config: Optional[dict] = None  # Custom difficulty

    # Episode configuration
    max_steps_per_episode: int = 50
    max_retries: int = 3

    # Domain configuration
    domain: Optional[str] = None  # "web", "desktop", "servicenow"

    # Prompt configuration
    use_classic_prompt: bool = False  # Use original simulator.system.md prompt
    custom_system_prompt: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        def get_value(x):
            """Get string value from enum or return string as-is."""
            return x.value if hasattr(x, 'value') else x

        return {
            "state_output": get_value(self.state_output),
            "abstraction": get_value(self.abstraction),
            "memory": get_value(self.memory),
            "reasoning": get_value(self.reasoning),
            "verification": get_value(self.verification),
            "temporal": get_value(self.temporal),
            "uncertainty": get_value(self.uncertainty),
            "grounding": get_value(self.grounding),
            "memory_window": self.memory_window,
            "memory_recent_steps": self.memory_recent_steps,
            "memory_max_checkpoints": self.memory_max_checkpoints,
            "include_hidden_elements": self.include_hidden_elements,
            "reasoning_include_examples": self.reasoning_include_examples,
            "verification_strict": self.verification_strict,
            "uncertainty_min_confidence": self.uncertainty_min_confidence,
            "uncertainty_selection_strategy": self.uncertainty_selection_strategy,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "max_tokens": self.max_tokens,
            "difficulty_preset": self.difficulty_preset,
            "difficulty_config": self.difficulty_config,
            "max_steps_per_episode": self.max_steps_per_episode,
            "max_retries": self.max_retries,
            "domain": self.domain,
            "use_classic_prompt": self.use_classic_prompt,
            "custom_system_prompt": self.custom_system_prompt,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SimulatorConfig":
        """Create config from dictionary."""
        # Parse enum values
        state_output = d.get("state_output", "delta_only")
        if isinstance(state_output, str):
            state_output = StateOutputMode(state_output)

        abstraction = d.get("abstraction", "full_dom")
        if isinstance(abstraction, str):
            abstraction = AbstractionLevel(abstraction)

        memory = d.get("memory", "rolling_window")
        if isinstance(memory, str):
            memory = MemoryMode(memory)

        reasoning = d.get("reasoning", "direct")
        if isinstance(reasoning, str):
            reasoning = ReasoningMode(reasoning)

        verification = d.get("verification", "schema")
        if isinstance(verification, str):
            verification = VerificationMode(verification)

        temporal = d.get("temporal", "instant")
        if isinstance(temporal, str):
            temporal = TemporalMode(temporal)

        uncertainty = d.get("uncertainty", "deterministic")
        if isinstance(uncertainty, str):
            uncertainty = UncertaintyMode(uncertainty)

        grounding = d.get("grounding", "llm_knowledge")
        if isinstance(grounding, str):
            grounding = GroundingStrategy(grounding)

        return cls(
            state_output=state_output,
            abstraction=abstraction,
            memory=memory,
            reasoning=reasoning,
            verification=verification,
            temporal=temporal,
            uncertainty=uncertainty,
            grounding=grounding,
            memory_window=d.get("memory_window", 5),
            memory_recent_steps=d.get("memory_recent_steps", 3),
            memory_max_checkpoints=d.get("memory_max_checkpoints", 10),
            include_hidden_elements=d.get("include_hidden_elements", False),
            reasoning_include_examples=d.get("reasoning_include_examples", True),
            verification_strict=d.get("verification_strict", False),
            uncertainty_min_confidence=d.get("uncertainty_min_confidence", 0.0),
            uncertainty_selection_strategy=d.get("uncertainty_selection_strategy", "most_likely"),
            llm_provider=d.get("llm_provider"),
            llm_model=d.get("llm_model"),
            max_tokens=d.get("max_tokens", 4096),
            difficulty_preset=d.get("difficulty_preset"),
            difficulty_config=d.get("difficulty_config"),
            max_steps_per_episode=d.get("max_steps_per_episode", 50),
            max_retries=d.get("max_retries", 3),
            domain=d.get("domain"),
            use_classic_prompt=d.get("use_classic_prompt", False),
            custom_system_prompt=d.get("custom_system_prompt"),
        )


# =============================================================================
# Presets
# =============================================================================

SIMULATOR_PRESETS = {
    # Classic: Reproduces original core simulator behavior
    "classic": SimulatorConfig(
        state_output=StateOutputMode.FULL_STATE,
        abstraction=AbstractionLevel.FULL_DOM,
        memory=MemoryMode.FULL_HISTORY,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.SCHEMA,
        temporal=TemporalMode.INSTANT,
        uncertainty=UncertaintyMode.DETERMINISTIC,
        grounding=GroundingStrategy.LLM_KNOWLEDGE,
        use_classic_prompt=True,
    ),

    # Default: Balanced configuration for general use
    "default": SimulatorConfig(
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction=AbstractionLevel.FULL_DOM,
        memory=MemoryMode.ROLLING_WINDOW,
        memory_window=5,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.SCHEMA,
        temporal=TemporalMode.INSTANT,
        uncertainty=UncertaintyMode.DETERMINISTIC,
        grounding=GroundingStrategy.LLM_KNOWLEDGE,
    ),

    # Efficient: Optimized for speed and token efficiency
    "efficient": SimulatorConfig(
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
        memory=MemoryMode.ROLLING_WINDOW,
        memory_window=3,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.SCHEMA,
        temporal=TemporalMode.INSTANT,
        uncertainty=UncertaintyMode.DETERMINISTIC,
        grounding=GroundingStrategy.LLM_KNOWLEDGE,
    ),

    # Thorough: Maximum accuracy, full verification
    "thorough": SimulatorConfig(
        state_output=StateOutputMode.FULL_STATE,
        abstraction=AbstractionLevel.FULL_DOM,
        memory=MemoryMode.FULL_HISTORY,
        reasoning=ReasoningMode.CHAIN,
        verification=VerificationMode.CONSTRAINT_CHECK,
        temporal=TemporalMode.ASYNC_AWARE,
        uncertainty=UncertaintyMode.WITH_CONFIDENCE,
        grounding=GroundingStrategy.LLM_KNOWLEDGE,
    ),

    # Robust: With constraint verification and uncertainty handling
    "robust": SimulatorConfig(
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
        memory=MemoryMode.ROLLING_WINDOW,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.CONSTRAINT_CHECK,
        verification_strict=True,
        temporal=TemporalMode.INSTANT,
        uncertainty=UncertaintyMode.ADMITS_UNCERTAINTY,
        grounding=GroundingStrategy.LLM_KNOWLEDGE,
    ),

    # Grounded: Example-grounded predictions for consistency
    "grounded": SimulatorConfig(
        state_output=StateOutputMode.DELTA_ONLY,
        abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
        memory=MemoryMode.ROLLING_WINDOW,
        reasoning=ReasoningMode.DIRECT,
        verification=VerificationMode.SCHEMA,
        temporal=TemporalMode.INSTANT,
        uncertainty=UncertaintyMode.DETERMINISTIC,
        grounding=GroundingStrategy.EXAMPLE_GROUNDED,
    ),
}


# =============================================================================
# Unified Simulator
# =============================================================================

class Simulator:
    """
    Unified LLM-based OS Simulator.

    A fully modular, configurable simulator that combines:
    - Production-ready features from core simulator (difficulty, error handling)
    - Experimental modules for design space exploration
    - Configuration file support for reproducible setups

    Usage:
        # From preset
        sim = Simulator.from_preset("classic")

        # From config file
        sim = Simulator.from_config_file("config.json")

        # Programmatic with modules
        sim = Simulator(
            config=SimulatorConfig(
                state_output=StateOutputMode.DELTA_ONLY,
                uncertainty=UncertaintyMode.WITH_CONFIDENCE,
            )
        )

        # Direct parameters (convenience)
        sim = Simulator(
            state_output="delta_only",
            abstraction="semantic_elements",
            difficulty_preset="medium",
        )
    """

    def __init__(
        self,
        config: Optional[SimulatorConfig] = None,
        config_path: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
        # Convenience parameters (override config)
        state_output: Optional[Union[str, StateOutputMode]] = None,
        abstraction: Optional[Union[str, AbstractionLevel]] = None,
        memory: Optional[Union[str, MemoryMode]] = None,
        reasoning: Optional[Union[str, ReasoningMode]] = None,
        verification: Optional[Union[str, VerificationMode]] = None,
        temporal: Optional[Union[str, TemporalMode]] = None,
        uncertainty: Optional[Union[str, UncertaintyMode]] = None,
        grounding: Optional[Union[str, GroundingStrategy]] = None,
        difficulty: Optional[str] = None,
        difficulty_config: Optional[DifficultyConfig] = None,
        domain: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the unified simulator.

        Args:
            config: SimulatorConfig object.
            config_path: Path to config.json file.
            llm_client: LLM client instance.
            state_output: State output mode (overrides config).
            abstraction: Abstraction level (overrides config).
            memory: Memory mode (overrides config).
            reasoning: Reasoning mode (overrides config).
            verification: Verification mode (overrides config).
            temporal: Temporal mode (overrides config).
            uncertainty: Uncertainty mode (overrides config).
            grounding: Grounding strategy (overrides config).
            difficulty: Difficulty preset (overrides config).
            difficulty_config: Custom difficulty configuration.
            domain: Domain name (overrides config).
            **kwargs: Additional parameters passed to SimulatorConfig.
        """
        # Load base config from file
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.json"
        self.config_path = Path(config_path)

        with open(self.config_path, "r") as f:
            self.file_config = json.load(f)

        # Start with provided config or default
        if config is not None:
            self.sim_config = config
        else:
            # Check if simulator config exists in file
            file_sim_config = self.file_config.get("simulator", {}).get("modules", {})
            if file_sim_config:
                self.sim_config = SimulatorConfig.from_dict(file_sim_config)
            else:
                self.sim_config = SimulatorConfig()

        # Apply overrides from direct parameters
        self._apply_overrides(
            state_output=state_output,
            abstraction=abstraction,
            memory=memory,
            reasoning=reasoning,
            verification=verification,
            temporal=temporal,
            uncertainty=uncertainty,
            grounding=grounding,
            difficulty=difficulty,
            domain=domain,
            **kwargs,
        )

        # Store difficulty config if provided directly
        if difficulty_config is not None:
            self._difficulty_config = difficulty_config
        else:
            self._difficulty_config = None

        # Initialize LLM client
        self.llm_client = llm_client or LLMClient(str(self.config_path))

        # Get LLM settings
        self._setup_llm_settings()

        # Initialize difficulty
        self._setup_difficulty()

        # Initialize modules
        self._init_modules()

        # Load system prompt
        self.system_prompt = self._load_system_prompt()

        # Episode state
        self.current_state: Optional[dict] = None
        self.initial_state: Optional[dict] = None
        self.instruction: Optional[dict] = None
        self.history: list[dict] = []
        self._step_count: int = 0

    def _apply_overrides(
        self,
        state_output=None,
        abstraction=None,
        memory=None,
        reasoning=None,
        verification=None,
        temporal=None,
        uncertainty=None,
        grounding=None,
        difficulty=None,
        domain=None,
        **kwargs,
    ):
        """Apply parameter overrides to config."""
        if state_output is not None:
            if isinstance(state_output, str):
                state_output = StateOutputMode(state_output)
            self.sim_config.state_output = state_output

        if abstraction is not None:
            if isinstance(abstraction, str):
                abstraction = AbstractionLevel(abstraction)
            self.sim_config.abstraction = abstraction

        if memory is not None:
            if isinstance(memory, str):
                memory = MemoryMode(memory)
            self.sim_config.memory = memory

        if reasoning is not None:
            if isinstance(reasoning, str):
                reasoning = ReasoningMode(reasoning)
            self.sim_config.reasoning = reasoning

        if verification is not None:
            if isinstance(verification, str):
                verification = VerificationMode(verification)
            self.sim_config.verification = verification

        if temporal is not None:
            if isinstance(temporal, str):
                temporal = TemporalMode(temporal)
            self.sim_config.temporal = temporal

        if uncertainty is not None:
            if isinstance(uncertainty, str):
                uncertainty = UncertaintyMode(uncertainty)
            self.sim_config.uncertainty = uncertainty

        if grounding is not None:
            if isinstance(grounding, str):
                grounding = GroundingStrategy(grounding)
            self.sim_config.grounding = grounding

        if difficulty is not None:
            self.sim_config.difficulty_preset = difficulty

        if domain is not None:
            self.sim_config.domain = domain

        # Apply any additional kwargs
        for key, value in kwargs.items():
            if hasattr(self.sim_config, key):
                setattr(self.sim_config, key, value)

    def _setup_llm_settings(self):
        """Setup LLM provider and model settings."""
        llm_config = self.file_config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("simulator", {})

        # Priority: sim_config > role_config > default
        self.provider = (
            self.sim_config.llm_provider or
            role_config.get("provider") or
            llm_config.get("default_provider")
        )
        self.model_name = (
            self.sim_config.llm_model or
            role_config.get("model")
        )

    def _setup_difficulty(self):
        """Setup difficulty configuration."""
        if self._difficulty_config is not None:
            self.difficulty = self._difficulty_config
        elif self.sim_config.difficulty_preset is not None:
            self.difficulty = get_difficulty_config(preset=self.sim_config.difficulty_preset)
        elif self.sim_config.difficulty_config is not None:
            self.difficulty = get_difficulty_from_dict(self.sim_config.difficulty_config)
        else:
            # Try file config
            file_difficulty = self.file_config.get("simulator", {}).get("difficulty", {})
            if file_difficulty:
                self.difficulty = get_difficulty_from_dict(file_difficulty)
            else:
                self.difficulty = get_difficulty_config(preset="easy")

    def _init_modules(self):
        """Initialize all modules based on configuration."""
        self._state_output_module = StateOutputModule(
            mode=self.sim_config.state_output
        )
        self._abstraction_module = AbstractionModule(
            level=self.sim_config.abstraction,
            include_hidden=self.sim_config.include_hidden_elements,
        )
        self._memory_module = MemoryModule(
            mode=self.sim_config.memory,
            window_size=self.sim_config.memory_window,
            recent_steps=self.sim_config.memory_recent_steps,
            max_checkpoints=self.sim_config.memory_max_checkpoints,
        )
        self._reasoning_module = ReasoningModule(
            mode=self.sim_config.reasoning,
            include_examples=self.sim_config.reasoning_include_examples,
        )
        self._verification_module = VerificationModule(
            mode=self.sim_config.verification,
            strict=self.sim_config.verification_strict,
            llm_client=self.llm_client,
        )
        self._temporal_module = TemporalModule(
            mode=self.sim_config.temporal
        )
        self._uncertainty_module = UncertaintyModule(
            mode=self.sim_config.uncertainty,
            min_confidence=self.sim_config.uncertainty_min_confidence,
            selection_strategy=self.sim_config.uncertainty_selection_strategy,
        )
        self._grounding_module = GroundingModule(
            strategy=self.sim_config.grounding
        )

        # Collect all modules
        self._modules = [
            self._state_output_module,
            self._abstraction_module,
            self._memory_module,
            self._reasoning_module,
            self._verification_module,
            self._temporal_module,
            self._uncertainty_module,
            self._grounding_module,
        ]

    def _load_system_prompt(self) -> str:
        """Load the system prompt based on configuration."""
        # Custom prompt takes priority
        if self.sim_config.custom_system_prompt:
            base_prompt = self.sim_config.custom_system_prompt
        # Classic prompt from file
        elif self.sim_config.use_classic_prompt:
            prompt_path = self.config_path.parent / "prompts" / "simulator.system.md"
            if prompt_path.exists():
                with open(prompt_path, "r") as f:
                    base_prompt = f.read()
            else:
                base_prompt = self._get_classic_prompt()
        # Modular prompt from modules
        else:
            base_prompt = self._build_modular_prompt()

        # Append difficulty modifiers
        difficulty_prompt = build_difficulty_prompt(self.difficulty)
        return base_prompt + "\n" + difficulty_prompt

    def _get_classic_prompt(self) -> str:
        """Get the classic simulator system prompt."""
        return """You are the World Engine. You manage the state of a computer OS.

## Instructions
1. **Analyze:** Review `current_state` and `action`.
2. **Predict:** Determine the next state logic based on the Action.
3. **Patch:** Output a list of **ID-Based Operations** (`state_ops`) to transform the state.

## STRICT SCALING RULES
1. **Target by ID:** You must identify UI nodes using their `bid`. Do NOT use array indices or paths.
2. **Minimal Scope:** Only output the specific properties that change. Never output the full node or full tree.
3. **Hidden State:** You may update `hidden_state` (e.g., to store clipboard data), but `ui` updates must be visual.

## Output Format (ID-Based Patching)
Return JSON with `thought`, `events`, and `state_ops`.
`state_ops` is a list of objects.

Supported Operations:
- `update`: { "op": "update", "bid": <id>, "props": { "property": "new_value" } }
- `delete`: { "op": "delete", "bid": <id> }
- `append`: { "op": "append", "parent_bid": <id>, "node": { "bid": <new_id>, "tag": "...", ... } }
- `hidden_update`: { "op": "hidden_update", "key": "<key>", "value": <value> }

### Example Output
{
  "thought": "User clicked the checkbox (bid 12). I need to toggle its checked state.",
  "state_ops": [
    { "op": "update", "bid": 12, "props": { "checked": true } }
  ],
  "events": ["Checkbox toggled"]
}"""

    def _build_modular_prompt(self) -> str:
        """Build prompt from module contributions."""
        context = {
            "domain": self.sim_config.domain,
        }
        return build_simulator_prompt(
            self._modules,
            context=context,
            domain=self.sim_config.domain,
            include_base=True,
        )

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def from_preset(
        cls,
        preset: str,
        config_path: Optional[str] = None,
        **kwargs,
    ) -> "Simulator":
        """
        Create simulator from a preset configuration.

        Args:
            preset: Preset name ("classic", "default", "efficient", "thorough", "robust", "grounded").
            config_path: Path to config.json for LLM settings.
            **kwargs: Additional overrides.

        Returns:
            Simulator instance.
        """
        if preset not in SIMULATOR_PRESETS:
            raise ValueError(f"Unknown preset: {preset}. Available: {list(SIMULATOR_PRESETS.keys())}")

        config = copy.deepcopy(SIMULATOR_PRESETS[preset])
        return cls(config=config, config_path=config_path, **kwargs)

    @classmethod
    def from_config_file(
        cls,
        config_path: str,
        section: str = "simulator.modules",
        **kwargs,
    ) -> "Simulator":
        """
        Create simulator from a config file.

        Args:
            config_path: Path to config.json.
            section: Dot-separated path to simulator config section.
            **kwargs: Additional overrides.

        Returns:
            Simulator instance.
        """
        with open(config_path, "r") as f:
            full_config = json.load(f)

        # Navigate to section
        config_dict = full_config
        for key in section.split("."):
            config_dict = config_dict.get(key, {})

        if config_dict:
            config = SimulatorConfig.from_dict(config_dict)
        else:
            config = SimulatorConfig()

        return cls(config=config, config_path=config_path, **kwargs)

    @classmethod
    def from_experimental_design(
        cls,
        design: "ExperimentalDesign",
        config_path: Optional[str] = None,
        **kwargs,
    ) -> "Simulator":
        """
        Create simulator from an ExperimentalDesign.

        Args:
            design: ExperimentalDesign from design_space.py.
            config_path: Path to config.json for LLM settings.
            **kwargs: Additional overrides.

        Returns:
            Simulator instance.
        """
        from ..experiments.design_space import design_to_simulator_config

        config_dict = design_to_simulator_config(design)
        config_dict.update(kwargs)

        return cls(config_path=config_path, **config_dict)

    # =========================================================================
    # Core Interface
    # =========================================================================

    def reset(
        self,
        initial_state: Optional[dict] = None,
        template_name: Optional[str] = None,
        instruction: Optional[dict] = None,
    ) -> dict:
        """
        Reset the simulator to an initial state.

        Args:
            initial_state: Full initial state dict.
            template_name: Name of template to load.
            instruction: Task instruction dict.

        Returns:
            Initial observation.
        """
        if initial_state is not None and template_name is not None:
            raise ValueError("Cannot specify both initial_state and template_name")

        if template_name is not None:
            initial_state = self._load_template(template_name)
        elif initial_state is None:
            initial_state = {
                "meta": {"tick": 0, "status": "running"},
                "hidden_state": {},
                "ui": {"bid": "root", "tag": "desktop", "children": []},
                "filesystem": {},
            }

        self.initial_state = copy.deepcopy(initial_state)
        self.current_state = copy.deepcopy(initial_state)
        self.instruction = instruction
        self.history = []
        self._step_count = 0

        # Ensure tick is 0
        if "meta" not in self.current_state:
            self.current_state["meta"] = {}
        self.current_state["meta"]["tick"] = 0
        self.current_state["meta"]["status"] = "running"

        # Reset modules
        self._memory_module.reset()
        self._temporal_module.reset()
        self._uncertainty_module.reset()

        # Render and apply abstraction
        observation = render_observation(self.current_state)
        preprocessor = self._abstraction_module.get_preprocessor()
        return preprocessor.preprocess(observation, {"instruction": instruction})

    def _load_template(self, template_name: str) -> dict:
        """Load a state template by name."""
        template_path = self.config_path.parent / "templates" / f"{template_name}.json"

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        with open(template_path, "r") as f:
            return json.load(f)

    def step(self, action: dict) -> tuple[dict, bool, dict]:
        """
        Execute one step in the simulator.

        Args:
            action: Action dict from the agent.

        Returns:
            Tuple of (observation, done, info).
        """
        if self.current_state is None:
            raise SimulatorError("Simulator not initialized. Call reset() first.")

        # Validate action
        is_valid, errors = validate_action_complete(action)
        if not is_valid:
            logger.warning(f"Invalid action: {errors}")
            return (
                self._get_observation(),
                False,
                {"error": "Invalid action", "details": errors}
            )

        # Extract debug payload
        agent_llm_data = action.get("_llm_data", {})
        action_for_history = {k: v for k, v in action.items() if not k.startswith("_")}

        # Handle finish action
        if action.get("action_type") == "finish":
            return self._handle_finish(action, action_for_history, agent_llm_data)

        # Build context for modules
        context = self._build_context(action)

        # Preprocess state with abstraction
        preprocessor = self._abstraction_module.get_preprocessor()
        processed_state = preprocessor.preprocess(self.current_state, context)

        # Get grounding context
        grounding_context = self._grounding_module.get_grounding_context(
            self.current_state, action, context
        )
        context.update(grounding_context)

        # Get LLM prediction
        try:
            llm_response = self._get_llm_prediction(processed_state, action_for_history, context)
        except Exception as e:
            logger.error(f"LLM prediction failed: {e}")
            return (
                self._get_observation(),
                False,
                {"error": "LLM prediction failed", "details": str(e)}
            )

        # Parse output with state output module
        state_parser = self._state_output_module.get_parser()
        state_ops = state_parser.parse(llm_response, self.current_state)

        # Handle uncertainty
        uncertainty_parser = self._uncertainty_module.get_parser()
        state_ops = uncertainty_parser.parse(llm_response, self.current_state)

        # Handle temporal effects
        temporal_parser = self._temporal_module.get_parser()
        temporal_ops = temporal_parser.parse(llm_response, self.current_state)
        if temporal_ops:
            state_ops.extend(temporal_ops)

        # Verify output
        verifier = self._verification_module.get_verifier()
        is_valid, verification_errors = verifier.verify(
            {"state_ops": state_ops, **llm_response},
            self.current_state,
            action,
            context,
        )

        if not is_valid:
            logger.warning(f"Verification failed: {verification_errors}")

        # Extract response components
        thought = llm_response.get("thought", "")
        events = llm_response.get("events", [])
        if isinstance(events, str):
            events = [events]

        # Validate operations
        op_errors = validate_ops(state_ops)
        if op_errors:
            logger.warning(f"Invalid state operations: {op_errors}")

        # Apply patches
        apply_id_patch(self.current_state, state_ops)

        # Increment tick
        self.current_state["meta"]["tick"] += 1
        self._step_count += 1

        # Check for episode end
        done = self._check_done()
        if done and self.current_state["meta"].get("status") != "failed":
            self.current_state["meta"]["status"] = "completed"

        # Update memory
        history_manager = self._memory_module.get_history_manager()
        step_record = {
            "tick": self.current_state["meta"]["tick"],
            "step": self._step_count,
            "action": copy.deepcopy(action_for_history),
            "thought": thought,
            "state_ops": copy.deepcopy(state_ops),
            "events": copy.deepcopy(events),
            "agent_llm_data": copy.deepcopy(agent_llm_data),
            "simulator_llm_data": copy.deepcopy(llm_response.get("_llm_data", {})),
        }
        history_manager.add_step(step_record)
        self.history.append(step_record)

        # Update uncertainty aggregator
        if hasattr(uncertainty_parser, 'get_confidence'):
            self._uncertainty_module.get_aggregator().add_step(
                confidence=uncertainty_parser.get_confidence(llm_response),
            )

        # Build info
        info = {
            "thought": thought,
            "events": events,
            "tick": self.current_state["meta"]["tick"],
            "verification_valid": is_valid,
            "verification_errors": verification_errors,
            "modules": self.get_module_config(),
        }

        return self._get_observation(), done, info

    def _handle_finish(
        self,
        action: dict,
        action_for_history: dict,
        agent_llm_data: dict,
    ) -> tuple[dict, bool, dict]:
        """Handle finish action."""
        self.current_state["meta"]["tick"] += 1
        self.current_state["meta"]["status"] = "completed"

        events = [action.get("text")] if action.get("text") else []

        self.history.append({
            "tick": self.current_state["meta"]["tick"],
            "action": copy.deepcopy(action_for_history),
            "thought": "",
            "state_ops": [],
            "events": copy.deepcopy(events),
            "agent_llm_data": copy.deepcopy(agent_llm_data),
            "simulator_llm_data": {},
        })

        info = {
            "thought": "",
            "events": events,
            "tick": self.current_state["meta"]["tick"],
        }

        return self._get_observation(), True, info

    def _build_context(self, action: dict) -> dict:
        """Build context for modules."""
        history_manager = self._memory_module.get_history_manager()

        return {
            "instruction": self.instruction,
            "action": action,
            "current_step": self._step_count,
            "history": history_manager.get_context(),
            "history_summary": self._get_history_summary(),
            "checkpoints": self._get_checkpoints(),
        }

    def _get_llm_prediction(
        self,
        processed_state: dict,
        action: dict,
        context: dict,
    ) -> dict:
        """Get state transition prediction from LLM."""
        # Build prompt
        if self.sim_config.use_classic_prompt:
            user_message = self._build_classic_user_message(self.current_state, action)
        else:
            user_message = self._build_modular_user_message(processed_state, action, context)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Call LLM
        response = self.llm_client.complete(
            messages=messages,
            provider=self.provider,
            model_name=self.model_name,
            json_mode=True,
        )

        # Process response
        raw_response = response
        if isinstance(response, str):
            response = json.loads(response)
        if isinstance(response, list):
            response = response[0] if response else {}
        if not isinstance(response, dict):
            response = {}

        # Attach LLM data
        response["_llm_data"] = {
            "role": "simulator",
            "provider": self.provider,
            "model": self.model_name,
            "system_prompt": self.system_prompt,
            "user_message": user_message,
            "raw_response": raw_response if isinstance(raw_response, str) else json.dumps(raw_response),
        }

        return response

    def _build_classic_user_message(self, state: dict, action: dict) -> str:
        """Build classic user message format."""
        parts = []

        if self.instruction:
            parts.append(f"## Task Instruction\n{self.instruction.get('instruction', '')}\n")

        parts.append("## Current State (Full - including hidden_state)")
        parts.append(f"```json\n{json.dumps(state, indent=2)}\n```\n")

        parts.append("## Action")
        parts.append(f"```json\n{json.dumps(action, indent=2)}\n```\n")

        parts.append("## Your Task")
        parts.append("Analyze the action and determine what state changes should occur.")
        parts.append("Output the state_ops to transform the state accordingly.")

        return "\n".join(parts)

    def _build_modular_user_message(
        self,
        processed_state: dict,
        action: dict,
        context: dict,
    ) -> str:
        """Build modular user message with context."""
        parts = []

        if self.instruction:
            parts.append(f"## Task Instruction\n{self.instruction.get('instruction', '')}\n")

        parts.append("## Current State")
        state_json = json.dumps(processed_state, indent=2)
        if len(state_json) > 10000:
            state_json = state_json[:10000] + "\n... (truncated)"
        parts.append(f"```json\n{state_json}\n```\n")

        parts.append("## Action to Process")
        parts.append(f"```json\n{json.dumps(action, indent=2)}\n```\n")

        # Add history context
        history = context.get("history", [])
        if history:
            parts.append("## History Context")
            parts.append(self._format_history_for_prompt(history))

        parts.append("\nPredict the state changes that result from this action.")

        return "\n".join(parts)

    def _format_history_for_prompt(self, history: list) -> str:
        """Format history for prompt."""
        if not history:
            return "No previous actions."

        lines = []
        for step in history[-5:]:
            action = step.get("action", {})
            action_type = action.get("action_type", "unknown")
            lines.append(f"- Step {step.get('step', '?')}: {action_type}")

        return "\n".join(lines)

    def _check_done(self) -> bool:
        """Check if episode should end."""
        if self.current_state is None:
            return True

        status = self.current_state.get("meta", {}).get("status", "running")
        if status in ("completed", "failed"):
            return True

        max_steps = self.sim_config.max_steps_per_episode
        if self.current_state["meta"]["tick"] >= max_steps:
            self.current_state["meta"]["status"] = "failed"
            return True

        return False

    def _get_observation(self) -> dict:
        """Get current observation with abstraction applied."""
        if self.current_state is None:
            return {}

        obs = render_observation(self.current_state)
        preprocessor = self._abstraction_module.get_preprocessor()
        return preprocessor.preprocess(obs, {"instruction": self.instruction})

    def _get_history_summary(self) -> str:
        """Get history summary."""
        history_manager = self._memory_module.get_history_manager()
        if hasattr(history_manager, 'get_summary'):
            return history_manager.get_summary()
        return ""

    def _get_checkpoints(self) -> list:
        """Get checkpoints."""
        history_manager = self._memory_module.get_history_manager()
        if hasattr(history_manager, 'get_checkpoints'):
            return history_manager.get_checkpoints()
        return []

    # =========================================================================
    # State Access
    # =========================================================================

    def get_state(self) -> dict:
        """Get current full state."""
        return copy.deepcopy(self.current_state) if self.current_state else {}

    def get_observation(self) -> dict:
        """Get current observation."""
        return self._get_observation()

    def get_history(self) -> list[dict]:
        """Get action history."""
        return copy.deepcopy(self.history)

    def get_config(self) -> SimulatorConfig:
        """Get current configuration."""
        return self.sim_config

    def get_module_config(self) -> dict:
        """Get module configuration as dict."""
        return {
            "state_output": self.sim_config.state_output.value,
            "abstraction": self.sim_config.abstraction.value,
            "memory": self.sim_config.memory.value,
            "reasoning": self.sim_config.reasoning.value,
            "verification": self.sim_config.verification.value,
            "temporal": self.sim_config.temporal.value,
            "uncertainty": self.sim_config.uncertainty.value,
            "grounding": self.sim_config.grounding.value,
        }

    def get_difficulty(self) -> DifficultyConfig:
        """Get current difficulty configuration."""
        return self.difficulty

    # =========================================================================
    # Configuration Updates
    # =========================================================================

    def set_difficulty(
        self,
        preset: Optional[str] = None,
        difficulty_config: Optional[DifficultyConfig] = None,
    ):
        """Change simulator difficulty."""
        if difficulty_config is not None:
            self.difficulty = difficulty_config
        elif preset is not None:
            self.difficulty = get_difficulty_config(preset=preset)
        else:
            raise ValueError("Must specify either preset or difficulty_config")

        self.system_prompt = self._load_system_prompt()
        logger.info(f"Difficulty changed to: {self.difficulty.preset}")

    # =========================================================================
    # Grounding Helpers
    # =========================================================================

    def add_example(self, example: dict) -> None:
        """Add an example for grounding."""
        self._grounding_module.add_example(example)

    def add_document(self, key: str, content: str) -> None:
        """Add documentation for grounding."""
        self._grounding_module.add_document(key, content)

    def add_trace(self, trace: dict) -> None:
        """Add a trace for grounding."""
        self._grounding_module.add_trace(trace)

    # =========================================================================
    # Episode Management
    # =========================================================================

    def save_episode(self, path: str):
        """Save episode to file."""
        episode = {
            "instruction": self.instruction,
            "initial_state": self.initial_state,
            "final_state": self.current_state,
            "history": self.history,
            "config": self.sim_config.to_dict(),
        }

        with open(path, "w") as f:
            json.dump(episode, f, indent=2)

        logger.info(f"Episode saved to {path}")

    def load_episode(self, path: str):
        """Load episode from file."""
        with open(path, "r") as f:
            episode = json.load(f)

        self.instruction = episode.get("instruction")
        self.initial_state = episode.get("initial_state")
        self.current_state = episode.get("final_state")
        self.history = episode.get("history", [])

        logger.info(f"Episode loaded from {path}")


# =============================================================================
# Convenience Functions
# =============================================================================

def create_simulator(
    preset: str = "default",
    config_path: Optional[str] = None,
    **kwargs,
) -> Simulator:
    """
    Create a simulator with a preset configuration.

    Args:
        preset: Preset name ("classic", "default", "efficient", etc.).
        config_path: Path to config file.
        **kwargs: Additional overrides.

    Returns:
        Simulator instance.
    """
    return Simulator.from_preset(preset, config_path=config_path, **kwargs)
