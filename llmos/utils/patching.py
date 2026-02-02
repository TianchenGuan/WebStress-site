"""
ID-Based Tree Patching for LLMOS.
Handles state modifications using bid-targeted operations.
"""

import copy
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PatchError(Exception):
    """Exception raised for patching errors."""
    pass


def find_node_by_bid(tree: dict, bid: Any) -> Optional[dict]:
    """
    Recursively find a node in the tree by its bid.

    Args:
        tree: The tree/subtree to search.
        bid: The bid to find.

    Returns:
        The node dict if found, None otherwise.
    """
    if not isinstance(tree, dict):
        return None

    # Check if this node has the target bid
    if tree.get("bid") == bid:
        return tree

    # Search in children
    children = tree.get("children", [])
    if isinstance(children, list):
        for child in children:
            result = find_node_by_bid(child, bid)
            if result is not None:
                return result

    return None


def bid_exists(tree: dict, bid: Any) -> bool:
    """
    Check if a bid already exists in the tree.

    Args:
        tree: The tree/subtree to search.
        bid: The bid to check.

    Returns:
        True if bid exists, False otherwise.
    """
    return find_node_by_bid(tree, bid) is not None


def find_parent_of_bid(tree: dict, bid: Any, parent: Optional[dict] = None) -> Optional[tuple[dict, int]]:
    """
    Find the parent node and index of a node with the given bid.

    Args:
        tree: The tree/subtree to search.
        bid: The bid to find.
        parent: The parent of the current tree (for recursion).

    Returns:
        Tuple of (parent_node, child_index) if found, None otherwise.
    """
    if not isinstance(tree, dict):
        return None

    children = tree.get("children", [])
    if isinstance(children, list):
        for i, child in enumerate(children):
            if isinstance(child, dict) and child.get("bid") == bid:
                return (tree, i)
            # Recurse into child
            result = find_parent_of_bid(child, bid, tree)
            if result is not None:
                return result

    return None


def apply_update(state: dict, bid: Any, props: dict) -> bool:
    """
    Update properties of a node identified by bid.

    Args:
        state: The full state object.
        bid: The bid of the node to update.
        props: Dictionary of properties to update.

    Returns:
        True if update was successful, False otherwise.
    """
    # Search in UI tree
    node = find_node_by_bid(state.get("ui", {}), bid)

    if node is None:
        logger.warning(f"Node with bid {bid} not found for update")
        return False

    # Apply property updates
    for key, value in props.items():
        node[key] = value

    logger.debug(f"Updated node {bid} with props: {props}")
    return True


def apply_delete(state: dict, bid: Any) -> bool:
    """
    Delete a node identified by bid.

    Args:
        state: The full state object.
        bid: The bid of the node to delete.

    Returns:
        True if deletion was successful, False otherwise.
    """
    # Find parent and index
    result = find_parent_of_bid(state.get("ui", {}), bid)

    if result is None:
        logger.warning(f"Node with bid {bid} not found for deletion")
        return False

    parent, index = result
    del parent["children"][index]

    logger.debug(f"Deleted node {bid}")
    return True


def apply_append(state: dict, parent_bid: Any, node: dict) -> bool:
    """
    Append a new node as a child of the node identified by parent_bid.

    Args:
        state: The full state object.
        parent_bid: The bid of the parent node.
        node: The new node to append.

    Returns:
        True if append was successful, False otherwise.
    """
    ui_tree = state.get("ui", {})
    parent = find_node_by_bid(ui_tree, parent_bid)

    if parent is None:
        logger.warning(f"Parent node with bid {parent_bid} not found for append")
        return False

    # Check for duplicate bid
    new_bid = node.get("bid")
    if new_bid is not None and bid_exists(ui_tree, new_bid):
        logger.warning(f"Duplicate bid {new_bid} detected during append - this may cause unpredictable behavior")

    # Ensure children list exists
    if "children" not in parent:
        parent["children"] = []

    parent["children"].append(node)

    logger.debug(f"Appended new node with bid {node.get('bid')} to parent {parent_bid}")
    return True


def apply_insert(state: dict, parent_bid: Any, index: int, node: dict) -> bool:
    """
    Insert a new node at a specific index under the parent.

    Args:
        state: The full state object.
        parent_bid: The bid of the parent node.
        index: The index at which to insert.
        node: The new node to insert.

    Returns:
        True if insert was successful, False otherwise.
    """
    ui_tree = state.get("ui", {})
    parent = find_node_by_bid(ui_tree, parent_bid)

    if parent is None:
        logger.warning(f"Parent node with bid {parent_bid} not found for insert")
        return False

    # Check for duplicate bid
    new_bid = node.get("bid")
    if new_bid is not None and bid_exists(ui_tree, new_bid):
        logger.warning(f"Duplicate bid {new_bid} detected during insert - this may cause unpredictable behavior")

    # Ensure children list exists
    if "children" not in parent:
        parent["children"] = []

    # Clamp index to valid range
    index = max(0, min(index, len(parent["children"])))
    parent["children"].insert(index, node)

    logger.debug(f"Inserted new node with bid {node.get('bid')} at index {index} under parent {parent_bid}")
    return True


def apply_hidden_update(state: dict, key: str, value: Any) -> bool:
    """
    Update a key in the hidden_state.

    Args:
        state: The full state object.
        key: The key in hidden_state to update.
        value: The new value.

    Returns:
        True (always succeeds).
    """
    if "hidden_state" not in state:
        state["hidden_state"] = {}

    state["hidden_state"][key] = value

    logger.debug(f"Updated hidden_state[{key}]")
    return True


def apply_meta_update(state: dict, key: str, value: Any) -> bool:
    """
    Update a key in the meta state.

    Args:
        state: The full state object.
        key: The key in meta to update.
        value: The new value.

    Returns:
        True (always succeeds).
    """
    if "meta" not in state:
        state["meta"] = {}

    state["meta"][key] = value

    logger.debug(f"Updated meta[{key}]")
    return True


def apply_filesystem_update(state: dict, path: str, props: dict) -> bool:
    """
    Update a file in the filesystem.

    Args:
        state: The full state object.
        path: The file path.
        props: Properties to update (content, visible, etc.).

    Returns:
        True if update was successful.
    """
    if "filesystem" not in state:
        state["filesystem"] = {}

    if path not in state["filesystem"]:
        state["filesystem"][path] = {"type": "file", "visible": True}

    state["filesystem"][path].update(props)

    logger.debug(f"Updated filesystem[{path}]")
    return True


def apply_id_patch(state: dict, state_ops: list[dict]) -> dict:
    """
    Apply a list of ID-based operations to the state.

    This is the main entry point for patching. It modifies the state in-place
    and returns it.

    Supported operations:
    - update: {"op": "update", "bid": <id>, "props": {...}}
    - delete: {"op": "delete", "bid": <id>}
    - append: {"op": "append", "parent_bid": <id>, "node": {...}}
    - insert: {"op": "insert", "parent_bid": <id>, "index": <n>, "node": {...}}
    - hidden_update: {"op": "hidden_update", "key": <key>, "value": <value>}
    - meta_update: {"op": "meta_update", "key": <key>, "value": <value>}
    - filesystem_update: {"op": "filesystem_update", "path": <path>, "props": {...}}

    Args:
        state: The full state object to modify.
        state_ops: List of operation dictionaries.

    Returns:
        The modified state (same object, modified in-place).
    """
    for op in state_ops:
        if not isinstance(op, dict):
            raise TypeError(f"Operation must be dict, got: {type(op)}")

        op_type = op.get("op")

        if op_type == "update":
            apply_update(state, op["bid"], op["props"])
        elif op_type == "delete":
            apply_delete(state, op["bid"])
        elif op_type == "append":
            apply_append(state, op["parent_bid"], op["node"])
        elif op_type == "insert":
            apply_insert(state, op["parent_bid"], op["index"], op["node"])
        elif op_type == "hidden_update":
            apply_hidden_update(state, op["key"], op["value"])
        elif op_type == "meta_update":
            apply_meta_update(state, op["key"], op["value"])
        elif op_type == "filesystem_update":
            apply_filesystem_update(state, op["path"], op["props"])
        else:
            raise ValueError(f"Unknown operation type: {op_type}")

    return state


def apply_id_patch_safe(state: dict, state_ops: list[dict]) -> dict:
    """
    Apply patches to a copy of the state (non-destructive).

    Args:
        state: The original state object.
        state_ops: List of operation dictionaries.

    Returns:
        A new state object with patches applied.
    """
    state_copy = copy.deepcopy(state)
    return apply_id_patch(state_copy, state_ops)


def _check_node_visibility(node: dict, path: str = "") -> list[str]:
    """
    Recursively check that all nodes have explicit 'visible' property.

    Args:
        node: The node to check.
        path: Path string for error messages.

    Returns:
        List of warning messages.
    """
    warnings = []
    bid = node.get("bid", "unknown")
    node_path = f"{path}/{bid}" if path else bid

    # Check if this node has visible property
    if "visible" not in node:
        warnings.append(f"Node '{node_path}' missing 'visible' property")

    # Check children recursively
    for child in node.get("children", []):
        if isinstance(child, dict):
            warnings.extend(_check_node_visibility(child, node_path))

    return warnings


def validate_ops(state_ops: list[dict]) -> list[str]:
    """
    Validate a list of operations for correctness.

    Args:
        state_ops: List of operation dictionaries.

    Returns:
        List of error messages (empty if valid).
    """
    errors = []

    required_fields = {
        "update": ["bid", "props"],
        "delete": ["bid"],
        "append": ["parent_bid", "node"],
        "insert": ["parent_bid", "index", "node"],
        "hidden_update": ["key", "value"],
        "meta_update": ["key", "value"],
        "filesystem_update": ["path", "props"],
    }

    for i, op in enumerate(state_ops):
        if not isinstance(op, dict):
            errors.append(f"Operation {i}: not a dictionary")
            continue

        op_type = op.get("op")
        if op_type is None:
            errors.append(f"Operation {i}: missing 'op' field")
            continue

        if op_type not in required_fields:
            errors.append(f"Operation {i}: unknown op type '{op_type}'")
            continue

        for field in required_fields[op_type]:
            if field not in op:
                errors.append(f"Operation {i} ({op_type}): missing required field '{field}'")

        # Check for missing 'visible' property on new nodes
        if op_type in ("append", "insert") and "node" in op:
            node = op["node"]
            if isinstance(node, dict):
                visibility_warnings = _check_node_visibility(node)
                for warning in visibility_warnings:
                    logger.warning(f"Operation {i} ({op_type}): {warning}")

    return errors
