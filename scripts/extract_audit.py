"""Extract slim per-task audit files from the baseline + variant result shards.

Creates audits/booking/<task_id>.json with:
  - task_id, difficulty, expected_steps, instruction, canonical_diff
  - baseline: {score, success, reasoning, checks, negative_checks, steps, elapsed, trajectory[], urls[]}
  - variant: {score, success, reasoning, checks, steps, elapsed, trajectory[], urls[], perturbation_type, perturbation_description}
"""
import json
from pathlib import Path
import glob
import yaml

ROOT = Path("/home/users/tg295/projects/LLMOS")
OUT = ROOT / "audits/booking"
OUT.mkdir(parents=True, exist_ok=True)

TASK_DIR = ROOT / "webagentbench/tasks/booking"
VARIANT_DIR = ROOT / "webagentbench/injector/variants"
BASELINE_GLOB = "results/webagentbench/booking_full/11207384_*.json"
VARIANT_GLOB = "results/webagentbench/booking_variants/11207443/*.json"


def _slim_traj(traj):
    """Drop DOM text; keep step number, thought (truncated), action, URL, status."""
    out = []
    for s in traj:
        out.append({
            "step": s.get("step"),
            "thought": (s.get("thought", "") or "")[:220],
            "action": s.get("action"),
            "targets": s.get("targets"),
            "url": s.get("replay_path") or s.get("result_path") or "",
            "status": s.get("status"),
            "elapsed": s.get("elapsed_seconds"),
        })
    return out


def _load_yaml(p):
    if not p.exists():
        return None
    with open(p) as f:
        return yaml.safe_load(f)


def _load_baseline_by_task():
    by_task = {}
    for f in sorted((ROOT).glob(BASELINE_GLOB)):
        d = json.load(open(f))
        rs = d.get("results", []) if isinstance(d, dict) else d
        for r in rs:
            by_task[r["task_id"]] = r
    return by_task


def _load_variant_by_task():
    by_task = {}
    for f in sorted((ROOT).glob(VARIANT_GLOB)):
        d = json.load(open(f))
        rs = d.get("results", []) if isinstance(d, dict) else d
        for r in rs:
            # each variant file contains the base task_id; we also want the variant meta
            task_id = r["task_id"]
            by_task[task_id] = {"result": r, "file": f.name, "degradation": d.get("degradation") if isinstance(d, dict) else None}
    return by_task


def main():
    baseline = _load_baseline_by_task()
    variant = _load_variant_by_task()

    for yp in sorted(TASK_DIR.glob("*.yaml")):
        task_def = _load_yaml(yp) or {}
        task_id = task_def.get("task_id") or yp.stem
        b = baseline.get(task_id)
        v = variant.get(task_id)

        audit = {
            "task_id": task_id,
            "difficulty": task_def.get("difficulty"),
            "expected_steps": task_def.get("expected_steps"),
            "time_limit_seconds": task_def.get("time_limit_seconds"),
            "primary_primitives": task_def.get("primary_primitives"),
            "instruction": task_def.get("instruction_template", "").strip(),
            "canonical_diff": task_def.get("canonical_diff"),
            "start_path": task_def.get("start_path"),
            "baseline": None,
            "variant": None,
        }

        if b:
            audit["baseline"] = {
                "score": b["evaluation"]["score"],
                "success": b["evaluation"].get("success"),
                "reasoning": b["evaluation"].get("reasoning"),
                "checks": b["evaluation"].get("checks"),
                "negative_checks": b["evaluation"].get("negative_checks"),
                "steps": b["agent"]["steps"],
                "elapsed_seconds": b["agent"]["elapsed_seconds"],
                "completed": b["agent"]["completed"],
                "trajectory": _slim_traj(b["agent"]["trajectory"]),
            }

        if v:
            vr = v["result"]
            deg = v.get("degradation") or {}
            audit["variant"] = {
                "variant_id": deg.get("variant_id"),
                "target_primitive": deg.get("target_primitive"),
                "perturbation_description": deg.get("description"),
                "score": vr["evaluation"]["score"],
                "success": vr["evaluation"].get("success"),
                "reasoning": vr["evaluation"].get("reasoning"),
                "checks": vr["evaluation"].get("checks"),
                "negative_checks": vr["evaluation"].get("negative_checks"),
                "steps": vr["agent"]["steps"],
                "elapsed_seconds": vr["agent"]["elapsed_seconds"],
                "completed": vr["agent"]["completed"],
                "trajectory": _slim_traj(vr["agent"]["trajectory"]),
            }

        out_path = OUT / f"{task_id}.json"
        out_path.write_text(json.dumps(audit, indent=2, default=str))

    print(f"Wrote {len(list(OUT.glob('*.json')))} audit files to {OUT}")


if __name__ == "__main__":
    main()
