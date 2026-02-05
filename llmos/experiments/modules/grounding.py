"""
Grounding Module: How the simulator grounds its predictions.

Modes:
- LLM_KNOWLEDGE: Pure LLM knowledge, no external grounding
- EXAMPLE_GROUNDED: Ground predictions with similar examples
- DOC_GROUNDED: Ground with documentation/specifications
- TRACE_GROUNDED: Ground with real environment traces

Each mode provides:
1. Prompt block explaining grounding expectations
2. Context retriever for grounding information
3. Integration with the prompt builder
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
import json

from .base import (
    Module,
    BasePromptBlock,
    PromptBlock,
)


class GroundingStrategy(str, Enum):
    """Available grounding strategies."""
    LLM_KNOWLEDGE = "llm_knowledge"
    EXAMPLE_GROUNDED = "example_grounded"
    DOC_GROUNDED = "doc_grounded"
    TRACE_GROUNDED = "trace_grounded"


# =============================================================================
# Prompt Blocks
# =============================================================================

LLM_KNOWLEDGE_PROMPT = """
## Grounding: LLM Knowledge

Use general UI/web knowledge. Rely on common patterns, not specific implementation details.
"""

EXAMPLE_GROUNDED_PROMPT = """
## Grounding: Similar Examples

Match predictions to these examples of similar actions:

{examples}

If no match, use general knowledge but note the gap.
"""

DOC_GROUNDED_PROMPT = """
## Grounding: Documentation

Follow this documentation for behavior and formats:

{documentation}

Documentation takes precedence over general expectations.
"""

TRACE_GROUNDED_PROMPT = """
## Grounding: Real Environment Traces

Match predictions to these real state transitions:

{traces}

Use exact behavior from traces. If no match, adapt closest trace and note it.
"""


class LLMKnowledgeBlock(BasePromptBlock):
    """Prompt block for pure LLM knowledge grounding."""

    def __init__(self):
        super().__init__("llm_knowledge_grounding", LLM_KNOWLEDGE_PROMPT)


class ExampleGroundedBlock(BasePromptBlock):
    """Prompt block for example-grounded predictions."""

    def __init__(self):
        super().__init__("example_grounded", EXAMPLE_GROUNDED_PROMPT)

    def render(self, context: dict) -> str:
        examples = context.get("grounding_examples", "No examples available.")
        return self._template.format(examples=examples)


class DocGroundedBlock(BasePromptBlock):
    """Prompt block for documentation-grounded predictions."""

    def __init__(self):
        super().__init__("doc_grounded", DOC_GROUNDED_PROMPT)

    def render(self, context: dict) -> str:
        documentation = context.get("grounding_documentation", "No documentation available.")
        return self._template.format(documentation=documentation)


class TraceGroundedBlock(BasePromptBlock):
    """Prompt block for trace-grounded predictions."""

    def __init__(self):
        super().__init__("trace_grounded", TRACE_GROUNDED_PROMPT)

    def render(self, context: dict) -> str:
        traces = context.get("grounding_traces", "No traces available.")
        return self._template.format(traces=traces)


# =============================================================================
# Grounding Retrievers
# =============================================================================

class BaseGroundingRetriever:
    """Base class for grounding retrievers."""

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def retrieve(
        self,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> str:
        """
        Retrieve grounding information for the given context.

        Returns formatted string to include in prompt.
        """
        return ""


class ExampleRetriever(BaseGroundingRetriever):
    """
    Retrieves similar examples from an example store.

    Examples can be:
    - From previous episodes
    - From a curated example set
    - From other agents' traces
    """

    def __init__(
        self,
        examples: Optional[list[dict]] = None,
        similarity_fn: Optional[Callable[[dict, dict], float]] = None,
        max_examples: int = 3,
    ):
        super().__init__("example_retriever")
        self._examples = examples or []
        self._similarity_fn = similarity_fn or self._default_similarity
        self._max_examples = max_examples

    def add_example(self, example: dict) -> None:
        """Add an example to the store."""
        self._examples.append(example)

    def set_examples(self, examples: list[dict]) -> None:
        """Set the example store."""
        self._examples = examples

    def retrieve(
        self,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> str:
        """Retrieve similar examples."""
        if not self._examples:
            return "No examples available."

        # Score examples by similarity
        scored = []
        for ex in self._examples:
            score = self._similarity_fn(
                {"state": current_state, "action": action},
                ex,
            )
            scored.append((score, ex))

        # Sort by score and take top examples
        scored.sort(key=lambda x: x[0], reverse=True)
        top_examples = [ex for _, ex in scored[:self._max_examples]]

        # Format examples
        return self._format_examples(top_examples)

    def _default_similarity(self, query: dict, example: dict) -> float:
        """Default similarity based on action type matching."""
        query_action = query.get("action", {}).get("action_type", "")
        ex_action = example.get("action", {}).get("action_type", "")

        # Exact action type match
        if query_action == ex_action:
            return 1.0

        # Partial match (same action family)
        action_families = {
            "click": ["click", "dblclick"],
            "input": ["fill", "type", "press"],
            "navigate": ["goto", "scroll"],
        }
        for family, members in action_families.items():
            if query_action in members and ex_action in members:
                return 0.5

        return 0.0

    def _format_examples(self, examples: list[dict]) -> str:
        """Format examples for prompt."""
        lines = []
        for i, ex in enumerate(examples, 1):
            lines.append(f"### Example {i}")

            action = ex.get("action", {})
            lines.append(f"Action: {action.get('action_type', 'unknown')}")
            if action.get("bid"):
                lines.append(f"  Target: bid={action['bid']}")

            state_before = ex.get("state_before_summary", "")
            if state_before:
                lines.append(f"State before: {state_before}")

            state_ops = ex.get("state_ops", [])
            if state_ops:
                lines.append(f"Changes ({len(state_ops)} ops):")
                for op in state_ops[:5]:  # Limit ops shown
                    lines.append(f"  - {op.get('op')}: {json.dumps(op)[:100]}")

            lines.append("")

        return "\n".join(lines) if lines else "No examples available."


class DocumentationRetriever(BaseGroundingRetriever):
    """
    Retrieves relevant documentation.

    Documentation can be:
    - UI component specs
    - Application behavior documentation
    - API documentation
    """

    def __init__(
        self,
        documents: Optional[dict[str, str]] = None,
        search_fn: Optional[Callable[[str, dict], list[str]]] = None,
    ):
        super().__init__("documentation_retriever")
        self._documents = documents or {}
        self._search_fn = search_fn

    def add_document(self, key: str, content: str) -> None:
        """Add a document."""
        self._documents[key] = content

    def set_documents(self, documents: dict[str, str]) -> None:
        """Set all documents."""
        self._documents = documents

    def retrieve(
        self,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> str:
        """Retrieve relevant documentation."""
        if not self._documents:
            return "No documentation available."

        # Extract search context
        action_type = action.get("action_type", "")
        target_bid = action.get("bid", "")

        # Find target element info
        target_element = self._find_element(current_state.get("ui", {}), target_bid)
        target_tag = target_element.get("tag", "") if target_element else ""

        # Search for relevant docs
        relevant_keys = []
        for key in self._documents:
            key_lower = key.lower()
            if action_type.lower() in key_lower:
                relevant_keys.append(key)
            elif target_tag.lower() in key_lower:
                relevant_keys.append(key)

        # If custom search function provided, use it
        if self._search_fn:
            search_query = f"{action_type} {target_tag}"
            relevant_keys = self._search_fn(search_query, self._documents)

        # Format documentation
        if not relevant_keys:
            return "No relevant documentation found."

        lines = []
        for key in relevant_keys[:3]:  # Limit docs shown
            lines.append(f"### {key}")
            lines.append(self._documents[key])
            lines.append("")

        return "\n".join(lines)

    def _find_element(self, node: dict, bid: Any) -> Optional[dict]:
        """Find element by bid in UI tree."""
        if not isinstance(node, dict):
            return None
        if node.get("bid") == bid:
            return node
        for child in node.get("children", []):
            found = self._find_element(child, bid)
            if found:
                return found
        return None


class TraceRetriever(BaseGroundingRetriever):
    """
    Retrieves relevant traces from real environment interactions.

    Traces are records of actual state transitions:
    - state_before: State before action
    - action: The action taken
    - state_after: State after action
    - state_ops: The actual changes that occurred
    """

    def __init__(
        self,
        traces: Optional[list[dict]] = None,
        similarity_fn: Optional[Callable[[dict, dict], float]] = None,
        max_traces: int = 2,
    ):
        super().__init__("trace_retriever")
        self._traces = traces or []
        self._similarity_fn = similarity_fn or self._default_trace_similarity
        self._max_traces = max_traces

    def add_trace(self, trace: dict) -> None:
        """Add a trace."""
        self._traces.append(trace)

    def set_traces(self, traces: list[dict]) -> None:
        """Set all traces."""
        self._traces = traces

    def retrieve(
        self,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> str:
        """Retrieve relevant traces."""
        if not self._traces:
            return "No traces available."

        # Score traces by similarity
        scored = []
        for trace in self._traces:
            score = self._similarity_fn(
                {"state": current_state, "action": action},
                trace,
            )
            scored.append((score, trace))

        # Sort and take top traces
        scored.sort(key=lambda x: x[0], reverse=True)
        top_traces = [t for _, t in scored[:self._max_traces]]

        return self._format_traces(top_traces)

    def _default_trace_similarity(self, query: dict, trace: dict) -> float:
        """Default similarity for traces."""
        score = 0.0

        # Action type match
        query_action = query.get("action", {}).get("action_type", "")
        trace_action = trace.get("action", {}).get("action_type", "")
        if query_action == trace_action:
            score += 0.5

        # Target element similarity
        query_bid = query.get("action", {}).get("bid")
        trace_bid = trace.get("action", {}).get("bid")
        if query_bid and trace_bid:
            # Could do more sophisticated matching here
            if str(query_bid) == str(trace_bid):
                score += 0.3

        # State similarity (simple: number of matching top-level keys)
        query_state = query.get("state", {})
        trace_state = trace.get("state_before", {})
        matching_keys = set(query_state.keys()) & set(trace_state.keys())
        if matching_keys:
            score += 0.2 * len(matching_keys) / max(len(query_state), 1)

        return score

    def _format_traces(self, traces: list[dict]) -> str:
        """Format traces for prompt."""
        lines = []
        for i, trace in enumerate(traces, 1):
            lines.append(f"### Trace {i}")

            action = trace.get("action", {})
            lines.append(f"Action: {action.get('action_type', 'unknown')}")

            # Show key state differences
            state_ops = trace.get("state_ops", [])
            if state_ops:
                lines.append(f"Observed changes:")
                for op in state_ops[:10]:  # Limit shown
                    op_type = op.get("op", "unknown")
                    bid = op.get("bid", op.get("parent_bid", "?"))
                    lines.append(f"  - {op_type} on bid={bid}")

            events = trace.get("events", [])
            if events:
                lines.append(f"Events: {', '.join(events[:5])}")

            lines.append("")

        return "\n".join(lines) if lines else "No traces available."


# =============================================================================
# Module
# =============================================================================

@dataclass
class GroundingModule(Module):
    """
    Module for grounding strategy configuration.

    Provides prompt blocks and retrievers for the selected strategy.
    """

    strategy: GroundingStrategy = GroundingStrategy.LLM_KNOWLEDGE
    examples: list[dict] = field(default_factory=list)
    documents: dict[str, str] = field(default_factory=dict)
    traces: list[dict] = field(default_factory=list)
    max_examples: int = 3
    max_traces: int = 2

    def __post_init__(self):
        self.name = f"grounding_{self.strategy.value}"
        self.description = f"Grounding strategy: {self.strategy.value}"

        # Initialize retrievers
        self._example_retriever = ExampleRetriever(
            examples=self.examples,
            max_examples=self.max_examples,
        )
        self._doc_retriever = DocumentationRetriever(
            documents=self.documents,
        )
        self._trace_retriever = TraceRetriever(
            traces=self.traces,
            max_traces=self.max_traces,
        )

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected strategy."""
        blocks = {
            GroundingStrategy.LLM_KNOWLEDGE: LLMKnowledgeBlock(),
            GroundingStrategy.EXAMPLE_GROUNDED: ExampleGroundedBlock(),
            GroundingStrategy.DOC_GROUNDED: DocGroundedBlock(),
            GroundingStrategy.TRACE_GROUNDED: TraceGroundedBlock(),
        }
        return [blocks[self.strategy]]

    def get_retriever(self) -> BaseGroundingRetriever:
        """Get the retriever for the current strategy."""
        retrievers = {
            GroundingStrategy.LLM_KNOWLEDGE: BaseGroundingRetriever("llm_knowledge"),
            GroundingStrategy.EXAMPLE_GROUNDED: self._example_retriever,
            GroundingStrategy.DOC_GROUNDED: self._doc_retriever,
            GroundingStrategy.TRACE_GROUNDED: self._trace_retriever,
        }
        return retrievers[self.strategy]

    def get_grounding_context(
        self,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> dict:
        """
        Get grounding context to add to prompt context.

        Returns dict with keys like 'grounding_examples', 'grounding_documentation', etc.
        """
        retriever = self.get_retriever()
        grounding_text = retriever.retrieve(current_state, action, context)

        context_key = {
            GroundingStrategy.LLM_KNOWLEDGE: None,
            GroundingStrategy.EXAMPLE_GROUNDED: "grounding_examples",
            GroundingStrategy.DOC_GROUNDED: "grounding_documentation",
            GroundingStrategy.TRACE_GROUNDED: "grounding_traces",
        }[self.strategy]

        if context_key:
            return {context_key: grounding_text}
        return {}

    def add_example(self, example: dict) -> None:
        """Add an example to the example store."""
        self._example_retriever.add_example(example)

    def add_document(self, key: str, content: str) -> None:
        """Add a document."""
        self._doc_retriever.add_document(key, content)

    def add_trace(self, trace: dict) -> None:
        """Add a trace."""
        self._trace_retriever.add_trace(trace)
