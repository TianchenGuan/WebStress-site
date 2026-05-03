"""Re-aggregate PrimBench v2 results across 6 models into a unified score matrix.

Background: each model's summary.json reflects only the *last* sbatch that
collaborator ran for that model — so summary.n is sometimes < total dispatches
because the trajectory.json files on disk are the union of multiple batches.
qwen has the opposite case: summary.results contains entries with
trajectory_path=None for tasks that crashed before producing a trajectory.

This script ignores the per-model summary.n / passed and rebuilds from
ground truth = union of (task_id, cond) keys seen across all 6 models.

For each (model, task_id, cond) cell:
  - prefer per-task trajectory.json's evaluation block (most authoritative)
  - else fall back to the matching entry in summary.json's results list
  - else mark as 'missing'

Output: long-format CSV + per-model + per-(env,cond) summary tables.

Usage:
    python scripts/aggregate_primbench_v2.py \\
        --root /usr/xtmp/tg295/primbench-results-v2 \\
        --out  /usr/xtmp/tg295/primbench-aggregate
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

MODELS = [
    "gemini_3_1_pro",
    "gemini_3_flash",
    "gpt_5_4",
    "gpt_5_4_mini",
    "opus_4_7",
    "qwen3_vl_235b",
]


def _load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _key(task_id: str, cond: str) -> str:
    return f"{task_id}__{cond}"


# task_id prefix → env name (some envs use abbreviated prefixes, e.g. pp_*)
_ENV_PREFIXES: tuple[tuple[str, str], ...] = (
    ("amazon_", "amazon"),
    ("booking_", "booking"),
    ("gmail_", "gmail"),
    ("lms_", "lms"),
    ("pp_", "patient_portal"),
    ("reddit_", "reddit"),
    ("rh_", "robinhood"),
)


def _parse_dirname(name: str) -> tuple[str, str]:
    if name.endswith("__clean"):
        return name[: -len("__clean")], "clean"
    if name.endswith("__intervention"):
        return name[: -len("__intervention")], "intervention"
    return name, "?"


def _env_from_task_id(task_id: str | None) -> str | None:
    if not task_id:
        return None
    for prefix, env in _ENV_PREFIXES:
        if task_id.startswith(prefix):
            return env
    return None


def _scan_model(model_dir: Path) -> dict[str, dict]:
    """Return {key: cell} for one model.

    Two data sources, used for different fields:
      - summary.json results[] → pick_metadata (task_id, cond, env, diff, variant)
      - tasks/<key>/trajectory.json → evaluation (score, success, steps, elapsed)

    summary entries with trajectory_path=None (qwen launcher-failure
    placeholders) carry their own evaluation block — surface those too.
    cell.source ∈ {'trajectory', 'summary'}
    """
    cells: dict[str, dict] = {}
    summary = _load_json(model_dir / "summary.json") or {}
    summary_index: dict[str, dict] = {}
    for r in summary.get("results", []):
        pm = r.get("pick_metadata") or {}
        task_id = pm.get("task_id") or r.get("task_id")
        cond = pm.get("cond") or ("intervention" if (r.get("variant_filename") or pm.get("variant_filename")) else "clean")
        summary_index[_key(task_id, cond)] = r

    tasks_dir = model_dir / "tasks"
    if tasks_dir.is_dir():
        for td in sorted(tasks_dir.iterdir()):
            if not td.is_dir():
                continue
            key = td.name
            traj = _load_json(td / "trajectory.json")
            if not traj:
                continue
            ev = traj.get("evaluation") or {}
            agent = traj.get("agent") or {}
            sm_entry = summary_index.get(key) or {}
            sm_pm = sm_entry.get("pick_metadata") or {}
            task_id, cond = _parse_dirname(key)
            tid = sm_pm.get("task_id") or task_id
            cells[key] = {
                "task_id": tid,
                "cond": sm_pm.get("cond") or cond,
                "env": sm_pm.get("env") or _env_from_task_id(tid),
                "diff": sm_pm.get("diff"),
                "variant_filename": sm_pm.get("variant_filename")
                    or sm_entry.get("variant_filename"),
                "score": ev.get("score"),
                "success": ev.get("success"),
                "steps": len(traj.get("steps") or []),
                "elapsed_seconds": agent.get("elapsed_seconds"),
                "source": "trajectory",
            }

    # summary-only entries (e.g. qwen tasks where _run_one crashed before
    # producing any trajectory.json — score/success still recorded by runner)
    for key, r in summary_index.items():
        if key in cells:
            continue
        ev = r.get("evaluation") or {}
        pm = r.get("pick_metadata") or {}
        task_id, cond = _parse_dirname(key)
        tid = pm.get("task_id") or r.get("task_id") or task_id
        cells[key] = {
            "task_id": tid,
            "cond": pm.get("cond") or cond,
            "env": pm.get("env") or _env_from_task_id(tid),
            "diff": pm.get("diff"),
            "variant_filename": pm.get("variant_filename") or r.get("variant_filename"),
            "score": ev.get("score"),
            "success": ev.get("success"),
            "steps": None,
            "elapsed_seconds": (r.get("agent") or {}).get("elapsed_seconds"),
            "source": "summary",
        }

    return cells


def _format_pct(n: int, total: int) -> str:
    if total <= 0:
        return "  -- "
    return f"{100*n/total:5.1f}%"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, help="dir containing per-model subdirs")
    p.add_argument("--out", required=True, help="output dir for CSV + tables")
    args = p.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    per_model: dict[str, dict[str, dict]] = {}
    for m in MODELS:
        md = root / m
        if not md.is_dir():
            print(f"  WARN: missing {md}")
            continue
        per_model[m] = _scan_model(md)
        print(f"  scanned {m}: {len(per_model[m])} cells")

    # union of dispatch keys = ground-truth dispatch set
    all_keys: set[str] = set()
    key_meta: dict[str, dict] = {}
    for m, cells in per_model.items():
        for k, c in cells.items():
            all_keys.add(k)
            if k not in key_meta:
                key_meta[k] = {
                    "task_id": c["task_id"],
                    "cond": c["cond"],
                    "env": c["env"],
                    "diff": c["diff"],
                    "variant_filename": c["variant_filename"],
                }
            else:
                # backfill from any model that had richer pick_metadata
                for f in ("env", "diff", "variant_filename"):
                    if not key_meta[k].get(f) and c.get(f):
                        key_meta[k][f] = c[f]

    print(f"\nunion dispatch keys: {len(all_keys)}")

    # write long CSV: one row per (model, key)
    csv_path = out / "scores_long.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "model", "task_id", "cond", "env", "diff", "variant_filename",
            "score", "success", "steps", "elapsed_seconds", "source",
        ])
        for m in MODELS:
            cells = per_model.get(m, {})
            for k in sorted(all_keys):
                meta = key_meta[k]
                c = cells.get(k)
                if c is None:
                    w.writerow([
                        m, meta["task_id"], meta["cond"], meta["env"], meta["diff"],
                        meta["variant_filename"], "", "", "", "", "missing",
                    ])
                else:
                    w.writerow([
                        m, c.get("task_id") or meta["task_id"], c.get("cond") or meta["cond"],
                        c.get("env") or meta["env"], c.get("diff") or meta["diff"],
                        c.get("variant_filename") if c.get("variant_filename") is not None else meta["variant_filename"],
                        c.get("score"), c.get("success"), c.get("steps"),
                        c.get("elapsed_seconds"), c.get("source"),
                    ])
    print(f"wrote {csv_path}")

    # per-model topline (relative to union dispatch)
    print(f"\n{'='*78}\nper-model (denominator = union of {len(all_keys)} dispatch keys)\n{'='*78}")
    print(f"{'model':18} {'attempted':>10} {'evaluated':>10} {'passed':>8} "
          f"{'pass-rate':>10} {'avg-score':>10} {'missing':>8}")
    rows = []
    for m in MODELS:
        cells = per_model.get(m, {})
        attempted = 0   # has any source (trajectory or summary placeholder)
        evaluated = 0   # score is not None
        passed = 0
        score_sum = 0.0
        score_n = 0
        for k in all_keys:
            c = cells.get(k)
            if c is None:
                continue
            attempted += 1
            sc = c.get("score")
            if sc is not None:
                evaluated += 1
                score_sum += float(sc)
                score_n += 1
                if c.get("success"):
                    passed += 1
        missing = len(all_keys) - attempted
        avg = score_sum / score_n if score_n else 0.0
        rows.append({
            "model": m,
            "attempted": attempted,
            "evaluated": evaluated,
            "passed": passed,
            "pass_rate": passed / len(all_keys) if all_keys else 0.0,
            "avg_score": avg,
            "missing": missing,
        })
        print(f"{m:18} {attempted:>10d} {evaluated:>10d} {passed:>8d} "
              f"{_format_pct(passed, len(all_keys)):>10} {avg:>10.4f} {missing:>8d}")

    (out / "topline.json").write_text(json.dumps({
        "n_dispatch_keys": len(all_keys),
        "rows": rows,
    }, indent=2))
    print(f"\nwrote {out/'topline.json'}")

    # per (env, cond) breakdown — average across 6 models, only counting evaluated cells
    print(f"\n{'='*78}\nper (env, cond) breakdown across 6 models\n{'='*78}")
    bucket = defaultdict(lambda: defaultdict(list))  # bucket[env][cond] = [scores]
    for m, cells in per_model.items():
        for k, c in cells.items():
            sc = c.get("score")
            env = c.get("env")
            cond = c.get("cond")
            if sc is None or not env or not cond:
                continue
            bucket[env][cond].append(float(sc))
    print(f"{'env':14} {'cond':14} {'n':>6} {'avg':>8} {'pass%':>8}")
    for env in sorted(bucket):
        for cond in sorted(bucket[env]):
            xs = bucket[env][cond]
            n = len(xs)
            avg = sum(xs) / n if n else 0
            pass_n = sum(1 for x in xs if x >= 0.5)
            print(f"{env:14} {cond:14} {n:>6} {avg:>8.3f} "
                  f"{_format_pct(pass_n, n):>8}")

    # clean → intervention delta per env, per model
    print(f"\n{'='*78}\nclean → intervention pass-rate delta (per env, per model)\n{'='*78}")
    print(f"{'env':14} " + " ".join(f"{m[:11]:>11}" for m in MODELS))
    env_set = sorted({c.get("env") for cells in per_model.values() for c in cells.values() if c.get("env")})
    for env in env_set:
        deltas = []
        for m in MODELS:
            cells = per_model.get(m, {})
            cs = [c for c in cells.values() if c.get("env") == env and c.get("cond") == "clean" and c.get("success") is not None]
            ints = [c for c in cells.values() if c.get("env") == env and c.get("cond") == "intervention" and c.get("success") is not None]
            cp = sum(1 for c in cs if c.get("success")) / len(cs) if cs else None
            ip = sum(1 for c in ints if c.get("success")) / len(ints) if ints else None
            if cp is None or ip is None:
                deltas.append("       --")
            else:
                deltas.append(f"  {(cp-ip)*100:+5.1f}pp")
        print(f"{env:14} " + " ".join(deltas))

    print(f"\n{'='*78}\ndone. CSV: {csv_path}\n{'='*78}")


if __name__ == "__main__":
    main()
