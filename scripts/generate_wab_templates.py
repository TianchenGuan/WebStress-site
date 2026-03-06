"""
Generate LLMOS templates from real WAB pages using Playwright.

Captures the actual aria_snapshot from each WAB page and converts it
into the LLMOS template JSON format. This ensures LLMOS observations
match what agents see in real browser evaluation.

Usage:
    # Start WAB server first (in another terminal):
    python -m webagentbench.server

    # Then generate templates:
    python scripts/generate_wab_templates.py

    # Or specify a custom server URL:
    python scripts/generate_wab_templates.py --url http://localhost:8080
"""

import argparse
import json
import re
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def aria_snapshot_to_llmos_ui(snapshot_text: str, page_id: str) -> dict:
    """
    Convert a Playwright aria_snapshot string into an LLMOS UI tree dict.

    Maps aria_snapshot's text format into the LLMOS node format with
    bid, tag, role, text, value, visible, bounds, children.
    """
    lines = snapshot_text.split("\n")
    bid_counter = [0]

    def make_bid(role: str, name: str) -> str:
        """Generate a descriptive bid from role and name."""
        bid_counter[0] += 1
        if name:
            # Sanitize name for bid
            safe = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:40].rstrip('_')
            return f"{role}_{safe}_{bid_counter[0]}"
        return f"{role}_{bid_counter[0]}"

    def parse_line(line: str) -> dict | None:
        """Parse one aria_snapshot line into an LLMOS node dict."""
        content = line.lstrip(" ")
        if content.startswith("- "):
            content = content[2:]
        if not content:
            return None

        # Skip Playwright annotation lines (/placeholder:, /url:, etc.)
        if content.startswith("/"):
            # Convert to a text node so the agent sees it
            annotation = content  # e.g. "/placeholder: e.g. Jane Doe"
            node = {
                "bid": make_bid("text", annotation),
                "tag": "span",
                "role": "text",
                "text": annotation,
                "visible": True,
                "bounds": {"x": 0, "y": 0, "width": 800, "height": 20},
            }
            return node, False

        # Extract role
        m = re.match(r"^([\w-]+)", content)
        if not m:
            return None
        role = m.group(1)
        rest = content[m.end():].strip()

        # Extract quoted name
        name = ""
        if rest.startswith('"'):
            end = rest.find('"', 1)
            if end != -1:
                name = rest[1:end]
                rest = rest[end + 1:].strip()

        # Extract attributes [checked] [disabled] [selected] etc.
        checked = None
        disabled = False
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
            elif attr == "selected":
                selected = True

        # Handle colon — inline value or children marker
        value = None
        has_children = False
        value_roles = {"textbox", "searchbox", "spinbutton"}

        if rest.startswith(":"):
            inline = rest[1:].strip()
            if inline:
                if role in value_roles:
                    value = inline
                elif not name:
                    name = inline
            else:
                has_children = True
        elif rest:
            if not name:
                name = rest.rstrip(":")
            if line.rstrip().endswith(":"):
                has_children = True

        # Map role to HTML-like tag
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

        return node, has_children

    # Parse the snapshot into a tree
    root_node = {
        "bid": "page_content",
        "tag": "main",
        "role": "main",
        "text": page_id.replace("_", " ").title(),
        "visible": True,
        "bounds": {"x": 0, "y": 50, "width": 1920, "height": 1030},
        "children": [],
    }

    # Stack: (indent_level, node_with_children_list)
    stack = [(-1, root_node)]

    for line in lines:
        if not line.strip():
            continue

        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)

        result = parse_line(line)
        if result is None:
            continue
        node, has_children = result

        # Pop stack to find parent
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent = stack[-1][1]
        if "children" not in parent:
            parent["children"] = []
        parent["children"].append(node)

        if has_children:
            node["children"] = []
            stack.append((indent, node))

    # Wrap in browser chrome (matching existing template structure)
    browser_root = {
        "bid": "root",
        "tag": "browser",
        "role": "application",
        "text": page_id.replace("_", " ").title(),
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
            root_node,
        ],
    }

    return browser_root


def build_template(page_def: dict, snapshot_text: str) -> dict:
    """Build a complete LLMOS template from a WAB page definition and its aria_snapshot."""
    page_id = page_def["page_id"]

    # Convert snapshot to UI tree
    ui = aria_snapshot_to_llmos_ui(snapshot_text, page_id)

    # Build hidden_state from manifest's success_criteria
    criteria = page_def.get("success_criteria", {})
    hidden_state = {
        "wab_page_id": page_id,
        "wab_instruction": page_def["instruction"],
        "task_completion_criteria": criteria,
    }

    # Build template
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
                "title": page_def.get("title", page_id),
                "active": True,
            }
        ],
        "history": [],
    }

    return template


def main():
    parser = argparse.ArgumentParser(description="Generate LLMOS templates from WAB pages")
    parser.add_argument("--url", type=str, default="http://localhost:8080",
                        help="WAB server URL")
    parser.add_argument("--output-dir", type=str, default="llmos/templates",
                        help="Output directory for templates")
    parser.add_argument("--pages", nargs="+", default=None,
                        help="Specific pages to generate (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print snapshot instead of writing templates")
    args = parser.parse_args()

    # Load manifest
    manifest_path = project_root / "webagentbench" / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    pages = manifest["pages"]
    if args.pages:
        pages = [p for p in pages if p["page_id"] in args.pages]

    # Launch Playwright
    from playwright.sync_api import sync_playwright

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for page_def in pages:
            page_id = page_def["page_id"]
            url = f"{args.url}/pages/{page_id}"

            print(f"[{page_id}] Loading {url}...")

            context = browser.new_context()
            page = context.new_page()

            try:
                page.goto(url, wait_until="networkidle")
                # Small wait for dynamic content to settle
                page.wait_for_timeout(500)

                # Capture aria_snapshot
                snapshot = page.locator("body").aria_snapshot()

                if args.dry_run:
                    print(f"\n--- {page_id} aria_snapshot ({len(snapshot.splitlines())} lines) ---")
                    print(snapshot[:2000])
                    if len(snapshot) > 2000:
                        print(f"... ({len(snapshot) - 2000} more chars)")
                    print()
                    continue

                # Build template
                template = build_template(page_def, snapshot)

                # Count nodes for reporting
                def count_nodes(node):
                    n = 1
                    for c in node.get("children", []):
                        n += count_nodes(c)
                    return n
                n_nodes = count_nodes(template["ui"])

                # Write template
                out_path = output_dir / f"wab_{page_id}.json"
                with open(out_path, "w") as f:
                    json.dump(template, f, indent=2)

                print(f"  -> {out_path} ({n_nodes} nodes)")

            except Exception as e:
                print(f"  ERROR: {e}")
            finally:
                context.close()

        browser.close()

    if not args.dry_run:
        print(f"\nGenerated {len(pages)} templates in {output_dir}/")


if __name__ == "__main__":
    main()
