#!/usr/bin/env python3
"""Scan the generated public website assets for unsafe strings.

Fails loud if any of the public JSON files or static assets contain:
  - API keys, tokens, controller secrets
  - private absolute paths (/home/, /Users/, /mnt/, /usr/project/xtmp/)
  - real annotator names (we want only P1-P4 / D1-D4 codes)
  - .env file references
  - raw model-provider response logs
  - hidden evaluator predicates (`canonical_diff`, `target` placeholders)
  - free-text human rubric comments
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent

# Each (pattern, label, severity). Severity "fail" stops the build.
# `info` is a soft warning that just gets reported.
PATTERNS: list[tuple[str, str, str]] = [
    (r"(?i)\b(api[_-]?key|secret|token|password)\b", "credential keyword", "fail"),
    (r"controller[_-]?secret", "controller secret", "fail"),
    (r"X-WAB-Controller-Secret", "controller secret header", "fail"),
    (r"ANTHROPIC_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY|HF_TOKEN", "live provider key var", "fail"),
    (r"\b(?:Weili|Michael|Xunjian|Tianchen|Keagan|Kyle|Royce|Daisy)\b", "real annotator name", "fail"),
    (r"/home/users/\w+|/Users/\w+|/mnt/\w+|/usr/project/xtmp/\w+", "private absolute path", "fail"),
    (r"\.env(?!\.example)", ".env file reference", "fail"),
    (r"raw_response|provider_response|raw_model_response", "raw provider response field", "fail"),
    # JSON key (quote+colon) that names a hidden evaluator predicate, NOT
    # the literal word appearing inside a variant description string.
    (r'"(canonical_diff|evaluator_expr|positive_obligations|negative_invariants)"\s*:', "hidden evaluator predicate key", "fail"),
    (r'"fields"\s*:\s*\{[^}]*"eq"\s*:', "evaluator field-equality predicate", "fail"),
    (r"free_text_comments?|rubric_freetext", "raw rubric free-text", "fail"),
    # `target:` blocks in YAML can leak the hidden ground truth; warn if any slip
    # into JSON exports.
    (r'"target":\s*\{', "hidden target block", "fail"),
]


def scan_text(text: str, label: str) -> list[tuple[str, str, str, str]]:
    """Return list of (label, severity, pattern_label, snippet) for every hit."""
    hits = []
    for patt, plabel, sev in PATTERNS:
        for m in re.finditer(patt, text):
            ctx_start = max(0, m.start() - 30)
            ctx_end = min(len(text), m.end() + 30)
            snippet = text[ctx_start:ctx_end].replace("\n", " ")
            hits.append((label, sev, plabel, snippet))
    return hits


def main() -> int:
    public = SITE / "public"
    if not public.exists():
        print(f"no public/ dir at {public}", file=sys.stderr)
        return 1

    targets: list[Path] = []
    targets.extend(public.glob("data/*.json"))
    targets.extend(public.glob("data/**/*.json"))

    all_hits: list[tuple[str, str, str, str]] = []
    for f in sorted(targets):
        try:
            text = f.read_text()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        rel = f.relative_to(SITE)
        all_hits.extend((str(rel), sev, plabel, snip) for (_, sev, plabel, snip) in scan_text(text, str(rel)))

    # Also scan that the generated JSON validates and matches expected shapes.
    tasks_path = public / "data" / "tasks_index.json"
    if tasks_path.exists():
        try:
            tasks = json.loads(tasks_path.read_text())
            assert isinstance(tasks, list)
            assert all("task_id" in t for t in tasks), "tasks_index missing task_id"
            assert all("public_instruction" in t for t in tasks), "tasks_index missing public_instruction"
            assert not any("canonical_diff" in t for t in tasks), "tasks_index leaked canonical_diff!"
            assert not any("target" in t and isinstance(t.get("target"), dict) for t in tasks), \
                "tasks_index leaked hidden target!"
            print(f"shape ok: tasks_index.json ({len(tasks)} entries)")
        except (json.JSONDecodeError, AssertionError) as e:
            print(f"FAIL shape check: {e}", file=sys.stderr)
            return 2

    fails = [h for h in all_hits if h[1] == "fail"]
    infos = [h for h in all_hits if h[1] == "info"]

    for path, sev, plabel, snip in fails:
        print(f"[FAIL] {path}: {plabel}  →  …{snip}…")
    for path, sev, plabel, snip in infos:
        print(f"[info] {path}: {plabel}  →  …{snip}…")

    if fails:
        print(f"\n{len(fails)} unsafe match(es) detected — refusing to ship public assets.", file=sys.stderr)
        return 3

    print(f"public export clean. scanned {len(targets)} files, "
          f"{len(infos)} info-only match(es).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
