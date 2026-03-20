"""
Unified Agent for LLMOS.

Uses the shared indexed accessibility tree format (shared.format) so that
the model sees the exact same observation/action format as WebAgentBench.
Converts unified actions back to LLMOS actions for the simulator.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .utils.llm_client import LLMClient
from shared.format import (
    SYSTEM_PROMPT,
    TreeNode,
    parse_action,
    build_initial_message,
    build_step_message,
)
from shared.llmos_adapter import state_to_indexed_tree, unified_action_to_llmos

logger = logging.getLogger(__name__)


class Agent:
    """
    LLM-based agent using the unified indexed accessibility tree format.

    Converts: observation → indexed tree → LLM → unified action → LLMOS action
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_path: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        json_mode: bool = False,
        max_history: Optional[int] = None,
    ):
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.json")

        self.llm_client = llm_client or LLMClient(config_path)

        with open(config_path) as f:
            config = json.load(f)

        llm_config = config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("agent", {})
        self.provider = provider or role_config.get("provider", llm_config.get("default_provider"))
        self.model = model or role_config.get("model")
        self.json_mode = json_mode
        self.max_history = max_history

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

        Returns an LLMOS action dict that the simulator understands.
        """
        # Convert observation to indexed tree
        is_wab = observation.get("meta", {}).get("platform") == "webagentbench"
        tree_text, ref_to_bid, node_map = state_to_indexed_tree(
            observation, skip_browser_chrome=is_wab,
        )

        # Build message
        if not self.conversation_history:
            user_msg = build_initial_message(self.instruction, tree_text)
        else:
            user_msg = build_step_message(self._last_status, tree_text)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_msg})

        # Call LLM
        response = self.llm_client.complete(
            messages=messages,
            model_name=self.model,
            provider=self.provider,
            json_mode=self.json_mode,
        )

        raw_response = response if isinstance(response, str) else json.dumps(response)
        unified_action = parse_action(raw_response)
        thought = unified_action.get("thought", "")

        # Convert to LLMOS action
        try:
            llmos_action = unified_action_to_llmos(unified_action, ref_to_bid)
        except KeyError as e:
            logger.warning(f"Agent referenced invalid ref {e} (valid refs: {sorted(ref_to_bid.keys())})")
            llmos_action = {"action_type": "noop"}
            # Override status so agent sees the error next step
            self._last_status = f"ERROR: ref {e} does not exist in the current page. Use only refs from the current observation."
            # Still record history so the agent learns from the mistake
            self.conversation_history.append({"role": "user", "content": user_msg})
            self.conversation_history.append({"role": "assistant", "content": raw_response})
            llmos_action["thought"] = thought
            llmos_action["_llm_data"] = {
                "role": "agent",
                "provider": self.provider,
                "model": self.model,
                "raw_response": raw_response,
                "thought": thought,
                "error": f"invalid ref {e}",
            }
            return llmos_action

        # Update conversation history
        self.conversation_history.append({"role": "user", "content": user_msg})
        self.conversation_history.append({"role": "assistant", "content": raw_response})

        if self.max_history is not None and len(self.conversation_history) > self.max_history:
            first_turn = self.conversation_history[:2]
            recent = self.conversation_history[-(self.max_history - 2):]
            self.conversation_history = first_turn + recent

        # Build status for next step
        self._last_status = _make_status(unified_action, node_map)

        # Attach metadata for debugging and trajectory export
        llmos_action["thought"] = thought
        llmos_action["_llm_data"] = {
            "role": "agent",
            "provider": self.provider,
            "model": self.model,
            "system_prompt": SYSTEM_PROMPT,
            "user_message": user_msg,
            "messages": messages,
            "raw_response": raw_response,
            "thought": thought,
            "unified_action": {k: v for k, v in unified_action.items() if k != "thought"},
            "tree_text": tree_text,
            "ref_to_bid": ref_to_bid,
        }

        return llmos_action


class HumanAgent:
    """Human-in-the-loop agent for debugging."""

    def __init__(self):
        self.instruction: Optional[str] = None

    def reset(self, instruction: str):
        self.instruction = instruction
        print(f"\n=== New Task ===\n{instruction}\n")

    def act(self, observation: dict) -> dict:
        tree_text, ref_to_bid, _ = state_to_indexed_tree(observation)
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


def _make_status(action: dict, node_map: Optional[dict[int, TreeNode]] = None) -> str:
    """Construct a status message matching WebAgentBench format."""
    name = action.get("action", "wait")
    ref = action.get("ref")

    def _ref_info(r: int) -> str:
        if node_map and r in node_map:
            node = node_map[r]
            return f' {node.role} "{node.name}"'
        return ""

    if name == "click" and ref:
        return f"Clicked [{ref}]{_ref_info(ref)}"
    if name == "dblclick" and ref:
        return f"Double-clicked [{ref}]{_ref_info(ref)}"
    if name == "fill" and ref:
        return f'Filled [{ref}] with "{str(action.get("value", ""))[:50]}"'
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
        return "Waited 1 second"
    if name == "finish":
        return "FINISH"
    return "Action executed"
