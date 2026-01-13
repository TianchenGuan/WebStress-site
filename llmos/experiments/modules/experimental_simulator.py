"""
Experimental Simulator: Wrapper that composes modules around base Simulator.

This wrapper allows experimenting with different design choices without
modifying the core Simulator class. It intercepts calls and applies
module-specific preprocessing, prompting, and postprocessing.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import copy
import json
import logging

from .base import Module, PromptBlock, StatePreprocessor, OutputParser, Verifier
from .state_output import StateOutputMode, StateOutputModule
from .abstraction import AbstractionLevel, AbstractionModule
from .memory import MemoryMode, MemoryModule
from .reasoning import ReasoningMode, ReasoningModule
from .verification import VerificationMode, VerificationModule
from .prompt_blocks import PromptBlockLibrary, build_simulator_prompt

logger = logging.getLogger(__name__)


@dataclass
class ExperimentalConfig:
    """Configuration for experimental simulator."""

    # State output
    state_output: StateOutputMode = StateOutputMode.DELTA_ONLY

    # Abstraction
    abstraction: AbstractionLevel = AbstractionLevel.FULL_DOM
    include_hidden_elements: bool = False

    # Memory
    memory: MemoryMode = MemoryMode.ROLLING_WINDOW
    memory_window: int = 5
    memory_recent_steps: int = 3
    memory_max_checkpoints: int = 10

    # Reasoning
    reasoning: ReasoningMode = ReasoningMode.DIRECT
    reasoning_include_examples: bool = True

    # Verification
    verification: VerificationMode = VerificationMode.SCHEMA
    verification_strict: bool = False

    # Domain
    domain: Optional[str] = None  # "web", "desktop", "servicenow"

    def to_dict(self) -> dict:
        return {
            "state_output": self.state_output.value,
            "abstraction": self.abstraction.value,
            "include_hidden_elements": self.include_hidden_elements,
            "memory": self.memory.value,
            "memory_window": self.memory_window,
            "memory_recent_steps": self.memory_recent_steps,
            "memory_max_checkpoints": self.memory_max_checkpoints,
            "reasoning": self.reasoning.value,
            "reasoning_include_examples": self.reasoning_include_examples,
            "verification": self.verification.value,
            "verification_strict": self.verification_strict,
            "domain": self.domain,
        }


class ExperimentalSimulator:
    """
    Experimental simulator wrapper.

    Wraps the base Simulator and applies modular components for
    different design choices.

    Usage:
        # Create with configuration
        sim = ExperimentalSimulator(
            state_output=StateOutputMode.DELTA_ONLY,
            abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=5,
            reasoning=ReasoningMode.CHAIN,
            verification=VerificationMode.CONSTRAINT_CHECK,
        )

        # Or from config object
        config = ExperimentalConfig(
            state_output=StateOutputMode.SEMANTIC_DESCRIPTION,
            ...
        )
        sim = ExperimentalSimulator.from_config(config)

        # Use like regular simulator
        obs = sim.reset(template_name="browser", instruction=task)
        obs, done, info = sim.step(action)
    """

    def __init__(
        self,
        # Module configurations
        state_output: StateOutputMode = StateOutputMode.DELTA_ONLY,
        abstraction: AbstractionLevel = AbstractionLevel.FULL_DOM,
        memory: MemoryMode = MemoryMode.ROLLING_WINDOW,
        reasoning: ReasoningMode = ReasoningMode.DIRECT,
        verification: VerificationMode = VerificationMode.SCHEMA,
        # Module parameters
        memory_window: int = 5,
        memory_recent_steps: int = 3,
        memory_max_checkpoints: int = 10,
        include_hidden_elements: bool = False,
        reasoning_include_examples: bool = True,
        verification_strict: bool = False,
        # Domain knowledge
        domain: Optional[str] = None,
        # Base simulator configuration
        config_path: Optional[str] = None,
        difficulty: Optional[str] = None,
        llm_client: Any = None,
        # Optional: inject custom base simulator
        base_simulator: Any = None,
    ):
        """Initialize experimental simulator with modules."""
        self.config_path = config_path
        self.difficulty = difficulty
        self.domain = domain

        # Store the LLM client for backward verification
        self._llm_client = llm_client

        # Initialize modules
        self._state_output_module = StateOutputModule(mode=state_output)
        self._abstraction_module = AbstractionModule(
            level=abstraction,
            include_hidden=include_hidden_elements,
        )
        self._memory_module = MemoryModule(
            mode=memory,
            window_size=memory_window,
            recent_steps=memory_recent_steps,
            max_checkpoints=memory_max_checkpoints,
        )
        self._reasoning_module = ReasoningModule(
            mode=reasoning,
            include_examples=reasoning_include_examples,
        )
        self._verification_module = VerificationModule(
            mode=verification,
            strict=verification_strict,
            llm_client=llm_client,
        )

        # Collect all modules
        self._modules = [
            self._state_output_module,
            self._abstraction_module,
            self._memory_module,
            self._reasoning_module,
            self._verification_module,
        ]

        # Prompt library
        self._prompt_library = PromptBlockLibrary()

        # Base simulator (lazy initialization)
        self._base_simulator = base_simulator
        self._initialized = base_simulator is not None

        # State
        self._current_state: Optional[dict] = None
        self._instruction: Optional[dict] = None
        self._step_count: int = 0

    @classmethod
    def from_config(
        cls,
        config: ExperimentalConfig,
        config_path: Optional[str] = None,
        **kwargs,
    ) -> "ExperimentalSimulator":
        """Create from configuration object."""
        return cls(
            state_output=config.state_output,
            abstraction=config.abstraction,
            memory=config.memory,
            reasoning=config.reasoning,
            verification=config.verification,
            memory_window=config.memory_window,
            memory_recent_steps=config.memory_recent_steps,
            memory_max_checkpoints=config.memory_max_checkpoints,
            include_hidden_elements=config.include_hidden_elements,
            reasoning_include_examples=config.reasoning_include_examples,
            verification_strict=config.verification_strict,
            domain=config.domain,
            config_path=config_path,
            **kwargs,
        )

    def _ensure_initialized(self) -> None:
        """Lazy initialization of base simulator."""
        if not self._initialized:
            from ...core.simulator import Simulator
            self._base_simulator = Simulator(
                config_path=self.config_path,
                difficulty=self.difficulty,
                llm_client=self._llm_client,
            )
            self._initialized = True

    def reset(
        self,
        initial_state: Optional[dict] = None,
        template_name: Optional[str] = None,
        instruction: Optional[dict] = None,
    ) -> dict:
        """
        Reset the simulator for a new episode.

        Args:
            initial_state: Optional initial state dict.
            template_name: Name of state template to use.
            instruction: Task instruction dict.

        Returns:
            Initial observation.
        """
        self._ensure_initialized()

        # Reset memory module
        self._memory_module.reset()
        self._step_count = 0
        self._instruction = instruction

        # Delegate to base simulator
        observation = self._base_simulator.reset(
            initial_state=initial_state,
            template_name=template_name,
            instruction=instruction,
        )

        self._current_state = self._base_simulator.get_state()

        # Apply abstraction preprocessing to observation
        preprocessor = self._abstraction_module.get_preprocessor()
        processed_obs = preprocessor.preprocess(
            observation,
            {"instruction": instruction},
        )

        return processed_obs

    def step(self, action: dict) -> tuple[dict, bool, dict]:
        """
        Execute one step in the simulator.

        This method:
        1. Preprocesses state based on abstraction level
        2. Builds prompt with all module contributions
        3. Calls LLM with custom prompt
        4. Parses output based on state output mode
        5. Verifies output
        6. Applies changes to state
        7. Updates memory

        Args:
            action: Action dict from agent.

        Returns:
            (observation, done, info)
        """
        self._ensure_initialized()

        # Build context for modules
        context = {
            "instruction": self._instruction,
            "action": action,
            "current_step": self._step_count,
            "history_summary": self._get_history_summary(),
            "checkpoints": self._get_checkpoints(),
        }

        # Get history context
        history_manager = self._memory_module.get_history_manager()
        history_context = history_manager.get_context()
        context["history"] = history_context

        # Preprocess state
        preprocessor = self._abstraction_module.get_preprocessor()
        processed_state = preprocessor.preprocess(
            self._current_state,
            context,
        )

        # Build experimental prompt
        experimental_prompt = self._build_prompt(processed_state, action, context)

        # Call LLM with experimental prompt
        # Note: This requires the base simulator to expose LLM client
        # or we inject our own processing
        llm_output = self._call_llm(experimental_prompt, processed_state, action)

        # Parse output based on state output mode
        parser = self._state_output_module.get_parser()
        state_ops = parser.parse(llm_output, self._current_state)

        # Verify output
        verifier = self._verification_module.get_verifier()
        is_valid, errors = verifier.verify(
            {"state_ops": state_ops, **llm_output},
            self._current_state,
            action,
            context,
        )

        if not is_valid:
            logger.warning(f"Verification failed: {errors}")
            # Optionally retry or use fallback

        # Apply state changes using base simulator's patching
        # We reconstruct the output in standard format
        standard_output = {
            "thought": llm_output.get("thought", ""),
            "state_ops": state_ops,
            "events": llm_output.get("events", []),
        }

        # Apply changes
        observation, done, info = self._apply_changes(standard_output, action)

        # Update memory
        step_record = {
            "step": self._step_count,
            "action": action,
            "state_ops": state_ops,
            "events": llm_output.get("events", []),
            "result": "success" if is_valid else "verification_failed",
        }
        history_manager.add_step(step_record)
        self._step_count += 1

        # Add experimental info
        info["experimental"] = {
            "verification_valid": is_valid,
            "verification_errors": errors,
            "state_ops_count": len(state_ops),
            "prompt_tokens": len(experimental_prompt.split()),  # Rough estimate
        }

        # Apply abstraction to observation
        processed_obs = preprocessor.preprocess(observation, context)

        return processed_obs, done, info

    def _build_prompt(
        self,
        processed_state: dict,
        action: dict,
        context: dict,
    ) -> str:
        """Build the experimental prompt from modules."""
        # Collect all prompt blocks from modules
        all_blocks = []
        for module in self._modules:
            all_blocks.extend(module.get_prompt_blocks())

        # Use prompt library to compose
        prompt = build_simulator_prompt(
            self._modules,
            context={
                **context,
                "state": json.dumps(processed_state, indent=2)[:5000],  # Truncate
                "action": json.dumps(action, indent=2),
            },
            domain=self.domain,
        )

        # Add state and action
        prompt += f"""

## Current State

```json
{json.dumps(processed_state, indent=2)[:10000]}
```

## Action to Process

```json
{json.dumps(action, indent=2)}
```

## History Context

{self._format_history_for_prompt(context.get('history', []))}

Now predict the state changes that result from this action.
"""

        return prompt

    def _format_history_for_prompt(self, history: list) -> str:
        """Format history for inclusion in prompt."""
        if not history:
            return "No previous actions in this episode."

        lines = []
        for step in history[-5]:  # Last 5 steps max in prompt
            action = step.get("action", {})
            action_type = action.get("action_type", "unknown")
            thought = action.get("thought", "")[:100]
            lines.append(f"- Step {step.get('step', '?')}: {action_type}")
            if thought:
                lines.append(f"  Thought: {thought}")

        return "\n".join(lines)

    def _call_llm(
        self,
        prompt: str,
        state: dict,
        action: dict,
    ) -> dict:
        """
        Call LLM with experimental prompt.

        Uses base simulator's LLM client if available.
        """
        self._ensure_initialized()

        # Get LLM client from base simulator
        llm_client = getattr(self._base_simulator, 'llm_client', None)
        if llm_client is None:
            raise RuntimeError("No LLM client available")

        # Get parser's expected schema
        parser = self._state_output_module.get_parser()
        output_schema = parser.get_output_schema()

        try:
            response = llm_client.complete(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Process the action and output state changes."},
                ],
                json_mode=True,
            )

            # Parse response
            if isinstance(response, str):
                return json.loads(response)
            return response

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return {"state_ops": [], "events": ["error:parse_failure"]}

    def _apply_changes(
        self,
        output: dict,
        action: dict,
    ) -> tuple[dict, bool, dict]:
        """
        Apply state changes to the simulator.

        Uses base simulator's patching mechanism.
        """
        from ...utils.patching import apply_id_patch

        state_ops = output.get("state_ops", [])
        events = output.get("events", [])

        # Apply patches to current state
        new_state = copy.deepcopy(self._current_state)
        try:
            apply_id_patch(new_state, state_ops)
        except Exception as e:
            logger.error(f"Failed to apply patches: {e}")
            events.append(f"error:patch_failure:{e}")

        # Update state
        self._current_state = new_state

        # Check for done condition
        status = new_state.get("meta", {}).get("status", "running")
        done = status in ("completed", "failed")

        # Create observation (filtered state)
        from ...utils.rendering import render_observation
        observation = render_observation(new_state)

        info = {
            "events": events,
            "thought": output.get("thought", ""),
            "status": status,
        }

        return observation, done, info

    def _get_history_summary(self) -> str:
        """Get history summary for context."""
        history_manager = self._memory_module.get_history_manager()

        # Check if it's a summarized history manager
        if hasattr(history_manager, 'get_summary'):
            return history_manager.get_summary()
        elif hasattr(history_manager, 'get_context_for_prompt'):
            return history_manager.get_context_for_prompt()

        return ""

    def _get_checkpoints(self) -> list:
        """Get checkpoints for context."""
        history_manager = self._memory_module.get_history_manager()

        if hasattr(history_manager, 'get_checkpoints'):
            return history_manager.get_checkpoints()

        return []

    def get_state(self) -> dict:
        """Get current full state."""
        return copy.deepcopy(self._current_state) if self._current_state else {}

    def get_observation(self) -> dict:
        """Get current observation (filtered state)."""
        if self._current_state is None:
            return {}

        from ...utils.rendering import render_observation
        obs = render_observation(self._current_state)

        # Apply abstraction
        preprocessor = self._abstraction_module.get_preprocessor()
        return preprocessor.preprocess(obs, {"instruction": self._instruction})

    def get_history(self) -> list:
        """Get episode history."""
        history_manager = self._memory_module.get_history_manager()
        return history_manager.get_context()

    def get_config(self) -> dict:
        """Get current experimental configuration."""
        return {
            "state_output": self._state_output_module.mode.value,
            "abstraction": self._abstraction_module.level.value,
            "memory": self._memory_module.mode.value,
            "reasoning": self._reasoning_module.mode.value,
            "verification": self._verification_module.mode.value,
            "domain": self.domain,
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_experimental_simulator(
    preset: str = "default",
    **kwargs,
) -> ExperimentalSimulator:
    """
    Create an experimental simulator with a preset configuration.

    Presets:
        default: Delta output, full DOM, rolling window, direct reasoning
        efficient: Delta output, semantic, rolling window, direct
        thorough: Full state, full DOM, full history, chain reasoning
        robust: Delta output, semantic, rolling window, constraint verification
    """
    presets = {
        "default": ExperimentalConfig(
            state_output=StateOutputMode.DELTA_ONLY,
            abstraction=AbstractionLevel.FULL_DOM,
            memory=MemoryMode.ROLLING_WINDOW,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
        ),
        "efficient": ExperimentalConfig(
            state_output=StateOutputMode.DELTA_ONLY,
            abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
            memory=MemoryMode.ROLLING_WINDOW,
            memory_window=3,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.SCHEMA,
        ),
        "thorough": ExperimentalConfig(
            state_output=StateOutputMode.FULL_STATE,
            abstraction=AbstractionLevel.FULL_DOM,
            memory=MemoryMode.FULL_HISTORY,
            reasoning=ReasoningMode.CHAIN,
            verification=VerificationMode.CONSTRAINT_CHECK,
        ),
        "robust": ExperimentalConfig(
            state_output=StateOutputMode.DELTA_ONLY,
            abstraction=AbstractionLevel.SEMANTIC_ELEMENTS,
            memory=MemoryMode.ROLLING_WINDOW,
            reasoning=ReasoningMode.DIRECT,
            verification=VerificationMode.CONSTRAINT_CHECK,
            verification_strict=True,
        ),
    }

    config = presets.get(preset, presets["default"])
    return ExperimentalSimulator.from_config(config, **kwargs)
