#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install PyYAML or run with the package's [yaml] extra") from exc


def walk_exprs(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "expr" and isinstance(child, str):
                count += 1
            count += walk_exprs(child)
    elif isinstance(value, list):
        for child in value:
            count += walk_exprs(child)
    return count


def audit(root: Path) -> dict[str, Any]:
    yamls = sorted(root.rglob("*.yaml"))
    out: dict[str, Any] = {
        "task_yaml_total": len(yamls),
        "canonical_diff_tasks": 0,
        "legacy_eval_tasks": 0,
        "tasks_with_both_blocks": 0,
        "env_counts": {},
        "legacy_expr_count": 0,
        "legacy_expr_lines": 0,
        "target_template_references": 0,
        "raw_initial_snapshot_references": 0,
        "canonical_expr_predicate_count": 0,
        "yaml_load_errors": [],
    }
    for path in yamls:
        env = path.parent.name
        out["env_counts"][env] = out["env_counts"].get(env, 0) + 1
        text = path.read_text(errors="ignore")
        out["target_template_references"] += len(re.findall(r"\{target\.[^}]+\}", text))
        out["raw_initial_snapshot_references"] += text.count("_initial_snapshot")
        try:
            data = yaml.safe_load(text) or {}
        except Exception as exc:  # pragma: no cover - depends on corpus
            out["yaml_load_errors"].append({"path": str(path), "error": str(exc)})
            continue
        has_canonical = bool(data.get("canonical_diff"))
        eval_block = data.get("eval") or {}
        checks = eval_block.get("checks") or []
        negatives = eval_block.get("negative_checks") or []
        has_legacy = bool(checks or negatives)
        out["canonical_diff_tasks"] += int(has_canonical)
        out["legacy_eval_tasks"] += int(has_legacy)
        out["tasks_with_both_blocks"] += int(has_canonical and has_legacy)
        for entry in [*checks, *negatives]:
            if isinstance(entry, dict) and isinstance(entry.get("expr"), str):
                out["legacy_expr_count"] += 1
                out["legacy_expr_lines"] += entry["expr"].count("\n") + 1
        if has_canonical:
            out["canonical_expr_predicate_count"] += walk_exprs(data["canonical_diff"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.tasks_root)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
