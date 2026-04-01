"""Task linter — catches benchmark construction bugs before any model run.

Checks every task YAML and variant YAML for:
  1. Eval expression syntax (must be valid Python after target substitution)
  2. Operator precedence traps (``and ... or`` without parentheses)
  3. Answer leakage (hardcoded answers in instruction_template)
  4. Actor name determinism (actors referenced in instructions need explicit names)
  5. Target reference integrity (every {target.X} in eval must be defined)
  6. Variant response_body schema validity (fake responses must match real API)
  7. Variant base_task_id validity (must reference an existing task)
  8. Eval expression attribute validity (only real model fields used)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

TASKS_DIR = Path(__file__).parent.parent / "tasks" / "gmail"
VARIANTS_DIR = Path(__file__).parent.parent / "injector" / "variants"
TARGET_RE = re.compile(r"\{target\.([^}]+)\}")
ACTOR_REF_RE = re.compile(r"\{actor\.(\w+)")


# ── helpers ──────────────────────────────────────────────────────────────

def _load_all_tasks() -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for path in sorted(TASKS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw and "task_id" in raw:
            tasks[raw["task_id"]] = raw
    return tasks


def _load_all_variants() -> list[tuple[str, dict[str, Any]]]:
    variants: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(VARIANTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw:
            variants.append((path.name, raw))
    return variants


def _collect_eval_exprs(task: dict) -> list[tuple[str, str, str]]:
    """Return (task_id, kind, expr) for every check expression."""
    ev = task.get("eval")
    if not ev:
        return []
    tid = task["task_id"]
    items: list[tuple[str, str, str]] = []
    for check in ev.get("checks") or []:
        expr = check["expr"] if isinstance(check, dict) else str(check)
        items.append((tid, "check", expr))
    for neg in ev.get("negative_checks") or []:
        expr = neg["expr"] if isinstance(neg, dict) else str(neg)
        items.append((tid, "neg_check", expr))
    return items


ALL_TASKS = _load_all_tasks()
ALL_VARIANTS = _load_all_variants()
ALL_EXPRS = []
for _t in ALL_TASKS.values():
    ALL_EXPRS.extend(_collect_eval_exprs(_t))


# ── 1. Eval expression syntax ────────────────────────────────────────────

@pytest.mark.parametrize(
    "task_id,kind,expr",
    ALL_EXPRS,
    ids=[f"{tid}:{kind}:{i}" for i, (tid, kind, _) in enumerate(ALL_EXPRS)],
)
def test_eval_expression_is_valid_python(task_id: str, kind: str, expr: str) -> None:
    """Every eval expression must parse as valid Python after target substitution."""
    # Replace {target.X} with a safe placeholder string
    test_expr = TARGET_RE.sub('"__placeholder__"', expr)
    try:
        ast.parse(test_expr, mode="eval")
    except SyntaxError as exc:
        pytest.fail(
            f"[{task_id}] {kind} expression has syntax error: {exc}\n"
            f"  raw:  {expr[:200]}\n"
            f"  test: {test_expr[:200]}"
        )


# ── 2. Operator precedence traps ─────────────────────────────────────────

@pytest.mark.parametrize(
    "task_id,kind,expr",
    ALL_EXPRS,
    ids=[f"{tid}:{kind}:{i}" for i, (tid, kind, _) in enumerate(ALL_EXPRS)],
)
def test_no_unparenthesized_and_or(task_id: str, kind: str, expr: str) -> None:
    """Flag ``A and B or C`` inside generator expressions (likely precedence bug).

    The pattern ``any(X and Y or Z for ...)`` evaluates as ``(X and Y) or Z``
    which almost always means the ``Z`` clause matches independent of ``X``.
    """
    # Find generator-expression bodies: content between ( and `for VAR in`)
    gen_re = re.compile(r"(?:any|all)\((.+?)\s+for\s+\w+\s+in\b", re.DOTALL)
    for m in gen_re.finditer(expr):
        body = m.group(1)
        # Look for `and ... or` where or is NOT inside parens
        parts = re.split(r"\b(and|or)\b", body)
        depth = 0
        saw_and = False
        for part in parts:
            part_stripped = part.strip()
            if part_stripped == "and":
                saw_and = True
                continue
            if part_stripped == "or" and saw_and and depth == 0:
                pytest.fail(
                    f"[{task_id}] {kind}: likely precedence bug — "
                    f"'and ... or' without parens in generator body.\n"
                    f"  expr: {expr[:200]}"
                )
            depth += part.count("(") - part.count(")")


# ── 3. Answer leakage in instructions ────────────────────────────────────

def test_no_answer_leakage_in_instructions() -> None:
    """Target values that are actual answers must not appear in instruction_template.

    Targets defined as literal values (not ``{output.X}`` or ``{actor.X}`` refs)
    are answer data. If they appear verbatim in the instruction, the agent
    doesn't need to do the task — the answer is given.
    """
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        instr = task.get("instruction_template", "") or task.get("instruction", "")
        targets = (task.get("seed") or {}).get("targets") or {}
        for tkey, tval in targets.items():
            if not isinstance(tval, str):
                continue
            # Skip template references — those are not literal values
            if tval.startswith("{"):
                continue
            if tval in instr:
                violations.append(
                    f"[{tid}] literal target '{tkey}' = '{tval}' "
                    f"appears in instruction_template"
                )
    assert not violations, "\n".join(violations)


# ── 4. Actor name determinism ────────────────────────────────────────────

def test_actors_referenced_in_instructions_have_explicit_names() -> None:
    """If an actor's name flows into the instruction, it must be explicit.

    Actors without ``name:`` get a random name from FakeDataGenerator,
    making the instruction non-deterministic across seeds.
    """
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        instr = task.get("instruction_template", "") or task.get("instruction", "")
        actors = (task.get("seed") or {}).get("actors") or {}
        targets = (task.get("seed") or {}).get("targets") or {}

        # Find which actor keys flow into the instruction via targets
        for tkey, tval in targets.items():
            if not isinstance(tval, str):
                continue
            m = ACTOR_REF_RE.search(tval)
            if not m:
                continue
            actor_key = m.group(1)
            # Check if this target is used in the instruction
            if f"{{target.{tkey}}}" not in instr:
                continue
            actor_spec = actors.get(actor_key, {})
            if isinstance(actor_spec, dict) and "name" not in actor_spec:
                violations.append(
                    f"[{tid}] instruction uses {{target.{tkey}}} → "
                    f"{{actor.{actor_key}}} but actor has no explicit name"
                )
    assert not violations, "\n".join(violations)


# ── 5. Target reference integrity ────────────────────────────────────────

def test_all_target_refs_in_eval_are_defined() -> None:
    """Every ``{target.X}`` in eval expressions must have a matching key in targets."""
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        ev = task.get("eval")
        if not ev:
            continue
        target_keys = set(((task.get("seed") or {}).get("targets") or {}).keys())
        for check in (ev.get("checks") or []) + (ev.get("negative_checks") or []):
            expr = check["expr"] if isinstance(check, dict) else str(check)
            for m in TARGET_RE.finditer(expr):
                ref = m.group(1)
                if ref not in target_keys:
                    violations.append(
                        f"[{tid}] eval references {{target.{ref}}} "
                        f"but targets only defines: {sorted(target_keys)}"
                    )
    assert not violations, "\n".join(violations)


# ── 6. Variant response_body schema validity ─────────────────────────────

def _expected_response_keys(url_pattern: str) -> set[str] | None:
    """Infer the real top-level response key for a Gmail mutation endpoint."""
    normalized = url_pattern.rstrip("*").rstrip("/")

    if normalized.endswith("/send"):
        return {"email"}
    if normalized.endswith("/settings"):
        return {"settings"}
    if "/emails/" in normalized and normalized.endswith(
        ("/read", "/star", "/label", "/archive", "/delete", "/forward")
    ):
        return {"email"}
    if normalized.endswith("/labels") or "/labels/" in normalized:
        return {"label"}
    if normalized.endswith("/filters") or "/filters/" in normalized:
        return {"filter"}
    if normalized.endswith("/contacts") or "/contacts/" in normalized:
        return {"contact"}
    return None


def test_variant_silent_fail_response_has_correct_top_level_key() -> None:
    """Silent-fail response_body must use the same top-level key as the real API.

    E.g. a fake /send response needs ``{"email": {...}}``, not ``{"success": true}``.
    If the SPA parses the response for state updates, a wrong key means the
    fake response is structurally broken (SPA ignores it = no-op variant).
    """
    warnings: list[str] = []
    for fname, variant in ALL_VARIANTS:
        vid = variant.get("variant_id", fname)
        for inj in variant.get("injections", []):
            if inj.get("layer") != "network":
                continue
            params = inj.get("params", {})
            if params.get("action") != "silent_fail":
                continue
            url_pat = params.get("url_pattern", "")
            resp = params.get("response_body", {})
            if not isinstance(resp, dict):
                continue

            expected = _expected_response_keys(url_pat)
            if expected:
                actual = set(resp.keys())
                if not expected.intersection(actual):
                    warnings.append(
                        f"[{vid}] silent_fail on {url_pat}: response keys "
                        f"{actual} don't include expected {expected}"
                    )
    assert not warnings, "\n".join(warnings)


def test_filter_silent_fail_payloads_include_required_filter_fields() -> None:
    """Fake filter responses must be structurally valid for the Settings UI.

    The Settings page renders created filters immediately and expects arrays
    like ``add_labels`` to exist. Returning ``{"filter": {"id": ...}}`` can
    break the page after a silent-fail instead of testing verification.
    """
    required_keys = {
        "id",
        "name",
        "query",
        "from_addresses",
        "subject_keywords",
        "label_requirements",
        "add_labels",
        "archive",
        "mark_read",
        "forward_to",
        "star",
        "never_spam",
    }
    violations: list[str] = []
    for fname, variant in ALL_VARIANTS:
        vid = variant.get("variant_id", fname)
        for inj in variant.get("injections", []):
            if inj.get("layer") != "network":
                continue
            params = inj.get("params", {})
            if params.get("action") != "silent_fail":
                continue
            if "/filters" not in str(params.get("url_pattern", "")):
                continue

            response_body = params.get("response_body", {})
            if not isinstance(response_body, dict):
                continue
            fake_filter = response_body.get("filter")
            if not isinstance(fake_filter, dict):
                violations.append(f"[{vid}] missing filter object in fake filter response")
                continue

            missing = sorted(required_keys - set(fake_filter.keys()))
            if missing:
                violations.append(f"[{vid}] fake filter payload missing keys: {missing}")
                continue

            for key in ("from_addresses", "subject_keywords", "label_requirements", "add_labels"):
                if not isinstance(fake_filter.get(key), list):
                    violations.append(f"[{vid}] fake filter payload field '{key}' must be a list")
    assert not violations, "\n".join(violations)


# ── 7. Variant base_task_id references valid tasks ───────────────────────

def test_variant_base_task_ids_exist() -> None:
    """Every variant's base_task_id must reference an actual task."""
    violations: list[str] = []
    for fname, variant in ALL_VARIANTS:
        btid = variant.get("base_task_id", "")
        if btid and btid not in ALL_TASKS:
            violations.append(f"[{fname}] base_task_id '{btid}' not found in tasks")
    assert not violations, "\n".join(violations)


# ── 8. Eval uses only valid model attributes ─────────────────────────────

# Known attributes on state collections and objects
_VALID_EMAIL_ATTRS = {
    "id", "from_addr", "from_name", "to", "cc", "bcc", "subject", "body",
    "timestamp", "is_read", "is_starred", "labels", "thread_id", "in_reply_to",
    "forwarded_from_id", "attachments", "archived", "deleted", "category",
    "snippet",
}
_VALID_CONTACT_ATTRS = {
    "id", "name", "email", "company", "note", "is_vip", "is_starred",
    "source", "last_contacted_at",
}
_VALID_FILTER_ATTRS = {
    "id", "name", "query", "from_addresses", "subject_keywords",
    "label_requirements", "has_attachment", "add_labels", "archive",
    "mark_read", "forward_to", "star", "never_spam",
}
_VALID_SETTINGS_ATTRS = {
    "id", "signature", "forwarding_address", "display_density",
    "vacation_responder_enabled", "vacation_responder_message",
    "auto_advance", "language", "input_tools_enabled", "right_to_left",
    "max_page_size", "undo_send_seconds", "default_reply_behavior",
    "hover_actions_enabled", "send_and_archive", "default_text_style",
}


def test_eval_expressions_use_valid_settings_attributes() -> None:
    """Settings attribute references in eval must match GmailSettings fields."""
    violations: list[str] = []
    settings_attr_re = re.compile(r"state\.settings\.(\w+)")
    for tid, kind, expr in ALL_EXPRS:
        for m in settings_attr_re.finditer(expr):
            attr = m.group(1)
            if attr not in _VALID_SETTINGS_ATTRS:
                violations.append(
                    f"[{tid}] {kind}: state.settings.{attr} — "
                    f"'{attr}' is not a GmailSettings field"
                )
    assert not violations, "\n".join(violations)


def test_eval_expressions_use_valid_email_attributes() -> None:
    """Email attribute references in eval must match Email model fields.

    Catches bugs like ``.is_deleted`` (should be ``.deleted``) or
    ``.is_archived`` (should be ``.archived``).
    """
    violations: list[str] = []
    # Match e.ATTR or m.ATTR where the variable iterates over emails
    email_attr_re = re.compile(r"(?<!['\"])\b[ems]\.(\w+)")
    for tid, kind, expr in ALL_EXPRS:
        for m in email_attr_re.finditer(expr):
            attr = m.group(1)
            # Skip known non-email patterns (method calls, builtins)
            if attr in ("body", "lower", "upper", "strip", "split", "startswith",
                        "endswith", "get", "join", "model_dump"):
                continue
            # Only flag attributes that look like email fields but aren't valid
            if attr.startswith("is_") and attr not in _VALID_EMAIL_ATTRS:
                violations.append(
                    f"[{tid}] {kind}: .{attr} — "
                    f"'{attr}' is not an Email field (valid: {sorted(a for a in _VALID_EMAIL_ATTRS if a.startswith('is_'))})"
                )
    assert not violations, "\n".join(violations)


# ── 9. All actors without names (advisory, not blocking) ─────────────────

def test_report_all_unnamed_actors() -> None:
    """Advisory: list all actors that lack explicit names.

    These actors get random names from FakeDataGenerator. This is fine
    if the name never appears in the instruction or eval checks. This test
    only flags actors that are referenced in eval expressions.
    """
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        actors = (task.get("seed") or {}).get("actors") or {}
        targets = (task.get("seed") or {}).get("targets") or {}
        ev = task.get("eval")
        if not ev:
            continue

        # Build set of actor keys referenced in eval (via targets)
        eval_text = ""
        for check in (ev.get("checks") or []) + (ev.get("negative_checks") or []):
            eval_text += check["expr"] if isinstance(check, dict) else str(check)

        for akey, aspec in actors.items():
            if isinstance(aspec, dict) and "name" not in aspec:
                # Check if any target referencing this actor is used in eval
                for tkey, tval in targets.items():
                    if isinstance(tval, str) and f"{{actor.{akey}" in tval:
                        if f"{{target.{tkey}}}" in eval_text:
                            violations.append(
                                f"[{tid}] actor '{akey}' has no explicit name "
                                f"but is referenced in eval via {{target.{tkey}}}"
                            )
    assert not violations, "\n".join(violations)
