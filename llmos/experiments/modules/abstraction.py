"""
Abstraction Module: Level of detail in state representation.

Modes:
- FULL_DOM: Complete UI tree with all attributes
- SEMANTIC_ELEMENTS: Only semantic elements (buttons, inputs, text, etc.)
- TASK_RELEVANT: Only elements relevant to the current task
- VIEWPORT_ONLY: Only visible elements within viewport
- INTERACTIVE_ONLY: Only interactive elements

Each mode provides:
1. State preprocessor to filter/transform state
2. Prompt block explaining the abstraction level
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional
import copy
import re

from .base import (
    Module,
    BasePromptBlock,
    BaseStatePreprocessor,
    PromptBlock,
    StatePreprocessor,
)


class AbstractionLevel(str, Enum):
    """Available abstraction levels."""
    FULL_DOM = "full_dom"
    SEMANTIC_ELEMENTS = "semantic_elements"
    TASK_RELEVANT = "task_relevant"
    VIEWPORT_ONLY = "viewport_only"
    INTERACTIVE_ONLY = "interactive_only"


# =============================================================================
# Prompt Blocks
# =============================================================================

FULL_DOM_PROMPT = """
## State Representation: Full DOM

You are given the complete UI tree with all elements and attributes.

The state includes:
- All HTML/UI elements with their full attributes
- Element hierarchy preserved exactly
- All text content, styles, and metadata
- Hidden elements marked with `visible: false`

Use the `bid` (browser ID) to reference elements in your operations.
"""

SEMANTIC_ELEMENTS_PROMPT = """
## State Representation: Semantic Elements

You are given a simplified view of the UI containing only semantic elements.

Included elements:
- Interactive: buttons, links, inputs, selects, checkboxes, radio buttons
- Text: headings, paragraphs, labels, error messages
- Containers: forms, dialogs, menus, lists
- Media: images with alt text

Excluded:
- Layout elements (div, span without semantic meaning)
- Style-only elements
- Script/style tags
- Hidden elements

Each element has:
- `bid`: Unique identifier for targeting
- `tag`: Semantic tag name
- `text`: Visible text content (if any)
- Key attributes: `href`, `value`, `checked`, `disabled`, `placeholder`, etc.

Focus on what the user can SEE and INTERACT with.
"""

TASK_RELEVANT_PROMPT = """
## State Representation: Task-Relevant Elements

You are given a FILTERED view containing only elements relevant to the current task.

Task: {instruction}

The state includes:
- Elements mentioned in the task (by name, type, or label)
- Elements required to complete the task
- Ancestor containers of relevant elements
- Error/status messages related to the task

Elements NOT relevant to the task have been filtered out.

Focus on completing the specified task efficiently.
Use the `bid` to reference elements in your operations.
"""

VIEWPORT_ONLY_PROMPT = """
## State Representation: Viewport Only

You are given only elements currently VISIBLE in the viewport.

The state includes:
- Elements within the visible screen area
- Elements with bounds intersecting viewport {viewport}
- Partially visible elements (clipped)

NOT included:
- Elements scrolled out of view
- Elements below the fold
- Hidden elements

When the action involves scrolling, you may need to predict
elements that will become visible.
"""

INTERACTIVE_ONLY_PROMPT = """
## State Representation: Interactive Elements Only

You are given only INTERACTIVE elements the user can act upon.

Included:
- Buttons (button, submit, reset)
- Links (a with href)
- Form inputs (input, textarea, select)
- Checkboxes and radio buttons
- Clickable elements (onclick handler)
- Focusable elements

Excluded:
- Static text (unless labels)
- Images without actions
- Decorative elements
- Disabled elements (optionally)

Each element shows:
- `bid`: Unique identifier
- `tag`: Element type
- `text`: Visible label/text
- Interaction attributes: `value`, `checked`, `disabled`, etc.
"""


class FullDOMPromptBlock(BasePromptBlock):
    """Prompt block for full DOM abstraction."""

    def __init__(self):
        super().__init__("full_dom_abstraction", FULL_DOM_PROMPT)


class SemanticElementsPromptBlock(BasePromptBlock):
    """Prompt block for semantic elements abstraction."""

    def __init__(self):
        super().__init__("semantic_elements_abstraction", SEMANTIC_ELEMENTS_PROMPT)


class TaskRelevantPromptBlock(BasePromptBlock):
    """Prompt block for task-relevant abstraction."""

    def __init__(self):
        super().__init__("task_relevant_abstraction", TASK_RELEVANT_PROMPT)

    def render(self, context: dict) -> str:
        instruction = context.get("instruction", "No task specified")
        if isinstance(instruction, dict):
            instruction = instruction.get("text", str(instruction))
        return self._template.format(instruction=instruction)


class ViewportOnlyPromptBlock(BasePromptBlock):
    """Prompt block for viewport-only abstraction."""

    def __init__(self):
        super().__init__("viewport_only_abstraction", VIEWPORT_ONLY_PROMPT)

    def render(self, context: dict) -> str:
        viewport = context.get("viewport", {"width": 1920, "height": 1080})
        return self._template.format(viewport=viewport)


class InteractiveOnlyPromptBlock(BasePromptBlock):
    """Prompt block for interactive-only abstraction."""

    def __init__(self):
        super().__init__("interactive_only_abstraction", INTERACTIVE_ONLY_PROMPT)


# =============================================================================
# State Preprocessors
# =============================================================================

# Tags considered semantic
SEMANTIC_TAGS = {
    # Interactive
    "button", "a", "input", "select", "option", "textarea",
    "checkbox", "radio", "switch", "slider",
    # Text
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "label", "span",
    "text", "heading", "title", "error", "message",
    # Containers
    "form", "dialog", "modal", "menu", "menuitem", "list", "listitem",
    "table", "row", "cell", "nav", "header", "footer", "main",
    # Media
    "img", "image", "icon", "video",
    # Desktop-specific (from LLMOS templates)
    "desktop", "window", "toolbar", "panel", "tab", "folder", "file",
    "notification", "tooltip", "dropdown",
}

# Attributes to preserve for semantic elements
SEMANTIC_ATTRIBUTES = {
    "bid", "tag", "text", "value", "href", "src", "alt",
    "checked", "selected", "disabled", "readonly", "placeholder",
    "name", "id", "type", "role", "aria-label", "title",
    "visible", "focused", "expanded", "children",
}


class FullDOMPreprocessor(BaseStatePreprocessor):
    """
    Preprocessor for full DOM abstraction.

    Passes state through with minimal changes.
    """

    def __init__(self):
        super().__init__("full_dom_preprocessor")

    def preprocess(self, state: dict, context: dict) -> dict:
        """Return state with minimal filtering."""
        result = copy.deepcopy(state)

        # Only filter out clearly internal/debug fields
        if "ui" in result:
            result["ui"] = self._clean_node(result["ui"])

        return result

    def _clean_node(self, node: dict) -> dict:
        """Remove only debug/internal fields."""
        if not isinstance(node, dict):
            return node

        cleaned = {}
        for key, value in node.items():
            # Skip internal fields
            if key.startswith("_") or key in ("debug", "internal"):
                continue

            if key == "children":
                cleaned["children"] = [
                    self._clean_node(child) for child in value
                    if isinstance(child, dict)
                ]
            else:
                cleaned[key] = value

        return cleaned


class SemanticElementsPreprocessor(BaseStatePreprocessor):
    """
    Preprocessor for semantic elements abstraction.

    Filters UI tree to only include semantic elements.
    """

    def __init__(self, include_hidden: bool = False):
        super().__init__("semantic_elements_preprocessor")
        self.include_hidden = include_hidden

    def preprocess(self, state: dict, context: dict) -> dict:
        """Filter state to semantic elements only."""
        result = copy.deepcopy(state)

        if "ui" in result:
            result["ui"] = self._filter_semantic(result["ui"])

        # Keep hidden_state but maybe filter it
        if "hidden_state" in result:
            # Remove internal hidden state, keep semantic state
            hidden = result["hidden_state"]
            result["hidden_state"] = {
                k: v for k, v in hidden.items()
                if not k.startswith("_")
            }

        return result

    def _filter_semantic(self, node: dict) -> Optional[dict]:
        """Recursively filter to semantic elements."""
        if not isinstance(node, dict):
            return None

        tag = node.get("tag", "").lower()
        visible = node.get("visible", True)

        # Skip hidden unless configured to include
        if not visible and not self.include_hidden:
            return None

        # Check if this node is semantic
        is_semantic = (
            tag in SEMANTIC_TAGS or
            node.get("role") in SEMANTIC_TAGS or
            self._has_semantic_content(node)
        )

        # Process children
        children = node.get("children", [])
        filtered_children = []
        for child in children:
            filtered = self._filter_semantic(child)
            if filtered is not None:
                filtered_children.append(filtered)

        # Include this node if semantic or has semantic children
        if is_semantic or filtered_children:
            result = self._extract_semantic_attrs(node)
            if filtered_children:
                result["children"] = filtered_children
            return result

        # If not semantic but has semantic descendants, return flattened children
        if filtered_children:
            # Return a container with just the children
            if len(filtered_children) == 1:
                return filtered_children[0]
            return {
                "bid": node.get("bid"),
                "tag": "container",
                "children": filtered_children,
            }

        return None

    def _has_semantic_content(self, node: dict) -> bool:
        """Check if node has meaningful semantic content."""
        # Has text content
        if node.get("text", "").strip():
            return True
        # Is interactive
        if node.get("onclick") or node.get("href"):
            return True
        # Has form-related attributes
        if any(node.get(attr) for attr in ["value", "placeholder", "checked"]):
            return True
        return False

    def _extract_semantic_attrs(self, node: dict) -> dict:
        """Extract only semantic attributes from node."""
        result = {}
        for key in SEMANTIC_ATTRIBUTES:
            if key in node and key != "children":
                value = node[key]
                # Truncate long text
                if key == "text" and isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                result[key] = value

        # Ensure bid and tag are present
        if "bid" not in result:
            result["bid"] = node.get("bid", "unknown")
        if "tag" not in result:
            result["tag"] = node.get("tag", "element")

        return result


class TaskRelevantPreprocessor(BaseStatePreprocessor):
    """
    Preprocessor that filters to task-relevant elements only.

    Uses the instruction to determine which elements are relevant.
    """

    def __init__(self, include_hidden: bool = False):
        super().__init__("task_relevant_preprocessor")
        self.include_hidden = include_hidden

    def preprocess(self, state: dict, context: dict) -> dict:
        """Filter state to task-relevant elements."""
        result = copy.deepcopy(state)

        instruction = context.get("instruction", "")
        if isinstance(instruction, dict):
            instruction = instruction.get("text", str(instruction))

        # Extract keywords from instruction
        keywords = self._extract_keywords(instruction)

        if "ui" in result:
            result["ui"] = self._filter_relevant(result["ui"], keywords)

        return result

    def _extract_keywords(self, instruction: str) -> set[str]:
        """Extract relevant keywords from instruction."""
        # Simple keyword extraction - lowercase words
        words = re.findall(r'\b[a-zA-Z]{2,}\b', instruction.lower())

        # Filter out common stop words
        stop_words = {
            "the", "a", "an", "to", "in", "on", "at", "for", "of",
            "and", "or", "is", "are", "it", "this", "that", "with",
            "from", "by", "be", "as", "was", "were", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can",
            "need", "want", "please", "click", "fill", "enter", "type",
            "select", "choose", "find", "go", "navigate", "open", "close",
        }

        # Add action-related keywords
        action_keywords = {
            "submit", "button", "form", "field", "input", "search",
            "menu", "dropdown", "checkbox", "radio", "link", "tab",
        }

        keywords = {w for w in words if w not in stop_words}
        keywords.update(action_keywords & set(words))

        return keywords

    def _filter_relevant(self, node: dict, keywords: set[str]) -> Optional[dict]:
        """Recursively filter to relevant elements."""
        if not isinstance(node, dict):
            return None

        visible = node.get("visible", True)
        if not visible and not self.include_hidden:
            return None

        # Check if this node is relevant
        is_relevant = self._is_relevant(node, keywords)

        # Process children
        children = node.get("children", [])
        filtered_children = []
        for child in children:
            filtered = self._filter_relevant(child, keywords)
            if filtered is not None:
                filtered_children.append(filtered)

        # Include if relevant or has relevant children
        if is_relevant or filtered_children:
            result = self._extract_attrs(node)
            if filtered_children:
                result["children"] = filtered_children
            return result

        return None

    def _is_relevant(self, node: dict, keywords: set[str]) -> bool:
        """Check if node is relevant to task keywords."""
        # Check text content
        text = node.get("text", "").lower()
        if any(kw in text for kw in keywords):
            return True

        # Check tag/role
        tag = node.get("tag", "").lower()
        role = node.get("role", "").lower()
        if tag in keywords or role in keywords:
            return True

        # Check common attributes
        for attr in ["name", "id", "placeholder", "aria-label", "title"]:
            value = str(node.get(attr, "")).lower()
            if any(kw in value for kw in keywords):
                return True

        # Always include interactive elements
        if tag in {"button", "input", "select", "a", "textarea"}:
            return True

        return False

    def _extract_attrs(self, node: dict) -> dict:
        """Extract relevant attributes from node."""
        result = {}
        for key in SEMANTIC_ATTRIBUTES:
            if key in node and key != "children":
                result[key] = node[key]
        if "bid" not in result:
            result["bid"] = node.get("bid", "unknown")
        if "tag" not in result:
            result["tag"] = node.get("tag", "element")
        return result


class ViewportOnlyPreprocessor(BaseStatePreprocessor):
    """
    Preprocessor that filters to elements within viewport bounds.
    """

    def __init__(
        self,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        include_partial: bool = True,
    ):
        super().__init__("viewport_only_preprocessor")
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.include_partial = include_partial

    def preprocess(self, state: dict, context: dict) -> dict:
        """Filter state to viewport-visible elements."""
        result = copy.deepcopy(state)

        if "ui" in result:
            result["ui"] = self._filter_viewport(result["ui"])

        return result

    def _filter_viewport(self, node: dict) -> Optional[dict]:
        """Recursively filter to viewport-visible elements."""
        if not isinstance(node, dict):
            return None

        bounds = node.get("bounds", {})
        in_viewport = self._is_in_viewport(bounds)

        if not in_viewport and not self.include_partial:
            return None

        # Process children
        children = node.get("children", [])
        filtered_children = []
        for child in children:
            filtered = self._filter_viewport(child)
            if filtered is not None:
                filtered_children.append(filtered)

        # Include if in viewport or has visible children
        if in_viewport or filtered_children:
            result = copy.deepcopy(node)
            result.pop("children", None)
            if filtered_children:
                result["children"] = filtered_children
            return result

        return None

    def _is_in_viewport(self, bounds: dict) -> bool:
        """Check if bounds intersect viewport."""
        if not bounds:
            return True  # Assume visible if no bounds

        x = bounds.get("x", 0)
        y = bounds.get("y", 0)
        width = bounds.get("width", 0)
        height = bounds.get("height", 0)

        # Check if element intersects viewport
        return (
            x < self.viewport_width and
            y < self.viewport_height and
            x + width > 0 and
            y + height > 0
        )


# Tags considered interactive
INTERACTIVE_TAGS = {
    "button", "a", "input", "select", "textarea", "option",
    "checkbox", "radio", "switch", "slider", "menuitem",
    "tab", "link",
}


class InteractiveOnlyPreprocessor(BaseStatePreprocessor):
    """
    Preprocessor that filters to interactive elements only.
    """

    def __init__(self, include_disabled: bool = False):
        super().__init__("interactive_only_preprocessor")
        self.include_disabled = include_disabled

    def preprocess(self, state: dict, context: dict) -> dict:
        """Filter state to interactive elements."""
        result = copy.deepcopy(state)

        if "ui" in result:
            result["ui"] = self._filter_interactive(result["ui"])

        return result

    def _filter_interactive(self, node: dict) -> Optional[dict]:
        """Recursively filter to interactive elements."""
        if not isinstance(node, dict):
            return None

        is_interactive = self._is_interactive(node)

        # Skip disabled unless configured to include
        if node.get("disabled") and not self.include_disabled:
            is_interactive = False

        # Process children
        children = node.get("children", [])
        filtered_children = []
        for child in children:
            filtered = self._filter_interactive(child)
            if filtered is not None:
                filtered_children.append(filtered)

        # Include if interactive or has interactive children
        if is_interactive or filtered_children:
            result = self._extract_interactive_attrs(node)
            if filtered_children:
                result["children"] = filtered_children
            return result

        return None

    def _is_interactive(self, node: dict) -> bool:
        """Check if node is interactive."""
        tag = node.get("tag", "").lower()
        role = node.get("role", "").lower()

        # Check tag/role
        if tag in INTERACTIVE_TAGS or role in INTERACTIVE_TAGS:
            return True

        # Check for click handlers
        if node.get("onclick") or node.get("clickable"):
            return True

        # Check role for interactive roles
        interactive_roles = {"button", "link", "menuitem", "tab", "checkbox", "radio"}
        if role in interactive_roles:
            return True

        return False

    def _extract_interactive_attrs(self, node: dict) -> dict:
        """Extract relevant attributes for interactive elements."""
        result = {}

        # Core attributes
        for key in ["bid", "tag", "text", "role"]:
            if key in node:
                result[key] = node[key]

        # Interactive attributes
        for key in ["value", "checked", "selected", "disabled", "href", "placeholder"]:
            if key in node:
                result[key] = node[key]

        if "bid" not in result:
            result["bid"] = node.get("bid", "unknown")
        if "tag" not in result:
            result["tag"] = node.get("tag", "element")

        return result


# =============================================================================
# Module
# =============================================================================

@dataclass
class AbstractionModule(Module):
    """
    Module for abstraction level configuration.

    Provides preprocessors and prompt blocks for the selected level.
    """

    level: AbstractionLevel = AbstractionLevel.FULL_DOM
    include_hidden: bool = False
    include_disabled: bool = False
    viewport_width: int = 1920
    viewport_height: int = 1080

    def __post_init__(self):
        self.name = f"abstraction_{self.level.value}"
        self.description = f"Abstraction level: {self.level.value}"

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected level."""
        blocks = {
            AbstractionLevel.FULL_DOM: FullDOMPromptBlock(),
            AbstractionLevel.SEMANTIC_ELEMENTS: SemanticElementsPromptBlock(),
            AbstractionLevel.TASK_RELEVANT: TaskRelevantPromptBlock(),
            AbstractionLevel.VIEWPORT_ONLY: ViewportOnlyPromptBlock(),
            AbstractionLevel.INTERACTIVE_ONLY: InteractiveOnlyPromptBlock(),
        }
        return [blocks[self.level]]

    def get_preprocessors(self) -> list[StatePreprocessor]:
        """Return preprocessor for selected level."""
        preprocessors = {
            AbstractionLevel.FULL_DOM: FullDOMPreprocessor(),
            AbstractionLevel.SEMANTIC_ELEMENTS: SemanticElementsPreprocessor(
                include_hidden=self.include_hidden
            ),
            AbstractionLevel.TASK_RELEVANT: TaskRelevantPreprocessor(
                include_hidden=self.include_hidden
            ),
            AbstractionLevel.VIEWPORT_ONLY: ViewportOnlyPreprocessor(
                viewport_width=self.viewport_width,
                viewport_height=self.viewport_height,
            ),
            AbstractionLevel.INTERACTIVE_ONLY: InteractiveOnlyPreprocessor(
                include_disabled=self.include_disabled
            ),
        }
        return [preprocessors[self.level]]

    def get_preprocessor(self) -> StatePreprocessor:
        """Get the preprocessor for the current level."""
        return self.get_preprocessors()[0]
