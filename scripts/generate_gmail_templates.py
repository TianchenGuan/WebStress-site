"""
Generate LLMOS templates for Gmail environment tasks.

Seeds Gmail state via the YAML-driven builder pipeline and converts the
resulting data model into LLMOS template UI trees matching the React
component accessibility structure.

Supports both:
- New YAML+builder tasks (webagentbench/tasks/gmail/*.yaml)
- Legacy seeder tasks (webagentbench/backend/seeder.py)

Usage:
    python scripts/generate_gmail_templates.py
    python scripts/generate_gmail_templates.py --tasks gmail_thread_detective gmail_thread_version_conflict
    python scripts/generate_gmail_templates.py --only-new   # only tasks without existing templates
    python scripts/generate_gmail_templates.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml

from webagentbench.backend.models.gmail import GmailSettings, Label
from webagentbench.backend.seeder import derive_anchor_time, derive_seed
from webagentbench.tasks._seed_builders import BUILDER_REGISTRY, SeedContext


# ── YAML task loader ─────────────────────────────────────────────────────

TASKS_DIR = project_root / "webagentbench" / "tasks" / "gmail"


def load_yaml_task(task_id: str) -> dict:
    """Load a task definition from its YAML file."""
    path = TASKS_DIR / f"{task_id}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_all_yaml_tasks() -> dict[str, dict]:
    """Load all gmail YAML task definitions."""
    tasks = {}
    for path in sorted(TASKS_DIR.glob("gmail_*.yaml")):
        task = yaml.safe_load(path.read_text())
        tasks[task["task_id"]] = task
    return tasks


# ── Seed runner (inline, bypasses missing _schema.py) ─────────────────

def _base_skeleton(task_id: str) -> dict[str, Any]:
    """Build the base Gmail state skeleton with system labels and settings."""
    labels = [
        Label(id="label_inbox", name="inbox", color="#202124", system=True),
        Label(id="label_starred", name="starred", color="#fbbc04", system=True),
        Label(id="label_snoozed", name="snoozed", color="#5f6368", system=True),
        Label(id="label_important", name="important", color="#d93025", system=True),
        Label(id="label_sent", name="sent", color="#188038", system=True),
        Label(id="label_scheduled", name="scheduled", color="#5f6368", system=True, show_in_label_list="show_if_unread"),
        Label(id="label_drafts", name="drafts", color="#5f6368", system=True),
        Label(id="label_allmail", name="all mail", color="#5f6368", system=True, show_in_label_list="hide"),
        Label(id="label_spam", name="spam", color="#5f6368", system=True, show_in_label_list="hide"),
        Label(id="label_trash", name="trash", color="#d93025", system=True),
        Label(id="label_promotions", name="promotions", color="#f9ab00", system=True),
        Label(id="label_updates", name="updates", color="#1a73e8", system=True),
        Label(id="label_vip", name="VIP", color="#e37400"),
    ]
    return {
        "env_id": "gmail",
        "task_id": task_id,
        "owner_name": "Avery Quinn",
        "owner_email": "avery.quinn@webagentbench.test",
        "emails": [], "drafts": [], "sent": [], "deleted": [],
        "contacts": [], "labels": labels, "filters": [],
        "settings": GmailSettings(
            id="settings_gmail", signature="Avery Quinn\nOperations Lead",
            forwarding_address="", display_density="comfortable",
            vacation_responder_enabled=False, auto_advance="newer",
            language="English (US)", input_tools_enabled=True,
            right_to_left=False, max_page_size=50, undo_send_seconds=5,
            default_reply_behavior="reply", hover_actions_enabled=True,
            send_and_archive=False, default_text_style="Sans Serif",
        ),
    }


_TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
_EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")


def _raw_lookup(kind: str, path: str, ctx: SeedContext) -> Any:
    if kind == "actor":
        parts = path.split(".", 1)
        actor = ctx.actors[parts[0]]
        if len(parts) == 1:
            return actor.name
        return getattr(actor, parts[1])
    return ctx.outputs[path]


def _resolve_value(value: Any, ctx: SeedContext) -> Any:
    if isinstance(value, str):
        exact = _EXACT_REF_RE.match(value)
        if exact:
            return _raw_lookup(exact.group(1), exact.group(2), ctx)
        return _TEMPLATE_RE.sub(
            lambda m: str(_raw_lookup(m.group(1), m.group(2), ctx)), value
        )
    if isinstance(value, list):
        return [_resolve_value(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_value(v, ctx) for k, v in value.items()}
    return value


def _add_generic_distractors(ctx: SeedContext, count: int) -> None:
    domains = ["updates.test", "partners.test", "community.test", "metrics.test"]
    subjects = [
        "Agenda draft for Monday check-in", "Customer feedback from pilot cohort",
        "Reminder on document review timing", "Quarterly metrics recap",
        "Notes from the partner sync", "Updated rollout checklist",
        "Follow-up on venue estimate", "Revised budget worksheet",
    ]
    for _ in range(count):
        sender_name = ctx.fake.name()
        sender_email = ctx.email_for_name(sender_name, domain=ctx.rng.choice(domains))
        subject = ctx.rng.choice(subjects)
        labels = ["inbox"]
        if ctx.rng.random() < 0.25:
            labels.append("updates")
        if ctx.rng.random() < 0.15:
            labels.append("promotions")
        ctx.base["emails"].append(
            ctx.email(
                from_name=sender_name, from_addr=sender_email,
                subject=subject, body=ctx.generic_email_body(sender_name),
                timestamp=ctx.now - timedelta(days=ctx.rng.randint(1, 20), hours=ctx.rng.randint(0, 22)),
                thread_id=ctx.next_id("thread"), labels=labels,
                is_read=ctx.rng.random() < 0.5,
                attachments=(
                    [ctx.attachment(ctx.rng.choice(["notes.txt", "summary.txt", "agenda.txt"]), "text/plain", "text")]
                    if ctx.rng.random() < 0.2 else []
                ),
            )
        )


def run_yaml_seed(task_def: dict, seed: int = 42) -> tuple[dict, dict]:
    """Execute the YAML seed pipeline and return (base_state, targets)."""
    now = derive_anchor_time(seed)
    task_id = task_def["task_id"]
    base = _base_skeleton(task_id)

    rng = random.Random(seed)
    try:
        from faker import Faker
        fake = Faker()
    except ImportError:
        from webagentbench.backend.seeder import _FallbackFaker
        fake = _FallbackFaker(seed)
    fake.seed_instance(seed)

    ctx = SeedContext(seed=seed, rng=rng, fake=fake, now=now, base=base)

    # 10 generic contacts (matches legacy order)
    base["contacts"] = [ctx.contact(is_vip=False) for _ in range(10)]

    seed_cfg = task_def.get("seed")
    if not seed_cfg:
        raise ValueError(f"Task {task_id} has no seed config")

    # 1. Resolve actors
    for key, actor_spec in seed_cfg.get("actors", {}).items():
        if isinstance(actor_spec, dict):
            ctx.resolve_actor(key, domain=actor_spec.get("domain"), is_vip=actor_spec.get("is_vip", False))
        else:
            ctx.resolve_actor(key)

    # 2. Execute builder steps
    for step in seed_cfg.get("steps", []):
        builder_name = step["use"]
        builder = BUILDER_REGISTRY.get(builder_name)
        if builder is None:
            raise KeyError(f"No builder registered for '{builder_name}' (task {task_id})")
        params = {k: _resolve_value(v, ctx) for k, v in step.get("params", {}).items()}
        result = builder(ctx, params)
        for out_key in step.get("outputs", []):
            if out_key in result:
                ctx.outputs[out_key] = result[out_key]

    # 3. Add distractors
    _add_generic_distractors(ctx, count=seed_cfg.get("distractors", 40))

    # 4. Sort
    base["emails"] = sorted(base["emails"], key=lambda e: e.timestamp, reverse=True)
    base["contacts"] = sorted(base["contacts"], key=lambda c: c.name.lower())

    # 5. Resolve targets
    targets = {}
    for key, tmpl in seed_cfg.get("targets", {}).items():
        targets[key] = _resolve_value(tmpl, ctx)

    return base, targets


# ── Gmail state → LLMOS UI tree ──────────────────────────────────────────

PAGE_SIZE = 16  # matches React Inbox component


def make_bid(role: str, name: str, counter: list[int]) -> str:
    counter[0] += 1
    if name:
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:40].rstrip('_')
        return f"{role}_{safe}_{counter[0]}"
    return f"{role}_{counter[0]}"


def _node(bid: str, tag: str, role: str, text: str = "", **kwargs) -> dict:
    node = {
        "bid": bid, "tag": tag, "role": role, "text": text,
        "visible": True, "bounds": {"x": 0, "y": 0, "width": 800, "height": 30},
    }
    node.update(kwargs)
    return node


def format_timestamp(ts: datetime) -> str:
    return ts.strftime("%b %d")


def gmail_state_to_ui(base: dict, task_def: dict) -> dict:
    """Convert seeded Gmail state dict to LLMOS UI tree."""
    counter = [0]

    def bid(role: str, name: str = "") -> str:
        return make_bid(role, name, counter)

    emails = base["emails"]

    # Categorize emails (matches React categoryOf() logic)
    inbox_emails = [e for e in emails if "inbox" in e.labels and not e.archived and not e.deleted]

    def _category_of(e):
        if "promotions" in e.labels:
            return "promotions"
        if "updates" in e.labels:
            return "updates"
        return "primary"

    primary_emails = [e for e in inbox_emails if _category_of(e) == "primary"]

    # Default: show Primary tab
    display_emails = primary_emails
    total = len(display_emails)
    page_emails = display_emails[:PAGE_SIZE]
    range_end = min(PAGE_SIZE, total)
    inbox_count = len(inbox_emails)

    # ── Topbar ──
    topbar = _node(
        bid("banner", "Gmail"), "header", "banner", "Gmail",
        children=[
            _node(bid("text", "Gmail"), "span", "text", "Gmail"),
            _node(bid("searchbox", "Search mail"), "input", "searchbox", "Search mail"),
        ],
    )

    # ── Sidebar ──
    sidebar = _node(
        bid("navigation", "Gmail navigation"), "nav", "navigation", "Gmail navigation",
        children=[
            _node(bid("button", "Compose"), "button", "button", "Compose"),
            _node(bid("link", "Inbox"), "a", "link", f"Inbox ({inbox_count})"),
            _node(bid("link", "Starred"), "a", "link", "Starred"),
            _node(bid("link", "Sent"), "a", "link", "Sent"),
            _node(bid("link", "Drafts"), "a", "link", "Drafts"),
            _node(bid("link", "Archive"), "a", "link", "Archive"),
            _node(bid("link", "Trash"), "a", "link", "Trash"),
            _node(bid("link", "Settings"), "a", "link", "Settings"),
            _node(bid("link", "Labels"), "a", "link", "Labels"),
        ],
    )

    # ── Main content ──
    tabs = [
        _node(bid("tab", "Primary"), "button", "tab", "Primary", selected=True),
        _node(bid("tab", "Promotions"), "button", "tab", "Promotions"),
        _node(bid("tab", "Updates"), "button", "tab", "Updates"),
        _node(bid("tab", "All Mail"), "button", "tab", "All Mail"),
    ]

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

    pagination = []
    if total > 0:
        pagination.append(_node(bid("text", f"1–{range_end} of {total}"), "span", "text", f"1–{range_end} of {total}"))
        pagination.append(_node(bid("button", "Previous page"), "button", "button", "Previous page", disabled=True))
        disabled = total <= PAGE_SIZE
        pagination.append(_node(bid("button", "Next page"), "button", "button", "Next page", **({"disabled": True} if disabled else {})))

    main_content = _node(
        bid("main", "Inbox"), "main", "main", "Inbox",
        children=tabs + email_rows + pagination,
    )

    page_content = _node("page_content", "main", "main", "Gmail", children=[topbar, sidebar, main_content])
    browser_root = _node(
        "root", "browser", "application", "Gmail",
        children=[
            _node("toolbar", "toolbar", "toolbar", "Browser Toolbar", children=[
                _node("url_bar", "input", "textbox", "Address", value="https://webagentbench.local/env/gmail/inbox"),
            ]),
            page_content,
        ],
    )
    return browser_root


def build_gmail_template(task_id: str, task_def: dict, base: dict, targets: dict) -> dict:
    ui = gmail_state_to_ui(base, task_def)

    hidden_state = {
        "wab_page_id": task_id,
        "wab_instruction": task_def.get("instruction_template", ""),
        "task_completion_criteria": targets,
    }

    return {
        "meta": {
            "tick": 0, "status": "running", "random_seed": 42,
            "platform": "webagentbench", "task_category": task_id,
            "target_primitives": task_def.get("primary_primitives", []),
        },
        "hidden_state": hidden_state,
        "ui": ui,
        "filesystem": {},
        "tabs": [{"id": 0, "url": "https://webagentbench.local/env/gmail/inbox", "title": "Gmail", "active": True}],
        "history": [],
    }


# ── Main ──────────────────────────────────────────────────────────────────


def count_nodes(node: dict) -> int:
    n = 1
    for c in node.get("children", []):
        n += count_nodes(c)
    return n


def main():
    parser = argparse.ArgumentParser(description="Generate LLMOS templates for Gmail tasks")
    parser.add_argument("--output-dir", type=str, default="llmos/templates")
    parser.add_argument("--tasks", nargs="+", default=None, help="Specific task IDs (default: all)")
    parser.add_argument("--only-new", action="store_true", help="Only generate tasks without existing templates")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all YAML task definitions
    all_tasks = load_all_yaml_tasks()

    if args.tasks:
        task_ids = args.tasks
    else:
        task_ids = list(all_tasks.keys())

    if args.only_new:
        task_ids = [t for t in task_ids if not (output_dir / f"{t}.json").exists()]

    generated = 0
    errors = 0

    for task_id in task_ids:
        task_def = all_tasks.get(task_id)
        if not task_def:
            print(f"[{task_id}] SKIP: no YAML definition found")
            continue

        try:
            base, targets = run_yaml_seed(task_def, seed=args.seed)
        except Exception as e:
            print(f"[{task_id}] ERROR: {e}")
            errors += 1
            continue

        if args.dry_run:
            emails = base["emails"]
            inbox = [e for e in emails if "inbox" in e.labels and not e.archived]
            print(f"[{task_id}] emails={len(emails)} inbox={len(inbox)} targets={list(targets.keys())[:4]}...")
            generated += 1
            continue

        template = build_gmail_template(task_id, task_def, base, targets)
        n_nodes = count_nodes(template["ui"])

        out_path = output_dir / f"{task_id}.json"
        with open(out_path, "w") as f:
            json.dump(template, f, indent=2, default=str)

        inbox_count = sum(1 for e in base["emails"] if "inbox" in e.labels and not e.archived)
        print(f"[{task_id}] -> {out_path} ({n_nodes} nodes, {inbox_count} inbox emails)")
        generated += 1

    print(f"\n{'Checked' if args.dry_run else 'Generated'} {generated} templates, {errors} errors")


if __name__ == "__main__":
    main()
