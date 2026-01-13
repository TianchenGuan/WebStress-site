"""
Base interfaces for modular experiment components.

All modules follow a simple protocol that allows them to be composed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


class PromptBlock(Protocol):
    """
    Protocol for prompt blocks that can be injected into the system prompt.

    Prompt blocks modify LLM behavior through instructions rather than code.
    """

    @property
    def name(self) -> str:
        """Unique name for this prompt block."""
        ...

    def render(self, context: dict) -> str:
        """
        Render this prompt block as text.

        Args:
            context: Dictionary with state, history, instruction, etc.

        Returns:
            Prompt text to be injected.
        """
        ...


class StatePreprocessor(Protocol):
    """
    Protocol for state preprocessing before sending to LLM.

    Preprocessors transform the full state into a representation
    suitable for the LLM based on the abstraction level.
    """

    @property
    def name(self) -> str:
        """Unique name for this preprocessor."""
        ...

    def preprocess(self, state: dict, context: dict) -> dict:
        """
        Transform state before sending to LLM.

        Args:
            state: Full simulator state.
            context: Additional context (instruction, history, etc.)

        Returns:
            Transformed state representation.
        """
        ...


class OutputParser(Protocol):
    """
    Protocol for parsing LLM output into state operations.

    Parsers handle different output modes (full state, delta, semantic).
    """

    @property
    def name(self) -> str:
        """Unique name for this parser."""
        ...

    def get_output_schema(self) -> dict:
        """Return JSON schema for expected output format."""
        ...

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """
        Parse LLM output into state operations.

        Args:
            llm_output: Raw output from LLM.
            current_state: Current simulator state.

        Returns:
            List of state operations (patches) to apply.
        """
        ...


class Verifier(Protocol):
    """
    Protocol for verification of LLM outputs.

    Verifiers check that outputs are valid and consistent.
    """

    @property
    def name(self) -> str:
        """Unique name for this verifier."""
        ...

    def verify(
        self,
        output: dict,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> tuple[bool, list[str]]:
        """
        Verify LLM output.

        Args:
            output: Parsed LLM output.
            current_state: State before action.
            action: Action that was taken.
            context: Additional context.

        Returns:
            (is_valid, list_of_errors)
        """
        ...


class HistoryManager(Protocol):
    """
    Protocol for managing conversation/action history.

    History managers determine what context is provided to the LLM.
    """

    @property
    def name(self) -> str:
        """Unique name for this history manager."""
        ...

    def add_step(self, step: dict) -> None:
        """Add a step to history."""
        ...

    def get_context(self, max_tokens: Optional[int] = None) -> list[dict]:
        """
        Get history context to include in prompt.

        Args:
            max_tokens: Optional token budget.

        Returns:
            List of history entries to include.
        """
        ...

    def reset(self) -> None:
        """Clear history for new episode."""
        ...


@dataclass
class Module:
    """
    Base class for experiment modules.

    Modules encapsulate a specific design choice and provide
    the components needed to implement it.
    """

    name: str
    description: str = ""

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt blocks this module contributes."""
        return []

    def get_preprocessors(self) -> list[StatePreprocessor]:
        """Return state preprocessors this module contributes."""
        return []

    def get_parsers(self) -> list[OutputParser]:
        """Return output parsers this module contributes."""
        return []

    def get_verifiers(self) -> list[Verifier]:
        """Return verifiers this module contributes."""
        return []

    def get_history_manager(self) -> Optional[HistoryManager]:
        """Return history manager if this module provides one."""
        return None


@dataclass
class ModuleConfig:
    """Configuration for a module."""
    enabled: bool = True
    params: dict = field(default_factory=dict)


# =============================================================================
# Base Implementations
# =============================================================================

class BasePromptBlock:
    """Base implementation of a prompt block."""

    def __init__(self, name: str, template: str):
        self._name = name
        self._template = template

    @property
    def name(self) -> str:
        return self._name

    def render(self, context: dict) -> str:
        """Render template with context variables."""
        try:
            return self._template.format(**context)
        except KeyError:
            # Return template as-is if context keys missing
            return self._template


class BaseStatePreprocessor:
    """Base implementation of state preprocessor."""

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def preprocess(self, state: dict, context: dict) -> dict:
        """Default: return state unchanged."""
        return state


class BaseOutputParser:
    """Base implementation of output parser."""

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def get_output_schema(self) -> dict:
        """Default schema for state operations."""
        return {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "state_ops": {"type": "array"},
                "events": {"type": "array"},
            },
            "required": ["state_ops"],
        }

    def parse(self, llm_output: dict, current_state: dict) -> list[dict]:
        """Default: extract state_ops directly."""
        return llm_output.get("state_ops", [])


class BaseVerifier:
    """Base implementation of verifier."""

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def verify(
        self,
        output: dict,
        current_state: dict,
        action: dict,
        context: dict,
    ) -> tuple[bool, list[str]]:
        """Default: always valid."""
        return True, []


class BaseHistoryManager:
    """Base implementation of history manager."""

    def __init__(self, name: str):
        self._name = name
        self._history: list[dict] = []

    @property
    def name(self) -> str:
        return self._name

    def add_step(self, step: dict) -> None:
        self._history.append(step)

    def get_context(self, max_tokens: Optional[int] = None) -> list[dict]:
        return self._history.copy()

    def reset(self) -> None:
        self._history = []
