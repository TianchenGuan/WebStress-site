"""
Abstraction Module: Level of detail in state representation.

Modes:
- FULL_DOM: Complete UI tree with all attributes
- SEMANTIC_ELEMENTS: Only semantic elements (buttons, inputs, text, etc.)

Each mode provides:
1. State preprocessor to filter/transform state
2. Prompt block explaining the abstraction level
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
import copy

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


class FullDOMPromptBlock(BasePromptBlock):
    """Prompt block for full DOM abstraction."""

    def __init__(self):
        super().__init__("full_dom_abstraction", FULL_DOM_PROMPT)


class SemanticElementsPromptBlock(BasePromptBlock):
    """Prompt block for semantic elements abstraction."""

    def __init__(self):
        super().__init__("semantic_elements_abstraction", SEMANTIC_ELEMENTS_PROMPT)


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

    def __post_init__(self):
        self.name = f"abstraction_{self.level.value}"
        self.description = f"Abstraction level: {self.level.value}"

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected level."""
        blocks = {
            AbstractionLevel.FULL_DOM: FullDOMPromptBlock(),
            AbstractionLevel.SEMANTIC_ELEMENTS: SemanticElementsPromptBlock(),
        }
        return [blocks[self.level]]

    def get_preprocessors(self) -> list[StatePreprocessor]:
        """Return preprocessor for selected level."""
        preprocessors = {
            AbstractionLevel.FULL_DOM: FullDOMPreprocessor(),
            AbstractionLevel.SEMANTIC_ELEMENTS: SemanticElementsPreprocessor(
                include_hidden=self.include_hidden
            ),
        }
        return [preprocessors[self.level]]

    def get_preprocessor(self) -> StatePreprocessor:
        """Get the preprocessor for the current level."""
        return self.get_preprocessors()[0]
