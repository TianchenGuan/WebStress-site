"""
Unified agent format for web agent training and evaluation.

Defines the shared observation format (indexed accessibility tree),
action space, system prompt, and message builders.
"""

from dataclasses import dataclass, field
from typing import Any
import json
import re


SCROLL_HINT_TEXT = "[-- viewport continues below --]"

# ── Tree Node ────────────────────────────────────────────────────────────


@dataclass
class TreeNode:
    """A node in the indexed accessibility tree."""

    role: str
    name: str = ""
    value: str | None = None
    checked: bool | None = None
    disabled: bool = False
    focused: bool = False
    selected: bool = False
    is_overlay: bool = False
    has_more_below: bool = False
    children: list["TreeNode"] = field(default_factory=list)
    source: Any = None  # Adapter-specific (bid for LLMos, LocatorInfo for Playwright)


# ── Roles ────────────────────────────────────────────────────────────────

INTERACTIVE_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "menuitem", "tab", "switch", "slider", "spinbutton", "searchbox",
    "option", "menuitemcheckbox", "menuitemradio", "treeitem",
}

SEMANTIC_ROLES = {
    "heading", "img", "alert", "dialog", "status", "banner",
    "navigation", "main", "complementary", "contentinfo",
    "form", "table", "cell", "row", "columnheader", "rowheader",
    "list", "listitem", "paragraph", "blockquote", "code",
    "region", "article", "figure", "separator",
}


def should_index(node: TreeNode) -> bool:
    """Decide whether a node gets a [ref] number in the rendered tree."""
    if node.role in INTERACTIVE_ROLES:
        return True
    if node.role in SEMANTIC_ROLES and node.name:
        return True
    if node.role == "text" and node.name:
        return True
    return False


# ── Tree Rendering ───────────────────────────────────────────────────────


def render_indexed_tree(root: TreeNode) -> tuple[str, dict[int, TreeNode]]:
    """
    Render a TreeNode tree into the indexed accessibility tree text format.

    Returns (text, ref_map) where ref_map[ref] is the TreeNode for that ref.
    """
    counter = [0]
    ref_map: dict[int, TreeNode] = {}
    lines: list[str] = []

    def walk(node: TreeNode, depth: int):
        indent = "  " * depth

        if node.is_overlay:
            lines.append(f"{indent}[OVERLAY]")
            for child in node.children:
                walk(child, depth + 1)
            return

        indexed = should_index(node)
        if indexed:
            counter[0] += 1
            ref = counter[0]
            ref_map[ref] = node
            lines.append(indent + _format_node(ref, node))

        child_depth = depth + (1 if indexed else 0)
        for child in node.children:
            walk(child, child_depth)

        if node.has_more_below:
            lines.append(f"{'  ' * child_depth}{SCROLL_HINT_TEXT}")

    walk(root, 0)
    return "\n".join(lines), ref_map


def _format_node(ref: int, node: TreeNode) -> str:
    """Format a single indexed node line."""
    parts = [f"[{ref}] {node.role}"]
    if node.name:
        display = node.name[:80] + "..." if len(node.name) > 80 else node.name
        parts.append(f'"{display}"')
    if node.value is not None and node.value != "":
        parts.append(f'value="{node.value}"')
    if node.checked is True:
        parts.append("checked")
    elif node.checked is False:
        parts.append("unchecked")
    if node.selected:
        parts.append("selected")
    if node.disabled:
        parts.append("disabled")
    if node.focused:
        parts.append("focused")
    return " ".join(parts)


# ── System Prompt ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a web agent. You interact with web pages to complete tasks.

## Observation
Each step, you receive an indexed accessibility tree showing visible elements:
- [N] role "name" — interactive or meaningful elements with a reference number
- Indentation shows nesting (parent-child relationships)
- Attributes: value="..." checked unchecked disabled focused selected
- [OVERLAY] marks elements blocking the page — handle these first
- [-- viewport continues below --] means the page extends beyond the visible area

## Actions
Respond with a JSON object containing "thought" and one action:

| Action         | Required         | Optional | Example                                                |
|----------------|------------------|----------|--------------------------------------------------------|
| click          | ref              |          | {"action":"click","ref":3}                             |
| dblclick       | ref              |          | {"action":"dblclick","ref":3}                          |
| fill           | ref, value       |          | {"action":"fill","ref":5,"value":"hello"}              |
| select         | ref, value       |          | {"action":"select","ref":8,"value":"California"}       |
| check          | ref              |          | {"action":"check","ref":12}                            |
| uncheck        | ref              |          | {"action":"uncheck","ref":12}                          |
| press          | key              | ref      | {"action":"press","key":"Enter"}                       |
| scroll         | direction        | ref      | {"action":"scroll","direction":"down"}                 |
| hover          | ref              |          | {"action":"hover","ref":4}                             |
| drag_and_drop  | from_ref, to_ref |          | {"action":"drag_and_drop","from_ref":2,"to_ref":7}    |
| wait           |                  |          | {"action":"wait"}                                      |
| finish         |                  | answer   | {"action":"finish","answer":"287"}                     |

## Rules
1. Output valid JSON only. Include "thought" for your reasoning.
2. Only use ref numbers from the CURRENT observation. Never reuse old refs.
3. One action per step.
4. Handle overlays/dialogs before interacting with background elements.
5. If you see [-- viewport continues below --], scroll down before concluding. Prefer explicit controls (buttons, links) over scrolling when available.
6. Before using finish, verify the task is actually complete — check that \
form values are correct, required actions were performed, and the page \
reflects the expected state.
"""


# ── Message Builders ─────────────────────────────────────────────────────


def build_initial_message(instruction: str, tree: str) -> str:
    return f"Task: {instruction}\n\n{tree}"


def build_step_message(status: str, tree: str) -> str:
    return f"Result: {status}\n\n{tree}"


# ── Response Parsing ─────────────────────────────────────────────────────


def parse_action(raw: str) -> dict:
    """Parse LLM response into an action dict. Strips thinking tags and markdown fences."""
    # Strip <think>...</think> (complete tags)
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Strip unclosed <think> tags (model hit max_tokens before closing)
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL).strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        fenced_lines = cleaned.splitlines()
        fenced_lines = fenced_lines[1:]
        if fenced_lines and fenced_lines[-1].strip() == "```":
            fenced_lines = fenced_lines[:-1]
        cleaned = "\n".join(fenced_lines).strip()

    # Try direct JSON parse
    try:
        result = json.loads(cleaned)
        return _normalize_action(result)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object, tolerating trailing data (multi-action responses,
    # extra closing braces, comments after JSON, etc.)
    brace_pos = cleaned.find("{")
    if brace_pos != -1:
        decoder = json.JSONDecoder()
        try:
            result, _ = decoder.raw_decode(cleaned, brace_pos)
            return _normalize_action(result)
        except json.JSONDecodeError:
            pass

    return {"action": "wait", "thought": f"Failed to parse: {raw[:200]}"}


def _normalize_action(action: dict) -> dict:
    """Fix common malformed action patterns from LLMs."""
    # Fix nested action: {"action": {"type": "click", "ref": 7}}
    # Should be:         {"action": "click", "ref": 7}
    inner = action.get("action")
    if isinstance(inner, dict):
        action_type = inner.get("type") or inner.get("action", "wait")
        normalized = {"action": action_type}
        for k, v in inner.items():
            if k not in ("type", "action"):
                normalized[k] = v
        # Preserve thought from outer dict
        if "thought" in action:
            normalized["thought"] = action["thought"]
        return normalized
    return action
