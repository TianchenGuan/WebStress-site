import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# python tools/convert_osworld_examples_to_instructions.py \                                  ─╯
#     --test-index ../OSWorld/evaluation_examples/test_small.json \
#     --examples-dir ../OSWorld/evaluation_examples/examples \
#     --out-dir instructions/osworld_small \
#     --out-jsonl instructions/osworld_small.jsonl


# Try to reuse validator from this repo; fall back to a no-op if import path differs
try:
    from validation import validate_instruction
except Exception:  # pragma: no cover
    def validate_instruction(_: Dict[str, Any]) -> None:
        return


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _slugify(text: str, max_len: int = 60) -> str:
    t = str(text or "").strip().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t[:max_len].rstrip("-")) or "task"


def _infer_app_label(category: str) -> str:
    c = (category or "").lower()
    if c == "chrome":
        return "Browser"
    if c == "gimp":
        return "GIMP"
    if c in {"libreoffice_writer", "writer"}:
        return "Writer|Document|LibreOffice"
    if c in {"libreoffice_calc", "calc"}:
        return "Calc|Spreadsheet|LibreOffice"
    if c in {"libreoffice_impress", "impress"}:
        return "Impress|Slides|Presentation|LibreOffice"
    if c == "thunderbird":
        return "Mail|Thunderbird|Email"
    if c == "vlc":
        return "VLC|Media|Player"
    if c in {"vs_code", "vscode", "code"}:
        return "VS Code|Editor|Code"
    if c == "os":
        return "Settings|System"
    # multi_apps or unknown
    return "Desktop|Files|Browser"


def _gather_expected_terms(example: Dict[str, Any]) -> List[str]:
    terms: List[str] = []
    ev = example.get("evaluator") or {}
    exp = ev.get("expected")
    # expected may be dict or list; try rule.expected or rule.include
    if isinstance(exp, dict):
        rules = exp.get("rules") or {}
        for key in ("expected", "include"):
            vals = rules.get(key)
            if isinstance(vals, list):
                for v in vals:
                    if isinstance(v, str):
                        terms.append(v)
    elif isinstance(exp, list):
        # Terms less obvious here; ignore for now
        pass
    # Fallback: look for result types that hint filenames
    res = ev.get("result")
    if isinstance(res, dict) and res.get("type") == "vm_command_line":
        # no direct terms
        pass
    return terms


def _gather_candidate_filepaths(example: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    # evaluator.result may include vm_file entries (or list of them)
    ev = example.get("evaluator") or {}
    res = ev.get("result")
    if isinstance(res, dict):
        if res.get("type") == "vm_file":
            p = res.get("path")
            if isinstance(p, str) and p.startswith("/"):
                paths.append(p)
    elif isinstance(res, list):
        for item in res:
            if isinstance(item, dict) and item.get("type") == "vm_file":
                p = item.get("path")
                if isinstance(p, str) and p.startswith("/"):
                    paths.append(p)
    # config may include an open/path which indicates a relevant file
    for step in example.get("config") or []:
        if isinstance(step, dict) and step.get("type") in {"open", "download"}:
            params = step.get("parameters") or {}
            p = params.get("path") or params.get("dest")
            if isinstance(p, str) and p.startswith("/"):
                paths.append(p)
            files = params.get("files")
            if isinstance(files, list):
                for f in files:
                    if isinstance(f, dict):
                        pp = f.get("path")
                        if isinstance(pp, str) and pp.startswith("/"):
                            paths.append(pp)
    # Deduplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for p in paths:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq


def _criteria_from_example(category: str, description: str, example: Dict[str, Any]) -> List[Dict[str, Any]]:
    crit: List[Dict[str, Any]] = []
    # App presence (light weight)
    app_label = _infer_app_label(category)
    if app_label:
        crit.append({"predicate": f"element_text_contains:{app_label}", "weight": 0.3})

    # Task-specific: expected terms or file existence
    terms = _gather_expected_terms(example)
    filepaths = _gather_candidate_filepaths(example)

    added_specific = False
    if terms:
        # Join a few high-signal terms
        snippet = "|".join([t for t in terms[:4] if isinstance(t, str) and t.strip()])
        if snippet:
            crit.append({"predicate": f"element_text_contains:{snippet}", "weight": 0.7})
            added_specific = True
    elif filepaths:
        # Prefer the first concrete VM path
        crit.append({"predicate": f"file_exists:{filepaths[0]}", "weight": 0.7})
        added_specific = True

    # Heuristic fallbacks based on description keywords
    if not added_specific:
        d = description.lower()
        if any(k in d for k in ["save", "export", "download", "create file", "write file", "screenshot"]):
            crit.append({"predicate": "element_text_contains:Saved|Exported|Downloaded|Created", "weight": 0.7})
        elif any(k in d for k in ["search engine", "homepage", "bookmark", "password", "extension"]):
            crit.append({"predicate": "element_text_contains:Settings|Preferences|Applied", "weight": 0.7})
        elif any(k in d for k in ["bold", "italic", "spacing", "font", "style", "format", "insert"]):
            crit.append({"predicate": "element_text_contains:Format|Applied|Updated", "weight": 0.7})
        else:
            crit.append({"predicate": "element_text_contains:Done|Success|Applied", "weight": 0.7})

    return crit


def convert_one(category: str, example: Dict[str, Any]) -> Dict[str, Any]:
    desc = str(example.get("instruction") or example.get("description") or "Desktop task")
    rid = str(example.get("id") or _slugify(desc))
    out: Dict[str, Any] = {
        "id": rid,
        "description": desc,
        "template": "desktop",
        "difficulty": "medium",
        "time_limit": 90,
        "success_criteria": _criteria_from_example(category, desc, example),
    }
    cfg = example.get("config")
    if isinstance(cfg, list) and cfg:
        out["config"] = cfg
    validate_instruction(out)
    return out


def _iter_test_index(index_json: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for category, ids in (index_json or {}).items():
        if not isinstance(ids, list):
            continue
        for tid in ids:
            if isinstance(tid, str):
                pairs.append((category, tid))
    return pairs


def main() -> None:
    p = argparse.ArgumentParser(description="Convert OSWorld evaluation examples to LLMOS Instruction JSONs.")
    p.add_argument("--test-index", default=os.path.join("OSWorld", "evaluation_examples", "test_small.json"), help="Path to test_small.json (or similar index)")
    p.add_argument("--examples-dir", default=os.path.join("OSWorld", "evaluation_examples", "examples"), help="Base directory of examples by category")
    p.add_argument("--out-dir", default=os.path.join("LLMOS", "instructions", "osworld_small"), help="Directory to write instruction JSON files")
    p.add_argument("--out-jsonl", default=os.path.join("LLMOS", "instructions", "osworld_small.jsonl"), help="Aggregate JSONL output path")
    args = p.parse_args()

    index = _read_json(args.test_index)
    pairs = _iter_test_index(index)
    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.out_jsonl), exist_ok=True)

    count = 0
    with open(args.out_jsonl, "w", encoding="utf-8") as outjl:
        for category, tid in pairs:
            # Build path: <examples_dir>/<category>/<id>.json
            path = os.path.join(args.examples_dir, category, f"{tid}.json")
            try:
                example = _read_json(path)
            except Exception as e:
                print(f"Skipping {path}: {e}")
                continue
            try:
                instr = convert_one(category, example)
            except Exception as e:
                print(f"Skipping {path} (convert error): {e}")
                continue
            # Write JSONL and per-file JSON
            outjl.write(json.dumps(instr, ensure_ascii=False, sort_keys=True) + "\n")
            out_path = os.path.join(args.out_dir, f"{instr['id']}.json")
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(instr, f, indent=2, ensure_ascii=False, sort_keys=True)
            except Exception as e:
                print(f"Failed writing {out_path}: {e}")
                continue
            count += 1

    print(f"Converted {count} tasks → {args.out_dir}/ and {args.out_jsonl}")


if __name__ == "__main__":
    main()
