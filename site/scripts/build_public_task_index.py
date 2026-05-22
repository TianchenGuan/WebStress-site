#!/usr/bin/env python3
"""Build the public task index JSON consumed by the website.

Reads task YAMLs, intervention variants, the Human-140 panel, and the
assignments ledger from `../webstress/` (relative to the site root) and
emits four sanitized JSON files under `public/data/`:

  - tasks_index.json     (one entry per base task; intervention paired in)
  - primitives.json      (one card per primitive, with counts + example)
  - environments.json    (one card per env, with counts + difficulty mix)

Crucially, we DO NOT export:
  - canonical_diff predicates (hidden evaluator state)
  - the `seed` block (latent target structure)
  - any annotator real names (we operate on P1-P4 / D1-D4 codes only)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
FORK_ROOT = SITE.parent
BENCH = FORK_ROOT / "webstress"
OUT = SITE / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# Hand-curated cards — definitions intentionally match the paper.
PRIMITIVE_CARDS = {
    "grounding": {
        "label": "Grounding",
        "definition": "Identifying and selecting the right visible object among distractors, decoys, and adversarial content.",
        "what_it_targets": "Disambiguation under decoys, look-alike labels, phishing-style content, and visually crowded surfaces.",
        "typical_families": ["Decoys & aliases", "Adversarial content", "Label misbinding"],
    },
    "planning": {
        "label": "Planning",
        "definition": "Executing a multi-step ordering or dependency, and revising the plan as new information arrives.",
        "what_it_targets": "Out-of-order timestamps, missing prerequisites, hidden ordering constraints.",
        "typical_families": ["Timestamp scramble", "Prerequisite hiding", "Contradictory update"],
    },
    "state_tracking": {
        "label": "State tracking",
        "definition": "Maintaining task-relevant state across pages, updates, and out-of-order events.",
        "what_it_targets": "Shuffled lists, contradictory partial updates, split information across screens.",
        "typical_families": ["Ordering shuffle", "Contradictory update", "Split information"],
    },
    "backtracking": {
        "label": "Backtracking",
        "definition": "Detecting a blocked or wrong path, reverting to a prior decision point, and trying an alternative.",
        "what_it_targets": "401 session expiry, 409 conflicts, planted wrong answers, transient 5xx errors.",
        "typical_families": ["Transient error", "Optimistic conflict", "Planted wrong answer"],
    },
    "patience": {
        "label": "Patience",
        "definition": "Calibrating retry timing under slow, flaky, or rate-limited conditions.",
        "what_it_targets": "Tail latency, progressive delay, 429 with Retry-After, stuck loaders.",
        "typical_families": ["Latency", "Rate limit", "Stuck loader"],
    },
    "exploration": {
        "label": "Exploration",
        "definition": "Finding alternative affordances when the obvious path is closed, hidden, or low-salience.",
        "what_it_targets": "Restricted affordance sets, hidden prerequisites, intercepting overlays.",
        "typical_families": ["Hidden/restricted affordance", "Prerequisite hiding", "Intercepting overlay"],
    },
    "verification": {
        "label": "Verification",
        "definition": "Confirming that the backend state actually changed after an action, rather than trusting a rendered confirmation.",
        "what_it_targets": "Fabricated-success HTTP responses, misleading 'Saved' toasts, silent writes, save drift.",
        "typical_families": ["Fabricated success", "Stale response", "Deceptive banner"],
    },
}

ENV_CARDS = {
    "gmail": ("Gmail", "Email", "Seeded Gmail clone: inbox, threads, labels, drafts, contacts, filters, and settings."),
    "amazon": ("Amazon", "E-commerce", "Seeded Amazon clone: browse, cart, orders, returns, reviews, wishlists, addresses, payments."),
    "reddit": ("Reddit", "Social", "Seeded Reddit clone: posts, comments, messages, notifications, subscriptions."),
    "robinhood": ("Robinhood", "Finance", "Seeded Robinhood clone: equity + options orders, watchlists, transfers, recurring investments, price alerts."),
    "booking": ("Booking", "Travel", "Seeded Booking.com clone: reservations, reviews, saved lists, messages, transactions."),
    "lms": ("LMS", "Education", "Seeded LMS clone: assignments, grades, discussions, peer reviews, enrollments."),
    "patient_portal": ("Patient Portal", "Healthcare", "Seeded patient-portal clone: appointments, prescriptions, lab results, messages, referrals, claims."),
}

# Map a variant's mechanism to a human-readable stressor family name. Keys
# come from `injections[0].params.action`; layer disambiguates duplicates.
FAMILY_BY_ACTION = {
    # Seed
    "add_confusing_decoys": "Decoys & aliases",
    "add_noise_orders": "Decoys & aliases",
    "add_decoy_notifications": "Decoys & aliases",
    "alias_entities": "Decoys & aliases",
    "inject_adv_content": "Adversarial content",
    "split_information": "Split information",
    "add_contradictory_update": "Contradictory update",
    "inflate_target_content": "Content inflation",
    "plant_wrong_answer": "Planted wrong answer",
    "hide_in_non_obvious_loc": "Hidden target",
    # Server
    "scramble_timestamps": "Timestamp scramble",
    "shuffle_positions": "Ordering shuffle",
    "inject_distractor_emails": "Distractor injection",
    "add_correction_notice": "Prerequisite hiding",
    "modify_response": "Field corruption",
    # Network
    "delay": "Latency",
    "error_then_success": "Transient error",
    "silent_fail": "Fabricated success",
    "misleading_success": "Fabricated success",
    "stale_data": "Stale response",
    "concurrent_modification": "Optimistic conflict",
    "rate_limit": "Rate limit",
    "session_expiry": "Session expiry",
    # Client
    "label_input_misalignment": "Label misbinding",
    "adjacent_selection": "Decoy element",
    "hide_affordance": "Hidden/restricted affordance",
    "false_banner": "Deceptive banner",
    "click_swallow": "Swallowed click",
    "input_corruption": "Input perturbation",
    "double_submit_trap": "Double-fire trap",
    "intercepting_overlay": "Intercepting overlay",
    "skeleton_never_resolves": "Stuck loader",
    "distractor_modal": "Interrupting modal",
}


def load_yaml(p: Path) -> dict:
    with open(p) as f:
        return yaml.safe_load(f) or {}


def normalize_instruction(text: str) -> str:
    if not text:
        return ""
    # Collapse the YAML block-scalar folding back into prose.
    return re.sub(r"\s+", " ", text).strip()


def load_human140_set() -> set[str]:
    panel = BENCH / "human" / "webstress_human_panel_v2_140.yaml"
    if not panel.exists():
        # legacy filename
        panel = BENCH / "human" / "webagentbench_human_panel_v2_140.yaml"
    if not panel.exists():
        return set()
    d = load_yaml(panel)
    out: set[str] = set()
    for entry in d.get("primary_panel") or []:
        tid = entry.get("base_task_id") if isinstance(entry, dict) else entry
        if tid:
            out.add(tid)
    return out


def load_duplicate_audit_set() -> set[str]:
    # Two sources: the panel YAML records the 35 duplicated task-conditions,
    # and the assignments YAML records the duplicate annotator assignments.
    out: set[str] = set()
    panel = BENCH / "human" / "webstress_human_panel_v2_140.yaml"
    if not panel.exists():
        panel = BENCH / "human" / "webagentbench_human_panel_v2_140.yaml"
    if panel.exists():
        d = load_yaml(panel)
        for entry in d.get("duplicate_subset") or []:
            tid = entry.get("base_task_id") if isinstance(entry, dict) else entry
            if tid:
                out.add(tid)
    assign = BENCH / "human" / "assignments_v1.yaml"
    if assign.exists():
        d = load_yaml(assign)
        for row in d.get("duplicate_condition_assignments") or []:
            tid = row.get("base")
            if tid:
                out.add(tid)
    return out


def main() -> int:
    if not BENCH.exists():
        sys.exit(
            f"missing benchmark at {BENCH}.\n"
            "Site assumes the WebStress benchmark code is checked out alongside as `webstress/`."
        )

    h140 = load_human140_set()
    audit = load_duplicate_audit_set()

    # Index every published variant by its base_task_id. The catalog ships
    # 519 *official* one-to-one pairings; on disk there are ~530 yamls because
    # 11 base tasks carry a backup variant. We pick the first published variant
    # alphabetically — same convention used to compute the paper's 519 number.
    variants_by_base: dict[str, dict] = {}
    for vp in sorted((BENCH / "injector" / "variants").glob("*.yaml")):
        v = load_yaml(vp)
        base = v.get("base_task_id")
        if not base or base in variants_by_base:
            continue
        action = ""
        for inj in v.get("injections") or []:
            params = inj.get("params") or {}
            action = params.get("action") or ""
            if action:
                break
        v["_layer"] = (v.get("injections") or [{}])[0].get("layer")
        v["_action"] = action
        v["_family"] = FAMILY_BY_ACTION.get(action) or action.replace("_", " ").title() or None
        v["_source"] = str(vp.relative_to(FORK_ROOT))
        variants_by_base[base] = v

    tasks: list[dict] = []
    primitive_counts: Counter = Counter()
    intervention_counts: Counter = Counter()
    env_difficulty_counts: dict = defaultdict(lambda: defaultdict(int))
    env_primitive_counts: dict = defaultdict(lambda: defaultdict(int))

    for tp in sorted((BENCH / "tasks").glob("*/*.yaml")):
        if tp.name.startswith("_"):
            continue
        t = load_yaml(tp)
        task_id = t.get("task_id")
        if not task_id:
            continue
        env_id = t.get("env_id")
        difficulty = t.get("difficulty")
        primary_prims = t.get("primary_primitives") or []
        if isinstance(primary_prims, str):
            primary_prims = [primary_prims]
        primary = primary_prims[0] if primary_prims else None
        secondary = (t.get("secondary_primitives") or [])
        if isinstance(secondary, str):
            secondary = [secondary]

        env_difficulty_counts[env_id][difficulty] += 1
        if primary:
            env_primitive_counts[env_id][primary] += 1
            primitive_counts[primary] += 1

        v = variants_by_base.get(task_id)
        if v:
            tp_target = v.get("target_primitive")
            intervention_counts[tp_target] += 1
            entry = {
                "task_id": task_id,
                "env_id": env_id,
                "title": t.get("title") or task_id.replace("_", " "),
                "public_instruction": normalize_instruction(t.get("instruction_template", "")),
                "difficulty": difficulty,
                "primary_primitive": primary,
                "secondary_primitives": secondary,
                "expected_steps": t.get("expected_steps") or 0,
                "time_limit_seconds": t.get("time_limit_seconds") or 0,
                "has_intervention": True,
                "variant_id": v.get("variant_id"),
                "target_primitive": tp_target,
                "intervention_layer": v.get("_layer"),
                "intervention_family": v.get("_family"),
                "intervention_summary_public": normalize_instruction(v.get("description", "")) or None,
                "human140": task_id in h140,
                "duplicate_audit": task_id in audit,
                "source_path": str(tp.relative_to(FORK_ROOT)),
            }
        else:
            entry = {
                "task_id": task_id,
                "env_id": env_id,
                "title": t.get("title") or task_id.replace("_", " "),
                "public_instruction": normalize_instruction(t.get("instruction_template", "")),
                "difficulty": difficulty,
                "primary_primitive": primary,
                "secondary_primitives": secondary,
                "expected_steps": t.get("expected_steps") or 0,
                "time_limit_seconds": t.get("time_limit_seconds") or 0,
                "has_intervention": False,
                "variant_id": None,
                "target_primitive": None,
                "intervention_layer": None,
                "intervention_family": None,
                "intervention_summary_public": None,
                "human140": task_id in h140,
                "duplicate_audit": task_id in audit,
                "source_path": str(tp.relative_to(FORK_ROOT)),
            }
        tasks.append(entry)

    tasks.sort(key=lambda x: (x["env_id"], x["task_id"]))

    # ---- emit tasks_index.json ----
    (OUT / "tasks_index.json").write_text(json.dumps(tasks, indent=2))

    # ---- emit primitives.json ----
    example_by_prim: dict[str, dict] = {}
    for entry in tasks:
        tp = entry.get("target_primitive")
        if tp and tp not in example_by_prim and entry.get("intervention_summary_public"):
            example_by_prim[tp] = entry
    primitive_cards = []
    for prim, meta in PRIMITIVE_CARDS.items():
        ex = example_by_prim.get(prim)
        primitive_cards.append(
            {
                "primitive": prim,
                "label": meta["label"],
                "definition": meta["definition"],
                "what_it_targets": meta["what_it_targets"],
                "typical_families": meta["typical_families"],
                "example_task_id": ex["task_id"] if ex else None,
                "example_intervention_summary": ex["intervention_summary_public"] if ex else None,
                "task_count": primitive_counts.get(prim, 0),
                "intervention_count": intervention_counts.get(prim, 0),
            }
        )
    (OUT / "primitives.json").write_text(json.dumps(primitive_cards, indent=2))

    # ---- emit environments.json ----
    env_cards = []
    for env_id, (label, domain, description) in ENV_CARDS.items():
        env_cards.append(
            {
                "env_id": env_id,
                "label": label,
                "domain": domain,
                "description": description,
                "task_count": sum(env_difficulty_counts[env_id].values()),
                "difficulty_counts": dict(env_difficulty_counts[env_id]),
                "primitive_counts": dict(env_primitive_counts[env_id]),
            }
        )
    (OUT / "environments.json").write_text(json.dumps(env_cards, indent=2))

    print(
        f"emitted: tasks_index.json ({len(tasks)} tasks), "
        f"primitives.json ({len(primitive_cards)}), "
        f"environments.json ({len(env_cards)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
