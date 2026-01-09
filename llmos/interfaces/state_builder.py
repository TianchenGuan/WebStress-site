"""
StateBuilder interface for creating initial states from various sources.
"""

import json
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from .task_provider import Task


@runtime_checkable
class StateBuilder(Protocol):
    """
    Protocol for building initial states for tasks.

    Implementations:
    - TemplateStateBuilder: Load from JSON templates (current LLMOS behavior)
    - BrowserStateBuilder: Build state from live browser/URL
    - BenchmarkStateBuilder: Build from benchmark-specific setup
    """

    def build(self, task: Task) -> dict:
        """
        Build the initial state for a task.

        Args:
            task: The task to build state for.

        Returns:
            State dict with required keys: meta, ui, hidden_state, filesystem
        """
        ...

    def supports_task(self, task: Task) -> bool:
        """
        Check if this builder can handle the task.

        Args:
            task: Task to check.

        Returns:
            True if this builder can create state for this task.
        """
        ...


class TemplateStateBuilder:
    """
    State builder that loads from JSON template files.

    This is the default implementation matching current LLMOS behavior.
    """

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        default_template: str = "desktop",
    ):
        """
        Initialize the template state builder.

        Args:
            templates_dir: Directory containing template JSON files.
            default_template: Default template name if task doesn't specify one.
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent / "templates"
        self.templates_dir = Path(templates_dir)
        self.default_template = default_template
        self._cache: dict[str, dict] = {}

    def build(self, task: Task) -> dict:
        """Build initial state from template."""
        template_name = task.initial_state_template or self.default_template
        return self._load_template(template_name)

    def _load_template(self, name: str) -> dict:
        """Load and cache a template."""
        if name not in self._cache:
            path = self.templates_dir / f"{name}.json"
            if not path.exists():
                raise FileNotFoundError(f"Template not found: {path}")
            with open(path) as f:
                self._cache[name] = json.load(f)
        # Return a copy to avoid mutations
        import copy
        return copy.deepcopy(self._cache[name])

    def supports_task(self, task: Task) -> bool:
        """Check if template exists for task."""
        template_name = task.initial_state_template or self.default_template
        path = self.templates_dir / f"{template_name}.json"
        return path.exists()

    def list_templates(self) -> list[str]:
        """List available template names."""
        return [p.stem for p in self.templates_dir.glob("*.json")]


class CompositeStateBuilder:
    """
    State builder that delegates to multiple builders based on task type.

    Useful when a benchmark has multiple environment types.
    """

    def __init__(self, builders: dict[str, StateBuilder]):
        """
        Initialize with a mapping of template names to builders.

        Args:
            builders: Dict mapping template/type names to StateBuilder instances.
        """
        self.builders = builders
        self.default_builder: Optional[StateBuilder] = None

    def set_default(self, builder: StateBuilder) -> None:
        """Set a fallback builder for unmatched tasks."""
        self.default_builder = builder

    def build(self, task: Task) -> dict:
        """Build state using the appropriate builder."""
        template = task.initial_state_template or "default"

        if template in self.builders:
            return self.builders[template].build(task)

        if self.default_builder:
            return self.default_builder.build(task)

        raise ValueError(f"No builder for template '{template}' and no default set")

    def supports_task(self, task: Task) -> bool:
        """Check if any builder can handle this task."""
        template = task.initial_state_template or "default"
        if template in self.builders:
            return self.builders[template].supports_task(task)
        if self.default_builder:
            return self.default_builder.supports_task(task)
        return False
