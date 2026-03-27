from __future__ import annotations

"""
Generate LLMOS templates from real browser accessibility trees in evaluation results.

Parses the indexed accessibility tree from agent messages in results_gpt5.2.json
and converts them into LLMOS template JSON format. This guarantees the template
tree matches what agents actually see in real browser evaluation.

Usage:
    python scripts/generate_templates_from_eval.py
    python scripts/generate_templates_from_eval.py --results results_gpt5.2.json
    python scripts/generate_templates_from_eval.py --pages scavenger_hunt wizard_form
    python scripts/generate_templates_from_eval.py --dry-run   # show tree, don't write
"""

import argparse
import json
import re
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ── Parsing indexed accessibility tree text → LLMOS UI nodes ──────────────


def parse_indexed_tree(tree_text: str) -> list[dict]:
    """
    Parse an indexed accessibility tree text into a flat list of
    (indent_level, node_dict) tuples, then assemble into a nested tree.

    Input format (from render_indexed_tree in shared/format.py):
        [1] heading "Insurance Application"
        [2] text "Step 1 of 4"
        [3] combobox "State"
          [4] option "California" selected
        [OVERLAY]
          [5] dialog "Confirm"
        [-- more content below --]
    """
    lines = tree_text.strip().split("\n")
    bid_counter = [0]

    def make_bid(role: str, name: str) -> str:
        bid_counter[0] += 1
        if name:
            safe = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:40].rstrip('_')
            return f"{role}_{safe}_{bid_counter[0]}"
        return f"{role}_{bid_counter[0]}"

    tag_map = {
        "heading": "h2", "button": "button", "link": "a",
        "textbox": "input", "combobox": "select", "option": "option",
        "checkbox": "input", "radio": "input", "text": "span",
        "paragraph": "p", "table": "table", "row": "tr",
        "cell": "td", "columnheader": "th", "rowheader": "th",
        "list": "ul", "listitem": "li", "img": "img",
        "navigation": "nav", "main": "main", "form": "form",
        "alert": "div", "dialog": "dialog", "status": "span",
        "tab": "button", "tabpanel": "div", "separator": "hr",
        "searchbox": "input", "spinbutton": "input", "slider": "input",
        "switch": "input", "menuitem": "li", "region": "section",
        "article": "article", "figure": "figure", "banner": "header",
        "contentinfo": "footer", "complementary": "aside",
    }

    def parse_node_line(line: str) -> dict | None:
        """Parse a single indexed tree line like: [N] role "name" attr1 attr2"""
        stripped = line.lstrip()

        # Skip markers
        if stripped.startswith("[-- more content below --]"):
            return None
        if stripped == "[OVERLAY]":
            # Return an overlay container marker
            return {
                "_overlay": True,
                "bid": make_bid("overlay", ""),
                "tag": "div",
                "role": "dialog",
                "text": "",
                "visible": True,
                "modal": True,
                "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            }

        # Match: [N] role "name" attrs...
        m = re.match(r'\[(\d+)\]\s+(\S+)', stripped)
        if not m:
            return None

        ref = int(m.group(1))
        role = m.group(2)
        rest = stripped[m.end():].strip()

        # Extract quoted name — names can contain embedded quotes,
        # so find the closing quote by looking for the last " before
        # any known trailing attribute keyword or end of string.
        name = ""
        if rest.startswith('"'):
            # Known attribute suffixes that follow the closing name quote
            attr_pat = re.compile(
                r'" (?:value="|checked\b|unchecked\b|selected\b|disabled\b|focused\b)'
            )
            am = attr_pat.search(rest, 1)
            if am:
                # Close quote is at am.start()
                name = rest[1:am.start()]
                rest = rest[am.start() + 2:].strip()  # skip closing quote + space
            else:
                # No attributes — closing quote is the last " in rest
                last_q = rest.rfind('"')
                if last_q > 0:
                    name = rest[1:last_q]
                    rest = rest[last_q + 1:].strip()
                else:
                    name = rest[1:]
                    rest = ""

        # Parse remaining attributes
        value = None
        checked = None
        disabled = False
        focused = False
        selected = False

        # Extract value="..." first (may contain spaces)
        vm = re.search(r'value="([^"]*)"', rest)
        if vm:
            value = vm.group(1)
            rest_after = rest[:vm.start()] + rest[vm.end():]
        else:
            rest_after = rest

        for token in rest_after.split():
            if token == "checked":
                checked = True
            elif token == "unchecked":
                checked = False
            elif token == "disabled":
                disabled = True
            elif token == "focused":
                focused = True
            elif token == "selected":
                selected = True

        tag = tag_map.get(role, "div")
        node = {
            "bid": make_bid(role, name),
            "tag": tag,
            "role": role,
            "text": name,
            "visible": True,
            "bounds": {"x": 0, "y": 0, "width": 800, "height": 30},
        }

        if value is not None:
            node["value"] = value
        if checked is not None:
            node["checked"] = checked
        if disabled:
            node["disabled"] = True
        if selected:
            node["selected"] = True
        if focused:
            node["focused"] = True

        return node

    # Parse all lines with their indent levels
    parsed = []  # list of (indent, node)
    for line in lines:
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip())
        node = parse_node_line(line)
        if node is not None:
            parsed.append((indent, node))

    # Build nested tree from indent levels
    # Stack: (indent, node_with_children)
    root_children = []
    stack = [(-1, {"children": root_children})]  # sentinel

    for indent, node in parsed:
        # Pop stack until we find a parent with lower indent
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent = stack[-1][1]
        if "children" not in parent:
            parent["children"] = []
        parent["children"].append(node)

        # This node can have children (any node can)
        node.setdefault("children", [])
        stack.append((indent, node))

    # Clean up empty children lists
    def clean(node):
        if not node.get("children"):
            node.pop("children", None)
        else:
            for child in node["children"]:
                clean(child)
    for n in root_children:
        clean(n)

    return root_children


def wrap_in_browser_chrome(page_nodes: list[dict], page_id: str, title: str) -> dict:
    """Wrap parsed page nodes in the standard LLMOS browser chrome."""
    page_content = {
        "bid": "page_content",
        "tag": "main",
        "role": "main",
        "text": title,
        "visible": True,
        "bounds": {"x": 0, "y": 50, "width": 1920, "height": 1030},
        "children": page_nodes,
    }

    browser_root = {
        "bid": "root",
        "tag": "browser",
        "role": "application",
        "text": title,
        "visible": True,
        "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
        "children": [
            {
                "bid": "toolbar",
                "tag": "toolbar",
                "role": "toolbar",
                "text": "Browser Toolbar",
                "visible": True,
                "bounds": {"x": 0, "y": 0, "width": 1920, "height": 50},
                "children": [
                    {
                        "bid": "url_bar",
                        "tag": "input",
                        "role": "textbox",
                        "text": "Address",
                        "value": f"https://webagentbench.local/pages/{page_id}",
                        "visible": True,
                        "bounds": {"x": 200, "y": 10, "width": 1200, "height": 30},
                    }
                ],
            },
            page_content,
        ],
    }

    return browser_root


def build_template_from_tree(
    page_def: dict,
    tree_text: str,
    existing_template: dict | None = None,
) -> dict:
    """Build a complete LLMOS template from a page definition and parsed tree."""
    page_id = page_def["page_id"]
    title = page_def.get("title", page_id.replace("_", " ").title())

    # Parse the indexed tree text into nodes
    page_nodes = parse_indexed_tree(tree_text)

    # Wrap in browser chrome
    ui = wrap_in_browser_chrome(page_nodes, page_id, title)

    # Build hidden_state from manifest
    criteria = page_def.get("success_criteria", {})
    hidden_state = {
        "wab_page_id": page_id,
        "wab_instruction": page_def["instruction"],
    }

    # Preserve anchored_content from existing template
    if existing_template:
        existing_ac = existing_template.get("hidden_state", {}).get("anchored_content")
        if existing_ac:
            hidden_state["anchored_content"] = existing_ac

    hidden_state["task_completion_criteria"] = criteria

    template = {
        "meta": {
            "tick": 0,
            "status": "running",
            "random_seed": 42,
            "platform": "webagentbench",
            "task_category": page_id,
            "target_primitives": page_def.get("primary_primitives", []),
        },
        "hidden_state": hidden_state,
        "ui": ui,
        "filesystem": {},
        "tabs": [
            {
                "id": 0,
                "url": f"https://webagentbench.local/pages/{page_id}",
                "title": title,
                "active": True,
            }
        ],
        "history": [],
    }

    return template


def extract_tree_from_message(content: str) -> str:
    """Extract the indexed tree from the initial user message (msg[1]).

    Format: "Task: <instruction>\\n\\n<tree>"
    """
    # Find the tree after the task instruction (double newline separator)
    parts = content.split("\n\n", 1)
    if len(parts) == 2:
        return parts[1]
    # Fallback: return everything after "Task: ...\n"
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("["):
            return "\n".join(lines[i:])
    return content


def count_nodes(node: dict) -> int:
    n = 1
    for c in node.get("children", []):
        n += count_nodes(c)
    return n


# ── Verification ──────────────────────────────────────────────────────────


def verify_round_trip(template: dict, original_tree: str, page_id: str) -> dict:
    """
    Verify that the template produces the same indexed tree as the original.

    Returns a report dict with match status and diff info.
    """
    from llmos.utils.rendering import render_observation
    from shared.llmos_adapter import state_to_indexed_tree

    observation = render_observation(template)
    rendered_tree, _, _ = state_to_indexed_tree(observation, skip_browser_chrome=True)

    original_lines = [l for l in original_tree.strip().split("\n") if l.strip()]
    rendered_lines = [l for l in rendered_tree.strip().split("\n") if l.strip()]

    # Compare line counts
    report = {
        "page_id": page_id,
        "original_lines": len(original_lines),
        "rendered_lines": len(rendered_lines),
        "match": original_lines == rendered_lines,
    }

    if not report["match"]:
        # Find first difference
        diffs = []
        max_lines = max(len(original_lines), len(rendered_lines))
        for i in range(min(10, max_lines)):
            orig = original_lines[i] if i < len(original_lines) else "<missing>"
            rend = rendered_lines[i] if i < len(rendered_lines) else "<missing>"
            if orig != rend:
                diffs.append({"line": i + 1, "original": orig.strip(), "rendered": rend.strip()})
        report["first_diffs"] = diffs
        report["line_diff"] = len(rendered_lines) - len(original_lines)

    return report


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Generate LLMOS templates from real browser accessibility trees"
    )
    parser.add_argument(
        "--results", type=str, default="results/webagentbench/archive/results_gpt5.2.json",
        help="Path to WAB evaluation results JSON",
    )
    parser.add_argument(
        "--output-dir", type=str, default="llmos/templates",
        help="Output directory for templates",
    )
    parser.add_argument(
        "--pages", nargs="+", default=None,
        help="Specific page IDs to generate (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print parsed trees without writing templates",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify round-trip fidelity after generating",
    )
    args = parser.parse_args()

    # Load evaluation results
    results_path = project_root / args.results
    with open(results_path) as f:
        eval_data = json.load(f)

    results = eval_data.get("results", [])
    if not results:
        print(f"ERROR: No results in {results_path}")
        sys.exit(1)

    # Load manifest for page definitions
    manifest_path = project_root / "webagentbench" / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    page_defs = {p["page_id"]: p for p in manifest["pages"]}

    # Filter pages if specified
    if args.pages:
        results = [r for r in results if r["page_id"] in args.pages]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reports = []

    for result in results:
        page_id = result["page_id"]
        page_def = page_defs.get(page_id)
        if not page_def:
            print(f"[{page_id}] SKIP: not in manifest")
            continue

        # Extract initial accessibility tree from agent's first observation
        messages = result.get("agent", {}).get("messages", [])
        if len(messages) < 2:
            print(f"[{page_id}] SKIP: no initial observation in messages")
            continue

        tree_text = extract_tree_from_message(messages[1]["content"])

        if args.dry_run:
            lines = tree_text.strip().split("\n")
            print(f"\n--- {page_id} ({len(lines)} lines) ---")
            print(tree_text[:3000])
            if len(tree_text) > 3000:
                print(f"... ({len(tree_text) - 3000} more chars)")
            continue

        # Load existing template for anchored_content preservation
        existing_path = output_dir / f"wab_{page_id}.json"
        existing_template = None
        if existing_path.exists():
            with open(existing_path) as f:
                existing_template = json.load(f)

        # Build new template
        template = build_template_from_tree(page_def, tree_text, existing_template)

        n_nodes = count_nodes(template["ui"])
        old_nodes = count_nodes(existing_template["ui"]) if existing_template else 0

        # Write template
        out_path = output_dir / f"wab_{page_id}.json"
        with open(out_path, "w") as f:
            json.dump(template, f, indent=2)

        diff_str = f" (was {old_nodes})" if existing_template else ""
        print(f"[{page_id}] -> {out_path} ({n_nodes} nodes{diff_str})")

        # Verify round-trip if requested
        if args.verify:
            report = verify_round_trip(template, tree_text, page_id)
            reports.append(report)
            status = "MATCH" if report["match"] else f"DIFF (Δ{report.get('line_diff', '?')} lines)"
            print(f"  verify: {status}")
            if not report["match"] and report.get("first_diffs"):
                for d in report["first_diffs"][:3]:
                    print(f"    L{d['line']}: '{d['original']}' vs '{d['rendered']}'")

    if not args.dry_run:
        total = len([r for r in results if r["page_id"] in page_defs])
        print(f"\nGenerated {total} templates in {output_dir}/")

    if reports:
        matched = sum(1 for r in reports if r["match"])
        print(f"\nVerification: {matched}/{len(reports)} exact matches")


if __name__ == "__main__":
    main()
