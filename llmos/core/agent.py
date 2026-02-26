"""
Agent for LLMos.

Uses the shared indexed accessibility tree format (shared.format) so that
the model sees the exact same observation/action format as it would during
WebAgentBench evaluation. Converts unified actions back to LLMos actions
so the episode loop (Orchestrator.run_episode) works without changes.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..utils.llm_client import LLMClient
from shared.format import (
    SYSTEM_PROMPT,
    parse_action,
    build_initial_message,
    build_step_message,
)
from shared.llmos_adapter import state_to_indexed_tree, unified_action_to_llmos

logger = logging.getLogger(__name__)


class Agent:
    """
    LLM-based agent using the unified indexed accessibility tree format.

    Internally converts:
      observation → indexed tree → LLM → unified action → LLMos action
    """

    MAX_HISTORY_MESSAGES = 20  # 10 turns

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_path: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        self.llm_client = llm_client or LLMClient(config_path)

        if config is None:
            config_path = config_path or str(Path(__file__).parent.parent / "config.json")
            with open(config_path) as f:
                config = json.load(f)

        llm_config = config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("agent", {})
        self.provider = provider or role_config.get("provider", llm_config.get("default_provider"))
        self.model_name = model_name or role_config.get("model")

        self.conversation_history: list[dict] = []
        self.instruction: Optional[str] = None
        self._last_status: str = ""

    def reset(self, instruction: str):
        """Reset for a new task."""
        self.instruction = instruction
        self.conversation_history = []
        self._last_status = ""

    def act(self, observation: dict) -> dict:
        """
        Generate an action from the observation.

        Converts observation to indexed tree, calls LLM with the shared
        unified prompt, parses a unified action, then converts it to a
        LLMos action dict that the simulator understands.
        """
        # Convert observation to indexed tree
        tree_text, ref_to_bid = state_to_indexed_tree(observation)

        # Build current user message
        if not self.conversation_history:
            user_msg = build_initial_message(self.instruction, tree_text)
        else:
            user_msg = build_step_message(self._last_status, tree_text)

        # Assemble full message list
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_msg})

        # Call LLM
        response = self.llm_client.complete(
            messages=messages,
            model_name=self.model_name,
            provider=self.provider,
            json_mode=True,
        )

        raw_response = response if isinstance(response, str) else json.dumps(response)
        unified_action = parse_action(raw_response)
        thought = unified_action.get("thought", "")

        # Convert to LLMos action
        llmos_action = unified_action_to_llmos(unified_action, ref_to_bid)

        # Update conversation history
        self.conversation_history.append({"role": "user", "content": user_msg})
        self.conversation_history.append({"role": "assistant", "content": raw_response})

        if len(self.conversation_history) > self.MAX_HISTORY_MESSAGES:
            first_turn = self.conversation_history[:2]
            recent = self.conversation_history[-(self.MAX_HISTORY_MESSAGES - 2):]
            self.conversation_history = first_turn + recent

        # Build status for next step's message
        self._last_status = _make_status(unified_action)

        # Attach metadata for debugging and trajectory export
        llmos_action["thought"] = thought
        llmos_action["_llm_data"] = {
            "role": "agent",
            "provider": self.provider,
            "model": self.model_name,
            "raw_response": raw_response,
            "thought": thought,
            "unified_action": {k: v for k, v in unified_action.items() if k != "thought"},
            "tree_text": tree_text,
            "ref_to_bid": ref_to_bid,
        }

        return llmos_action


class HumanAgent:
    """Human-in-the-loop agent for debugging/demonstration."""

    def __init__(self):
        self.instruction: Optional[str] = None

    def reset(self, instruction: str):
        """Reset for new task."""
        self.instruction = instruction
        print(f"\n=== New Task ===\n{instruction}\n")

    def act(self, observation: dict) -> dict:
        """Get action from human input, showing the indexed tree."""
        tree_text, ref_to_bid = state_to_indexed_tree(observation)

        tick = observation.get("meta", {}).get("tick", 0)
        print(f"\n=== Step {tick} ===")
        print(tree_text)
        print(f"\nref → bid: {ref_to_bid}")

        print("\nEnter action as JSON (e.g. {\"action\":\"click\",\"ref\":3}):")
        try:
            user_input = input("> ").strip()
            if user_input.lower() in ("noop", "wait"):
                return {"action_type": "noop"}
            unified_action = json.loads(user_input)
            return unified_action_to_llmos(unified_action, ref_to_bid)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error: {e}, using noop")
            return {"action_type": "noop"}
        except EOFError:
            return {"action_type": "noop"}


def create_agent(
    agent_type: str = "llm",
    config_path: Optional[str] = None,
    **kwargs,
) -> Agent | HumanAgent:
    """Create an agent instance."""
    if agent_type == "human":
        return HumanAgent()
    return Agent(config_path=config_path, **kwargs)


def _make_status(action: dict) -> str:
    """Construct a human-readable status message from a unified action."""
    name = action.get("action", "wait")
    ref = action.get("ref")

    if name == "click" and ref:
        return f"Clicked [{ref}]"
    if name == "dblclick" and ref:
        return f"Double-clicked [{ref}]"
    if name == "fill" and ref:
        return f'Filled [{ref}] with "{action.get("value", "")[:50]}"'
    if name == "select" and ref:
        return f'Selected "{action.get("value", "")}" in [{ref}]'
    if name == "check" and ref:
        return f"Checked [{ref}]"
    if name == "uncheck" and ref:
        return f"Unchecked [{ref}]"
    if name == "hover" and ref:
        return f"Hovered [{ref}]"
    if name == "press":
        return f"Pressed {action.get('key', '')}"
    if name == "scroll":
        return f"Scrolled {action.get('direction', 'down')}"
    if name == "drag_and_drop":
        return f"Dragged [{action.get('from_ref')}] to [{action.get('to_ref')}]"
    if name == "wait":
        return "Waited"
    if name == "finish":
        return "Finished"
    return "Action executed"
