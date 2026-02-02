"""
ObservationRenderer interface for converting state to agent-visible observations.
"""

from typing import Any, Optional, Protocol, runtime_checkable

from .task_provider import Task


@runtime_checkable
class ObservationRenderer(Protocol):
    """
    Protocol for rendering state into agent-visible observations.

    Implementations:
    - DefaultObservationRenderer: Filter hidden_state, render as dict (current behavior)
    - TextObservationRenderer: Render as accessibility tree text
    - HTMLObservationRenderer: Render as HTML (for web benchmarks)
    - ScreenshotRenderer: Render as image (for vision models)
    """

    def render(self, state: dict, task: Optional[Task] = None) -> Any:
        """
        Render state into agent-visible observation.

        Args:
            state: Full simulator state.
            task: Optional task for context.

        Returns:
            Observation in the appropriate format.
        """
        ...

    def supports_modality(self, modality: str) -> bool:
        """
        Check if this renderer supports a modality.

        Args:
            modality: One of 'dict', 'text', 'html', 'image'.

        Returns:
            True if supported.
        """
        ...


class DefaultObservationRenderer:
    """
    Default observation renderer using LLMOS rendering utils.

    Filters out hidden_state and other internal fields.
    """

    def __init__(self, max_content_length: int = 1000):
        """
        Initialize renderer.

        Args:
            max_content_length: Max length for file content (truncated beyond).
        """
        self.max_content_length = max_content_length

    def render(self, state: dict, task: Optional[Task] = None) -> dict:
        """Render state as filtered dict observation."""
        from ..utils.rendering import render_observation
        return render_observation(state)

    def supports_modality(self, modality: str) -> bool:
        return modality == "dict"


class TextObservationRenderer:
    """
    Observation renderer that produces accessibility tree text.

    Useful for text-based agents that don't need structured state.
    """

    def __init__(
        self,
        include_interactive_summary: bool = False,
        max_elements: int = 50,
    ):
        """
        Initialize renderer.

        Args:
            include_interactive_summary: Whether to include list of interactive elements.
                                         Default False - agent should infer interactivity.
            max_elements: Max number of elements to include in summary.
        """
        self.include_interactive_summary = include_interactive_summary
        self.max_elements = max_elements

    def render(self, state: dict, task: Optional[Task] = None) -> str:
        """Render state as accessibility tree text."""
        from ..utils.rendering import render_ui_as_text, extract_focusable_elements

        parts = []

        # UI tree
        ui_text = render_ui_as_text(state)
        parts.append("## UI Elements\n```")
        parts.append(ui_text)
        parts.append("```\n")

        # Interactive elements summary
        if self.include_interactive_summary:
            elements = extract_focusable_elements(state)[:self.max_elements]
            if elements:
                parts.append("## Interactive Elements")
                for elem in elements:
                    bid = elem.get("bid", "?")
                    tag = elem.get("tag", "?")
                    text = elem.get("text", elem.get("label", ""))[:50]
                    parts.append(f"- [{bid}] {tag}: {text}")

        return "\n".join(parts)

    def supports_modality(self, modality: str) -> bool:
        return modality == "text"


class HybridObservationRenderer:
    """
    Observation renderer that combines multiple formats.

    Returns a dict with both structured and text representations.
    """

    def __init__(self):
        self.dict_renderer = DefaultObservationRenderer()
        self.text_renderer = TextObservationRenderer()

    def render(self, state: dict, task: Optional[Task] = None) -> dict:
        """Render state with multiple representations."""
        return {
            "state": self.dict_renderer.render(state, task),
            "text": self.text_renderer.render(state, task),
        }

    def supports_modality(self, modality: str) -> bool:
        return modality in ("dict", "text", "hybrid")
