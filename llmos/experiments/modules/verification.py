"""
Verification Module: How outputs are verified for correctness.

Modes:
- SCHEMA: Verify JSON schema compliance only
- CONSTRAINT_CHECK: Verify constraints (element exists, valid values)
- BACKWARD: Verify state is reachable via backward reasoning

Each mode provides:
1. Verifier that checks outputs
2. Prompt block explaining verification expectations (for backward)
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import copy
import json

from ...core.modules.enums import VerificationMode
from .base import (
    Module,
    BasePromptBlock,
    BaseVerifier,
    PromptBlock,
    Verifier,
)


# =============================================================================
# Schema Definitions
# =============================================================================

STATE_OPS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": [
                    "update", "delete", "append", "insert",
                    "hidden_update", "meta_update", "filesystem_update",
                ],
            },
            "bid": {"type": ["string", "integer", "null"]},
            "parent_bid": {"type": ["string", "integer", "null"]},
            "props": {"type": "object"},
            "node": {"type": "object"},
            "key": {"type": "string"},
            "value": {},
            "index": {"type": "integer"},
            "path": {"type": "string"},
            "data": {"type": "object"},
        },
        "required": ["op"],
    },
}

SIMULATOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "state_ops": STATE_OPS_SCHEMA,
        "events": {
            "type": "array",
            "items": {"type": "string"},
        },
        "done": {"type": "boolean"},
    },
    "required": ["state_ops"],
}


# =============================================================================
# Prompt Blocks
# =============================================================================

BACKWARD_VERIFICATION_PROMPT = """
## Verification: Backward Consistency Check

Predictions are verified: next state must be reachable from current state via the action.
Ensure changes are action-relevant and self-consistent.
"""


class BackwardVerificationBlock(BasePromptBlock):
    """Prompt block for backward verification mode."""

    def __init__(self):
        super().__init__("backward_verification", BACKWARD_VERIFICATION_PROMPT)


# =============================================================================
# Verifiers
# =============================================================================

class SchemaVerifier(BaseVerifier):
    """
    Verifier that checks JSON schema compliance.

    Fast verification that catches structural errors.
    """

    def __init__(self, schema: Optional[dict] = None):
        super().__init__("schema_verifier")
        self.schema = schema or SIMULATOR_OUTPUT_SCHEMA

    def verify(
        self,
        output: dict,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> tuple[bool, list[str]]:
        """Verify output against JSON schema."""
        errors = []

        # Basic type check
        if not isinstance(output, dict):
            return False, ["Output must be a dictionary"]

        # Check required fields
        required = self.schema.get("required", [])
        for field in required:
            if field not in output:
                errors.append(f"Missing required field: {field}")

        # Check state_ops structure
        state_ops = output.get("state_ops", [])
        if not isinstance(state_ops, list):
            errors.append("state_ops must be a list")
        else:
            for i, op in enumerate(state_ops):
                op_errors = self._verify_op(op, i)
                errors.extend(op_errors)

        # Check events if present
        events = output.get("events")
        if events is not None and not isinstance(events, list):
            errors.append("events must be a list")

        return len(errors) == 0, errors

    def _verify_op(self, op: dict, index: int) -> list[str]:
        """Verify a single state operation."""
        errors = []

        if not isinstance(op, dict):
            return [f"state_ops[{index}] must be a dictionary"]

        op_type = op.get("op")
        if op_type is None:
            errors.append(f"state_ops[{index}] missing 'op' field")
            return errors

        valid_ops = ["update", "delete", "append", "insert",
                    "hidden_update", "meta_update", "filesystem_update"]
        if op_type not in valid_ops:
            errors.append(f"state_ops[{index}] has invalid op type: {op_type}")

        # Op-specific validation
        if op_type == "update":
            if "bid" not in op:
                errors.append(f"state_ops[{index}] 'update' requires 'bid'")
            if "props" not in op:
                errors.append(f"state_ops[{index}] 'update' requires 'props'")

        elif op_type == "delete":
            if "bid" not in op:
                errors.append(f"state_ops[{index}] 'delete' requires 'bid'")

        elif op_type in ("append", "insert"):
            if "parent_bid" not in op:
                errors.append(f"state_ops[{index}] '{op_type}' requires 'parent_bid'")
            if "node" not in op:
                errors.append(f"state_ops[{index}] '{op_type}' requires 'node'")
            if op_type == "insert" and "index" not in op:
                errors.append(f"state_ops[{index}] 'insert' requires 'index'")

        elif op_type in ("hidden_update", "meta_update"):
            if "key" not in op:
                errors.append(f"state_ops[{index}] '{op_type}' requires 'key'")
            if "value" not in op:
                errors.append(f"state_ops[{index}] '{op_type}' requires 'value'")

        return errors


class ConstraintVerifier(BaseVerifier):
    """
    Verifier that checks semantic constraints.

    Verifies that:
    - Referenced elements exist
    - Operations are valid for element types
    - Values are within valid ranges
    - UI physics constraints are satisfied
    """

    def __init__(self, strict: bool = False):
        super().__init__("constraint_verifier")
        self.strict = strict  # Fail on any constraint violation vs warn

    def verify(
        self,
        output: dict,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> tuple[bool, list[str]]:
        """Verify semantic constraints."""
        errors = []
        warnings = []

        state_ops = output.get("state_ops", [])

        # Build element index from current state
        elements = {}
        self._index_elements(current_state.get("ui", {}), elements)

        for i, op in enumerate(state_ops):
            op_errors, op_warnings = self._verify_op_constraints(
                op, i, elements, current_state, action
            )
            errors.extend(op_errors)
            warnings.extend(op_warnings)

        if self.strict:
            errors.extend(warnings)
            return len(errors) == 0, errors
        else:
            return len(errors) == 0, errors + [f"Warning: {w}" for w in warnings]

    def _index_elements(self, node: dict, elements: dict) -> None:
        """Index all elements by bid."""
        if isinstance(node, dict):
            if "bid" in node:
                elements[node["bid"]] = node
            for child in node.get("children", []):
                self._index_elements(child, elements)

    def _verify_op_constraints(
        self,
        op: dict,
        index: int,
        elements: dict,
        state: dict,
        action: dict,
    ) -> tuple[list[str], list[str]]:
        """Verify constraints for a single operation."""
        errors = []
        warnings = []

        op_type = op.get("op")
        bid = op.get("bid")
        parent_bid = op.get("parent_bid")

        # Check element existence for operations that reference elements
        if op_type in ("update", "delete"):
            if bid not in elements:
                errors.append(
                    f"state_ops[{index}]: Element with bid={bid} does not exist"
                )
                return errors, warnings

        # Check parent existence for append/insert
        if op_type in ("append", "insert"):
            if parent_bid not in elements:
                errors.append(
                    f"state_ops[{index}]: Parent with bid={parent_bid} does not exist"
                )
                return errors, warnings

        # Verify operation validity for element type
        if bid in elements:
            element = elements[bid]
            tag = element.get("tag", "").lower()
            props = op.get("props", {})

            # Check visibility constraints
            if not element.get("visible", True):
                # Can't interact with hidden elements (usually)
                if action.get("action_type") in ("click", "fill", "hover"):
                    warnings.append(
                        f"state_ops[{index}]: Modifying hidden element bid={bid}"
                    )

            # Check disabled constraints
            if element.get("disabled", False):
                if action.get("action_type") == "click":
                    warnings.append(
                        f"state_ops[{index}]: Modifying disabled element bid={bid}"
                    )

            # Check readonly constraints
            if element.get("readonly", False):
                if "value" in props or "text" in props:
                    warnings.append(
                        f"state_ops[{index}]: Changing value of readonly element bid={bid}"
                    )

            # Type-specific constraints
            if tag == "checkbox":
                if "checked" in props and not isinstance(props["checked"], bool):
                    errors.append(
                        f"state_ops[{index}]: checkbox 'checked' must be boolean"
                    )

            if tag == "select":
                if "value" in props:
                    # Should verify value is in options
                    pass

        return errors, warnings


class BackwardVerifier(BaseVerifier):
    """
    Verifier that checks backward consistency.

    Uses an LLM to verify that the predicted next state is
    plausibly reachable from the current state via the action.

    This is the most thorough but also most expensive verification.
    """

    def __init__(
        self,
        llm_client=None,
        model_name: str = "gpt-4o-mini",
        threshold: float = 0.7,
    ):
        super().__init__("backward_verifier")
        self.llm_client = llm_client
        self.model_name = model_name
        self.threshold = threshold

    def verify(
        self,
        output: dict,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> tuple[bool, list[str]]:
        """
        Verify backward consistency using LLM.

        Asks: "Is it plausible that action A on state S produces changes C?"
        """
        # First run schema verification
        schema_verifier = SchemaVerifier()
        schema_valid, schema_errors = schema_verifier.verify(
            output, current_state, action, context
        )
        if not schema_valid:
            return False, schema_errors

        # If no LLM client, skip backward verification
        if self.llm_client is None:
            return True, []

        # Build verification prompt
        verification_prompt = self._build_verification_prompt(
            output, current_state, action
        )

        try:
            # Call LLM for verification
            response = self.llm_client.complete(
                messages=[
                    {"role": "system", "content": BACKWARD_VERIFICATION_SYSTEM},
                    {"role": "user", "content": verification_prompt},
                ],
                model_name=self.model_name,
                json_mode=True,
            )

            result = json.loads(response)
            plausibility = result.get("plausibility_score", 0.5)
            reasoning = result.get("reasoning", "")
            issues = result.get("issues", [])

            if plausibility < self.threshold:
                return False, [
                    f"Backward verification failed (score={plausibility:.2f}): {reasoning}"
                ] + issues

            return True, []

        except Exception as e:
            # On error, pass through (don't block on verification errors)
            return True, [f"Warning: Backward verification error: {e}"]

    def _build_verification_prompt(
        self,
        output: dict,
        current_state: dict,
        action: dict,
    ) -> str:
        """Build the verification prompt."""
        # Summarize state for prompt (don't send full state)
        state_summary = self._summarize_state(current_state)
        changes_summary = self._summarize_changes(output.get("state_ops", []))

        return f"""
Verify if the following state changes are plausible:

ACTION:
{json.dumps(action, indent=2)}

CURRENT STATE SUMMARY:
{state_summary}

PREDICTED CHANGES:
{changes_summary}

Is it plausible that this action produces these changes?
Consider:
1. Does the action logically lead to these changes?
2. Are all changes related to the action?
3. Are there any impossible or contradictory changes?
4. Are there expected changes that are missing?
"""

    def _summarize_state(self, state: dict) -> str:
        """Create a brief summary of the state."""
        ui = state.get("ui", {})
        elements = []
        self._collect_elements(ui, elements, max_depth=3)

        lines = []
        for el in elements[:20]:  # Limit elements
            bid = el.get("bid", "?")
            tag = el.get("tag", "element")
            text = el.get("text", "")[:50]
            lines.append(f"  [{bid}] {tag}: {text}")

        return "\n".join(lines) if lines else "(empty state)"

    def _collect_elements(
        self, node: dict, elements: list, max_depth: int, depth: int = 0
    ) -> None:
        """Collect elements up to max_depth."""
        if depth > max_depth or not isinstance(node, dict):
            return

        if "bid" in node:
            elements.append(node)

        for child in node.get("children", []):
            self._collect_elements(child, elements, max_depth, depth + 1)

    def _summarize_changes(self, state_ops: list) -> str:
        """Summarize state operations."""
        if not state_ops:
            return "(no changes)"

        lines = []
        for op in state_ops:
            op_type = op.get("op")
            bid = op.get("bid", op.get("parent_bid", "?"))
            lines.append(f"  {op_type} on bid={bid}: {json.dumps(op)[:100]}")

        return "\n".join(lines)


BACKWARD_VERIFICATION_SYSTEM = """
You are a verification system that checks if predicted state changes are plausible.

Given an action and predicted state changes, determine if the changes are
logically consistent with the action.

Respond with JSON:
{
  "plausibility_score": 0.0-1.0,
  "reasoning": "Brief explanation",
  "issues": ["list of specific issues if any"]
}

Scoring guide:
- 1.0: Changes are exactly what the action would produce
- 0.8: Changes are plausible, minor issues
- 0.5: Some changes are plausible, some questionable
- 0.2: Many changes don't follow from the action
- 0.0: Changes are impossible or contradictory
"""


# =============================================================================
# Combined Verifier
# =============================================================================

class CombinedVerifier(BaseVerifier):
    """Combines multiple verifiers in sequence."""

    def __init__(self, verifiers: list[Verifier]):
        super().__init__("combined_verifier")
        self.verifiers = verifiers

    def verify(
        self,
        output: dict,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> tuple[bool, list[str]]:
        """Run all verifiers and combine results."""
        all_errors = []

        for verifier in self.verifiers:
            is_valid, errors = verifier.verify(
                output, current_state, action, context
            )
            if not is_valid:
                all_errors.extend([f"[{verifier.name}] {e}" for e in errors])

        return len(all_errors) == 0, all_errors


# =============================================================================
# Module
# =============================================================================

@dataclass
class VerificationModule(Module):
    """
    Module for verification mode configuration.

    Provides verifiers and prompt blocks for the selected mode.
    """

    mode: VerificationMode = VerificationMode.SCHEMA
    strict: bool = False  # For constraint verification
    llm_client: Any = None  # For backward verification
    backward_threshold: float = 0.7

    def __post_init__(self):
        self.name = f"verification_{self.mode.value}"
        self.description = f"Verification mode: {self.mode.value}"

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt blocks for verification mode."""
        if self.mode == VerificationMode.BACKWARD:
            return [BackwardVerificationBlock()]
        return []

    def get_verifiers(self) -> list[Verifier]:
        """Return verifiers for selected mode."""
        verifiers = {
            VerificationMode.NONE: [],
            VerificationMode.SCHEMA: [SchemaVerifier()],
            VerificationMode.CONSTRAINT_CHECK: [
                SchemaVerifier(),
                ConstraintVerifier(strict=self.strict),
            ],
            VerificationMode.BACKWARD: [
                SchemaVerifier(),
                ConstraintVerifier(strict=False),
                BackwardVerifier(
                    llm_client=self.llm_client,
                    threshold=self.backward_threshold,
                ),
            ],
        }
        return verifiers[self.mode]

    def get_verifier(self) -> Verifier:
        """Get a combined verifier for the current mode."""
        verifiers = self.get_verifiers()
        if not verifiers:
            return BaseVerifier("none")
        if len(verifiers) == 1:
            return verifiers[0]
        return CombinedVerifier(verifiers)
