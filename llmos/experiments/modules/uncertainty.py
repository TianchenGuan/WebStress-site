"""
Uncertainty Module: How the simulator expresses uncertainty about predictions.

Modes:
- DETERMINISTIC: Single prediction, no uncertainty
- WITH_CONFIDENCE: Single prediction with confidence score
- PROBABILISTIC: Multiple possible outcomes with probabilities
- ADMITS_UNCERTAINTY: Explicitly flags uncertain predictions

Each mode provides:
1. Prompt block explaining uncertainty expectations
2. Output schema for uncertainty data
3. Handler for uncertainty-aware decision making
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


class UncertaintyMode(str, Enum):
    """Available uncertainty modes."""
    DETERMINISTIC = "deterministic"
    WITH_CONFIDENCE = "with_confidence"
    PROBABILISTIC = "probabilistic"
    ADMITS_UNCERTAINTY = "admits_uncertainty"


# =============================================================================
# Prompt Blocks
# =============================================================================

DETERMINISTIC_PROMPT = """
## Uncertainty Mode: Deterministic

Provide a SINGLE, DEFINITE prediction for how the state changes.

- Do not express uncertainty or alternatives
- Predict the most likely outcome as if it definitely happens
- Make confident predictions even when multiple outcomes are possible
- Your prediction is treated as ground truth

Output format:
```json
{
  "thought": "Confident reasoning about what happens",
  "state_ops": [...]
}
```
"""

WITH_CONFIDENCE_PROMPT = """
## Uncertainty Mode: With Confidence Scores

Provide predictions WITH CONFIDENCE SCORES indicating how certain you are.

For each aspect of your prediction, provide a confidence level:
- `confidence`: 0.0 to 1.0 overall confidence
- Per-operation confidence when predictions vary in certainty

Confidence guidelines:
- 0.95-1.0: Highly confident, standard UI behavior
- 0.8-0.95: Confident, but some edge cases possible
- 0.6-0.8: Moderately confident, depends on implementation details
- 0.4-0.6: Uncertain, multiple outcomes equally likely
- 0.0-0.4: Low confidence, guessing

Output format:
```json
{
  "thought": "Reasoning with confidence assessment",
  "confidence": 0.85,
  "confidence_reasoning": "Standard button click behavior, high confidence",
  "state_ops": [
    {
      "op": "update",
      "bid": "btn1",
      "props": {"disabled": true},
      "op_confidence": 0.95
    }
  ]
}
```

Be calibrated: your confidence scores should reflect actual accuracy.
"""

PROBABILISTIC_PROMPT = """
## Uncertainty Mode: Probabilistic Outcomes

Provide MULTIPLE POSSIBLE OUTCOMES with their probabilities.

When actions can result in different states depending on:
- Hidden state you can't observe
- External factors (network, server responses)
- Non-deterministic UI behavior
- User-specific configurations

Provide all plausible outcomes:

```json
{
  "thought": "Analysis of possible outcomes",
  "outcomes": [
    {
      "probability": 0.7,
      "description": "Form submits successfully",
      "state_ops": [
        {"op": "update", "bid": "msg", "props": {"text": "Success!", "visible": true}}
      ],
      "events": ["form:submit:success"]
    },
    {
      "probability": 0.2,
      "description": "Validation error on server",
      "state_ops": [
        {"op": "update", "bid": "error", "props": {"text": "Server validation failed", "visible": true}}
      ],
      "events": ["form:submit:validation_error"]
    },
    {
      "probability": 0.1,
      "description": "Network error",
      "state_ops": [
        {"op": "update", "bid": "error", "props": {"text": "Connection failed", "visible": true}}
      ],
      "events": ["form:submit:network_error"]
    }
  ]
}
```

Requirements:
- Probabilities must sum to 1.0
- Include at least the most likely outcome
- Limit to 3-5 outcomes for clarity
- Include error/edge cases when relevant
"""

ADMITS_UNCERTAINTY_PROMPT = """
## Uncertainty Mode: Admits Uncertainty

Explicitly FLAG areas of uncertainty in your predictions.

When you're uncertain about any aspect, mark it clearly:

```json
{
  "thought": "Reasoning about what I know and don't know",
  "state_ops": [...],
  "uncertainties": [
    {
      "aspect": "exact_error_message",
      "reason": "Error message wording depends on server implementation",
      "impact": "low",
      "fallback": "Generic error text used"
    },
    {
      "aspect": "loading_duration",
      "reason": "Network latency unknown",
      "impact": "medium",
      "fallback": "Assumed instant completion"
    }
  ],
  "assumptions": [
    "User has permission to submit this form",
    "Server is operational",
    "No concurrent edits"
  ]
}
```

Uncertainty impacts:
- `low`: Cosmetic differences, doesn't affect task completion
- `medium`: May affect user's next action choice
- `high`: Could determine task success/failure

Being explicit about uncertainty helps:
1. Training: Focus on reducing high-impact uncertainty
2. Evaluation: Account for legitimate prediction variance
3. Agents: Make decisions considering uncertainty
"""


class DeterministicBlock(BasePromptBlock):
    """Prompt block for deterministic mode."""

    def __init__(self):
        super().__init__("deterministic_uncertainty", DETERMINISTIC_PROMPT)


class WithConfidenceBlock(BasePromptBlock):
    """Prompt block for confidence score mode."""

    def __init__(self):
        super().__init__("with_confidence_uncertainty", WITH_CONFIDENCE_PROMPT)


class ProbabilisticBlock(BasePromptBlock):
    """Prompt block for probabilistic mode."""

    def __init__(self):
        super().__init__("probabilistic_uncertainty", PROBABILISTIC_PROMPT)


class AdmitsUncertaintyBlock(BasePromptBlock):
    """Prompt block for admits uncertainty mode."""

    def __init__(self):
        super().__init__("admits_uncertainty", ADMITS_UNCERTAINTY_PROMPT)


# =============================================================================
# Output Schemas
# =============================================================================

CONFIDENCE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence_reasoning": {"type": "string"},
        "state_ops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string"},
                    "op_confidence": {"type": "number"},
                },
            },
        },
        "events": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["state_ops", "confidence"],
}

PROBABILISTIC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "probability": {"type": "number", "minimum": 0, "maximum": 1},
                    "description": {"type": "string"},
                    "state_ops": {"type": "array"},
                    "events": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["probability", "state_ops"],
            },
        },
    },
    "required": ["outcomes"],
}

ADMITS_UNCERTAINTY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "state_ops": {"type": "array"},
        "events": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "aspect": {"type": "string"},
                    "reason": {"type": "string"},
                    "impact": {"type": "string", "enum": ["low", "medium", "high"]},
                    "fallback": {"type": "string"},
                },
                "required": ["aspect", "reason", "impact"],
            },
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["state_ops"],
}


# =============================================================================
# Output Parsers
# =============================================================================

class DeterministicParser(BaseOutputParser):
    """Parser for deterministic mode - no special handling."""

    def __init__(self):
        super().__init__("deterministic_parser")

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        return llm_output.get("state_ops", [])


class WithConfidenceParser(BaseOutputParser):
    """Parser for confidence score mode."""

    def __init__(self, min_confidence: float = 0.0):
        super().__init__("with_confidence_parser")
        self.min_confidence = min_confidence

    def get_output_schema(self) -> dict:
        return CONFIDENCE_OUTPUT_SCHEMA

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Extract state ops, optionally filtering by confidence."""
        state_ops = llm_output.get("state_ops", [])

        if self.min_confidence > 0:
            # Filter ops below confidence threshold
            filtered = []
            for op in state_ops:
                op_conf = op.get("op_confidence", llm_output.get("confidence", 1.0))
                if op_conf >= self.min_confidence:
                    filtered.append(op)
            return filtered

        return state_ops

    def get_confidence(self, llm_output: dict) -> float:
        """Get overall confidence score."""
        return llm_output.get("confidence", 1.0)

    def get_confidence_reasoning(self, llm_output: dict) -> str:
        """Get confidence reasoning."""
        return llm_output.get("confidence_reasoning", "")


class ProbabilisticParser(BaseOutputParser):
    """Parser for probabilistic mode."""

    def __init__(self, selection_strategy: str = "most_likely"):
        """
        Args:
            selection_strategy: How to select from outcomes
                - "most_likely": Choose highest probability
                - "sample": Random sample by probability
                - "all": Return all outcomes (for analysis)
        """
        super().__init__("probabilistic_parser")
        self.selection_strategy = selection_strategy

    def get_output_schema(self) -> dict:
        return PROBABILISTIC_OUTPUT_SCHEMA

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Select outcome and return its state ops."""
        outcomes = llm_output.get("outcomes", [])

        if not outcomes:
            return llm_output.get("state_ops", [])

        if self.selection_strategy == "most_likely":
            # Select highest probability outcome
            selected = max(outcomes, key=lambda o: o.get("probability", 0))
            return selected.get("state_ops", [])

        elif self.selection_strategy == "sample":
            # Random sample weighted by probability
            import random
            probs = [o.get("probability", 0) for o in outcomes]
            total = sum(probs)
            if total > 0:
                probs = [p / total for p in probs]  # Normalize
                selected = random.choices(outcomes, weights=probs, k=1)[0]
                return selected.get("state_ops", [])

        # Default: return first outcome
        return outcomes[0].get("state_ops", []) if outcomes else []

    def get_outcomes(self, llm_output: dict) -> list[dict]:
        """Get all outcomes for analysis."""
        return llm_output.get("outcomes", [])

    def get_most_likely_outcome(self, llm_output: dict) -> Optional[dict]:
        """Get the most likely outcome."""
        outcomes = llm_output.get("outcomes", [])
        if not outcomes:
            return None
        return max(outcomes, key=lambda o: o.get("probability", 0))


class AdmitsUncertaintyParser(BaseOutputParser):
    """Parser for admits uncertainty mode."""

    def __init__(self):
        super().__init__("admits_uncertainty_parser")

    def get_output_schema(self) -> dict:
        return ADMITS_UNCERTAINTY_OUTPUT_SCHEMA

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Extract state ops."""
        return llm_output.get("state_ops", [])

    def get_uncertainties(self, llm_output: dict) -> list[dict]:
        """Get list of uncertainties."""
        return llm_output.get("uncertainties", [])

    def get_high_impact_uncertainties(self, llm_output: dict) -> list[dict]:
        """Get uncertainties with high impact."""
        uncertainties = llm_output.get("uncertainties", [])
        return [u for u in uncertainties if u.get("impact") == "high"]

    def get_assumptions(self, llm_output: dict) -> list[str]:
        """Get list of assumptions."""
        return llm_output.get("assumptions", [])

    def has_high_uncertainty(self, llm_output: dict) -> bool:
        """Check if prediction has high-impact uncertainty."""
        return len(self.get_high_impact_uncertainties(llm_output)) > 0


# =============================================================================
# Uncertainty Aggregator
# =============================================================================

class UncertaintyAggregator:
    """
    Aggregates uncertainty information across an episode.

    Useful for:
    - Analyzing where the simulator is uncertain
    - Identifying patterns in uncertainty
    - Adjusting training based on uncertainty
    """

    def __init__(self):
        self._step_confidence: list[float] = []
        self._uncertainties: list[dict] = []
        self._assumptions: set[str] = set()

    def add_step(
        self,
        confidence: Optional[float] = None,
        uncertainties: Optional[list[dict]] = None,
        assumptions: Optional[list[str]] = None,
    ) -> None:
        """Record uncertainty info for a step."""
        if confidence is not None:
            self._step_confidence.append(confidence)
        if uncertainties:
            self._uncertainties.extend(uncertainties)
        if assumptions:
            self._assumptions.update(assumptions)

    def get_average_confidence(self) -> float:
        """Get average confidence across episode."""
        if not self._step_confidence:
            return 1.0
        return sum(self._step_confidence) / len(self._step_confidence)

    def get_min_confidence(self) -> float:
        """Get minimum confidence in episode."""
        if not self._step_confidence:
            return 1.0
        return min(self._step_confidence)

    def get_uncertainty_summary(self) -> dict:
        """Get summary of uncertainties."""
        by_impact = {"low": 0, "medium": 0, "high": 0}
        for u in self._uncertainties:
            impact = u.get("impact", "low")
            by_impact[impact] = by_impact.get(impact, 0) + 1

        return {
            "total_uncertainties": len(self._uncertainties),
            "by_impact": by_impact,
            "unique_assumptions": len(self._assumptions),
            "avg_confidence": self.get_average_confidence(),
        }

    def reset(self) -> None:
        """Reset for new episode."""
        self._step_confidence = []
        self._uncertainties = []
        self._assumptions = set()


# =============================================================================
# Module
# =============================================================================

@dataclass
class UncertaintyModule(Module):
    """
    Module for uncertainty mode configuration.

    Provides prompt blocks, parsers, and uncertainty tracking.
    """

    mode: UncertaintyMode = UncertaintyMode.DETERMINISTIC
    min_confidence: float = 0.0  # For WITH_CONFIDENCE mode
    selection_strategy: str = "most_likely"  # For PROBABILISTIC mode

    def __post_init__(self):
        self.name = f"uncertainty_{self.mode.value}"
        self.description = f"Uncertainty mode: {self.mode.value}"
        self._aggregator = UncertaintyAggregator()

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected mode."""
        blocks = {
            UncertaintyMode.DETERMINISTIC: DeterministicBlock(),
            UncertaintyMode.WITH_CONFIDENCE: WithConfidenceBlock(),
            UncertaintyMode.PROBABILISTIC: ProbabilisticBlock(),
            UncertaintyMode.ADMITS_UNCERTAINTY: AdmitsUncertaintyBlock(),
        }
        return [blocks[self.mode]]

    def get_parsers(self) -> list[OutputParser]:
        """Return parser for selected mode."""
        parsers = {
            UncertaintyMode.DETERMINISTIC: DeterministicParser(),
            UncertaintyMode.WITH_CONFIDENCE: WithConfidenceParser(
                min_confidence=self.min_confidence
            ),
            UncertaintyMode.PROBABILISTIC: ProbabilisticParser(
                selection_strategy=self.selection_strategy
            ),
            UncertaintyMode.ADMITS_UNCERTAINTY: AdmitsUncertaintyParser(),
        }
        return [parsers[self.mode]]

    def get_parser(self) -> OutputParser:
        """Get the parser for the current mode."""
        return self.get_parsers()[0]

    def get_aggregator(self) -> UncertaintyAggregator:
        """Get the uncertainty aggregator."""
        return self._aggregator

    def reset(self) -> None:
        """Reset for new episode."""
        self._aggregator.reset()
