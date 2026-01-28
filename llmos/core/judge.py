"""
Judge Module for LLMOS.
Evaluates agent performance and provides scores.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ..utils.llm_client import LLMClient
from ..utils.rendering import render_ui_as_text
from ..utils.validation import validate_judge_output

logger = logging.getLogger(__name__)


class Judge:
    """
    Evaluates agent performance on tasks.

    Prioritizes fast programmatic evaluation; falls back to LLM for complex cases.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_path: Optional[str] = None,
        use_llm: bool = True,
        fast_model: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """
        Initialize the judge.

        Args:
            llm_client: LLM client instance.
            config_path: Path to config file.
            use_llm: Whether to use LLM for evaluation (disable for speed).
            fast_model: Model name for fast evaluation (overrides config).
            provider: LLM provider to use (overrides config).
        """
        self.llm_client = llm_client or LLMClient(config_path)
        self.use_llm = use_llm

        # Load config for role-specific settings
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.json"
        with open(config_path, "r") as f:
            config = json.load(f)

        self.max_steps_per_episode = config.get("simulator", {}).get("max_steps_per_episode", 50)

        # Get role-specific LLM settings (params override config)
        llm_config = config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("judge", {})
        self.provider = provider or role_config.get("provider", llm_config.get("default_provider"))
        self.fast_model = fast_model or role_config.get("model")

        # Load system prompt (compact version for speed)
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the judge system prompt."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "judge.system.md"

        if prompt_path.exists():
            with open(prompt_path, "r") as f:
                return f.read()

        return self._get_default_system_prompt()

    def _get_default_system_prompt(self) -> str:
        """Get the default judge system prompt."""
        return """You are a fair and thorough evaluator of computer-use agent performance.

## Your Task
Evaluate whether an agent successfully completed a given task based on:
1. The original instruction
2. The final state of the system
3. The action history

## Evaluation Criteria
- **Success**: Did the agent achieve the stated goal?
- **Efficiency**: Did the agent take a reasonable number of steps?
- **Correctness**: Were the agent's actions appropriate?

## Output Format
Return a JSON object with:
{
  "score": <0.0 to 1.0>,
  "success": <true/false>,
  "reasoning": "<explanation of your evaluation>",
  "feedback": "<constructive feedback for improvement>",
  "partial_credits": [
    {"criterion": "<criterion>", "met": <true/false>, "weight": <0-1>, "note": "<note>"}
  ],
  "error_analysis": {
    "error_type": "<none|wrong_action|incomplete|timeout|wrong_target|misunderstanding>",
    "critical_mistake_step": <step number or null>,
    "suggestion": "<improvement suggestion>"
  }
}

## Scoring Guidelines
- 1.0: Perfect completion
- 0.8-0.99: Completed with minor issues
- 0.5-0.79: Partially completed
- 0.1-0.49: Made progress but failed
- 0.0: No meaningful progress
"""

    def evaluate(
        self,
        instruction: dict,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict] = None,
    ) -> dict:
        """
        Evaluate an episode.

        Evaluation order (fast to slow):
        1. Programmatic evaluation (instant) - if success_criteria defined
        2. Heuristic evaluation (instant) - basic success heuristics
        3. LLM evaluation (slow) - only if needed and enabled

        Args:
            instruction: The task instruction.
            final_state: The final state after the episode.
            history: List of action history entries.
            initial_state: Optional initial state for comparison.

        Returns:
            Judge output dict with score, success, reasoning, etc.
        """
        # 1. Try programmatic evaluation first (instant, no LLM)
        if instruction and "success_criteria" in instruction:
            prog_result = self._programmatic_evaluate(
                instruction["success_criteria"],
                final_state,
                history
            )
            if prog_result is not None:
                return prog_result

        # 2. Try heuristic evaluation (instant)
        heuristic_result = self._heuristic_evaluate(instruction, final_state, history)
        if heuristic_result is not None:
            return heuristic_result

        # 3. Fall back to LLM evaluation (if enabled)
        if self.use_llm:
            return self._llm_evaluate(instruction, final_state, history, initial_state)

        # 4. Default: unable to evaluate without LLM
        return self._default_output("No success_criteria and LLM disabled")

    def _heuristic_evaluate(
        self,
        instruction: dict,
        final_state: dict,
        history: list[dict]
    ) -> Optional[dict]:
        """
        Fast heuristic evaluation without LLM.

        Returns evaluation for clear-cut cases:
        - Timeout (max steps reached)
        - Status explicitly set to completed/failed
        - No actions taken

        Scoring: success=1.0, partial=-0.5, failure=-1.0

        Returns None if heuristics can't determine outcome.
        """
        status = final_state.get("meta", {}).get("status", "running")
        tick = final_state.get("meta", {}).get("tick", 0)
        num_actions = len(history)

        # Case 1: Explicit status set by simulator
        # Do not treat status alone as authoritative success. In this project, the
        # environment may set status optimistically (or the agent may terminate early).
        # Prefer programmatic criteria or LLM evaluation with evidence.
        if status == "completed":
            return None

        if status == "failed":
            # Check if timeout (partial credit for trying)
            if tick >= self.max_steps_per_episode:
                return {
                    "score": -0.5,  # Partial penalty for timeout (at least tried)
                    "success": False,
                    "reasoning": f"Timeout: reached max steps ({tick}/{self.max_steps_per_episode})",
                    "feedback": "Try to complete the task more efficiently",
                    "error_analysis": {"error_type": "timeout", "critical_mistake_step": None, "suggestion": "Plan actions more carefully"}
                }
            return {
                "score": -1.0,  # Full penalty for explicit failure
                "success": False,
                "reasoning": "Task failed (status=failed)",
                "feedback": "Review the approach",
                "error_analysis": {"error_type": "incomplete", "critical_mistake_step": None, "suggestion": ""}
            }

        # Case 2: No actions taken
        if num_actions == 0:
            return {
                "score": -1.0,  # Full penalty for no attempt
                "success": False,
                "reasoning": "No actions were taken",
                "feedback": "Agent did not attempt the task",
                "error_analysis": {"error_type": "incomplete", "critical_mistake_step": 0, "suggestion": "Start by analyzing the UI"}
            }

        # Can't determine from heuristics alone
        return None

    def _programmatic_evaluate(
        self,
        criteria: dict,
        final_state: dict,
        history: list[dict]
    ) -> Optional[dict]:
        """
        Attempt programmatic evaluation based on success criteria.

        Args:
            criteria: Success criteria from instruction.
            final_state: Final state.
            history: Action history.

        Returns:
            Judge output if evaluation possible, None otherwise.
        """
        criteria_type = criteria.get("type")
        conditions = criteria.get("conditions", [])

        if criteria_type == "state_match" and conditions:
            return self._evaluate_state_match(conditions, final_state)

        return None

    def _evaluate_state_match(
        self,
        conditions: list[dict],
        state: dict
    ) -> dict:
        """
        Evaluate state match conditions.

        Args:
            conditions: List of conditions to check.
            state: State to check against.

        Returns:
            Judge output.
        """
        partial_credits = []
        total_weight = 0
        earned_weight = 0

        for condition in conditions:
            path = condition.get("path", "")
            operator = condition.get("operator", "equals")
            expected = condition.get("value")
            weight = condition.get("weight", 1.0)

            total_weight += weight

            # Get actual value from state
            actual = self._get_value_by_path(state, path)

            # Check condition
            met = self._check_condition(actual, operator, expected)

            if met:
                earned_weight += weight

            partial_credits.append({
                "criterion": f"{path} {operator} {expected}",
                "met": met,
                "weight": weight,
                "note": f"Actual: {actual}"
            })

        # Calculate score: map [0, 1] to [-1, 1]
        # 0% met -> -1.0, 50% met -> 0.0, 100% met -> 1.0
        raw_score = earned_weight / total_weight if total_weight > 0 else 0
        score = (raw_score * 2) - 1  # Linear mapping: 0->-1, 0.5->0, 1->1
        success = raw_score >= 0.9  # 90% threshold for success

        return {
            "score": score,
            "success": success,
            "reasoning": f"Programmatic evaluation: {earned_weight}/{total_weight} conditions met ({raw_score:.0%})",
            "partial_credits": partial_credits,
            "feedback": "See partial credits for details",
            "error_analysis": {
                "error_type": "none" if success else "incomplete",
                "critical_mistake_step": None,
                "suggestion": "" if success else "Some conditions were not met"
            }
        }

    def _get_value_by_path(self, obj: dict, path: str) -> Any:
        """
        Get a value from a nested dict using dot notation path.

        Args:
            obj: The dict to search.
            path: Dot-separated path (e.g., "meta.tick" or "ui.children.0.text").

        Returns:
            The value at the path, or None if not found.
        """
        if not path:
            return obj

        parts = path.split(".")
        current = obj

        for part in parts:
            if current is None:
                return None

            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx] if 0 <= idx < len(current) else None
                except ValueError:
                    return None
            else:
                return None

        return current

    def _check_condition(self, actual: Any, operator: str, expected: Any) -> bool:
        """
        Check if a condition is met.

        Args:
            actual: Actual value.
            operator: Comparison operator.
            expected: Expected value.

        Returns:
            True if condition is met.
        """
        if operator == "equals":
            return actual == expected
        elif operator == "contains":
            if isinstance(actual, str):
                return expected in actual
            elif isinstance(actual, (list, dict)):
                return expected in actual
            return False
        elif operator == "exists":
            return actual is not None
        elif operator == "not_exists":
            return actual is None
        elif operator == "greater_than":
            try:
                return float(actual) > float(expected)
            except (TypeError, ValueError):
                return False
        elif operator == "less_than":
            try:
                return float(actual) < float(expected)
            except (TypeError, ValueError):
                return False

        return False

    def _llm_evaluate(
        self,
        instruction: dict,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict],
    ) -> dict:
        """
        Evaluate using LLM (minimal information for speed).

        Args:
            instruction: Task instruction.
            final_state: Final state.
            history: Action history.
            initial_state: Initial state.

        Returns:
            Judge output.
        """
        # Build compact user message (minimal info for speed)
        user_message = self._build_compact_message(instruction, final_state, history)

        # Use compact system prompt for speed
        compact_prompt = """You are evaluating whether a computer-use agent truly completed the task.
Do NOT trust environment status fields (e.g., meta.status='completed') or the agent claiming success.
Evaluate based on concrete evidence in the final state and the action history/events.
Return JSON:
{"score": -1.0 to 1.0 (failure=-1, partial=0, success=1), "success": true/false, "reasoning": "brief explanation", "feedback": "one tip", "error_analysis": {"error_type": "none|wrong_action|incomplete|timeout|misunderstanding|wrong_target", "critical_mistake_step": null, "suggestion": ""}}"""

        messages = [
            {"role": "system", "content": compact_prompt},
            {"role": "user", "content": user_message},
        ]

        response = self.llm_client.complete(
            messages=messages,
            provider=self.provider,
            model_name=self.fast_model,
            json_mode=True,
        )

        # Handle string response
        raw_response = response
        if isinstance(response, str):
            response = json.loads(response)

        # Normalize common type issues before schema validation
        if isinstance(response, dict):
            score = response.get("score")
            if isinstance(score, str):
                response["score"] = float(score)  # Let ValueError raise

            success = response.get("success")
            if isinstance(success, str):
                lowered = success.strip().lower()
                if lowered == "true":
                    response["success"] = True
                elif lowered == "false":
                    response["success"] = False
                else:
                    raise ValueError(f"Invalid success value from LLM: {success!r}")

            if "reasoning" not in response or not isinstance(response.get("reasoning"), str):
                response["reasoning"] = str(response.get("reasoning", ""))

            error_analysis = response.get("error_analysis")
            if isinstance(error_analysis, dict):
                cms = error_analysis.get("critical_mistake_step")
                if isinstance(cms, str):
                    error_analysis["critical_mistake_step"] = int(cms)  # Let ValueError raise

        # Validate response
        is_valid, errors = validate_judge_output(response)
        if not is_valid:
            raise ValueError(f"Invalid judge output: {errors}")

        # Attach LLM data flow for debugging/visualization
        response["_llm_data"] = {
            "role": "judge",
            "provider": self.provider,
            "model": self.fast_model,
            "system_prompt": compact_prompt,
            "user_message": user_message,
            "raw_response": raw_response if isinstance(raw_response, str) else json.dumps(raw_response),
        }

        return response

    def _build_compact_message(
        self,
        instruction: dict,
        final_state: dict,
        history: list[dict],
    ) -> str:
        """Build a minimal evaluation message for fast LLM evaluation."""
        # Task (one line)
        task = instruction.get("instruction", "Unknown task") if instruction else "Unknown task"

        # Outcome summary (minimal)
        status = final_state.get("meta", {}).get("status", "running")
        tick = final_state.get("meta", {}).get("tick", 0)

        # Action summary (just types and count, no details)
        action_types = [h.get("action", {}).get("action_type", "?") for h in history]
        action_summary = f"{len(history)} actions"
        if action_types:
            # Count action types
            from collections import Counter
            counts = Counter(action_types)
            action_summary += f": {dict(counts)}"

        # Evidence snippets
        active_tab = next((t for t in final_state.get("tabs", []) if t.get("active")), None)
        active_tab_summary = ""
        if active_tab:
            active_tab_summary = f"url={active_tab.get('url','')}, title={active_tab.get('title','')}"

        recent_events: list[str] = []
        for entry in history[-5:]:
            for ev in entry.get("events", []) or []:
                if isinstance(ev, str) and ev:
                    recent_events.append(ev[:200])
        if len(recent_events) > 10:
            recent_events = recent_events[-10:]

        ui_text = render_ui_as_text(final_state)
        if len(ui_text) > 2000:
            ui_text = ui_text[:2000] + "\n... [truncated]"

        return f"""Task: {task}
Result: status={status}, steps={tick}
ActiveTab: {active_tab_summary}
Actions: {action_summary}
RecentEvents: {recent_events}
UI (text):\n{ui_text}
Did the agent complete the task?"""

    def _build_evaluation_message(
        self,
        instruction: dict,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict],
    ) -> str:
        """Build the full evaluation message for LLM (legacy, more detailed)."""
        parts = []

        # Instruction
        parts.append("## Task Instruction")
        if instruction:
            inst_text = instruction.get("instruction", str(instruction))
            parts.append(inst_text)
        else:
            parts.append("(No instruction provided)")
        parts.append("")

        # Final state summary
        parts.append("## Final State")
        state_summary = {
            "tick": final_state.get("meta", {}).get("tick"),
            "status": final_state.get("meta", {}).get("status"),
        }
        parts.append(f"```json\n{json.dumps(state_summary, indent=2)}\n```")
        parts.append("")

        # Action history
        parts.append("## Action History")
        parts.append(f"Total steps: {len(history)}")
        if history:
            parts.append("\nActions taken:")
            for i, entry in enumerate(history[-10:]):  # Last 10 actions
                action = entry.get("action", {})
                thought = entry.get("thought", "")[:50]
                parts.append(f"{i+1}. {action.get('action_type', '?')}: {thought}...")
        parts.append("")

        parts.append("Please evaluate the agent's performance.")

        return "\n".join(parts)

    def _default_output(self, error_reason: str) -> dict:
        """Generate default output on evaluation error.

        Uses a neutral score (0.0) rather than a harsh penalty (-1.0) because
        evaluation errors (e.g., LLM API failures) are not the agent's fault
        and shouldn't unduly penalize training. A score of 0.0 means "no signal"
        rather than "agent failed".
        """
        return {
            "score": 0.0,  # Neutral score for evaluation errors (not agent's fault)
            "success": False,
            "reasoning": f"Evaluation error: {error_reason}",
            "feedback": "Could not properly evaluate - this is not counted as a failure",
            "error_analysis": {
                "error_type": "evaluation_error",
                "critical_mistake_step": None,
                "suggestion": "Evaluation infrastructure issue, not agent error"
            }
        }


def create_judge(config_path: Optional[str] = None) -> Judge:
    """Create a judge instance."""
    return Judge(config_path=config_path)
