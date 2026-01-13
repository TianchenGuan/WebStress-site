"""
Simulator Engine for LLMOS.
Core state machine that uses LLM for state transitions.
"""

import json
import copy
import logging
from pathlib import Path
from typing import Optional

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

logger = logging.getLogger(__name__)


class SimulatorError(Exception):
    """Exception raised for simulator errors."""
    pass


class Simulator:
    """
    LLM-based OS Simulator.

    Maintains ground truth state and uses LLM to predict state transitions.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_path: Optional[str] = None,
        difficulty: Optional[str] = None,
        difficulty_config: Optional[DifficultyConfig] = None,
    ):
        """
        Initialize the simulator.

        Args:
            llm_client: LLM client instance. If None, creates new one.
            config_path: Path to config file.
            difficulty: Difficulty preset ("easy", "medium", "hard", "expert").
            difficulty_config: Custom difficulty configuration (overrides preset).
        """
        self.llm_client = llm_client or LLMClient(config_path)

        # Load config
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.json"
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.simulator_config = self.config.get("simulator", {})
        self.max_retries = self.simulator_config.get("max_retries", 3)

        # Get role-specific LLM settings
        llm_config = self.config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("simulator", {})
        self.provider = role_config.get("provider", llm_config.get("default_provider"))
        self.model_name = role_config.get("model")

        # Set difficulty configuration
        if difficulty_config is not None:
            self.difficulty = difficulty_config
        elif difficulty is not None:
            self.difficulty = get_difficulty_config(preset=difficulty)
        else:
            # Load from config or default to easy
            config_difficulty = self.simulator_config.get("difficulty", {})
            if config_difficulty:
                self.difficulty = get_difficulty_from_dict(config_difficulty)
            else:
                self.difficulty = get_difficulty_config(preset="easy")

        # Load system prompt (includes difficulty modifiers)
        self.system_prompt = self._load_system_prompt()

        # State
        self.current_state: Optional[dict] = None
        self.initial_state: Optional[dict] = None
        self.instruction: Optional[dict] = None
        self.history: list[dict] = []

    def _load_system_prompt(self) -> str:
        """Load the simulator system prompt with difficulty modifiers."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "simulator.system.md"

        if prompt_path.exists():
            with open(prompt_path, "r") as f:
                base_prompt = f.read()
        else:
            # Default prompt if file doesn't exist
            base_prompt = self._get_default_system_prompt()

        # Append difficulty modifiers
        difficulty_prompt = build_difficulty_prompt(self.difficulty)
        return base_prompt + "\n" + difficulty_prompt

    def _get_default_system_prompt(self) -> str:
        """Get the default simulator system prompt."""
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

    def reset(
        self,
        initial_state: Optional[dict] = None,
        template_name: Optional[str] = None,
        instruction: Optional[dict] = None,
    ) -> dict:
        """
        Reset the simulator to an initial state.

        Args:
            initial_state: Full initial state dict. Mutually exclusive with template_name.
            template_name: Name of template to load (e.g., 'desktop', 'browser').
            instruction: Task instruction dict.

        Returns:
            Initial observation.
        """
        if initial_state is not None and template_name is not None:
            raise ValueError("Cannot specify both initial_state and template_name")

        if template_name is not None:
            initial_state = self._load_template(template_name)
        elif initial_state is None:
            # Default empty state
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

        # Ensure tick is 0
        if "meta" not in self.current_state:
            self.current_state["meta"] = {}
        self.current_state["meta"]["tick"] = 0
        self.current_state["meta"]["status"] = "running"

        return render_observation(self.current_state)

    def _load_template(self, template_name: str) -> dict:
        """Load a state template by name."""
        template_path = Path(__file__).parent.parent / "templates" / f"{template_name}.json"

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
            # Return current state without changes
            return (
                render_observation(self.current_state),
                False,
                {"error": "Invalid action", "details": errors}
            )

        # Extract agent's LLM debug payload without mutating the input action dict
        # (the simulator LLM should see only the action fields).
        agent_llm_data = action.get("_llm_data", {})
        # Create a clean copy of action for history and LLM (without internal metadata)
        action_for_history = {k: v for k, v in action.items() if not k.startswith("_")}

        # Explicit termination action (preferred over heuristics)
        if action.get("action_type") == "finish":
            self.current_state["meta"]["tick"] += 1
            # Treat finish as "agent claims it is done", not authoritative success/failure.
            # The Judge should determine success based on evidence in state/history.
            self.current_state["meta"]["status"] = "terminated"

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

            observation = render_observation(self.current_state)
            info = {"thought": "", "events": events, "tick": self.current_state["meta"]["tick"]}
            return observation, True, info

        # Get LLM prediction (use clean action without internal metadata)
        try:
            llm_response = self._get_llm_prediction(action_for_history)
        except Exception as e:
            logger.error(f"LLM prediction failed: {e}")
            return (
                render_observation(self.current_state),
                False,
                {"error": "LLM prediction failed", "details": str(e)}
            )

        # Extract operations
        state_ops = llm_response.get("state_ops", [])
        thought = llm_response.get("thought", "")
        events = llm_response.get("events", [])

        # Validate operations
        op_errors = validate_ops(state_ops)
        if op_errors:
            logger.warning(f"Invalid state operations: {op_errors}")

        # Apply patches
        apply_id_patch(self.current_state, state_ops)

        # Increment tick
        self.current_state["meta"]["tick"] += 1

        # Check for episode end
        done = self._check_done()
        if done and self.current_state["meta"].get("status") != "failed":
            self.current_state["meta"]["status"] = "completed"

        # Record history with LLM data flow
        # IMPORTANT: Deep copy mutable data to prevent reference corruption
        self.history.append({
            "tick": self.current_state["meta"]["tick"],
            "action": copy.deepcopy(action_for_history),
            "thought": thought,
            "state_ops": copy.deepcopy(state_ops),
            "events": copy.deepcopy(events),
            "agent_llm_data": copy.deepcopy(agent_llm_data),  # Agent's LLM input/output
            "simulator_llm_data": copy.deepcopy(llm_response.get("_llm_data", {})),  # Simulator's LLM input/output
        })

        # Render observation
        observation = render_observation(self.current_state)

        info = {
            "thought": thought,
            "events": events,
            "tick": self.current_state["meta"]["tick"],
        }

        return observation, done, info

    def _get_llm_prediction(self, action: dict) -> dict:
        """
        Get state transition prediction from LLM.

        Args:
            action: The action to process.

        Returns:
            LLM response with state_ops, thought, events.
        """
        # Simulator LLM sees the FULL state (including hidden_state)
        # so it can correctly predict state transitions
        # (Only the Agent sees filtered observations)

        # current_state is guaranteed non-None here (checked in step())
        assert self.current_state is not None

        # Build user message with full state
        user_message = self._build_user_message(self.current_state, action)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Call LLM with role-specific model
        response = self.llm_client.complete(
            messages=messages,
            provider=self.provider,
            model_name=self.model_name,
            json_mode=True,
        )

        # Handle string response (shouldn't happen with json_mode, but be safe)
        raw_response = response
        if isinstance(response, str):
            response = json.loads(response)

        # Handle list response (LLM sometimes returns [{}] instead of {})
        if isinstance(response, list):
            response = response[0] if response else {}

        # Ensure response is a dict
        if not isinstance(response, dict):
            logger.warning(f"Unexpected response type: {type(response)}, using empty dict")
            response = {}

        # Attach full LLM data flow for debugging/visualization
        response["_llm_data"] = {
            "role": "simulator",
            "provider": self.provider,
            "model": self.model_name,
            "system_prompt": self.system_prompt,
            "user_message": user_message,
            "raw_response": raw_response if isinstance(raw_response, str) else json.dumps(raw_response),
        }

        return response

    def _build_user_message(self, state: dict, action: dict) -> str:
        """Build the user message for the Simulator LLM.

        Args:
            state: The FULL state (including hidden_state) - Simulator needs this
                   to correctly predict transitions (e.g., clipboard, correct answers).
            action: The action from the agent.
        """
        parts = []

        # Add instruction context if available
        if self.instruction:
            parts.append(f"## Task Instruction\n{self.instruction.get('instruction', '')}\n")

        # Add current state (FULL state for Simulator LLM)
        parts.append("## Current State (Full - including hidden_state)")
        parts.append(f"```json\n{json.dumps(state, indent=2)}\n```\n")

        # Add action
        parts.append("## Action")
        parts.append(f"```json\n{json.dumps(action, indent=2)}\n```\n")

        # Add guidance
        parts.append("## Your Task")
        parts.append("Analyze the action and determine what state changes should occur.")
        parts.append("Output the state_ops to transform the state accordingly.")

        return "\n".join(parts)

    def _check_done(self) -> bool:
        """
        Check if the episode should end.

        Override this method for custom termination conditions.
        """
        if self.current_state is None:
            return True

        # Check if status is already set to completed/failed
        status = self.current_state.get("meta", {}).get("status", "running")
        if status in ("completed", "failed"):
            return True

        # Check max steps
        max_steps = self.simulator_config.get("max_steps_per_episode", 50)
        if self.current_state["meta"]["tick"] >= max_steps:
            self.current_state["meta"]["status"] = "failed"
            return True

        return False

    def get_state(self) -> dict:
        """Get the current full state (including hidden_state)."""
        return copy.deepcopy(self.current_state) if self.current_state else {}

    def get_observation(self) -> dict:
        """Get the current observation (filtered state)."""
        if self.current_state is None:
            return {}
        return render_observation(self.current_state)

    def get_history(self) -> list[dict]:
        """Get the action history."""
        return copy.deepcopy(self.history)

    def get_difficulty(self) -> DifficultyConfig:
        """Get the current difficulty configuration."""
        return self.difficulty

    def set_difficulty(
        self,
        preset: Optional[str] = None,
        difficulty_config: Optional[DifficultyConfig] = None,
    ):
        """
        Change the simulator difficulty.

        This regenerates the system prompt with new difficulty modifiers.
        Useful for curriculum learning within a session.

        Args:
            preset: Difficulty preset ("easy", "medium", "hard", "expert").
            difficulty_config: Custom difficulty configuration.
        """
        if difficulty_config is not None:
            self.difficulty = difficulty_config
        elif preset is not None:
            self.difficulty = get_difficulty_config(preset=preset)
        else:
            raise ValueError("Must specify either preset or difficulty_config")

        # Regenerate system prompt with new difficulty
        self.system_prompt = self._load_system_prompt()
        logger.info(f"Simulator difficulty changed to: {self.difficulty.preset}")

    def save_episode(self, path: str):
        """
        Save the episode to a file.

        Args:
            path: Path to save the episode JSON.
        """
        episode = {
            "instruction": self.instruction,
            "initial_state": self.initial_state,
            "final_state": self.current_state,
            "history": self.history,
        }

        with open(path, "w") as f:
            json.dump(episode, f, indent=2)

        logger.info(f"Episode saved to {path}")

    def load_episode(self, path: str):
        """
        Load an episode from a file.

        Args:
            path: Path to the episode JSON.
        """
        with open(path, "r") as f:
            episode = json.load(f)

        self.instruction = episode.get("instruction")
        self.initial_state = episode.get("initial_state")
        self.current_state = episode.get("final_state")
        self.history = episode.get("history", [])

        logger.info(f"Episode loaded from {path}")


def create_simulator(
    config_path: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> Simulator:
    """
    Create a new simulator instance.

    Args:
        config_path: Path to config file.
        difficulty: Difficulty preset ("easy", "medium", "hard", "expert").

    Returns:
        Simulator instance.
    """
    return Simulator(config_path=config_path, difficulty=difficulty)
