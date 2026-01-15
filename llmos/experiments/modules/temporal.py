"""
Temporal Module: How temporal aspects are handled in state transitions.

Modes:
- INSTANT: Actions have immediate effects (synchronous)
- ASYNC_AWARE: Model loading states, delays, and async operations
- EVENT_DRIVEN: Explicit event sequences with timing

Each mode provides:
1. Prompt block explaining temporal expectations
2. Output schema for temporal effects
3. Post-processor for handling async states
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
import copy

from .base import (
    Module,
    BasePromptBlock,
    BaseOutputParser,
    PromptBlock,
    OutputParser,
)


class TemporalMode(str, Enum):
    """Available temporal modes."""
    INSTANT = "instant"
    ASYNC_AWARE = "async_aware"
    EVENT_DRIVEN = "event_driven"


# =============================================================================
# Prompt Blocks
# =============================================================================

INSTANT_TEMPORAL_PROMPT = """
## Temporal Mode: Instant Effects

All actions have IMMEDIATE effects. There are no loading states, delays,
or asynchronous operations to model.

When predicting state changes:
- The action completes instantly
- All effects are applied in the same tick
- No intermediate states needed
- The resulting state is stable and complete

Example: click(submit_button)
- Form validates instantly
- Result (success or error) appears immediately
- No loading spinners or "processing..." states
"""

ASYNC_AWARE_PROMPT = """
## Temporal Mode: Async-Aware

Model REALISTIC asynchronous behavior. Some actions trigger operations
that don't complete instantly.

Async behaviors to model:

1. **Loading States**: Show loading indicators when waiting
   - "Loading..." text
   - Spinner icons
   - Disabled buttons during operation
   - Progress bars

2. **Pending Operations**: Mark operations that are in progress
   ```json
   {
     "state_ops": [...],
     "pending_ops": [
       {
         "op_id": "submit_form_1",
         "type": "network_request",
         "started_at": "tick",
         "expected_duration": "1-3 ticks",
         "on_complete": "show_success_message",
         "on_error": "show_error_message"
       }
     ]
   }
   ```

3. **Completion Events**: When async ops complete
   ```json
   {
     "events": ["async:complete:submit_form_1"]
   }
   ```

Common async scenarios:
- Form submission → loading → success/error
- Navigation → loading → new page
- Data fetch → loading → data displayed
- File upload → progress → complete

Output `async_state` when modeling pending operations:
```json
{
  "thought": "Form is being submitted",
  "state_ops": [
    {"op": "update", "bid": "submit_btn", "props": {"disabled": true, "text": "Submitting..."}}
  ],
  "async_state": {
    "pending": true,
    "operation": "form_submit",
    "will_complete_in": 1
  }
}
```
"""

EVENT_DRIVEN_PROMPT = """
## Temporal Mode: Event-Driven

Model UI changes as explicit EVENT SEQUENCES with ordering and timing.

Every state change is triggered by an event. Events can trigger other events.

Event structure:
```json
{
  "events": [
    {
      "id": "evt_1",
      "type": "user_action",
      "action": "click",
      "target": "submit_btn",
      "timestamp": 0
    },
    {
      "id": "evt_2",
      "type": "state_change",
      "trigger": "evt_1",
      "changes": [{"bid": "submit_btn", "prop": "disabled", "value": true}],
      "timestamp": 0
    },
    {
      "id": "evt_3",
      "type": "async_start",
      "trigger": "evt_1",
      "operation": "form_submit",
      "timestamp": 0
    },
    {
      "id": "evt_4",
      "type": "async_complete",
      "trigger": "evt_3",
      "result": "success",
      "timestamp": 1
    },
    {
      "id": "evt_5",
      "type": "state_change",
      "trigger": "evt_4",
      "changes": [{"bid": "message", "prop": "text", "value": "Success!"}],
      "timestamp": 1
    }
  ]
}
```

Event types:
- `user_action`: User-initiated action
- `state_change`: UI state modification
- `async_start`: Async operation begins
- `async_complete`: Async operation finishes
- `timer`: Scheduled/delayed event
- `animation_end`: Animation completes

When modeling event-driven changes:
1. List all events in causal order
2. Include trigger references (which event caused this)
3. Assign timestamps (relative tick numbers)
4. Derive state_ops from state_change events
"""


class InstantTemporalBlock(BasePromptBlock):
    """Prompt block for instant temporal mode."""

    def __init__(self):
        super().__init__("instant_temporal", INSTANT_TEMPORAL_PROMPT)


class AsyncAwareBlock(BasePromptBlock):
    """Prompt block for async-aware temporal mode."""

    def __init__(self):
        super().__init__("async_aware_temporal", ASYNC_AWARE_PROMPT)


class EventDrivenBlock(BasePromptBlock):
    """Prompt block for event-driven temporal mode."""

    def __init__(self):
        super().__init__("event_driven_temporal", EVENT_DRIVEN_PROMPT)


# =============================================================================
# Output Parsers
# =============================================================================

ASYNC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "state_ops": {"type": "array"},
        "events": {"type": "array", "items": {"type": "string"}},
        "async_state": {
            "type": "object",
            "properties": {
                "pending": {"type": "boolean"},
                "operation": {"type": "string"},
                "will_complete_in": {"type": "integer"},
            },
        },
        "pending_ops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op_id": {"type": "string"},
                    "type": {"type": "string"},
                    "expected_duration": {"type": "string"},
                },
            },
        },
    },
    "required": ["state_ops"],
}

EVENT_DRIVEN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "trigger": {"type": "string"},
                    "timestamp": {"type": "integer"},
                    "changes": {"type": "array"},
                },
                "required": ["id", "type"],
            },
        },
        "state_ops": {"type": "array"},
    },
    "required": ["events"],
}


class InstantTemporalParser(BaseOutputParser):
    """Parser for instant temporal mode - no special handling needed."""

    def __init__(self):
        super().__init__("instant_temporal_parser")

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        return llm_output.get("state_ops", [])


class AsyncAwareParser(BaseOutputParser):
    """Parser for async-aware temporal mode."""

    def __init__(self):
        super().__init__("async_aware_parser")

    def get_output_schema(self) -> dict:
        return ASYNC_OUTPUT_SCHEMA

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Extract state ops and handle async state."""
        state_ops = llm_output.get("state_ops", [])

        # Check for async state that needs tracking
        async_state = llm_output.get("async_state", {})
        if async_state.get("pending"):
            # Add hidden state update to track pending operation
            state_ops.append({
                "op": "hidden_update",
                "key": "_pending_async",
                "value": {
                    "operation": async_state.get("operation"),
                    "will_complete_in": async_state.get("will_complete_in", 1),
                },
            })

        return state_ops

    def get_async_state(self, llm_output: dict) -> Optional[dict]:
        """Get async state for tracking."""
        return llm_output.get("async_state")

    def get_pending_ops(self, llm_output: dict) -> list[dict]:
        """Get pending operations."""
        return llm_output.get("pending_ops", [])


class EventDrivenParser(BaseOutputParser):
    """Parser for event-driven temporal mode."""

    def __init__(self):
        super().__init__("event_driven_parser")

    def get_output_schema(self) -> dict:
        return EVENT_DRIVEN_OUTPUT_SCHEMA

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Convert event sequence to state ops."""
        events = llm_output.get("events", [])
        state_ops = []

        # If state_ops already provided, use them
        if llm_output.get("state_ops"):
            return llm_output["state_ops"]

        # Extract state_ops from state_change events
        for event in events:
            if event.get("type") == "state_change":
                changes = event.get("changes", [])
                for change in changes:
                    if "bid" in change and "prop" in change:
                        state_ops.append({
                            "op": "update",
                            "bid": change["bid"],
                            "props": {change["prop"]: change.get("value")},
                        })

        return state_ops

    def get_events(self, llm_output: dict) -> list[dict]:
        """Get the full event sequence."""
        return llm_output.get("events", [])

    def get_events_at_tick(self, llm_output: dict, tick: int) -> list[dict]:
        """Get events at a specific timestamp."""
        events = llm_output.get("events", [])
        return [e for e in events if e.get("timestamp") == tick]


# =============================================================================
# Async State Manager
# =============================================================================

class AsyncStateManager:
    """
    Manages async operations across multiple ticks.

    Tracks pending operations and resolves them when their duration expires.
    """

    def __init__(self):
        self._pending: list[dict] = []

    def add_pending(self, op: dict) -> None:
        """Add a pending async operation."""
        self._pending.append(op)

    def tick(self) -> list[dict]:
        """
        Advance time by one tick. Returns operations that completed.

        Returns list of completed operations with their results.
        """
        completed = []
        still_pending = []

        for op in self._pending:
            remaining = op.get("will_complete_in", 1) - 1
            if remaining <= 0:
                completed.append(op)
            else:
                op["will_complete_in"] = remaining
                still_pending.append(op)

        self._pending = still_pending
        return completed

    def get_pending(self) -> list[dict]:
        """Get all pending operations."""
        return self._pending.copy()

    def has_pending(self) -> bool:
        """Check if there are pending operations."""
        return len(self._pending) > 0

    def clear(self) -> None:
        """Clear all pending operations."""
        self._pending = []


# =============================================================================
# Module
# =============================================================================

@dataclass
class TemporalModule(Module):
    """
    Module for temporal mode configuration.

    Provides prompt blocks, parsers, and async state management.
    """

    mode: TemporalMode = TemporalMode.INSTANT

    def __post_init__(self):
        self.name = f"temporal_{self.mode.value}"
        self.description = f"Temporal mode: {self.mode.value}"
        self._async_manager = AsyncStateManager()

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected mode."""
        blocks = {
            TemporalMode.INSTANT: InstantTemporalBlock(),
            TemporalMode.ASYNC_AWARE: AsyncAwareBlock(),
            TemporalMode.EVENT_DRIVEN: EventDrivenBlock(),
        }
        return [blocks[self.mode]]

    def get_parsers(self) -> list[OutputParser]:
        """Return parser for selected mode."""
        parsers = {
            TemporalMode.INSTANT: InstantTemporalParser(),
            TemporalMode.ASYNC_AWARE: AsyncAwareParser(),
            TemporalMode.EVENT_DRIVEN: EventDrivenParser(),
        }
        return [parsers[self.mode]]

    def get_parser(self) -> OutputParser:
        """Get the parser for the current mode."""
        return self.get_parsers()[0]

    def get_async_manager(self) -> AsyncStateManager:
        """Get the async state manager."""
        return self._async_manager

    def reset(self) -> None:
        """Reset async state for new episode."""
        self._async_manager.clear()
