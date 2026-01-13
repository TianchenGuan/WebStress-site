"""
Deterministic Rendering for LLMOS.
Filters the "God View" state to create agent-safe observations.
"""

import copy
import logging
from typing import Optional

from .occlusion import compute_occlusion_precise, filter_occluded_nodes

logger = logging.getLogger(__name__)

# Maximum content length before truncation
MAX_CONTENT_LENGTH = 1000
TRUNCATION_SUFFIX = "... [truncated]"


def render_observation(
    state: dict,
    include_meta: bool = True,
    apply_occlusion: bool = True,
) -> dict:
    """
    Render an observation from the full state by filtering sensitive data.

    This function:
    1. Removes hidden_state entirely
    2. Removes meta.random_seed
    3. Hides files marked visible: false
    4. Truncates long file contents
    5. Filters out fully occluded UI elements (based on z_index and bounds)
    6. Marks partially occluded elements with invisible_area

    Args:
        state: The full state object (with hidden_state).
        include_meta: Whether to include meta information.
        apply_occlusion: Whether to filter occluded elements based on z_index.

    Returns:
        A filtered observation safe for the agent.
    """
    # Deep copy to avoid modifying original
    obs = copy.deepcopy(state)

    # 1. Remove hidden_state completely
    if "hidden_state" in obs:
        del obs["hidden_state"]

    # 2. Filter meta
    if "meta" in obs:
        if not include_meta:
            del obs["meta"]
        else:
            # Remove random_seed from meta
            if "random_seed" in obs["meta"]:
                del obs["meta"]["random_seed"]

    # 3. Filter filesystem
    if "filesystem" in obs:
        obs["filesystem"] = _filter_filesystem(obs["filesystem"])

    # 4. Filter UI tree (remove any nodes marked not visible)
    if "ui" in obs:
        obs["ui"] = _filter_ui_tree(obs["ui"])

    # 5. Apply occlusion filtering (remove fully occluded, mark partially occluded)
    if apply_occlusion and "ui" in obs and obs["ui"] is not None:
        occlusion_map = compute_occlusion_precise(obs["ui"])
        obs["ui"] = filter_occluded_nodes(obs["ui"], occlusion_map)

    return obs


def _filter_filesystem(filesystem: dict) -> dict:
    """
    Filter filesystem entries.

    - Removes files with visible: false
    - Truncates long file contents

    Args:
        filesystem: The filesystem dict.

    Returns:
        Filtered filesystem dict.
    """
    filtered = {}

    for path, entry in filesystem.items():
        if not isinstance(entry, dict):
            continue

        # Skip hidden files
        if not entry.get("visible", True):
            continue

        # Copy and truncate content if needed
        filtered_entry = copy.copy(entry)

        if "content" in filtered_entry:
            content = filtered_entry["content"]
            if isinstance(content, str) and len(content) > MAX_CONTENT_LENGTH:
                filtered_entry["content"] = content[:MAX_CONTENT_LENGTH] + TRUNCATION_SUFFIX

        filtered[path] = filtered_entry

    return filtered


def _filter_ui_tree(node: dict) -> Optional[dict]:
    """
    Recursively filter the UI tree.

    - Removes nodes with visible: false
    - Preserves tree structure otherwise

    Args:
        node: A UI tree node.

    Returns:
        Filtered node or None if node should be hidden.
    """
    if not isinstance(node, dict):
        return node

    # Check if node is visible
    if not node.get("visible", True):
        return None

    # Copy node
    filtered = {}
    for key, value in node.items():
        if key == "children":
            # Recursively filter children
            if isinstance(value, list):
                filtered_children = []
                for child in value:
                    filtered_child = _filter_ui_tree(child)
                    if filtered_child is not None:
                        filtered_children.append(filtered_child)
                if filtered_children:
                    filtered["children"] = filtered_children
        else:
            filtered[key] = value

    return filtered


def render_ui_as_text(state: dict, indent: int = 0) -> str:
    """
    Render the UI tree as indented text (accessibility tree format).

    Useful for text-based agents that prefer a linearized representation.

    Args:
        state: The state object (or just the UI portion).
        indent: Current indentation level.

    Returns:
        Text representation of the UI tree.
    """
    ui = state.get("ui", state) if "ui" in state else state

    return _render_node_as_text(ui, indent)


def _render_node_as_text(node: dict, indent: int = 0) -> str:
    """
    Recursively render a node as text.

    Args:
        node: A UI tree node.
        indent: Current indentation level.

    Returns:
        Text representation.
    """
    if not isinstance(node, dict):
        return ""

    lines = []
    prefix = "  " * indent

    # Build node description
    bid = node.get("bid", "?")
    tag = node.get("tag", "unknown")
    role = node.get("role", "")
    text = node.get("text", "")
    value = node.get("value", "")

    # Build attribute string
    attrs = []
    if role:
        attrs.append(f"role={role}")
    if text:
        # Truncate long text
        display_text = text[:50] + "..." if len(text) > 50 else text
        attrs.append(f'text="{display_text}"')
    if value:
        attrs.append(f'value="{value}"')
    if node.get("focused"):
        attrs.append("focused")
    if node.get("checked"):
        attrs.append("checked")
    if node.get("disabled"):
        attrs.append("disabled")

    attr_str = " " + " ".join(attrs) if attrs else ""

    lines.append(f"{prefix}[{bid}] {tag}{attr_str}")

    # Render children
    children = node.get("children", [])
    for child in children:
        lines.append(_render_node_as_text(child, indent + 1))

    return "\n".join(lines)


def summarize_state(state: dict) -> dict:
    """
    Create a compact summary of the state for logging/debugging.

    Args:
        state: The full or filtered state.

    Returns:
        A compact summary dict.
    """
    summary = {
        "tick": state.get("meta", {}).get("tick", 0),
        "status": state.get("meta", {}).get("status", "unknown"),
    }

    # Count UI elements
    if "ui" in state:
        summary["ui_elements"] = _count_nodes(state["ui"])

    # Count files
    if "filesystem" in state:
        summary["files"] = len(state["filesystem"])

    # Count tabs
    if "tabs" in state:
        summary["tabs"] = len(state["tabs"])
        active_tab = next((t for t in state["tabs"] if t.get("active")), None)
        if active_tab:
            summary["active_url"] = active_tab.get("url", "")

    return summary


def _count_nodes(node: dict) -> int:
    """Count total nodes in a UI tree."""
    if not isinstance(node, dict):
        return 0

    count = 1
    for child in node.get("children", []):
        count += _count_nodes(child)

    return count


def extract_focusable_elements(state: dict) -> list[dict]:
    """
    Extract all focusable/interactive elements from the UI tree.

    Useful for agents to understand available actions.

    Args:
        state: The state object.

    Returns:
        List of interactive element summaries.
    """
    ui = state.get("ui", {})
    elements = []
    _collect_interactive(ui, elements)
    return elements


def _collect_interactive(node: dict, elements: list):
    """Recursively collect interactive elements."""
    if not isinstance(node, dict):
        return

    # Check if interactive
    tag = node.get("tag", "").lower()
    role = node.get("role", "").lower()

    interactive_tags = {"button", "input", "select", "textarea", "a", "link", "checkbox", "radio"}
    interactive_roles = {"button", "link", "textbox", "checkbox", "radio", "combobox", "menuitem"}

    if tag in interactive_tags or role in interactive_roles:
        text = node.get("text", "")
        # Truncate with indicator if text is too long
        max_text_len = 50
        if len(text) > max_text_len:
            text = text[:max_text_len] + "..."
        elements.append({
            "bid": node.get("bid"),
            "tag": tag,
            "role": role,
            "text": text,
            "value": node.get("value"),
            "disabled": node.get("disabled", False),
        })

    # Recurse
    for child in node.get("children", []):
        _collect_interactive(child, elements)
