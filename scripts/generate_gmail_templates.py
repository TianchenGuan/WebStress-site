"""
Generate LLMOS templates for Gmail environment tasks.

Seeds Gmail state via GmailSeeder and converts the resulting data model into
LLMOS template UI trees matching the React component accessibility structure.

Usage:
    python scripts/generate_gmail_templates.py
    python scripts/generate_gmail_templates.py --tasks gmail_thread_detective gmail_inbox_triage_protocol
    python scripts/generate_gmail_templates.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from webagentbench.backend.seeder import Seeder
from webagentbench.backend.tasks import GMAIL_TASK_INDEX


# ── Gmail state → LLMOS UI tree ──────────────────────────────────────────

PAGE_SIZE = 16  # matches React Inbox component


def make_bid(role: str, name: str, counter: list[int]) -> str:
    """Generate a descriptive bid from role and name."""
    counter[0] += 1
    if name:
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:40].rstrip('_')
        return f"{role}_{safe}_{counter[0]}"
    return f"{role}_{counter[0]}"


def _node(bid: str, tag: str, role: str, text: str = "", **kwargs) -> dict:
    """Create an LLMOS UI node."""
    node = {
        "bid": bid,
        "tag": tag,
        "role": role,
        "text": text,
        "visible": True,
        "bounds": {"x": 0, "y": 0, "width": 800, "height": 30},
    }
    node.update(kwargs)
    return node


def format_timestamp(ts: datetime) -> str:
    """Format email timestamp for display."""
    return ts.strftime("%b %d")


def gmail_state_to_ui(base: dict, task_def: dict) -> dict:
    """Convert seeded Gmail state dict to LLMOS UI tree.

    Produces a tree matching the React Gmail component accessibility structure:
    - banner (topbar with search)
    - navigation (sidebar with compose, mailbox links)
    - main (inbox with category tabs, email list, pagination)
    """
    counter = [0]

    def bid(role: str, name: str = "") -> str:
        return make_bid(role, name, counter)

    emails = base["emails"]
    contacts = base["contacts"]
    labels = base["labels"]

    # Categorize emails for inbox view (matches React categoryOf() logic)
    inbox_emails = [e for e in emails if "inbox" in e.labels and not e.archived and not e.deleted]

    def _category_of(e):
        if "promotions" in e.labels:
            return "promotions"
        if "updates" in e.labels:
            return "updates"
        return "primary"

    primary_emails = [e for e in inbox_emails if _category_of(e) == "primary"]
    promo_emails = [e for e in inbox_emails if _category_of(e) == "promotions"]
    update_emails = [e for e in inbox_emails if _category_of(e) == "updates"]

    # Default: show Primary tab (initial inbox state)
    display_emails = primary_emails
    total = len(display_emails)
    page_emails = display_emails[:PAGE_SIZE]
    range_end = min(PAGE_SIZE, total)

    inbox_count = len(inbox_emails)
    unread_count = sum(1 for e in inbox_emails if not e.is_read)

    # ── Topbar ──
    topbar = _node(
        bid("banner", "Gmail"), "header", "banner", "Gmail",
        children=[
            _node(bid("text", "Gmail"), "span", "text", "Gmail"),
            _node(bid("searchbox", "Search mail"), "input", "searchbox", "Search mail"),
        ],
    )

    # ── Sidebar ──
    sidebar_links = [
        _node(bid("button", "Compose"), "button", "button", "Compose"),
        _node(bid("link", "Inbox"), "a", "link", f"Inbox ({inbox_count})"),
        _node(bid("link", "Starred"), "a", "link", "Starred"),
        _node(bid("link", "Sent"), "a", "link", "Sent"),
        _node(bid("link", "Drafts"), "a", "link", "Drafts"),
        _node(bid("link", "Archive"), "a", "link", "Archive"),
        _node(bid("link", "Trash"), "a", "link", "Trash"),
        _node(bid("link", "Settings"), "a", "link", "Settings"),
        _node(bid("link", "Labels"), "a", "link", "Labels"),
    ]
    sidebar = _node(
        bid("navigation", "Gmail navigation"), "nav", "navigation", "Gmail navigation",
        children=sidebar_links,
    )

    # ── Main content (inbox) ──
    # Category tabs
    tabs = [
        _node(bid("tab", "Primary"), "button", "tab", "Primary", selected=True),
        _node(bid("tab", "Promotions"), "button", "tab", "Promotions"),
        _node(bid("tab", "Updates"), "button", "tab", "Updates"),
        _node(bid("tab", "All Mail"), "button", "tab", "All Mail"),
    ]

    # Email rows
    email_rows = []
    for e in page_emails:
        star_label = f"Unstar {e.subject}" if e.is_starred else f"Star {e.subject}"
        snippet = " ".join(e.body.split())[:140]
        row = _node(
            bid("article", e.subject), "article", "article", "",
            children=[
                _node(bid("button", star_label), "button", "button", star_label),
                _node(bid("text", e.from_name), "span", "text", e.from_name),
                _node(
                    bid("link", f"Open thread {e.subject}"), "a", "link",
                    f"Open thread {e.subject}",
                    children=[
                        _node(bid("text", e.subject), "span", "text", e.subject),
                        _node(bid("text", snippet), "span", "text", snippet),
                    ],
                ),
                _node(bid("button", f"Archive {e.subject}"), "button", "button", f"Archive {e.subject}"),
                _node(bid("button", f"Delete {e.subject}"), "button", "button", f"Delete {e.subject}"),
                _node(bid("text", format_timestamp(e.timestamp)), "span", "text", format_timestamp(e.timestamp)),
            ],
        )
        email_rows.append(row)

    # Pagination
    pagination = []
    if total > 0:
        pagination.append(
            _node(bid("text", f"1–{range_end} of {total}"), "span", "text", f"1–{range_end} of {total}"),
        )
        pagination.append(
            _node(bid("button", "Previous page"), "button", "button", "Previous page", disabled=True),
        )
        if total > PAGE_SIZE:
            pagination.append(
                _node(bid("button", "Next page"), "button", "button", "Next page"),
            )
        else:
            pagination.append(
                _node(bid("button", "Next page"), "button", "button", "Next page", disabled=True),
            )

    main_content = _node(
        bid("main", "Inbox"), "main", "main", "Inbox",
        children=tabs + email_rows + pagination,
    )

    # ── Browser chrome wrapper ──
    page_content = _node(
        "page_content", "main", "main", "Gmail",
        children=[topbar, sidebar, main_content],
    )

    browser_root = _node(
        "root", "browser", "application", "Gmail",
        children=[
            _node(
                "toolbar", "toolbar", "toolbar", "Browser Toolbar",
                children=[
                    _node(
                        "url_bar", "input", "textbox", "Address",
                        value="https://webagentbench.local/env/gmail/inbox",
                    ),
                ],
            ),
            page_content,
        ],
    )

    return browser_root


def build_gmail_template(task_id: str, task_def: dict, base: dict, targets: dict) -> dict:
    """Build a complete LLMOS template for a Gmail task."""
    ui = gmail_state_to_ui(base, task_def)

    hidden_state = {
        "wab_page_id": task_id,
        "wab_instruction": task_def.get("instruction_template", ""),
        "task_completion_criteria": targets,
    }

    template = {
        "meta": {
            "tick": 0,
            "status": "running",
            "random_seed": 42,
            "platform": "webagentbench",
            "task_category": task_id,
            "target_primitives": task_def.get("primary_primitives", []),
        },
        "hidden_state": hidden_state,
        "ui": ui,
        "filesystem": {},
        "tabs": [
            {
                "id": 0,
                "url": "https://webagentbench.local/env/gmail/inbox",
                "title": "Gmail",
                "active": True,
            }
        ],
        "history": [],
    }

    return template


# ── Main ──────────────────────────────────────────────────────────────────


def count_nodes(node: dict) -> int:
    n = 1
    for c in node.get("children", []):
        n += count_nodes(c)
    return n


def main():
    parser = argparse.ArgumentParser(
        description="Generate LLMOS templates for Gmail environment tasks"
    )
    parser.add_argument(
        "--output-dir", type=str, default="llmos/templates",
        help="Output directory for templates",
    )
    parser.add_argument(
        "--tasks", nargs="+", default=None,
        help="Specific task IDs to generate (default: all 20)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for deterministic generation",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print template info without writing files",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get task list
    if args.tasks:
        task_ids = args.tasks
    else:
        task_ids = list(GMAIL_TASK_INDEX.keys())

    seeder = Seeder(args.seed)

    for task_id in task_ids:
        task_def = GMAIL_TASK_INDEX.get(task_id)
        if not task_def:
            print(f"[{task_id}] SKIP: not in GMAIL_TASK_INDEX")
            continue

        # Generate seeded state
        base, targets = seeder.generate("gmail", task_id)

        if args.dry_run:
            emails = base["emails"]
            inbox = [e for e in emails if "inbox" in e.labels and not e.archived]
            primary = [e for e in inbox if e.category == "primary"]
            print(f"\n--- {task_id} ---")
            print(f"  Emails: {len(emails)} total, {len(inbox)} inbox, {len(primary)} primary")
            print(f"  Contacts: {len(base['contacts'])}")
            print(f"  Targets: {list(targets.keys())[:5]}...")
            print(f"  Instruction: {task_def['instruction_template'][:100]}...")
            continue

        # Build template
        template = build_gmail_template(task_id, task_def, base, targets)
        n_nodes = count_nodes(template["ui"])

        # Write template
        out_path = output_dir / f"{task_id}.json"
        with open(out_path, "w") as f:
            json.dump(template, f, indent=2, default=str)

        emails = base["emails"]
        inbox_count = sum(1 for e in emails if "inbox" in e.labels and not e.archived)
        print(f"[{task_id}] -> {out_path} ({n_nodes} nodes, {inbox_count} inbox emails)")

    if not args.dry_run:
        print(f"\nGenerated {len(task_ids)} templates in {output_dir}/")


if __name__ == "__main__":
    main()
