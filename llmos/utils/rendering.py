"""
Deterministic Rendering for LLMOS.
Filters the "God View" state to create agent-safe observations.

The agent should only see what a real user would see on screen:
- Hidden elements are not visible
- Minimized windows and their contents are not visible
- Elements outside the viewport are not visible
- Elements fully occluded by other windows are not visible
- Filesystem entries are only visible if displayed in an open file explorer
"""

import copy
import logging
from typing import Optional

from .occlusion import compute_occlusion_precise, filter_occluded_nodes

logger = logging.getLogger(__name__)

# Maximum content length before truncation
MAX_CONTENT_LENGTH = 1000
TRUNCATION_SUFFIX = "... [truncated]"

# Default viewport/screen dimensions
DEFAULT_VIEWPORT = {"x": 0, "y": 0, "width": 1920, "height": 1080}


def render_observation(
    state: dict,
    include_meta: bool = True,
    apply_occlusion: bool = True,
    filter_filesystem_by_display: bool = True,
    viewport: Optional[dict] = None,
) -> dict:
    """
    Render an observation from the full state by filtering to only show
    what would be visible on a real screen.

    Filtering rules (agent only sees what's on screen):
    1. hidden_state is never visible (internal simulator data)
    2. Elements with visible=false are not shown
    3. Elements in minimized windows are not shown
    4. Elements outside viewport bounds are not shown
    5. Elements fully occluded by higher z_index elements are not shown
    6. Filesystem entries only shown if displayed in open file explorer window
    7. File contents are truncated for long files

    Args:
        state: The full state object (with hidden_state).
        include_meta: Whether to include meta information.
        apply_occlusion: Whether to filter occluded elements based on z_index.
        filter_filesystem_by_display: If True, only show filesystem entries that are
            visible in an open file explorer window.
        viewport: Screen viewport bounds. Elements outside are filtered.

    Returns:
        A filtered observation showing only what's visible on screen.
    """
    if viewport is None:
        viewport = DEFAULT_VIEWPORT

    # Deep copy to avoid modifying original
    obs = copy.deepcopy(state)

    # 1. Remove hidden_state completely (never visible to agent)
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

    # 3. Get displayed paths from UI (before filtering UI)
    displayed_paths = None
    if filter_filesystem_by_display and "ui" in obs:
        displayed_paths = _get_displayed_paths(obs["ui"])

    # 4. Filter filesystem (only show files visible in open windows)
    if "filesystem" in obs:
        obs["filesystem"] = _filter_filesystem(obs["filesystem"], displayed_paths)

    # 5. Filter UI tree comprehensively:
    #    - Remove nodes with visible=false
    #    - Remove contents of minimized windows
    #    - Remove elements outside viewport
    if "ui" in obs:
        obs["ui"] = _filter_ui_tree_comprehensive(obs["ui"], viewport)

    # 6. Apply occlusion filtering (remove fully occluded, mark partially occluded)
    if apply_occlusion and "ui" in obs and obs["ui"] is not None:
        occlusion_map = compute_occlusion_precise(obs["ui"])
        obs["ui"] = filter_occluded_nodes(obs["ui"], occlusion_map)

    return obs


def _filter_filesystem(filesystem: dict, displayed_paths: Optional[set] = None) -> dict:
    """
    Filter filesystem entries based on visibility and what's currently displayed.

    - Removes files with visible: false
    - If displayed_paths is provided, only show files under those paths
    - Truncates long file contents

    Args:
        filesystem: The filesystem dict.
        displayed_paths: Optional set of directory paths currently shown in open windows.
                        If None, shows all visible files. If empty set, shows nothing.

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

        # If displayed_paths is specified, only show files under those paths
        if displayed_paths is not None:
            is_displayed = False
            for displayed_dir in displayed_paths:
                if path == displayed_dir or path.startswith(displayed_dir.rstrip('/') + '/'):
                    is_displayed = True
                    break
            if not is_displayed:
                continue

        # Copy and truncate content if needed
        filtered_entry = copy.copy(entry)

        if "content" in filtered_entry:
            content = filtered_entry["content"]
            if isinstance(content, str) and len(content) > MAX_CONTENT_LENGTH:
                filtered_entry["content"] = content[:MAX_CONTENT_LENGTH] + TRUNCATION_SUFFIX

        filtered[path] = filtered_entry

    return filtered


def _get_displayed_paths(ui: dict) -> set:
    """
    Extract paths currently displayed in open file explorer windows.

    Looks for windows with role='window' that have an address bar or
    current_path property indicating what directory is being displayed.

    Args:
        ui: The UI tree.

    Returns:
        Set of directory paths currently visible in file explorer windows.
    """
    displayed = set()
    _collect_displayed_paths(ui, displayed)
    return displayed


def _collect_displayed_paths(node: dict, paths: set) -> None:
    """Recursively collect displayed paths from UI tree."""
    if not isinstance(node, dict):
        return

    # Check if this node represents a file explorer with a current path
    if node.get("role") == "window" or node.get("tag") == "window":
        # Look for current_path property
        current_path = node.get("current_path")
        if current_path:
            paths.add(current_path)

        # Also check address bar value
        for child in node.get("children", []):
            if isinstance(child, dict):
                if child.get("role") in ("address_bar", "textbox", "location"):
                    value = child.get("value", "")
                    if value and value.startswith("/"):
                        paths.add(value)

    # Recurse into children
    for child in node.get("children", []):
        _collect_displayed_paths(child, paths)


def _filter_ui_tree(node: dict) -> Optional[dict]:
    """
    Recursively filter the UI tree (basic version).

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


def _filter_ui_tree_comprehensive(
    node: dict,
    viewport: dict,
    parent_visible: bool = True,
    parent_minimized: bool = False,
) -> Optional[dict]:
    """
    Comprehensively filter UI tree to show only what's visible on screen.

    Filters out:
    - Nodes with visible=false
    - Contents of minimized windows (window with state="minimized")
    - Elements completely outside viewport bounds
    - Elements in collapsed containers (collapsed=true)

    Args:
        node: A UI tree node.
        viewport: Screen viewport bounds {x, y, width, height}.
        parent_visible: Whether parent is visible (inherited).
        parent_minimized: Whether any ancestor window is minimized.

    Returns:
        Filtered node or None if node should be hidden.
    """
    if not isinstance(node, dict):
        return node

    # Check explicit visibility flag
    if not node.get("visible", True):
        return None

    # Check if this is a minimized window
    is_minimized = (
        node.get("state") == "minimized" or
        node.get("minimized", False) or
        parent_minimized
    )

    # Check if this is a collapsed container
    is_collapsed = node.get("collapsed", False)

    # Check if element is within viewport
    bounds = node.get("bounds")
    if bounds and not _is_within_viewport(bounds, viewport):
        # Element is completely outside viewport - not visible
        # But keep windows even if partially outside (they might have visible parts)
        if node.get("role") != "window" and node.get("tag") != "window":
            return None

    # If window is minimized, only show the window itself (in taskbar),
    # not its contents
    if is_minimized and node.get("role") not in ("window", "application"):
        # This is content inside a minimized window - hide it
        if parent_minimized:
            return None

    # Copy node properties (except children)
    filtered = {}
    for key, value in node.items():
        if key != "children":
            filtered[key] = value

    # Process children
    children = node.get("children", [])
    if isinstance(children, list) and children:
        # If this window is minimized, don't show its children
        if is_minimized and (node.get("role") == "window" or node.get("tag") == "window"):
            # Window is minimized - children not visible on screen
            # Just show the window exists (appears in taskbar) but no contents
            pass
        # If this container is collapsed, don't show children
        elif is_collapsed:
            pass
        else:
            filtered_children = []
            for child in children:
                filtered_child = _filter_ui_tree_comprehensive(
                    child,
                    viewport,
                    parent_visible=True,
                    parent_minimized=is_minimized,
                )
                if filtered_child is not None:
                    filtered_children.append(filtered_child)
            if filtered_children:
                filtered["children"] = filtered_children

    return filtered


def _is_within_viewport(bounds: dict, viewport: dict) -> bool:
    """
    Check if element bounds are at least partially within viewport.

    Args:
        bounds: Element bounds {x, y, width, height}.
        viewport: Viewport bounds {x, y, width, height}.

    Returns:
        True if element is at least partially visible in viewport.
    """
    if not bounds or not viewport:
        return True  # Assume visible if no bounds info

    elem_left = bounds.get("x", 0)
    elem_top = bounds.get("y", 0)
    elem_right = elem_left + bounds.get("width", 0)
    elem_bottom = elem_top + bounds.get("height", 0)

    vp_left = viewport.get("x", 0)
    vp_top = viewport.get("y", 0)
    vp_right = vp_left + viewport.get("width", 1920)
    vp_bottom = vp_top + viewport.get("height", 1080)

    # Check if there's any overlap
    return not (
        elem_right < vp_left or   # Element is left of viewport
        elem_left > vp_right or   # Element is right of viewport
        elem_bottom < vp_top or   # Element is above viewport
        elem_top > vp_bottom      # Element is below viewport
    )


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
