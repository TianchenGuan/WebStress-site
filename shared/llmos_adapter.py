"""
LLMos adapter for the unified agent format.

Converts LLMos observations → indexed tree,
and converts unified actions → LLMos actions.
"""

from .format import TreeNode, render_indexed_tree, INTERACTIVE_ROLES, SEMANTIC_ROLES


# ── LLMos state → TreeNode ───────────────────────────────────────────────


def llmos_state_to_tree(observation: dict) -> TreeNode:
    """
    Convert a filtered LLMos observation (after render_observation) into a TreeNode.

    Expects observation with "ui" key containing the accessibility tree dict.
    """
    ui = observation.get("ui", observation)
    return _convert_node(ui)


def _convert_node(node: dict) -> TreeNode:
    """Recursively convert an LLMos UI dict node to a TreeNode."""
    role = node.get("role") or node.get("tag") or "unknown"
    name = node.get("text", "")
    value = node.get("value")
    if value is not None:
        value = str(value)

    # Detect overlay: dialog/modal windows at high z_index
    is_overlay = (
        role in ("dialog", "alertdialog", "modal")
        or node.get("modal", False)
    )

    tree_node = TreeNode(
        role=role,
        name=name,
        value=value,
        checked=node.get("checked"),
        disabled=node.get("disabled", False),
        focused=node.get("focused", False),
        selected=node.get("selected", False),
        is_overlay=is_overlay,
        source=node.get("bid"),  # Store the bid for action mapping
    )

    for child in node.get("children", []):
        if isinstance(child, dict):
            tree_node.children.append(_convert_node(child))

    return tree_node


# ── Observation → indexed tree ───────────────────────────────────────────


def state_to_indexed_tree(
    observation: dict,
    skip_browser_chrome: bool = False,
) -> tuple[str, dict[int, str], dict[int, "TreeNode"]]:
    """
    Convert a filtered LLMos observation to an indexed accessibility tree.

    Returns (tree_text, ref_to_bid, node_map) where:
      - ref_to_bid[ref] = bid string
      - node_map[ref] = TreeNode (for status message generation)
    """
    root = llmos_state_to_tree(observation)

    if skip_browser_chrome:
        root = _find_page_content(root) or root

    text, node_map = render_indexed_tree(root)

    ref_to_bid: dict[int, str] = {}
    for ref, node in node_map.items():
        ref_to_bid[ref] = node.source  # source is the bid

    return text, ref_to_bid, node_map


def _find_page_content(root: TreeNode) -> TreeNode | None:
    """
    Find the main page content node, skipping browser chrome (toolbar, URL bar).

    WAB templates have structure: root(application) → toolbar + page_content(main).
    Playwright's aria_snapshot only captures body content, so we skip to the main
    node and return a synthetic unindexed wrapper around its children.  This avoids
    the main node itself being indexed as [1] (which would shift all refs by +1
    compared to real-browser observations where no main wrapper exists).
    """
    for child in root.children:
        if child.role == "main":
            # Wrap children in a synthetic root that won't be indexed
            # (role="root" with no name → should_index() returns False)
            wrapper = TreeNode(role="root", children=child.children)
            return wrapper
    return None


# ── Unified action → LLMos action ───────────────────────────────────────

# Mapping from unified action names to LLMos action_type
_ACTION_MAP = {
    "click": "click",
    "dblclick": "dblclick",
    "fill": "fill",
    "select": "select_option",
    "check": "click",      # LLMos toggles checkbox via click
    "uncheck": "click",    # LLMos toggles checkbox via click
    "press": "press",
    "scroll": "scroll",
    "hover": "hover",
    "drag_and_drop": "drag_and_drop",
    "wait": "noop",
    "finish": "finish",
}


def unified_action_to_llmos(action: dict, ref_to_bid: dict[int, str]) -> dict:
    """
    Convert a unified action dict to an LLMos action dict.

    Args:
        action: Unified action, e.g. {"action": "fill", "ref": 3, "value": "hello"}
        ref_to_bid: Mapping from ref numbers to LLMos bids.

    Returns:
        LLMos action, e.g. {"action_type": "fill", "bid": "email_input", "text": "hello"}
    """
    action_name = action["action"]
    llmos_type = _ACTION_MAP[action_name]

    if action_name == "finish":
        return {
            "action_type": "finish",
            "success": True,
            "text": action.get("answer", ""),
        }

    if action_name == "wait":
        return {"action_type": "noop"}

    if action_name == "drag_and_drop":
        return {
            "action_type": "drag_and_drop",
            "from_bid": ref_to_bid[action["from_ref"]],
            "to_bid": ref_to_bid[action["to_ref"]],
        }

    if action_name == "press":
        ref = action.get("ref")
        if ref:
            return {
                "action_type": "press",
                "bid": ref_to_bid[ref],
                "key": action["key"],
            }
        return {
            "action_type": "keyboard_press",
            "key": action["key"],
        }

    if action_name == "scroll":
        ref = action.get("ref")
        result = {
            "action_type": "scroll",
            "direction": action.get("direction", "down"),
        }
        if ref:
            result["bid"] = ref_to_bid[ref]
        return result

    # Standard ref-based actions
    ref = action["ref"]
    bid = ref_to_bid[ref]
    result = {"action_type": llmos_type, "bid": bid}

    if action_name == "fill":
        result["text"] = action["value"]
    elif action_name == "select":
        result["options"] = [action["value"]]

    return result
