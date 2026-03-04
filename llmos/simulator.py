"""
LLM-based OS Simulator.

Predicts UI state transitions using an LLM as the "physics engine".
Given (current_state, action), calls the LLM to predict state_ops,
then applies them deterministically via patching.
"""

import copy
import json
import logging
import re
from pathlib import Path
from typing import Optional

from .utils.llm_client import LLMClient
from .utils.patching import apply_id_patch, validate_ops
from .utils.rendering import render_observation, render_ui_as_text

logger = logging.getLogger(__name__)


class Simulator:
    """
    LLM-based state transition engine.

    Usage:
        sim = Simulator(llm_client)
        obs = sim.reset("desktop", instruction)
        obs, done, info = sim.step(action)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_path: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        system_prompt: Optional[str] = None,
        behavior: str = "",
        max_steps: int = 50,
    ):
        """
        Args:
            llm_client: LLM client instance.
            config_path: Path to config.json.
            model: LLM model name (overrides config).
            provider: LLM provider (overrides config).
            system_prompt: Custom system prompt (overrides default).
            behavior: Extra instructions appended to the system prompt.
                      Use this to control difficulty, strictness, or
                      scenario-specific behavior without changing the base prompt.
            max_steps: Maximum steps per episode.
        """
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.json")
        self._config_path = Path(config_path)

        with open(self._config_path) as f:
            config = json.load(f)

        self.llm_client = llm_client or LLMClient(config_path)

        # Resolve model/provider from config
        llm_config = config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("simulator", {})
        self.provider = provider or role_config.get("provider", llm_config.get("default_provider"))
        self.model = model or role_config.get("model")
        self.max_steps = max_steps

        # Load system prompt
        if system_prompt:
            self._system_prompt = system_prompt
        else:
            self._system_prompt = self._load_default_prompt()

        # Append behavior instructions
        if behavior:
            self._system_prompt += f"\n\n## Behavior\n\n{behavior}"

        # Episode state
        self.current_state: Optional[dict] = None
        self.initial_state: Optional[dict] = None
        self.instruction: Optional[dict] = None
        self.history: list[dict] = []
        self._step_count: int = 0

    def _load_default_prompt(self) -> str:
        """Load the default simulator system prompt."""
        prompt_path = self._config_path.parent / "prompts" / "simulator.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        # Inline fallback
        return (
            "You are the World Engine. You simulate a computer OS environment.\n"
            "Given current_state and action, output state_ops as JSON.\n"
            "Target elements by bid. Only output changed properties.\n"
        )

    # =========================================================================
    # Core Interface
    # =========================================================================

    def reset(
        self,
        template_name: Optional[str] = None,
        instruction: Optional[dict] = None,
        initial_state: Optional[dict] = None,
    ) -> dict:
        """
        Reset the simulator to an initial state.

        Args:
            template_name: Name of template to load (e.g. "desktop", "browser").
            instruction: Task instruction dict.
            initial_state: Pre-built initial state (mutually exclusive with template_name).

        Returns:
            Initial observation (filtered for agent).
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

        # Store task paths in hidden_state for on-demand content generation
        initial_state = self._enhance_for_task(initial_state, instruction)

        self.initial_state = copy.deepcopy(initial_state)
        self.current_state = copy.deepcopy(initial_state)
        self.instruction = instruction
        self.history = []
        self._step_count = 0

        # Ensure meta
        self.current_state.setdefault("meta", {})
        self.current_state["meta"]["tick"] = 0
        self.current_state["meta"]["status"] = "running"

        return render_observation(self.current_state)

    def step(self, action: dict) -> tuple[dict, bool, dict]:
        """
        Execute one step.

        Args:
            action: Action dict from the agent.

        Returns:
            (observation, done, info)
        """
        if self.current_state is None:
            raise RuntimeError("Simulator not initialized. Call reset() first.")

        # Extract debug payload before cleaning
        agent_llm_data = action.get("_llm_data", {})
        action_clean = {k: v for k, v in action.items() if not k.startswith("_")}

        # Handle finish action
        if action.get("action_type") == "finish":
            return self._handle_finish(action_clean, agent_llm_data)

        # Get LLM prediction
        llm_response = self._predict(action_clean)

        # Extract components
        thought = llm_response.get("thought", "")
        state_ops = llm_response.get("state_ops", [])
        events = llm_response.get("events", [])
        if isinstance(events, str):
            events = [events]

        # Validate and apply patches
        op_errors = validate_ops(state_ops)
        if op_errors:
            logger.warning(f"Invalid state operations: {op_errors}")
        apply_id_patch(self.current_state, state_ops)

        # Increment tick
        self.current_state["meta"]["tick"] += 1
        self._step_count += 1

        # Check done
        done = self._check_done()
        if done and self.current_state["meta"].get("status") != "failed":
            self.current_state["meta"]["status"] = "completed"

        # Record history
        step_record = {
            "tick": self.current_state["meta"]["tick"],
            "step": self._step_count,
            "action": dict(action_clean),
            "thought": thought,
            "agent_thought": agent_llm_data.get("thought", ""),
            "state_ops": copy.deepcopy(state_ops),
            "events": list(events),
            "agent_llm_data": dict(agent_llm_data),
            "simulator_llm_data": dict(llm_response.get("_llm_data", {})),
        }
        self.history.append(step_record)

        info = {
            "thought": thought,
            "events": events,
            "tick": self.current_state["meta"]["tick"],
        }

        return render_observation(self.current_state), done, info

    def get_state(self) -> dict:
        """Get the full current state (for judge/evaluation)."""
        return copy.deepcopy(self.current_state) if self.current_state else {}

    def get_history(self) -> list[dict]:
        """Get the episode history."""
        return list(self.history)

    # =========================================================================
    # Internal
    # =========================================================================

    def _handle_finish(
        self, action: dict, agent_llm_data: dict,
    ) -> tuple[dict, bool, dict]:
        """Handle finish action."""
        self.current_state["meta"]["tick"] += 1
        self.current_state["meta"]["status"] = "completed"

        events = [action.get("text")] if action.get("text") else []

        self.history.append({
            "tick": self.current_state["meta"]["tick"],
            "step": self._step_count + 1,
            "action": dict(action),
            "thought": "",
            "agent_thought": agent_llm_data.get("thought", ""),
            "state_ops": [],
            "events": list(events),
            "agent_llm_data": dict(agent_llm_data),
            "simulator_llm_data": {},
        })

        return render_observation(self.current_state), True, {"events": events}

    def _predict(self, action: dict) -> dict:
        """Call LLM to predict state transition."""
        user_message = self._build_user_message(action)

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_message},
        ]

        response = self.llm_client.complete(
            messages=messages,
            provider=self.provider,
            model_name=self.model,
            json_mode=True,
        )

        raw_response = response
        if isinstance(response, str):
            response = json.loads(response)
        if isinstance(response, list):
            response = response[0] if response else {}
        if not isinstance(response, dict):
            response = {}

        response["_llm_data"] = {
            "role": "simulator",
            "provider": self.provider,
            "model": self.model,
            "system_prompt": self._system_prompt,
            "user_message": user_message,
            "raw_response": raw_response if isinstance(raw_response, str) else json.dumps(raw_response),
        }

        return response

    def _build_user_message(self, action: dict) -> str:
        """Build user message for the LLM."""
        parts = []

        if self.instruction:
            parts.append(f"## Task Instruction\n{self.instruction.get('instruction', '')}\n")

        parts.append("## Current State (Full - including hidden_state)")
        state_json = json.dumps(self._prepare_state(), indent=2)
        if len(state_json) > 15000:
            state_json = state_json[:15000] + "\n... (truncated)"
        parts.append(f"```json\n{state_json}\n```\n")

        parts.append("## Action")
        parts.append(f"```json\n{json.dumps(action, indent=2)}\n```\n")

        # History context (last 5 steps)
        if self.history:
            parts.append("## Recent History")
            for step in self.history[-5:]:
                a = step.get("action", {})
                parts.append(f"- Step {step.get('step', '?')}: {a.get('action_type', '?')}")
            parts.append("")

        # BID reminder
        top_bids = self._collect_top_bids()
        if top_bids:
            parts.append(f"**Active bids**: {', '.join(top_bids)}. Reuse these bids when updating elements.\n")

        parts.append("Predict the state changes that result from this action.")
        return "\n".join(parts)

    def _prepare_state(self) -> dict:
        """Prepare state for the LLM prompt (full state including hidden_state)."""
        if self.current_state is None:
            return {}
        state = copy.deepcopy(self.current_state)
        # Truncate long text fields
        self._truncate_node(state.get("ui", {}))
        return state

    def _truncate_node(self, node: dict, max_text: int = 500) -> None:
        """Truncate long text in UI nodes recursively."""
        if not isinstance(node, dict):
            return
        for key in ("text", "value"):
            val = node.get(key, "")
            if isinstance(val, str) and len(val) > max_text:
                node[key] = val[:max_text] + "..."
        for child in node.get("children", []):
            self._truncate_node(child, max_text)

    def _collect_top_bids(self) -> list[str]:
        """Collect top-level bids for the BID consistency hint."""
        if not self.current_state or "ui" not in self.current_state:
            return []
        bids = []
        root = self.current_state["ui"]
        if root.get("bid"):
            bids.append(str(root["bid"]))
        for child in root.get("children", []):
            if isinstance(child, dict) and child.get("bid"):
                bids.append(str(child["bid"]))
        return bids[:10]

    def _check_done(self) -> bool:
        """Check if the episode should end."""
        status = self.current_state.get("meta", {}).get("status", "running")
        if status in ("completed", "failed"):
            return True
        if self._step_count >= self.max_steps:
            self.current_state["meta"]["status"] = "failed"
            return True
        return False

    def _load_template(self, template_name: str) -> dict:
        """Load a state template by name."""
        template_path = self._config_path.parent / "templates" / f"{template_name}.json"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        with open(template_path) as f:
            return json.load(f)

    def _enhance_for_task(self, state: dict, instruction: Optional[dict]) -> dict:
        """Store task info in hidden_state for on-demand content generation."""
        if instruction is None:
            return state

        task_text = instruction.get("instruction", "")
        if not task_text:
            return state

        state.setdefault("hidden_state", {})
        # Extract directory paths mentioned in task
        paths = re.findall(r'(?:/[\w./]+|~/[\w./]+)', task_text)
        state["hidden_state"]["task_paths"] = [p.replace("~", "/home/user") for p in paths]
        state["hidden_state"]["task_instruction"] = task_text

        return state
