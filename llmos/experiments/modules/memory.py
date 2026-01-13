"""
Memory Module: How history/context is managed.

Modes:
- FULL_HISTORY: Include complete episode history
- ROLLING_WINDOW: Include last N steps
- SUMMARIZED: LLM-summarized history + recent steps
- CHECKPOINTS: Key milestone states only

Each mode provides:
1. History manager to track and retrieve context
2. Prompt block explaining what history is provided
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
import copy
import json

from .base import (
    Module,
    BasePromptBlock,
    BaseHistoryManager,
    PromptBlock,
    HistoryManager,
)


class MemoryMode(str, Enum):
    """Available memory modes."""
    FULL_HISTORY = "full_history"
    ROLLING_WINDOW = "rolling_window"
    SUMMARIZED = "summarized"
    CHECKPOINTS = "checkpoints"


# =============================================================================
# Prompt Blocks
# =============================================================================

FULL_HISTORY_PROMPT = """
## Context: Full History

You are provided with the COMPLETE history of this episode:
- All previous actions taken
- All previous state changes
- All events that occurred

Use this history to understand the full context of the task.
The history is provided in chronological order from oldest to newest.
"""

ROLLING_WINDOW_PROMPT = """
## Context: Rolling Window (Last {window_size} Steps)

You are provided with the LAST {window_size} steps of this episode.
Earlier history has been truncated to fit within context limits.

Current step: {current_step}
History starts from step: {start_step}

Focus on recent context while being aware that earlier steps are not shown.
"""

SUMMARIZED_HISTORY_PROMPT = """
## Context: Summarized History

You are provided with:
1. A SUMMARY of earlier episode history
2. DETAILED recent steps (last {recent_steps} steps)

Episode Summary:
{summary}

The detailed recent steps follow below.
"""

CHECKPOINTS_PROMPT = """
## Context: Key Checkpoints

You are provided with KEY MILESTONE states from this episode.
These represent significant state changes or decision points.

Checkpoints:
{checkpoints_description}

Current step: {current_step}

Use these checkpoints to understand the episode trajectory.
"""


class FullHistoryPromptBlock(BasePromptBlock):
    """Prompt block for full history mode."""

    def __init__(self):
        super().__init__("full_history_context", FULL_HISTORY_PROMPT)


class RollingWindowPromptBlock(BasePromptBlock):
    """Prompt block for rolling window mode."""

    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        template = ROLLING_WINDOW_PROMPT.replace("{window_size}", str(window_size))
        super().__init__("rolling_window_context", template)

    def render(self, context: dict) -> str:
        current_step = context.get("current_step", 0)
        start_step = max(0, current_step - self.window_size)
        return self._template.format(
            window_size=self.window_size,
            current_step=current_step,
            start_step=start_step,
        )


class SummarizedHistoryPromptBlock(BasePromptBlock):
    """Prompt block for summarized history mode."""

    def __init__(self, recent_steps: int = 3):
        self.recent_steps = recent_steps
        super().__init__("summarized_history_context", SUMMARIZED_HISTORY_PROMPT)

    def render(self, context: dict) -> str:
        summary = context.get("history_summary", "No earlier history.")
        return self._template.format(
            recent_steps=self.recent_steps,
            summary=summary,
        )


class CheckpointsPromptBlock(BasePromptBlock):
    """Prompt block for checkpoints mode."""

    def __init__(self):
        super().__init__("checkpoints_context", CHECKPOINTS_PROMPT)

    def render(self, context: dict) -> str:
        checkpoints = context.get("checkpoints", [])
        current_step = context.get("current_step", 0)

        if checkpoints:
            desc_lines = []
            for i, cp in enumerate(checkpoints):
                step = cp.get("step", i)
                description = cp.get("description", "Checkpoint")
                desc_lines.append(f"  Step {step}: {description}")
            checkpoints_desc = "\n".join(desc_lines)
        else:
            checkpoints_desc = "  (No checkpoints recorded yet)"

        return self._template.format(
            checkpoints_description=checkpoints_desc,
            current_step=current_step,
        )


# =============================================================================
# History Managers
# =============================================================================

class FullHistoryManager(BaseHistoryManager):
    """
    Manager that keeps complete episode history.
    """

    def __init__(self):
        super().__init__("full_history_manager")

    def get_context(self, max_tokens: Optional[int] = None) -> list[dict]:
        """Return all history."""
        return self._history.copy()

    def get_context_for_prompt(self) -> str:
        """Format history for prompt inclusion."""
        if not self._history:
            return "No previous actions in this episode."

        lines = []
        for i, step in enumerate(self._history):
            action = step.get("action", {})
            action_type = action.get("action_type", "unknown")
            thought = action.get("thought", "")
            result = step.get("result", "")

            lines.append(f"Step {i + 1}:")
            lines.append(f"  Action: {action_type}")
            if thought:
                lines.append(f"  Thought: {thought[:100]}...")
            if result:
                lines.append(f"  Result: {result[:100]}...")

        return "\n".join(lines)


class RollingWindowManager(BaseHistoryManager):
    """
    Manager that keeps only the last N steps.
    """

    def __init__(self, window_size: int = 5):
        super().__init__("rolling_window_manager")
        self.window_size = window_size

    def get_context(self, max_tokens: Optional[int] = None) -> list[dict]:
        """Return last window_size steps."""
        return self._history[-self.window_size:]

    def get_context_for_prompt(self) -> str:
        """Format recent history for prompt inclusion."""
        recent = self.get_context()
        if not recent:
            return "No previous actions in this episode."

        total_steps = len(self._history)
        start_step = total_steps - len(recent) + 1

        lines = []
        if total_steps > self.window_size:
            lines.append(f"[{total_steps - self.window_size} earlier steps omitted]")
            lines.append("")

        for i, step in enumerate(recent):
            step_num = start_step + i
            action = step.get("action", {})
            action_type = action.get("action_type", "unknown")
            thought = action.get("thought", "")

            lines.append(f"Step {step_num}:")
            lines.append(f"  Action: {action_type}")
            if thought:
                lines.append(f"  Thought: {thought[:100]}...")

        return "\n".join(lines)


class SummarizedHistoryManager(BaseHistoryManager):
    """
    Manager that summarizes old history and keeps recent steps detailed.

    Requires a summarization function to be provided.
    """

    def __init__(
        self,
        recent_steps: int = 3,
        summarize_fn: Optional[Callable[[list[dict]], str]] = None,
        summarize_threshold: int = 5,
    ):
        super().__init__("summarized_history_manager")
        self.recent_steps = recent_steps
        self.summarize_fn = summarize_fn or self._default_summarize
        self.summarize_threshold = summarize_threshold
        self._summary: str = ""
        self._summarized_until: int = 0

    def add_step(self, step: dict) -> None:
        super().add_step(step)
        # Trigger summarization if history is getting long
        if len(self._history) - self._summarized_until > self.summarize_threshold:
            self._update_summary()

    def _update_summary(self) -> None:
        """Update the summary of older history."""
        steps_to_summarize = self._history[self._summarized_until:-self.recent_steps]
        if steps_to_summarize:
            new_summary = self.summarize_fn(steps_to_summarize)
            if self._summary:
                self._summary = f"{self._summary}\n{new_summary}"
            else:
                self._summary = new_summary
            self._summarized_until = len(self._history) - self.recent_steps

    def _default_summarize(self, steps: list[dict]) -> str:
        """Default summarization: just list action types."""
        action_types = []
        for step in steps:
            action = step.get("action", {})
            action_types.append(action.get("action_type", "unknown"))
        return f"Earlier actions: {', '.join(action_types)}"

    def get_context(self, max_tokens: Optional[int] = None) -> list[dict]:
        """Return recent steps only (summary is separate)."""
        return self._history[-self.recent_steps:]

    def get_summary(self) -> str:
        """Get the accumulated summary."""
        return self._summary

    def get_context_for_prompt(self) -> str:
        """Format summarized + recent history for prompt."""
        lines = []

        if self._summary:
            lines.append("Summary of earlier steps:")
            lines.append(self._summary)
            lines.append("")

        recent = self.get_context()
        if recent:
            lines.append("Recent steps (detailed):")
            start_step = len(self._history) - len(recent) + 1
            for i, step in enumerate(recent):
                action = step.get("action", {})
                action_type = action.get("action_type", "unknown")
                thought = action.get("thought", "")
                bid = action.get("bid", "")

                lines.append(f"Step {start_step + i}:")
                lines.append(f"  Action: {action_type}" + (f" on bid={bid}" if bid else ""))
                if thought:
                    lines.append(f"  Thought: {thought[:150]}")

        return "\n".join(lines) if lines else "No history yet."

    def reset(self) -> None:
        super().reset()
        self._summary = ""
        self._summarized_until = 0


class CheckpointManager(BaseHistoryManager):
    """
    Manager that keeps only key checkpoint states.

    Checkpoints are created when:
    - Significant state changes occur
    - User explicitly marks a checkpoint
    - Certain action types complete (e.g., navigation, form submission)
    """

    # Actions that trigger automatic checkpoints
    CHECKPOINT_ACTIONS = {
        "goto", "submit", "finish", "navigate",
        "login", "logout", "save", "delete", "create",
    }

    def __init__(
        self,
        max_checkpoints: int = 10,
        checkpoint_detector: Optional[Callable[[dict, dict], bool]] = None,
    ):
        super().__init__("checkpoint_manager")
        self.max_checkpoints = max_checkpoints
        self.checkpoint_detector = checkpoint_detector or self._default_detector
        self._checkpoints: list[dict] = []

    def add_step(self, step: dict) -> None:
        super().add_step(step)

        # Check if this step should create a checkpoint
        prev_state = self._history[-2] if len(self._history) > 1 else {}
        if self.checkpoint_detector(step, prev_state):
            self._add_checkpoint(step, len(self._history))

    def _default_detector(self, step: dict, prev_state: dict) -> bool:
        """Default checkpoint detection based on action type."""
        action = step.get("action", {})
        action_type = action.get("action_type", "")

        # Checkpoint on certain action types
        if action_type.lower() in self.CHECKPOINT_ACTIONS:
            return True

        # Checkpoint on status changes
        if step.get("status_changed"):
            return True

        # Checkpoint on significant state changes (heuristic)
        events = step.get("events", [])
        if any("error" in str(e).lower() for e in events):
            return True
        if any("success" in str(e).lower() for e in events):
            return True

        return False

    def _add_checkpoint(self, step: dict, step_num: int) -> None:
        """Add a checkpoint."""
        action = step.get("action", {})
        action_type = action.get("action_type", "unknown")

        checkpoint = {
            "step": step_num,
            "action_type": action_type,
            "description": self._describe_checkpoint(step),
            "timestamp": step_num,  # Using step as timestamp
            "state_summary": step.get("state_summary", ""),
        }
        self._checkpoints.append(checkpoint)

        # Trim if too many checkpoints
        if len(self._checkpoints) > self.max_checkpoints:
            # Keep first, last, and evenly spaced middle checkpoints
            self._trim_checkpoints()

    def _describe_checkpoint(self, step: dict) -> str:
        """Generate description for checkpoint."""
        action = step.get("action", {})
        action_type = action.get("action_type", "unknown")
        thought = action.get("thought", "")

        if thought:
            return f"{action_type}: {thought[:50]}"
        return action_type

    def _trim_checkpoints(self) -> None:
        """Trim checkpoints to max_checkpoints, keeping important ones."""
        if len(self._checkpoints) <= self.max_checkpoints:
            return

        # Always keep first and last
        first = self._checkpoints[0]
        last = self._checkpoints[-1]

        # Select evenly spaced middle checkpoints
        middle = self._checkpoints[1:-1]
        keep_count = self.max_checkpoints - 2
        step = len(middle) / keep_count if keep_count > 0 else 1

        kept_middle = []
        for i in range(keep_count):
            idx = int(i * step)
            if idx < len(middle):
                kept_middle.append(middle[idx])

        self._checkpoints = [first] + kept_middle + [last]

    def get_context(self, max_tokens: Optional[int] = None) -> list[dict]:
        """Return checkpoint data."""
        return self._checkpoints.copy()

    def get_checkpoints(self) -> list[dict]:
        """Get all checkpoints."""
        return self._checkpoints.copy()

    def get_context_for_prompt(self) -> str:
        """Format checkpoints for prompt."""
        if not self._checkpoints:
            return "No checkpoints recorded yet."

        lines = ["Key checkpoints in this episode:"]
        for cp in self._checkpoints:
            step = cp.get("step", "?")
            desc = cp.get("description", "Checkpoint")
            lines.append(f"  [{step}] {desc}")

        # Add current position
        lines.append(f"\nCurrent step: {len(self._history)}")

        return "\n".join(lines)

    def mark_checkpoint(self, description: str) -> None:
        """Manually mark current state as checkpoint."""
        if self._history:
            step = self._history[-1]
            checkpoint = {
                "step": len(self._history),
                "action_type": "manual",
                "description": description,
                "timestamp": len(self._history),
            }
            self._checkpoints.append(checkpoint)

    def reset(self) -> None:
        super().reset()
        self._checkpoints = []


# =============================================================================
# Module
# =============================================================================

@dataclass
class MemoryModule(Module):
    """
    Module for memory/context management configuration.

    Provides history managers and prompt blocks for the selected mode.
    """

    mode: MemoryMode = MemoryMode.ROLLING_WINDOW
    window_size: int = 5  # For rolling window
    recent_steps: int = 3  # For summarized
    max_checkpoints: int = 10  # For checkpoints
    summarize_fn: Optional[Callable[[list[dict]], str]] = None

    def __post_init__(self):
        self.name = f"memory_{self.mode.value}"
        self.description = f"Memory mode: {self.mode.value}"
        self._history_manager: Optional[HistoryManager] = None

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected mode."""
        blocks = {
            MemoryMode.FULL_HISTORY: FullHistoryPromptBlock(),
            MemoryMode.ROLLING_WINDOW: RollingWindowPromptBlock(self.window_size),
            MemoryMode.SUMMARIZED: SummarizedHistoryPromptBlock(self.recent_steps),
            MemoryMode.CHECKPOINTS: CheckpointsPromptBlock(),
        }
        return [blocks[self.mode]]

    def get_history_manager(self) -> HistoryManager:
        """Return history manager for selected mode."""
        if self._history_manager is None:
            managers = {
                MemoryMode.FULL_HISTORY: FullHistoryManager(),
                MemoryMode.ROLLING_WINDOW: RollingWindowManager(self.window_size),
                MemoryMode.SUMMARIZED: SummarizedHistoryManager(
                    recent_steps=self.recent_steps,
                    summarize_fn=self.summarize_fn,
                ),
                MemoryMode.CHECKPOINTS: CheckpointManager(
                    max_checkpoints=self.max_checkpoints,
                ),
            }
            self._history_manager = managers[self.mode]
        return self._history_manager

    def reset(self) -> None:
        """Reset the history manager."""
        if self._history_manager is not None:
            self._history_manager.reset()
