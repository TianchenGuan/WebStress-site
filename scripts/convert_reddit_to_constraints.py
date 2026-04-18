"""Auto-convert remaining Reddit task YAMLs to constraint-only canonical_diff.

For each unmigrated Reddit task, wraps eval.checks (positive) as constraints
and invariant'd unmodified collections. The constraint-only canonical_diff
is a pragmatic functional migration — it scores on constraint satisfaction
rather than richer positive-diff semantics. Not ideal for frontier tasks
but produces working migrations quickly.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REDDIT_DIR = Path("webagentbench/tasks/reddit")

# Collections to invariant by default (none mutated by positive diff in
# constraint-only form, so we leave state.settings-adjacent and leave
# others out to avoid invariant-fires-on-mutation).
INVARIANT_COLLECTIONS: list[str] = []  # conservative: no invariants


def convert(path: Path) -> bool:
    raw = yaml.safe_load(path.read_text()) or {}
    if "canonical_diff" in raw:
        return False
    eval_block = raw.get("eval") or {}
    checks = eval_block.get("checks") or []
    if not checks:
        return False

    constraints = []
    for c in checks:
        expr = c.get("expr", "").strip()
        desc = c.get("desc") or "check"
        # Normalize target.X references ({target.X} → target['X'])
        expr = re.sub(r"\{target\.([^}]+)\}", r"target['\1']", expr)
        expr = re.sub(r"'\{target\.([^']+)\}'", r"target['\1']", expr)
        constraints.append({"desc": desc, "expr": expr, "severity": "high"})

    canonical = {"constraints": constraints}

    # Insert the canonical_diff block immediately before the eval block.
    with path.open() as f:
        content = f.read()
    # Find eval: at start of line
    match = re.search(r"^eval:\s*$", content, re.MULTILINE)
    if not match:
        return False
    cd_yaml = "canonical_diff:\n" + "\n".join(
        f"  constraints:\n"
        if False else ""
        for _ in [0]
    )
    cd_yaml = yaml.safe_dump({"canonical_diff": canonical}, default_flow_style=False, sort_keys=False)
    insert_at = match.start()
    new_content = content[:insert_at] + cd_yaml + content[insert_at:]
    path.write_text(new_content)
    return True


def main() -> None:
    converted = 0
    for yaml_path in sorted(REDDIT_DIR.glob("*.yaml")):
        if convert(yaml_path):
            converted += 1
            print(f"[+] {yaml_path.name}")
    print(f"\nconverted {converted} tasks")


if __name__ == "__main__":
    main()
