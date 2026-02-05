"""
State Output Module: How the simulator outputs state changes.

Modes:
- FULL_STATE: Output complete state every step
- DELTA_ONLY: Output only what changed (state operations)
- SEMANTIC_DESCRIPTION: Output natural language description of changes

Each mode provides:
1. Prompt block instructing LLM on output format
2. Output parser to convert LLM response to state operations
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
import copy
import json

from .base import (
    Module,
    BasePromptBlock,
    BaseOutputParser,
    PromptBlock,
    OutputParser,
)


class StateOutputMode(str, Enum):
    """Available state output modes."""
    FULL_STATE = "full_state"
    DELTA_ONLY = "delta_only"
    SEMANTIC_DESCRIPTION = "semantic_description"


# =============================================================================
# Prompt Blocks
# =============================================================================

FULL_STATE_PROMPT = """
## Output Format: Full State

Output COMPLETE next state (not just changes):
```json
{
  "thought": "reasoning",
  "next_state": {"meta": {...}, "ui": {...}, "hidden_state": {...}, "filesystem": {...}},
  "events": ["event1"]
}
```
"""

DELTA_ONLY_PROMPT = """
## Output Format: Delta Only (State Operations)

You must output ONLY the changes to apply to the current state.

Output JSON with this structure:
```json
{
  "thought": "Your reasoning about what changes",
  "state_ops": [
    {"op": "update", "bid": <element_id>, "props": {"key": "new_value"}},
    {"op": "delete", "bid": <element_id>},
    {"op": "append", "parent_bid": <parent_id>, "node": {...}},
    {"op": "insert", "parent_bid": <parent_id>, "index": <n>, "node": {...}},
    {"op": "hidden_update", "key": "<key>", "value": <value>},
    {"op": "meta_update", "key": "<key>", "value": <value>}
  ],
  "events": ["event1", "event2"]
}
```

Operation types:
- `update`: Modify properties of element with given bid
- `delete`: Remove element with given bid
- `append`: Add new node as last child of parent
- `insert`: Insert new node at specific index under parent
- `hidden_update`: Update hidden_state key
- `meta_update`: Update meta key (e.g., status)

Important:
- Only output operations for elements that CHANGE
- Do NOT output unchanged elements
- Use element `bid` (browser ID) to identify elements
"""

SEMANTIC_DESCRIPTION_PROMPT = """
## Output Format: Semantic Description

Describe changes in natural language with structured change list:
```json
{
  "thought": "reasoning",
  "description": "The button becomes disabled and a loading spinner appears.",
  "changes": [{"element": "submit button", "bid": "btn1", "change_type": "property_change", "details": {"disabled": true}}],
  "events": ["event1"]
}
```
Change types: `property_change`, `appear`, `disappear`, `move`
"""


class FullStatePromptBlock(BasePromptBlock):
    """Prompt block for full state output mode."""

    def __init__(self):
        super().__init__("full_state_output", FULL_STATE_PROMPT)


class DeltaOnlyPromptBlock(BasePromptBlock):
    """Prompt block for delta-only output mode."""

    def __init__(self):
        super().__init__("delta_only_output", DELTA_ONLY_PROMPT)


class SemanticDescriptionPromptBlock(BasePromptBlock):
    """Prompt block for semantic description output mode."""

    def __init__(self):
        super().__init__("semantic_description_output", SEMANTIC_DESCRIPTION_PROMPT)


# =============================================================================
# Output Parsers
# =============================================================================

class FullStateParser(BaseOutputParser):
    """
    Parser for full state output mode.

    Converts complete next_state into state operations by diffing
    with current state.
    """

    def __init__(self):
        super().__init__("full_state_parser")

    def get_output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "next_state": {"type": "object"},
                "events": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["next_state"],
        }

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Convert full next_state to state operations by diffing."""
        next_state = llm_output.get("next_state", {})

        if not next_state:
            return []

        ops = []

        # Diff UI tree
        if "ui" in next_state:
            ui_ops = self._diff_ui_tree(
                current_state.get("ui", {}),
                next_state.get("ui", {}),
            )
            ops.extend(ui_ops)

        # Diff hidden_state
        current_hidden = current_state.get("hidden_state", {})
        next_hidden = next_state.get("hidden_state", {})
        for key, value in next_hidden.items():
            if current_hidden.get(key) != value:
                ops.append({
                    "op": "hidden_update",
                    "key": key,
                    "value": value,
                })

        # Diff meta
        current_meta = current_state.get("meta", {})
        next_meta = next_state.get("meta", {})
        for key in ["status"]:  # Only certain meta keys
            if key in next_meta and current_meta.get(key) != next_meta[key]:
                ops.append({
                    "op": "meta_update",
                    "key": key,
                    "value": next_meta[key],
                })

        return ops

    def _diff_ui_tree(self, current: dict, next_: dict) -> list[dict]:
        """Diff two UI trees and generate operations."""
        ops = []

        # Build bid -> node maps
        current_nodes = {}
        next_nodes = {}
        current_parents = {}
        next_parents = {}
        self._collect_nodes(current, current_nodes)
        self._collect_nodes(next_, next_nodes, next_parents)

        # Find updates
        for bid, next_node in next_nodes.items():
            if bid in current_nodes:
                # Check for property changes
                current_node = current_nodes[bid]
                changed_props = {}
                for key, value in next_node.items():
                    if key not in ("children", "bid") and current_node.get(key) != value:
                        changed_props[key] = value
                if changed_props:
                    ops.append({
                        "op": "update",
                        "bid": bid,
                        "props": changed_props,
                    })
            else:
                parent_bid = next_parents.get(bid)
                if parent_bid in current_nodes:
                    ops.append({
                        "op": "append",
                        "parent_bid": parent_bid,
                        "node": copy.deepcopy(next_node),
                    })

        # Find deletions
        for bid in current_nodes:
            if bid not in next_nodes:
                ops.append({
                    "op": "delete",
                    "bid": bid,
                })

        return ops

    def _collect_nodes(self, node: dict, nodes: dict, parents: Optional[dict] = None, parent_bid: Optional[str] = None) -> None:
        """Recursively collect all nodes by bid."""
        if isinstance(node, dict):
            if "bid" in node:
                nodes[node["bid"]] = node
                if parents is not None:
                    parents[node["bid"]] = parent_bid
            for child in node.get("children", []):
                self._collect_nodes(child, nodes, parents, node.get("bid"))


class DeltaOnlyParser(BaseOutputParser):
    """
    Parser for delta-only output mode.

    Directly uses state_ops from LLM output.
    """

    def __init__(self):
        super().__init__("delta_only_parser")

    def get_output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "state_ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["update", "delete", "append", "insert",
                                        "hidden_update", "meta_update"],
                            },
                        },
                        "required": ["op"],
                    },
                },
                "events": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["state_ops"],
        }

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Extract state_ops directly from output."""
        return llm_output.get("state_ops", [])


class SemanticDescriptionParser(BaseOutputParser):
    """
    Parser for semantic description output mode.

    Converts semantic change descriptions to state operations.
    """

    def __init__(self):
        super().__init__("semantic_description_parser")

    def get_output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "description": {"type": "string"},
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "element": {"type": "string"},
                            "bid": {"type": ["integer", "string", "null"]},
                            "change_type": {
                                "type": "string",
                                "enum": ["property_change", "appear", "disappear", "move"],
                            },
                            "details": {},
                        },
                        "required": ["element", "change_type"],
                    },
                },
                "events": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["description", "changes"],
        }

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Convert semantic changes to state operations."""
        changes = llm_output.get("changes", [])
        ops = []

        for change in changes:
            change_type = change.get("change_type")
            bid = change.get("bid")
            details = change.get("details", {})

            if change_type == "property_change" and bid is not None:
                if isinstance(details, dict):
                    ops.append({
                        "op": "update",
                        "bid": bid,
                        "props": details,
                    })

            elif change_type == "disappear" and bid is not None:
                ops.append({
                    "op": "delete",
                    "bid": bid,
                })

            elif change_type == "appear":
                # For new elements, we need parent info
                # This is a simplified handling
                if isinstance(details, dict) and "parent_bid" in details:
                    node = details.get("node", {})
                    if "bid" not in node:
                        # Generate a bid based on description
                        node["bid"] = f"new_{hash(change.get('element', '')) % 10000}"
                    ops.append({
                        "op": "append",
                        "parent_bid": details["parent_bid"],
                        "node": node,
                    })

        return ops


# =============================================================================
# Module
# =============================================================================

@dataclass
class StateOutputModule(Module):
    """
    Module for state output mode configuration.

    Provides prompt blocks and parsers for the selected output mode.
    """

    mode: StateOutputMode = StateOutputMode.DELTA_ONLY

    def __post_init__(self):
        self.name = f"state_output_{self.mode.value}"
        self.description = f"State output mode: {self.mode.value}"

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected mode."""
        blocks = {
            StateOutputMode.FULL_STATE: FullStatePromptBlock(),
            StateOutputMode.DELTA_ONLY: DeltaOnlyPromptBlock(),
            StateOutputMode.SEMANTIC_DESCRIPTION: SemanticDescriptionPromptBlock(),
        }
        return [blocks[self.mode]]

    def get_parsers(self) -> list[OutputParser]:
        """Return parser for selected mode."""
        parsers = {
            StateOutputMode.FULL_STATE: FullStateParser(),
            StateOutputMode.DELTA_ONLY: DeltaOnlyParser(),
            StateOutputMode.SEMANTIC_DESCRIPTION: SemanticDescriptionParser(),
        }
        return [parsers[self.mode]]

    def get_parser(self) -> OutputParser:
        """Get the parser for the current mode."""
        return self.get_parsers()[0]
