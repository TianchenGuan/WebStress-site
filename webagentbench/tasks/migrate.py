"""Migration scaffolder — prints the complete authoring context for a task
so a human or LLM can write the canonical_diff block in one pass.

Usage:
    python -m webagentbench.tasks.migrate <task_id>
    python -m webagentbench.tasks.migrate <task_id> --prompt
    python -m webagentbench.tasks.migrate <task_id> --neighbors 3
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASKS_DIR = _REPO_ROOT / "webagentbench" / "tasks"
_MODELS_DIR = _REPO_ROOT / "webagentbench" / "backend" / "models"


def _find_task_yaml(task_id: str) -> Path | None:
    for path in _TASKS_DIR.rglob("*.yaml"):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("task_id") == task_id:
            return path
    return None


def _load_task_raw(task_id: str) -> tuple[Path, dict]:
    path = _find_task_yaml(task_id)
    if path is None:
        sys.stderr.write(f"Task {task_id!r} not found\n")
        sys.exit(1)
    return path, yaml.safe_load(path.read_text()) or {}


def _entity_classes(env_id: str) -> dict[str, list[tuple[str, str]]]:
    path = _MODELS_DIR / f"{env_id}.py"
    if not path.is_file():
        return {}
    src = path.read_text()
    classes: dict[str, list[tuple[str, str]]] = {}
    for m in re.finditer(
        r"^class\s+(\w+)\s*\(\s*BaseEntity\s*\)\s*:\s*\n((?:\s{4}.*\n)*)",
        src, re.MULTILINE,
    ):
        name = m.group(1)
        body = m.group(2)
        fields: list[tuple[str, str]] = []
        for line in body.splitlines():
            fm = re.match(r"\s{4}(\w+)\s*:\s*([^=]+?)(?:\s*=\s*.+)?$", line)
            if fm and not fm.group(1).isupper() and fm.group(1) != "model_config":
                if "ClassVar" in fm.group(2):
                    continue
                fields.append((fm.group(1), fm.group(2).strip()))
        if fields:
            classes[name] = fields
    return classes


def _state_collections(env_id: str) -> dict[str, str]:
    path = _MODELS_DIR / f"{env_id}.py"
    if not path.is_file():
        return {}
    src = path.read_text()
    m = re.search(
        r"^class\s+\w+State\s*\(\s*BaseEnvState\s*\)\s*:\s*\n((?:\s{4}.*\n)*)",
        src, re.MULTILINE,
    )
    if not m:
        return {}
    body = m.group(1)
    out = {}
    for line in body.splitlines():
        fm = re.match(r"\s{4}(\w+)\s*:\s*list\[(\w+)\]", line)
        if fm:
            out[fm.group(1)] = fm.group(2)
    return out


def _already_migrated_tasks(env_id: str | None = None) -> list[tuple[str, Path]]:
    out = []
    for path in _TASKS_DIR.rglob("*.yaml"):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        if raw.get("canonical_diff") is None:
            continue
        if env_id and raw.get("env_id") != env_id:
            continue
        out.append((raw["task_id"], path))
    return out


def _find_neighbors(task_id: str, task_raw: dict, limit: int = 2) -> list[tuple[str, Path]]:
    env = task_raw.get("env_id")
    candidates = [c for c in _already_migrated_tasks(env_id=env) if c[0] != task_id]
    primitives = set(task_raw.get("primary_primitives") or [])
    def sim(n):
        nraw = yaml.safe_load(n[1].read_text()) or {}
        return len(primitives & set(nraw.get("primary_primitives") or []))
    candidates.sort(key=sim, reverse=True)
    return candidates[:limit]


def _header(text: str) -> str:
    return f"\n{'=' * 72}\n  {text}\n{'=' * 72}\n"


def _print_instruction(raw: dict) -> str:
    instruction = raw.get("instruction_template") or raw.get("instruction") or "(missing)"
    return _header("1. INSTRUCTION TEMPLATE") + textwrap.fill(
        instruction, width=70, initial_indent="  ", subsequent_indent="  ") + "\n"


def _print_seed_outputs(raw: dict) -> str:
    lines = [_header("2. SEED OUTPUTS (available as target.*)")]
    seed = raw.get("seed") or {}
    steps = seed.get("steps") or []
    if not steps:
        return "".join(lines) + "\n  (no seed steps)\n"
    for i, step in enumerate(steps):
        use = step.get("use", "?")
        outputs = step.get("outputs") or []
        lines.append(f"\n  Step {i}: use={use!r}")
        for output in outputs:
            lines.append(f"    - target.{output}")
    targets = seed.get("targets") or {}
    if targets:
        lines.append("\n\n  Declared targets (bound into resolved_targets):")
        for key, value in targets.items():
            lines.append(f"    target.{key:<30}  <- {value}")
    return "\n".join(lines) + "\n"


def _print_env_schema(env_id: str) -> str:
    lines = [_header(f"3. ENV STATE SCHEMA - {env_id}")]
    collections = _state_collections(env_id)
    classes = _entity_classes(env_id)
    lines.append("\n  Top-level state.* collections:")
    for col, typ in collections.items():
        lines.append(f"    state.{col:<22}  list[{typ}]")
    lines.append("\n\n  Entity classes and fields:")
    for cls, fields in classes.items():
        lines.append(f"\n    class {cls}:")
        for fname, fann in fields:
            lines.append(f"      {fname:<26}  {fann}")
    return "\n".join(lines) + "\n"


def _print_legacy_checks(raw: dict) -> str:
    lines = [_header("4. LEGACY CHECKS (reference only - do not translate 1:1)")]
    block = raw.get("eval") or {}
    checks = block.get("checks") or []
    neg = block.get("negative_checks") or []
    lines.append(f"\n  Positive checks ({len(checks)}):")
    for c in checks:
        desc = (c.get("desc") or "").replace("\n", " ")
        expr = (c.get("expr") or "").replace("\n", " ").strip()
        lines.append(f"    [+] {desc}")
        lines.append(f"        expr: {expr[:100]}")
    lines.append(f"\n  Negative checks ({len(neg)}):")
    for c in neg:
        desc = (c.get("desc") or "").replace("\n", " ")
        expr = (c.get("expr") or "").replace("\n", " ").strip()
        penalty = c.get("penalty", "?")
        lines.append(f"    [-] {desc}  (penalty={penalty})")
        lines.append(f"        expr: {expr[:100]}")
    lines.append(
        "\n  NOTE: These capture what the original author thought was required. "
        "Re-derive from the instruction first (Protocol M1-M2); use as coverage sanity check."
    )
    return "\n".join(lines) + "\n"


def _print_neighbors(task_id: str, raw: dict, limit: int) -> str:
    lines = [_header("5. NEIGHBOR TEMPLATES (already-migrated, same env)")]
    neighbors = _find_neighbors(task_id, raw, limit=limit)
    if not neighbors:
        lines.append("\n  (no already-migrated tasks in this env yet - pilot!)")
        return "".join(lines) + "\n"
    for nid, npath in neighbors:
        nraw = yaml.safe_load(npath.read_text()) or {}
        cd = nraw.get("canonical_diff")
        lines.append(f"\n  -- {nid} ({npath.relative_to(_REPO_ROOT)})")
        if cd is not None:
            cd_yaml = yaml.safe_dump({"canonical_diff": cd}, default_flow_style=False, sort_keys=False)
            for line in cd_yaml.splitlines()[:60]:
                lines.append(f"    {line}")
    return "\n".join(lines) + "\n"


def _print_protocol_reminder() -> str:
    lines = [_header("6. AUTHORING PROTOCOL - 8-step reminder")]
    steps = [
        "1. Parse instruction - actor verb, target type, quantifier, identity, property, implicit invariants",
        "2. Identify entity types from Section 3 schema above",
        "3. Enumerate agent-mutable fields; classify each",
        "4. Derive create/update/delete; use bijection for 'for each' / 'all'",
        "5. Derive invariants. Default: every non-mentioned collection gets preserve: ALL",
        "6. Derive named_invariants; severity critical=0.3 high=0.2 medium=0.15 low=0.1",
        "7. Preview: python -m webagentbench.tasks.preview <task_id> --seed 42",
        "8. Validate: python -m webagentbench.tasks.validate <task_id>",
    ]
    lines.append("")
    for s in steps:
        lines.append(f"  {s}")
    lines.append("\n  Protocol: docs/guides/canonical-diff-authoring-protocol.md")
    lines.append("  Hazards:  docs/guides/canonical-diff-migration-hazards.md")
    return "\n".join(lines) + "\n"


def _print_llm_prompt(task_id: str, raw: dict, env_id: str) -> str:
    classes = _entity_classes(env_id)
    collections = _state_collections(env_id)
    instruction = raw.get("instruction_template") or raw.get("instruction") or ""
    seed = raw.get("seed") or {}
    targets_block = seed.get("targets") or {}

    schema_lines = []
    for cls, fields in classes.items():
        field_summary = ", ".join(f"{n}:{a.split('|')[0].strip()}" for n, a in fields[:8])
        schema_lines.append(f"  {cls}: {field_summary}")
    schema_text = "\n".join(schema_lines)
    target_keys = ", ".join(targets_block.keys())
    collections_str = "\n".join(f'  state.{c}: list[{t}]' for c, t in collections.items())

    body = f"""\
SYSTEM: You are a WebAgentBench task author. Produce a canonical_diff YAML
block following docs/guides/canonical-diff-authoring-protocol.md.

Required form:
  canonical_diff:
    create: [...]     # required state mutations (use bijection for "for each")
    update: [...]     # existing entities that must change (with where: selector)
    delete: [...]     # entities to remove
    invariant: [...]  # collections that must stay unchanged
    named_invariants: # labels mapped to diff entries
      - name: "Agent did not <verb> <object>"
        ref: invariant[N] | create[N] | update[N] | delete[N]
        severity: critical | high | medium | low

TASK
----
task_id: {task_id}
env_id: {env_id}

INSTRUCTION
-----------
{instruction}

AVAILABLE TARGETS
-----------------
{target_keys or '(none - seed may need extension; see Protocol M5)'}

ENV COLLECTIONS
---------------
{collections_str}

ENTITY FIELDS
-------------
{schema_text}

CHECKLIST:
  1. Actor verb maps to create / update / delete
  2. Quantifier "for each X" maps to bijection.over: target.X
  3. Identity constraints become predicates (eq, in, between, substring, ...)
  4. Collections not mentioned by the instruction become invariants
     (skip audit_log and system-managed collections)
  5. Name every invariant with a human-readable label via ref:

Output ONLY the canonical_diff YAML block, no preamble.
"""
    return _header("7. LLM PROMPT - ready to paste") + "\n" + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task_id")
    parser.add_argument("--prompt", action="store_true", help="Also emit the LLM prompt")
    parser.add_argument("--neighbors", type=int, default=2, help="How many neighbor tasks to show")
    parser.add_argument("--sections", default="all", help="Comma-separated section numbers (default all)")
    args = parser.parse_args()

    path, raw = _load_task_raw(args.task_id)
    env_id = raw.get("env_id") or "unknown"

    want = set(range(1, 8)) if args.sections == "all" else {int(s) for s in args.sections.split(",")}

    parts = []
    parts.append("=" * 72)
    parts.append(f"  MIGRATION SCAFFOLD: {args.task_id}")
    parts.append(f"  YAML: {path.relative_to(_REPO_ROOT)}")
    parts.append("=" * 72)

    if 1 in want:
        parts.append(_print_instruction(raw))
    if 2 in want:
        parts.append(_print_seed_outputs(raw))
    if 3 in want:
        parts.append(_print_env_schema(env_id))
    if 4 in want:
        parts.append(_print_legacy_checks(raw))
    if 5 in want:
        parts.append(_print_neighbors(args.task_id, raw, args.neighbors))
    if 6 in want:
        parts.append(_print_protocol_reminder())
    if args.prompt or 7 in want:
        parts.append(_print_llm_prompt(args.task_id, raw, env_id))

    print("\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
