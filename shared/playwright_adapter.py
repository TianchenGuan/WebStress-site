"""
Playwright adapter for the unified agent format.

Converts Playwright accessibility tree (aria_snapshot) → indexed tree,
and executes unified actions on Playwright pages.
"""

from dataclasses import dataclass
import re

from .format import TreeNode, render_indexed_tree


@dataclass
class LocatorInfo:
    """Info needed to reconstruct a Playwright Locator."""

    role: str
    name: str
    nth: int = 0


# Roles where inline text after colon represents the current value
_VALUE_ROLES = {"textbox", "searchbox", "spinbutton"}


# ── aria_snapshot parsing ────────────────────────────────────────────────


def parse_aria_snapshot(text: str) -> TreeNode:
    """Parse Playwright aria_snapshot() output into a TreeNode tree."""
    root = TreeNode(role="root")
    if not text or text == "(empty page)":
        return root

    lines = text.split("\n")
    # Stack of (indent_level, node)
    stack: list[tuple[int, TreeNode]] = [(-1, root)]

    for line in lines:
        if not line.strip():
            continue

        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)

        if stripped.startswith("- "):
            content = stripped[2:]
        else:
            content = stripped

        node, has_children = _parse_snapshot_line(content)

        # Pop stack to find parent at lower indent
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent = stack[-1][1]
        parent.children.append(node)

        if has_children:
            stack.append((indent, node))

    return root


def _parse_snapshot_line(line: str) -> tuple[TreeNode, bool]:
    """Parse one line of aria_snapshot into (TreeNode, has_children)."""
    has_children = False

    # Extract role (first word, may contain hyphens)
    m = re.match(r"^([\w-]+)", line)
    role = m.group(1) if m else "text"
    rest = line[m.end():].strip() if m else line

    # Extract quoted name
    name = ""
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end != -1:
            name = rest[1:end]
            rest = rest[end + 1:].strip()

    # Extract bracket attributes [checked] [disabled] [level=2] etc.
    checked = None
    disabled = False
    focused = False
    selected = False

    while rest.startswith("["):
        end = rest.find("]")
        if end == -1:
            break
        attr = rest[1:end]
        rest = rest[end + 1:].strip()

        if attr == "checked":
            checked = True
        elif attr == "disabled":
            disabled = True
        elif attr == "focused":
            focused = True
        elif attr == "selected":
            selected = True
        # Ignore level=N, expanded, pressed, etc.

    # Handle colon — children marker or inline text
    value = None
    if rest.startswith(":"):
        inline = rest[1:].strip()
        if inline:
            # Inline text after colon
            if role in _VALUE_ROLES:
                value = inline
            elif not name:
                name = inline
        else:
            has_children = True
    elif rest:
        # Trailing text without colon — treat as name extension
        if not name:
            name = rest.rstrip(":")
        if line.rstrip().endswith(":"):
            has_children = True

    node = TreeNode(
        role=role,
        name=name,
        value=value,
        checked=checked,
        disabled=disabled,
        focused=focused,
        selected=selected,
        source=LocatorInfo(role=role, name=name),
    )
    return node, has_children


# ── Page to indexed tree ─────────────────────────────────────────────────


def page_to_indexed_tree(page) -> tuple[str, dict[int, LocatorInfo]]:
    """
    Convert a Playwright page to an indexed accessibility tree.

    Returns (tree_text, ref_map) where ref_map[ref] = LocatorInfo.
    """
    snapshot_text = page.locator("body").aria_snapshot()
    root = parse_aria_snapshot(snapshot_text or "")

    _mark_overlays(root)
    _assign_nth_indices(root)

    text, node_map = render_indexed_tree(root)

    ref_map: dict[int, LocatorInfo] = {}
    for ref, node in node_map.items():
        ref_map[ref] = node.source

    return text, ref_map


def _mark_overlays(root: TreeNode):
    """Mark dialog/alertdialog children as overlays."""
    for child in root.children:
        if child.role in ("dialog", "alertdialog"):
            child.is_overlay = True


def _assign_nth_indices(root: TreeNode):
    """Walk tree and set LocatorInfo.nth for disambiguation."""
    seen: dict[tuple[str, str], int] = {}

    def walk(node: TreeNode):
        if isinstance(node.source, LocatorInfo):
            key = (node.source.role, node.source.name)
            count = seen.get(key, 0)
            node.source.nth = count
            seen[key] = count + 1
        for child in node.children:
            walk(child)

    walk(root)


# ── Action execution ─────────────────────────────────────────────────────


def execute_unified_action(
    page, action: dict, ref_map: dict[int, LocatorInfo]
) -> str:
    """Execute a unified action on a Playwright page. Returns status string."""
    action_type = action.get("action", "wait")

    if action_type == "finish":
        return "FINISH"

    if action_type == "wait":
        page.wait_for_timeout(1000)
        return "Waited 1 second"

    if action_type == "press":
        key = action["key"]
        ref = action.get("ref")
        if ref:
            _resolve(page, ref_map[ref]).press(key)
        else:
            page.keyboard.press(key)
        return f"Pressed {key}"

    if action_type == "scroll":
        direction = action.get("direction", "down")
        delta = -300 if direction == "up" else 300
        ref = action.get("ref")
        if ref and ref in ref_map:
            _resolve(page, ref_map[ref]).evaluate(f"el => el.scrollBy(0, {delta})")
        else:
            page.mouse.wheel(0, delta)
        return f"Scrolled {direction}"

    if action_type == "drag_and_drop":
        from_loc = _resolve(page, ref_map[action["from_ref"]])
        to_loc = _resolve(page, ref_map[action["to_ref"]])
        from_loc.drag_to(to_loc)
        return f"Dragged [{action['from_ref']}] to [{action['to_ref']}]"

    # All remaining actions require ref
    ref = action["ref"]
    info = ref_map[ref]
    locator = _resolve(page, info)

    if action_type == "click":
        locator.click()
        return f'Clicked [{ref}] {info.role} "{info.name}"'

    if action_type == "dblclick":
        locator.dblclick()
        return f'Double-clicked [{ref}] {info.role} "{info.name}"'

    if action_type == "fill":
        locator.fill(action["value"])
        return f'Filled [{ref}] with "{action["value"][:50]}"'

    if action_type == "select":
        locator.select_option(label=action["value"])
        return f'Selected "{action["value"]}" in [{ref}]'

    if action_type == "check":
        locator.check()
        return f"Checked [{ref}]"

    if action_type == "uncheck":
        locator.uncheck()
        return f"Unchecked [{ref}]"

    if action_type == "hover":
        locator.hover()
        return f"Hovered [{ref}]"

    raise ValueError(f"Unknown action: {action_type}")


def _resolve(page, info: LocatorInfo):
    """Resolve LocatorInfo to a Playwright Locator."""
    if info.role in ("text", "paragraph") and info.name:
        return page.get_by_text(info.name, exact=False).nth(info.nth)
    return page.get_by_role(info.role, name=info.name).nth(info.nth)
