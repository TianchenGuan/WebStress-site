"""
Deterministic rendering for LLMOS.
Filters the "God View" state to create agent-safe observations.

The agent should only see what a real user would see on screen:
- Hidden elements are not visible
- Minimized windows and their contents are not visible
- Filesystem entries are only visible if displayed in an open file explorer
"""

import copy
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 1000
TRUNCATION_SUFFIX = "... [truncated]"


def render_observation(
    state: dict,
    include_meta: bool = True,
) -> dict:
    """
    Render an observation from the full state by filtering to only show
    what would be visible on a real screen.

    Filtering rules:
    1. hidden_state is never visible
    2. Elements with visible=false are not shown
    3. Elements in minimized windows are not shown
    4. Filesystem entries only shown if displayed in open file explorer

    Returns:
        Filtered observation for the agent.
    """
    obs = copy.deepcopy(state)

    # 1. Remove hidden_state
    obs.pop("hidden_state", None)

    # 2. Filter meta
    if "meta" in obs:
        if not include_meta:
            del obs["meta"]
        else:
            obs["meta"].pop("random_seed", None)

    # 3. Get displayed paths from UI (before filtering)
    displayed_paths = _get_displayed_paths(obs.get("ui", {}))

    # 4. Filter filesystem
    if "filesystem" in obs:
        obs["filesystem"] = _filter_filesystem(obs["filesystem"], displayed_paths)

    # 5. Filter UI tree
    if "ui" in obs:
        obs["ui"] = _filter_ui_tree(obs["ui"])

    return obs


def _filter_filesystem(filesystem: dict, displayed_paths: Optional[set] = None) -> dict:
    """Filter filesystem to only show visible, displayed entries."""
    filtered = {}
    for path, entry in filesystem.items():
        if not isinstance(entry, dict):
            continue
        if not entry.get("visible", True):
            continue
        if displayed_paths is not None:
            if not any(path == d or path.startswith(d.rstrip('/') + '/') for d in displayed_paths):
                continue
        filtered_entry = copy.copy(entry)
        content = filtered_entry.get("content", "")
        if isinstance(content, str) and len(content) > MAX_CONTENT_LENGTH:
            filtered_entry["content"] = content[:MAX_CONTENT_LENGTH] + TRUNCATION_SUFFIX
        filtered[path] = filtered_entry
    return filtered


def _get_displayed_paths(ui: dict) -> set:
    """Extract paths currently displayed in open file explorer windows."""
    displayed = set()
    _collect_displayed_paths(ui, displayed)
    return displayed


def _collect_displayed_paths(node: dict, paths: set) -> None:
    """Recursively collect displayed paths from UI tree."""
    if not isinstance(node, dict):
        return
    if node.get("role") == "window" or node.get("tag") == "window":
        current_path = node.get("current_path")
        if current_path:
            paths.add(current_path)
        for child in node.get("children", []):
            if isinstance(child, dict) and child.get("role") in ("address_bar", "textbox", "location"):
                value = child.get("value", "")
                if value and value.startswith("/"):
                    paths.add(value)
    for child in node.get("children", []):
        _collect_displayed_paths(child, paths)


def _filter_ui_tree(
    node: dict,
    parent_minimized: bool = False,
) -> Optional[dict]:
    """
    Filter UI tree to show only visible elements.

    Removes:
    - Nodes with visible=false
    - Contents of minimized windows
    - Collapsed containers
    """
    if not isinstance(node, dict):
        return node

    if not node.get("visible", True):
        return None

    is_minimized = (
        node.get("state") == "minimized"
        or node.get("minimized", False)
        or parent_minimized
    )

    is_collapsed = node.get("collapsed", False)

    if is_minimized and node.get("role") not in ("window", "application"):
        if parent_minimized:
            return None

    # Copy node without children
    filtered = {k: v for k, v in node.items() if k != "children"}

    children = node.get("children", [])
    if isinstance(children, list) and children:
        is_window = node.get("role") == "window" or node.get("tag") == "window"
        if (is_minimized and is_window) or is_collapsed:
            pass  # Don't show children
        else:
            filtered_children = []
            for child in children:
                fc = _filter_ui_tree(child, parent_minimized=is_minimized)
                if fc is not None:
                    filtered_children.append(fc)
            if filtered_children:
                filtered["children"] = filtered_children

    return filtered


def render_ui_as_text(state: dict, indent: int = 0) -> str:
    """Render UI tree as indented text (for judge/debugging)."""
    ui = state.get("ui", state) if "ui" in state else state
    return _render_node_text(ui, indent)


def _render_node_text(node: dict, indent: int = 0) -> str:
    if not isinstance(node, dict):
        return ""
    lines = []
    prefix = "  " * indent
    bid = node.get("bid", "?")
    tag = node.get("tag", "unknown")
    role = node.get("role", "")
    text = node.get("text", "")

    attrs = []
    if role:
        attrs.append(f"role={role}")
    if text:
        display = text[:50] + "..." if len(text) > 50 else text
        attrs.append(f'text="{display}"')
    if node.get("value"):
        attrs.append(f'value="{node["value"]}"')
    if node.get("focused"):
        attrs.append("focused")
    if node.get("checked"):
        attrs.append("checked")
    if node.get("disabled"):
        attrs.append("disabled")

    attr_str = " " + " ".join(attrs) if attrs else ""
    lines.append(f"{prefix}[{bid}] {tag}{attr_str}")

    for child in node.get("children", []):
        lines.append(_render_node_text(child, indent + 1))
    return "\n".join(lines)


def summarize_state(state: dict) -> dict:
    """Create a compact summary of state for logging."""
    summary = {
        "tick": state.get("meta", {}).get("tick", 0),
        "status": state.get("meta", {}).get("status", "unknown"),
    }
    if "ui" in state:
        summary["ui_elements"] = _count_nodes(state["ui"])
    if "filesystem" in state:
        summary["files"] = len(state["filesystem"])
    if "tabs" in state:
        summary["tabs"] = len(state["tabs"])
    return summary


def _count_nodes(node: dict) -> int:
    if not isinstance(node, dict):
        return 0
    return 1 + sum(_count_nodes(c) for c in node.get("children", []))
