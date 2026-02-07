"""
Agent Wrapper for LLMOS.
Handles observation processing and action generation.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union

from ..utils.llm_client import LLMClient
from ..utils.rendering import render_ui_as_text, extract_focusable_elements
from ..utils.validation import validate_action_complete
from ..prompts.agent_prompt import AGENT_SYSTEM_PROMPT as DEFAULT_AGENT_PROMPT
from .action_space import ActionSpaceConfig, get_action_space, get_action_prompt_section

logger = logging.getLogger(__name__)


class Agent:
    """
    LLM-based Agent for interacting with the simulator.

    Processes observations and generates actions.
    """

    MAX_HISTORY_MESSAGES = 12
    MAX_FILESYSTEM_DISPLAY = 10

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_path: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        action_space: Optional[Union[str, ActionSpaceConfig]] = None,
        config: Optional[dict] = None,
    ):
        """
        Initialize the agent.

        Args:
            llm_client: LLM client instance. If None, creates new one.
            config_path: Path to config file.
            model_name: Model to use for the agent (overrides config).
            provider: LLM provider to use (overrides config).
            action_space: Action space preset ("minimal", "standard", "full") or config.
                          Default "minimal" excludes noop and send_msg_to_user.
            config: Pre-loaded config dict. If provided, skips file loading.
        """
        self.llm_client = llm_client or LLMClient(config_path)

        # Load config for role-specific settings
        if config is None:
            if config_path is None:
                config_path = str(Path(__file__).parent.parent / "config.json")
            with open(config_path, "r") as f:
                config = json.load(f)

        # Get role-specific LLM settings (params override config)
        llm_config = config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("agent", {})
        self.provider = provider or role_config.get("provider", llm_config.get("default_provider"))
        self.model_name = model_name or role_config.get("model")

        # Configure action space (default: minimal - no noop/send_msg_to_user)
        if action_space is None:
            self.action_space = get_action_space("minimal")
        elif isinstance(action_space, str):
            self.action_space = get_action_space(action_space)
        else:
            self.action_space = action_space

        self.allowed_actions = self.action_space.get_actions()

        # Load system prompt (with action space customization)
        self.system_prompt = self._load_system_prompt()

        # Conversation history for multi-turn
        self.conversation_history: list[dict] = []

        # Current instruction
        self.instruction: Optional[str] = None

    def _load_system_prompt(self) -> str:
        """Load the agent system prompt with dynamic action space."""
        return self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build system prompt with configured action space."""
        action_section = get_action_prompt_section(self.allowed_actions)

        return f"""You are a computer-use agent. Your task is to interact with a computer OS to accomplish user goals.

## Rules
1. **Output JSON only.** No markdown, no code fences.
2. **Never invent `bid`s.** Only use `bid` values from the current observation.
3. **One action per step.**

## Observation Format
You receive:
- `meta`: Current tick/step
- `ui`: Accessibility tree (elements have `bid` identifiers)
- `filesystem`: Visible files
- `tabs`: Browser tabs (if applicable)

## Action Space
{action_section}

## Output Format
```json
{{"thought": "Your reasoning", "action": {{"action_type": "...", ...}}}}
```

## Strategy
1. Read the instruction carefully
2. Find relevant elements by text/role
3. Use fill for inputs, click for buttons
4. Verify each action had the intended effect
5. Use finish when task is complete
"""

    def reset(self, instruction: str):
        """
        Reset the agent for a new task.

        Args:
            instruction: The task instruction.
        """
        self.instruction = instruction
        self.conversation_history = []

    def act(self, observation: dict) -> dict:
        """
        Generate an action based on the observation.

        Args:
            observation: The current observation from the simulator.

        Returns:
            Action dict. Falls back to noop on parse/validation failure.
        """
        # Build the user message
        user_message = self._build_user_message(observation)

        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        # Always include instruction at the start (it's the task context)
        if self.instruction:
            messages.append({
                "role": "user",
                "content": f"## Task\n{self.instruction}\n\nI will now show you the current state. Please complete this task."
            })

        # Add conversation history
        messages.extend(self.conversation_history)

        # Add current observation
        messages.append({"role": "user", "content": user_message})

        # Call LLM and parse response, with graceful fallback to noop
        thought = ""
        raw_response = None
        parse_error = None
        try:
            response = self.llm_client.complete(
                messages=messages,
                model_name=self.model_name,
                provider=self.provider,
                json_mode=True,
            )

            raw_response = response
            if isinstance(response, str):
                response = json.loads(response)

            # Handle list response (LLM sometimes returns [{}] instead of {})
            if isinstance(response, list):
                response = response[0] if response else {}

            # Ensure response is a dict
            if not isinstance(response, dict):
                logger.warning(f"Unexpected response type: {type(response)}")
                response = {}

            thought = response.get("thought", "")
            action = self._extract_action(response)

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            parse_error = str(e)
            logger.warning(f"Agent parse/validation error, falling back to noop: {e}")
            action = {"action_type": "noop"}
            if raw_response is not None:
                raw_str = raw_response if isinstance(raw_response, str) else json.dumps(raw_response)
                logger.debug(f"Raw response that failed: {raw_str[:500]}")

        # Attach LLM data flow for debugging/visualization
        action["_llm_data"] = {
            "role": "agent",
            "provider": self.provider,
            "model": self.model_name,
            "system_prompt": self.system_prompt,
            "user_message": user_message,
            "raw_response": raw_response if isinstance(raw_response, str) else json.dumps(raw_response) if raw_response is not None else "",
            "thought": thought,
        }
        if parse_error:
            action["_llm_data"]["_parse_error"] = parse_error

        # Update conversation history (compact + in-format to reinforce JSON-only outputs)
        # Only store the action (not _llm_data) to save tokens and avoid leaking internals.
        assistant_payload_action = dict(action)
        assistant_payload_action.pop("_llm_data", None)
        assistant_payload = {"thought": thought, "action": assistant_payload_action}

        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append(
            {"role": "assistant", "content": json.dumps(assistant_payload, separators=(",", ":"))}
        )

        # Keep history manageable while preserving context.
        # Strategy: Keep the first turn (2 messages) + last 5 turns (10 messages)
        # This preserves initial context which is critical for multi-step tasks.
        if len(self.conversation_history) > self.MAX_HISTORY_MESSAGES:
            # Keep first 2 messages (initial observation + response) + last (max_history - 2) messages
            first_turn = self.conversation_history[:2]
            recent_messages = self.conversation_history[-(self.MAX_HISTORY_MESSAGES - 2):]
            self.conversation_history = first_turn + recent_messages

        return action

    def _build_user_message(self, observation: dict) -> str:
        """Build the user message from observation."""
        parts = []

        # Add tick info
        tick = observation.get("meta", {}).get("tick", 0)
        parts.append(f"## Step {tick}\n")

        # Add UI tree as text (more readable)
        if "ui" in observation:
            parts.append("### UI Elements")
            ui_text = render_ui_as_text(observation)
            parts.append(f"```\n{ui_text}\n```\n")

        # Add tabs info
        if "tabs" in observation and observation["tabs"]:
            parts.append("### Browser Tabs")
            for tab in observation["tabs"]:
                active = " (active)" if tab.get("active") else ""
                parts.append(f"- Tab {tab.get('id')}: {tab.get('title', 'Untitled')}{active}")
            parts.append("")

        # Add filesystem info
        if "filesystem" in observation and observation["filesystem"]:
            parts.append("### Files")
            for path, info in list(observation["filesystem"].items())[:self.MAX_FILESYSTEM_DISPLAY]:
                parts.append(f"- {path}")
            parts.append("")

        parts.append("What action should I take next?")

        return "\n".join(parts)

    def _extract_action(self, response: dict) -> dict:
        """Extract action from LLM response. Returns noop on validation failure."""
        # Response should have 'action' key
        if "action" in response:
            action = response["action"]
        else:
            # Maybe the response is the action itself
            action = response

        # Validate action structure
        is_valid, errors = validate_action_complete(action)
        if not is_valid:
            logger.warning(f"Invalid action generated, falling back to noop: {errors}")
            return {"action_type": "noop"}

        # Validate action is in allowed set (noop always allowed as internal fallback)
        action_type = action.get("action_type")
        if action_type != "noop" and action_type not in self.allowed_actions:
            logger.warning(
                f"Action '{action_type}' not in allowed actions: {self.allowed_actions}, falling back to noop"
            )
            return {"action_type": "noop"}

        return action

    def get_thought(self, response: dict) -> str:
        """Extract thought from LLM response."""
        return response.get("thought", "")


class HumanAgent:
    """
    Human-in-the-loop agent for debugging/demonstration.
    """

    def __init__(self):
        self.instruction: Optional[str] = None

    def reset(self, instruction: str):
        """Reset for new task."""
        self.instruction = instruction
        print(f"\n=== New Task ===\n{instruction}\n")

    def act(self, observation: dict) -> dict:
        """
        Get action from human input.

        Args:
            observation: Current observation.

        Returns:
            Action dict.
        """
        # Display observation summary
        tick = observation.get("meta", {}).get("tick", 0)
        print(f"\n=== Step {tick} ===")

        # Show interactive elements
        interactive = extract_focusable_elements(observation)
        if interactive:
            print("\nInteractive elements:")
            for elem in interactive[:15]:
                print(f"  [{elem['bid']}] {elem['tag']}: {elem.get('text', '')[:30]}")

        # Get action from user
        print("\nEnter action as JSON (or 'noop'):")
        try:
            user_input = input("> ").strip()
            if user_input.lower() == "noop":
                return {"action_type": "noop"}
            return json.loads(user_input)
        except json.JSONDecodeError:
            print("Invalid JSON, using noop")
            return {"action_type": "noop"}
        except EOFError:
            return {"action_type": "noop"}


def create_agent(
    agent_type: str = "llm",
    config_path: Optional[str] = None,
    **kwargs
) -> Union[Agent, HumanAgent]:
    """
    Create an agent instance.

    Args:
        agent_type: Type of agent ('llm' or 'human').
        config_path: Path to config file.
        **kwargs: Additional arguments for the agent.

    Returns:
        Agent or HumanAgent instance.
    """
    if agent_type == "human":
        return HumanAgent()
    else:
        return Agent(config_path=config_path, **kwargs)
