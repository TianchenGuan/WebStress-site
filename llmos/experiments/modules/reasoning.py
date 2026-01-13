"""
Reasoning Module: How the simulator reasons about state transitions.

Modes:
- DIRECT: Only model immediate, direct effects of actions
- CHAIN: Reason about multi-step causal chains and consequences

Each mode provides:
1. Prompt block instructing the reasoning approach
2. Output schema for capturing reasoning
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .base import (
    Module,
    BasePromptBlock,
    BaseOutputParser,
    PromptBlock,
    OutputParser,
)


class ReasoningMode(str, Enum):
    """Available reasoning modes."""
    DIRECT = "direct"
    CHAIN = "chain"


# =============================================================================
# Prompt Blocks
# =============================================================================

DIRECT_REASONING_PROMPT = """
## Reasoning Mode: Direct Effects

Focus on the IMMEDIATE, DIRECT effects of the action.

When predicting state changes:
1. Identify what the action directly affects
2. Determine the immediate state change
3. Do NOT reason about secondary or cascading effects

Example for click(submit_button):
- Direct effect: Form submission initiated
- Do NOT consider: What happens after submission, server responses, etc.

Keep your reasoning focused and concise. Only output changes that are
the DIRECT result of the action, not downstream consequences.
"""

CHAIN_REASONING_PROMPT = """
## Reasoning Mode: Causal Chain

Reason through the FULL CHAIN of consequences from the action.

When predicting state changes:
1. Identify the direct effect of the action
2. For each direct effect, consider what it triggers
3. Continue until you reach stable state or natural stopping point
4. Capture all changes in the causal chain

Structure your reasoning as a chain:
```
Action: click(submit_button)
Chain of effects:
1. Form submission initiated
   → 2. Validation runs on all fields
      → 3a. If valid: Form data sent to server
         → 4a. Loading indicator appears
         → 4b. Submit button becomes disabled
      → 3b. If invalid: Error messages appear on invalid fields
         → 4c. First invalid field gets focus
```

For each effect in the chain:
- State what changes
- Identify what it triggers next
- Continue until no more triggered effects

Output ALL state changes that result from the causal chain, not just
the immediate effect.

Important: Distinguish between:
- Certain effects (will definitely happen)
- Conditional effects (depend on state, mark with conditions)
- Possible effects (might happen, mark as uncertain)
"""


class DirectReasoningBlock(BasePromptBlock):
    """Prompt block for direct reasoning mode."""

    def __init__(self):
        super().__init__("direct_reasoning", DIRECT_REASONING_PROMPT)


class ChainReasoningBlock(BasePromptBlock):
    """Prompt block for chain reasoning mode."""

    def __init__(self):
        super().__init__("chain_reasoning", CHAIN_REASONING_PROMPT)


# =============================================================================
# Output Enhancement
# =============================================================================

DIRECT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {
            "type": "string",
            "description": "Brief reasoning about direct effects",
        },
        "direct_effect": {
            "type": "string",
            "description": "The single direct effect of this action",
        },
        "state_ops": {
            "type": "array",
            "description": "State operations for direct effects only",
        },
        "events": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["thought", "state_ops"],
}

CHAIN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {
            "type": "string",
            "description": "Initial reasoning about the action",
        },
        "causal_chain": {
            "type": "array",
            "description": "Chain of cause-effect relationships",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer"},
                    "cause": {"type": "string"},
                    "effect": {"type": "string"},
                    "certainty": {
                        "type": "string",
                        "enum": ["certain", "conditional", "possible"],
                    },
                    "condition": {
                        "type": "string",
                        "description": "Condition if certainty is conditional",
                    },
                },
                "required": ["step", "cause", "effect"],
            },
        },
        "state_ops": {
            "type": "array",
            "description": "All state operations from the causal chain",
        },
        "events": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["thought", "causal_chain", "state_ops"],
}


class DirectReasoningParser(BaseOutputParser):
    """Parser for direct reasoning output."""

    def __init__(self):
        super().__init__("direct_reasoning_parser")

    def get_output_schema(self) -> dict:
        return DIRECT_OUTPUT_SCHEMA

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Extract state ops from direct reasoning output."""
        return llm_output.get("state_ops", [])


class ChainReasoningParser(BaseOutputParser):
    """Parser for chain reasoning output."""

    def __init__(self, include_uncertain: bool = False):
        super().__init__("chain_reasoning_parser")
        self.include_uncertain = include_uncertain

    def get_output_schema(self) -> dict:
        return CHAIN_OUTPUT_SCHEMA

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """
        Extract state ops from chain reasoning output.

        Optionally filters out uncertain effects.
        """
        state_ops = llm_output.get("state_ops", [])

        if not self.include_uncertain:
            # Filter ops based on causal chain certainty
            causal_chain = llm_output.get("causal_chain", [])
            uncertain_effects = set()

            for link in causal_chain:
                certainty = link.get("certainty", "certain")
                if certainty == "possible":
                    effect = link.get("effect", "")
                    uncertain_effects.add(effect)

            # This is a simplified filter - in practice would need
            # more sophisticated matching between effects and ops
            # For now, include all ops
            pass

        return state_ops

    def get_causal_chain(self, llm_output: dict) -> list[dict]:
        """Extract the causal chain for analysis."""
        return llm_output.get("causal_chain", [])


# =============================================================================
# Chain Reasoning Helpers
# =============================================================================

CHAIN_EXAMPLES_PROMPT = """
## Causal Chain Examples

Example 1: Click on checkbox
```
Action: click(checkbox_agree_terms)
Causal Chain:
1. Checkbox state toggles (unchecked → checked)
   → 2. Form validation re-runs
      → 3. If all required fields valid: Submit button enables
      → 3. If still invalid: Submit button stays disabled
```

Example 2: Fill email field
```
Action: fill(input_email, "user@example.com")
Causal Chain:
1. Email field value updates to "user@example.com"
   → 2. Field validation triggers
      → 3a. If valid email format: Error message clears, field border green
      → 3b. If invalid format: Error message appears, field border red
   → 4. Form-level validation may re-run
      → 5. Submit button state may update
```

Example 3: Click delete button
```
Action: click(button_delete_item)
Causal Chain:
1. Confirmation dialog appears
   → 2. Main content dims/disabled
   → 3. Focus moves to dialog
   OR (if no confirmation required):
1. Item removed from list
   → 2. List re-renders
      → 3a. If list empty: Empty state message appears
      → 3b. If items remain: Items shift up
   → 4. Success notification appears (temporary)
```

Apply similar causal reasoning to the current action.
"""


class ChainExamplesBlock(BasePromptBlock):
    """Prompt block with causal chain examples."""

    def __init__(self):
        super().__init__("chain_examples", CHAIN_EXAMPLES_PROMPT)


# =============================================================================
# Module
# =============================================================================

@dataclass
class ReasoningModule(Module):
    """
    Module for reasoning mode configuration.

    Provides prompt blocks and parsers for the selected reasoning mode.
    """

    mode: ReasoningMode = ReasoningMode.DIRECT
    include_examples: bool = True
    include_uncertain_effects: bool = False

    def __post_init__(self):
        self.name = f"reasoning_{self.mode.value}"
        self.description = f"Reasoning mode: {self.mode.value}"

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt blocks for selected mode."""
        blocks = []

        if self.mode == ReasoningMode.DIRECT:
            blocks.append(DirectReasoningBlock())
        else:
            blocks.append(ChainReasoningBlock())
            if self.include_examples:
                blocks.append(ChainExamplesBlock())

        return blocks

    def get_parsers(self) -> list[OutputParser]:
        """Return parser for selected mode."""
        parsers = {
            ReasoningMode.DIRECT: DirectReasoningParser(),
            ReasoningMode.CHAIN: ChainReasoningParser(
                include_uncertain=self.include_uncertain_effects
            ),
        }
        return [parsers[self.mode]]

    def get_parser(self) -> OutputParser:
        """Get the parser for the current mode."""
        return self.get_parsers()[0]
