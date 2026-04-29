# Trajectory-Component Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `canonical_diff` with a `trajectory:` block (routes / interactions / sequence sub-keys) so process-only requirements become enforceable, and roll the eval out across all 519 tasks via per-env vocabulary tables and a mechanical generator.

**Architecture:** Wire the already-discarded `trajectory` parameter in `webagentbench/eval_core/orchestrator.py` through three new sub-matchers. Per-env vocabulary tables (`route_map.yaml`, `role_map.yaml`, `verb_templates.yaml`) provide the degradation-tolerant resolution of paths and ARIA labels. A 3-trajectory regression suite (do-nothing / happy-path / state-only-shortcut) is the objective correctness gate for every generated `trajectory:` block.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, FastAPI session backend (existing), BrowserGym + browser-use harnesses (existing).

**Spec:** `docs/superpowers/specs/2026-04-29-trajectory-component-eval-design.md`

---

## File Structure

**Create:**
- `webagentbench/eval_core/trajectory_norm.py` — harness-agnostic step normalizer (BG dict + browser-use dict → canonical `TrajectoryStep`).
- `webagentbench/eval_core/match_trajectory.py` — three sub-matchers (routes / interactions / sequence) + `relax:` application.
- `webagentbench/tasks/trajectory_schema.py` — Pydantic models for the `trajectory:` sub-block (kept separate from `canonical_diff.py` for diff cleanliness).
- `webagentbench/tasks/<env>/route_map.yaml` (×7 envs) — symbolic-name → URL template.
- `webagentbench/tasks/<env>/role_map.yaml` (×7 envs) — role → set of ARIA labels.
- `webagentbench/tasks/<env>/verb_templates.yaml` (×7 envs) — instruction-verb → trajectory-fragment generator.
- `webagentbench/tasks/trajectory_generator.py` — verb extractor + template applier + placeholder resolver.
- `webagentbench/tests/trajectory_regression.py` — shared 3-trajectory regression harness.
- `webagentbench/tests/test_trajectory_<task>.py` (one per process-bearing task, generated in Stage D).

**Modify:**
- `webagentbench/eval_core/orchestrator.py:73-80` — remove `del trajectory`, normalize, dispatch to `match_trajectory`, merge into report.
- `webagentbench/tasks/canonical_diff.py` — add optional `trajectory:` field to `CanonicalDiffBlock`; import trajectory schema.
- `webagentbench/agent_eval.py:257-267` — append `state_after` snapshot to each trajectory step.
- `webagentbench/browseruse_eval.py:291-340` — same: append `state_after` snapshot at `build_trajectory_step` call sites.
- `webagentbench/backend/state.py` — add `SessionManager.snapshot_state(session_id)` returning a deep `model_copy` (used by harnesses).

**Test fixtures (create):**
- `webagentbench/tests/fixtures/trajectory/amazon_browse_category_happy.json` — recorded happy-path trajectory.
- `webagentbench/tests/fixtures/trajectory/amazon_browse_category_shortcut.json` — synthetic state-only shortcut.

---

## Stage A — Schema, matcher, normalizer (SERIAL, single PR)

### Task A1: Add `snapshot_state` helper to `SessionManager`

**Files:**
- Modify: `webagentbench/backend/state.py`
- Test: `webagentbench/tests/test_session_snapshot.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_session_snapshot.py
"""Verify SessionManager.snapshot_state returns an isolated deep copy."""

from webagentbench.backend.state import SessionManager


def test_snapshot_is_isolated_deep_copy():
    sm = SessionManager()
    sid, _, _ = sm.create_session(env_id="amazon", task_id="amazon_browse_category", seed=42)

    snap_a = sm.snapshot_state(sid)
    state = sm.get_state(sid)
    state.add_to_cart(product_id="X-test-id", quantity=1)
    snap_b = sm.snapshot_state(sid)

    assert len(snap_a.cart_items) == 0
    assert len(snap_b.cart_items) == 1
    # Mutating snap_a must not touch live state
    snap_a.cart_items.append(object())
    assert len(sm.get_state(sid).cart_items) == 1


def test_snapshot_unknown_session_returns_none():
    sm = SessionManager()
    assert sm.snapshot_state("nonexistent") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_session_snapshot.py -v
```

Expected: FAIL with `AttributeError: 'SessionManager' object has no attribute 'snapshot_state'`.

- [ ] **Step 3: Add the method**

In `webagentbench/backend/state.py`, near `get_initial_snapshot`:

```python
def snapshot_state(self, session_id: str) -> BaseEnvState | None:
    """Return a deep copy of the current state, safe to mutate independently.

    Used by harnesses to record per-step state snapshots into trajectories
    so that the trajectory matcher can interleave route/interaction events
    with state-mutation events for the sequence component.
    """
    with self._lock:
        state = self._sessions.get(session_id)
        return state.model_copy(deep=True) if state is not None else None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_session_snapshot.py -v
```

Expected: PASS (2/2).

- [ ] **Step 5: Commit**

```bash
git add webagentbench/backend/state.py webagentbench/tests/test_session_snapshot.py
git commit -m "feat(eval): add SessionManager.snapshot_state for trajectory eval"
```

---

### Task A2: Trajectory step normalizer

**Files:**
- Create: `webagentbench/eval_core/trajectory_norm.py`
- Test: `webagentbench/tests/test_trajectory_norm.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_trajectory_norm.py
"""Verify trajectory normalizer collapses BG and browser-use shapes."""

from webagentbench.eval_core.trajectory_norm import normalize_trajectory


def test_browsergym_shape():
    raw = [
        {
            "step": 1,
            "thought": "I should browse Electronics.",
            "action": {"action": "click", "ref": 12, "label": "Electronics"},
            "raw_action": "click('a12')",
            "targets": [{"label": "Electronics", "role": "link"}],
            "status": "ok",
            "reward": 0.0,
            "elapsed_seconds": 1.5,
            "last_action_error": "",
        }
    ]
    out = normalize_trajectory(raw, harness="browsergym", env_id="amazon")
    assert len(out) == 1
    s = out[0]
    assert s["step"] == 1
    assert s["action_type"] == "click"
    assert s["target_label"] == "Electronics"
    assert s["url"] is None  # BG harness does not record URL today
    assert s["state_after"] is None


def test_browseruse_shape():
    raw = [
        {
            "step": 1,
            "url": "https://x.test/env/amazon/category/electronics",
            "thinking": "Browse Electronics.",
            "memory": "",
            "next_goal": "find cheapest",
            "actions": [{"action": "click", "click": {"index": 12, "label": "Electronics"}}],
            "status": "ok",
            "elapsed": 1.5,
            "state_after": {"cart_items": []},
        }
    ]
    out = normalize_trajectory(raw, harness="browser-use", env_id="amazon")
    assert len(out) == 1
    s = out[0]
    assert s["step"] == 1
    assert s["action_type"] == "click"
    assert s["target_label"] == "Electronics"
    assert s["path"] == "/category/electronics"
    assert s["state_after"] == {"cart_items": []}


def test_unknown_harness_raises():
    import pytest
    with pytest.raises(ValueError, match="harness"):
        normalize_trajectory([], harness="unknown", env_id="amazon")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_trajectory_norm.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'webagentbench.eval_core.trajectory_norm'`.

- [ ] **Step 3: Implement the normalizer**

```python
# webagentbench/eval_core/trajectory_norm.py
"""Harness-agnostic trajectory step normalizer.

Both the BrowserGym (`agent_eval.py`) and browser-use (`browseruse_eval.py`)
harnesses emit per-step records with overlapping but differently-shaped fields.
This module collapses them into the canonical TrajectoryStep dict consumed by
``match_trajectory``.

Canonical TrajectoryStep keys:
    step:         int (1-indexed)
    url:          str | None  — full URL at start of step (browser-use only today)
    path:         str | None  — env-relative path extracted from url
    action_type:  str         — canonical: click, type, select_option, scroll,
                                navigate, done, noop
    target_label: str | None  — ARIA label of clicked/affected element
    target_role:  str | None  — set later by match_trajectory via role_map
    value:        str | None  — for type/select_option
    state_after:  dict | None — server-state snapshot after this step
"""
from __future__ import annotations

import re
from typing import Any

_ENV_PATH_RE = re.compile(r"/env/[^/?#]+(?P<path>/[^?#]*)?")


def _extract_path(url: str | None) -> str | None:
    if not url:
        return None
    m = _ENV_PATH_RE.search(url)
    if m:
        return m.group("path") or "/"
    return url if url.startswith("/") else None


def _normalize_browsergym_step(raw: dict[str, Any]) -> dict[str, Any]:
    action = raw.get("action") or {}
    if not isinstance(action, dict):
        action = {}
    targets = raw.get("targets") or []
    target_label = None
    if targets and isinstance(targets, list) and isinstance(targets[0], dict):
        target_label = targets[0].get("label")
    return {
        "step": raw.get("step"),
        "url": None,
        "path": None,
        "action_type": action.get("action") or "noop",
        "target_label": target_label or action.get("label"),
        "target_role": None,
        "value": action.get("value") or action.get("text"),
        "state_after": raw.get("state_after"),
    }


def _normalize_browseruse_step(raw: dict[str, Any]) -> dict[str, Any]:
    actions = raw.get("actions") or []
    action0 = actions[0] if actions else {}
    if not isinstance(action0, dict):
        action0 = {}
    action_type = action0.get("action") or "noop"
    inner = action0.get(action_type) if isinstance(action0.get(action_type), dict) else {}
    target_label = inner.get("label") if isinstance(inner, dict) else None
    value = inner.get("text") or inner.get("value") if isinstance(inner, dict) else None
    url = raw.get("url")
    return {
        "step": raw.get("step"),
        "url": url,
        "path": _extract_path(url),
        "action_type": action_type,
        "target_label": target_label,
        "target_role": None,
        "value": value,
        "state_after": raw.get("state_after"),
    }


def normalize_trajectory(
    raw: list[dict[str, Any]],
    harness: str,
    env_id: str,
) -> list[dict[str, Any]]:
    """Convert raw harness trajectory to canonical TrajectoryStep list."""
    if harness == "browsergym":
        fn = _normalize_browsergym_step
    elif harness == "browser-use":
        fn = _normalize_browseruse_step
    else:
        raise ValueError(f"Unknown harness: {harness!r}")
    del env_id  # reserved for future env-specific path normalisation
    return [fn(step) for step in raw]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_trajectory_norm.py -v
```

Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add webagentbench/eval_core/trajectory_norm.py webagentbench/tests/test_trajectory_norm.py
git commit -m "feat(eval): trajectory normalizer for BG and browser-use harnesses"
```

---

### Task A3: Trajectory schema (Pydantic models)

**Files:**
- Create: `webagentbench/tasks/trajectory_schema.py`
- Modify: `webagentbench/tasks/canonical_diff.py`
- Test: `webagentbench/tests/test_trajectory_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_trajectory_schema.py
"""Verify the trajectory: sub-block schema."""

import pytest
from pydantic import ValidationError

from webagentbench.tasks.canonical_diff import CanonicalDiffBlock


def test_trajectory_block_optional():
    block = CanonicalDiffBlock(create=[], update=[], delete=[], invariant=[])
    assert block.trajectory is None


def test_routes_block_parses():
    block = CanonicalDiffBlock(
        create=[], update=[], delete=[], invariant=[],
        trajectory={
            "routes": {
                "must_visit": [{"path": "/category/{slug}", "min_count": 1}],
                "must_not_visit": [{"path": "/admin"}],
            }
        },
    )
    assert block.trajectory.routes.must_visit[0].path == "/category/{slug}"
    assert block.trajectory.routes.must_visit[0].min_count == 1


def test_interactions_block_parses():
    block = CanonicalDiffBlock(
        create=[], update=[], delete=[], invariant=[],
        trajectory={
            "interactions": {
                "must_include": [{"action": "type", "target_role": "search_input"}],
            }
        },
    )
    assert block.trajectory.interactions.must_include[0].target_role == "search_input"


def test_sequence_block_parses():
    block = CanonicalDiffBlock(
        create=[], update=[], delete=[], invariant=[],
        trajectory={
            "sequence": {
                "ordered": [
                    {"visit": "/orders/{order_id}"},
                    {"ref": "cancel_order"},
                ],
            }
        },
    )
    assert len(block.trajectory.sequence.ordered) == 2


def test_relax_block_parses():
    block = CanonicalDiffBlock(
        create=[], update=[], delete=[], invariant=[],
        trajectory={
            "routes": {"must_visit": [{"path": "/search"}]},
            "relax": {"routes": ["/search"], "interactions": ["search_input"]},
        },
    )
    assert "/search" in block.trajectory.relax.routes
    assert "search_input" in block.trajectory.relax.interactions


def test_unknown_action_rejected():
    with pytest.raises(ValidationError):
        CanonicalDiffBlock(
            create=[], update=[], delete=[], invariant=[],
            trajectory={
                "interactions": {"must_include": [{"action": "telepathy", "target_role": "x"}]},
            },
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_trajectory_schema.py -v
```

Expected: FAIL — `CanonicalDiffBlock` has no `trajectory` field.

- [ ] **Step 3: Create trajectory schema module**

```python
# webagentbench/tasks/trajectory_schema.py
"""Pydantic v2 schema for the ``trajectory:`` sub-block of canonical_diff.

See ``docs/superpowers/specs/2026-04-29-trajectory-component-eval-design.md``
§Schema extension. Three optional sub-keys:

  routes:       page-route log assertions
  interactions: interaction log assertions
  sequence:     ordered events across routes/interactions/state-changes

Plus an optional ``relax:`` block used by degradation variants to drop
specific checks from an inherited base task.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_ALLOWED_ACTIONS = frozenset({
    "click", "type", "select_option", "scroll", "navigate", "done", "noop"
})


class RoutePattern(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., description="URL path; may contain {ref} placeholders bound to canonical_diff bijection refs")
    min_count: int = Field(default=1, ge=1)


class RoutesBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_visit: list[RoutePattern] = Field(default_factory=list)
    must_not_visit: list[RoutePattern] = Field(default_factory=list)


class InteractionPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["click", "type", "select_option", "scroll", "navigate", "done", "noop"]
    target_role: str | None = None
    value_contains: str | None = None
    min_count: int = Field(default=1, ge=1)


class InteractionsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_include: list[InteractionPattern] = Field(default_factory=list)
    must_not_include: list[InteractionPattern] = Field(default_factory=list)


class SequenceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visit: str | None = None
    interaction: str | None = None  # role name
    ref: str | None = None          # name of a create/update/delete entry


class SequenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordered: list[SequenceEvent] = Field(default_factory=list)
    unordered: list[SequenceEvent] = Field(default_factory=list)


class RelaxBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routes: list[str] = Field(default_factory=list)
    interactions: list[str] = Field(default_factory=list)
    sequence: list[str] = Field(default_factory=list)


class TrajectoryBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routes: RoutesBlock | None = None
    interactions: InteractionsBlock | None = None
    sequence: SequenceBlock | None = None
    relax: RelaxBlock | None = None


__all__ = [
    "TrajectoryBlock", "RoutesBlock", "InteractionsBlock",
    "SequenceBlock", "RelaxBlock", "RoutePattern", "InteractionPattern",
    "SequenceEvent",
]
```

- [ ] **Step 4: Wire into `CanonicalDiffBlock`**

In `webagentbench/tasks/canonical_diff.py`, add the import and field. Locate the `CanonicalDiffBlock` class definition; add:

```python
from .trajectory_schema import TrajectoryBlock  # noqa: E402  (at top with other imports)
```

And add to the `CanonicalDiffBlock` model:

```python
trajectory: TrajectoryBlock | None = None
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_trajectory_schema.py -v
```

Expected: PASS (6/6).

- [ ] **Step 6: Commit**

```bash
git add webagentbench/tasks/trajectory_schema.py webagentbench/tasks/canonical_diff.py webagentbench/tests/test_trajectory_schema.py
git commit -m "feat(eval): trajectory: sub-block schema with routes/interactions/sequence/relax"
```

---

### Task A4: Routes sub-matcher

**Files:**
- Create: `webagentbench/eval_core/match_trajectory.py`
- Test: `webagentbench/tests/test_match_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_match_routes.py
"""Routes sub-matcher: must_visit / must_not_visit with ref placeholders."""

from webagentbench.eval_core.match_trajectory import match_routes
from webagentbench.tasks.trajectory_schema import RoutesBlock


def _step(step, path):
    return {"step": step, "path": path, "url": None, "action_type": "navigate",
            "target_label": None, "target_role": None, "value": None, "state_after": None}


def test_must_visit_satisfied():
    block = RoutesBlock.model_validate({"must_visit": [{"path": "/category/electronics"}]})
    steps = [_step(1, "/"), _step(2, "/category/electronics"), _step(3, "/cart")]
    checks, neg = match_routes(steps, block, refs={})
    assert len(checks) == 1 and checks[0]["passed"] is True


def test_must_visit_unsatisfied():
    block = RoutesBlock.model_validate({"must_visit": [{"path": "/category/electronics"}]})
    steps = [_step(1, "/"), _step(2, "/cart")]
    checks, neg = match_routes(steps, block, refs={})
    assert len(checks) == 1 and checks[0]["passed"] is False


def test_must_visit_with_ref_placeholder():
    block = RoutesBlock.model_validate({"must_visit": [{"path": "/orders/{order_id}"}]})
    steps = [_step(1, "/orders/abc-42")]
    checks, neg = match_routes(steps, block, refs={"order_id": "abc-42"})
    assert checks[0]["passed"] is True


def test_must_visit_min_count():
    block = RoutesBlock.model_validate({"must_visit": [{"path": "/products/.+", "min_count": 3}]})
    steps = [_step(1, "/products/a"), _step(2, "/products/b")]
    checks, neg = match_routes(steps, block, refs={})
    assert checks[0]["passed"] is False  # only 2 < 3


def test_must_not_visit_violation():
    block = RoutesBlock.model_validate({"must_not_visit": [{"path": "/admin"}]})
    steps = [_step(1, "/admin/users")]
    checks, neg = match_routes(steps, block, refs={})
    assert len(neg) == 1 and neg[0]["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_match_routes.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement routes sub-matcher**

```python
# webagentbench/eval_core/match_trajectory.py
"""Trajectory matcher: routes / interactions / sequence sub-matchers.

Each sub-matcher consumes a normalized trajectory (see trajectory_norm.py)
plus the corresponding sub-block of TrajectoryBlock and returns
(checks, negative_checks) lists in the same shape as eval_core/matcher.py.
"""
from __future__ import annotations

import re
from typing import Any

from webagentbench.tasks.trajectory_schema import (
    InteractionsBlock,
    RoutesBlock,
    SequenceBlock,
    TrajectoryBlock,
)


def _resolve_path(path: str, refs: dict[str, Any]) -> str:
    """Replace {ref_name} placeholders with bijection-resolved values, then
    treat the result as a regex (callers may write `/products/.+` literally)."""
    def sub(m: re.Match) -> str:
        key = m.group(1)
        val = refs.get(key)
        if val is None:
            return m.group(0)  # leave as literal — will fail to match
        return re.escape(str(val))
    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", sub, path)


def match_routes(
    steps: list[dict[str, Any]],
    block: RoutesBlock,
    refs: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    checks: list[dict] = []
    neg: list[dict] = []
    paths = [s.get("path") or "" for s in steps]

    for entry in block.must_visit:
        pattern = re.compile(_resolve_path(entry.path, refs))
        hits = sum(1 for p in paths if pattern.fullmatch(p))
        passed = hits >= entry.min_count
        checks.append({
            "kind": "trajectory.routes.must_visit",
            "desc": f"visited {entry.path} >= {entry.min_count} time(s) (got {hits})",
            "passed": passed,
            "_relax_key": entry.path,
        })

    for entry in block.must_not_visit:
        pattern = re.compile(_resolve_path(entry.path, refs))
        hits = sum(1 for p in paths if pattern.fullmatch(p))
        passed = hits == 0
        neg.append({
            "kind": "trajectory.routes.must_not_visit",
            "desc": f"did not visit {entry.path} (got {hits})",
            "passed": passed,
            "penalty": 0.5 if not passed else 0.0,
            "_relax_key": entry.path,
        })

    return checks, neg


def match_interactions(steps, block, role_map, refs):  # noqa: ARG001  — Task A5
    raise NotImplementedError


def match_sequence(steps, block, refs, agent_diff):  # noqa: ARG001  — Task A6
    raise NotImplementedError


def apply_relax(checks: list[dict], neg: list[dict], relax) -> tuple[list[dict], list[dict]]:
    """Drop checks whose `_relax_key` matches an entry in the relax block."""
    if relax is None:
        return checks, neg
    keys = set(relax.routes) | set(relax.interactions) | set(relax.sequence)
    checks = [c for c in checks if c.get("_relax_key") not in keys]
    neg = [n for n in neg if n.get("_relax_key") not in keys]
    return checks, neg


def match_trajectory(
    steps: list[dict[str, Any]],
    block: TrajectoryBlock | None,
    role_map: dict[str, list[str]],
    refs: dict[str, Any],
    agent_diff: list[Any] | None = None,
) -> tuple[list[dict], list[dict]]:
    if block is None:
        return [], []
    checks: list[dict] = []
    neg: list[dict] = []
    if block.routes is not None:
        c, n = match_routes(steps, block.routes, refs)
        checks.extend(c); neg.extend(n)
    if block.interactions is not None:
        c, n = match_interactions(steps, block.interactions, role_map, refs)
        checks.extend(c); neg.extend(n)
    if block.sequence is not None:
        c, n = match_sequence(steps, block.sequence, refs, agent_diff or [])
        checks.extend(c); neg.extend(n)
    return apply_relax(checks, neg, block.relax)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_match_routes.py -v
```

Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add webagentbench/eval_core/match_trajectory.py webagentbench/tests/test_match_routes.py
git commit -m "feat(eval): routes sub-matcher with bijection ref placeholders"
```

---

### Task A5: Interactions sub-matcher with role resolution

**Files:**
- Modify: `webagentbench/eval_core/match_trajectory.py`
- Test: `webagentbench/tests/test_match_interactions.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_match_interactions.py
"""Interactions sub-matcher: action+target_role+value matching."""

from webagentbench.eval_core.match_trajectory import match_interactions
from webagentbench.tasks.trajectory_schema import InteractionsBlock


ROLE_MAP = {
    "search_input": ["Search products", "Find items", "Search"],
    "sort_control": ["Sort by", "Order by"],
}


def _step(step, action_type, label, value=None):
    return {"step": step, "path": None, "url": None,
            "action_type": action_type, "target_label": label,
            "target_role": None, "value": value, "state_after": None}


def test_must_include_role_match():
    block = InteractionsBlock.model_validate(
        {"must_include": [{"action": "type", "target_role": "search_input"}]}
    )
    steps = [_step(1, "type", "Search products", value="laptop")]
    checks, neg = match_interactions(steps, block, ROLE_MAP, refs={})
    assert checks[0]["passed"] is True


def test_must_include_role_match_with_degraded_label():
    """Client-degradation may relabel; the role lookup absorbs it."""
    block = InteractionsBlock.model_validate(
        {"must_include": [{"action": "type", "target_role": "search_input"}]}
    )
    steps = [_step(1, "type", "Find items", value="laptop")]
    checks, neg = match_interactions(steps, block, ROLE_MAP, refs={})
    assert checks[0]["passed"] is True


def test_must_include_value_contains():
    block = InteractionsBlock.model_validate(
        {"must_include": [{"action": "type", "target_role": "search_input",
                            "value_contains": "{target.search_q}"}]}
    )
    steps = [_step(1, "type", "Search", value="laptop pro")]
    checks, neg = match_interactions(steps, block, ROLE_MAP, refs={"target.search_q": "laptop"})
    assert checks[0]["passed"] is True


def test_must_include_unsatisfied():
    block = InteractionsBlock.model_validate(
        {"must_include": [{"action": "select_option", "target_role": "sort_control"}]}
    )
    steps = [_step(1, "click", "Add to cart")]
    checks, neg = match_interactions(steps, block, ROLE_MAP, refs={})
    assert checks[0]["passed"] is False


def test_must_not_include_violation():
    block = InteractionsBlock.model_validate(
        {"must_not_include": [{"action": "click", "target_role": "sort_control"}]}
    )
    steps = [_step(1, "click", "Sort by")]
    checks, neg = match_interactions(steps, block, ROLE_MAP, refs={})
    assert neg[0]["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_match_interactions.py -v
```

Expected: FAIL with `NotImplementedError` from the stub.

- [ ] **Step 3: Implement interactions sub-matcher**

In `webagentbench/eval_core/match_trajectory.py`, replace the `match_interactions` stub with:

```python
def _label_matches_role(label: str | None, role: str, role_map: dict[str, list[str]]) -> bool:
    if label is None:
        return False
    labels = role_map.get(role) or []
    return label in labels


def _resolve_value(template: str | None, refs: dict[str, Any]) -> str | None:
    if template is None:
        return None
    def sub(m: re.Match) -> str:
        key = m.group(1)
        val = refs.get(key)
        return str(val) if val is not None else m.group(0)
    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}", sub, template)


def match_interactions(
    steps: list[dict[str, Any]],
    block: InteractionsBlock,
    role_map: dict[str, list[str]],
    refs: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    checks: list[dict] = []
    neg: list[dict] = []

    def _step_matches(step: dict, pat) -> bool:
        if step.get("action_type") != pat.action:
            return False
        if pat.target_role is not None and not _label_matches_role(
            step.get("target_label"), pat.target_role, role_map
        ):
            return False
        if pat.value_contains is not None:
            needle = _resolve_value(pat.value_contains, refs) or ""
            haystack = step.get("value") or ""
            if needle not in haystack:
                return False
        return True

    for pat in block.must_include:
        hits = sum(1 for s in steps if _step_matches(s, pat))
        passed = hits >= pat.min_count
        checks.append({
            "kind": "trajectory.interactions.must_include",
            "desc": f"interaction action={pat.action} role={pat.target_role} >= {pat.min_count} (got {hits})",
            "passed": passed,
            "_relax_key": pat.target_role or pat.action,
        })

    for pat in block.must_not_include:
        hits = sum(1 for s in steps if _step_matches(s, pat))
        passed = hits == 0
        neg.append({
            "kind": "trajectory.interactions.must_not_include",
            "desc": f"avoided action={pat.action} role={pat.target_role} (got {hits})",
            "passed": passed,
            "penalty": 0.5 if not passed else 0.0,
            "_relax_key": pat.target_role or pat.action,
        })

    return checks, neg
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_match_interactions.py -v
```

Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add webagentbench/eval_core/match_trajectory.py webagentbench/tests/test_match_interactions.py
git commit -m "feat(eval): interactions sub-matcher with role-vocabulary lookup"
```

---

### Task A6: Sequence sub-matcher

**Files:**
- Modify: `webagentbench/eval_core/match_trajectory.py`
- Test: `webagentbench/tests/test_match_sequence.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_match_sequence.py
"""Sequence sub-matcher: ordered/unordered events across routes + diff refs."""

from webagentbench.eval_core.match_trajectory import match_sequence
from webagentbench.tasks.trajectory_schema import SequenceBlock


def _step(step, path=None, action_type="navigate", state_after=None):
    return {"step": step, "path": path, "url": None,
            "action_type": action_type, "target_label": None,
            "target_role": None, "value": None, "state_after": state_after}


def test_ordered_visit_before_ref():
    """visit /orders/X must precede the cancel_order diff entry."""
    steps = [
        _step(1, path="/orders/abc"),                     # visit at step 1
        _step(2, action_type="click", state_after={"orders": [{"id": "abc", "status": "cancelled"}]}),
    ]
    block = SequenceBlock.model_validate(
        {"ordered": [{"visit": "/orders/{order_id}"}, {"ref": "cancel_order"}]}
    )
    # agent_diff is a list of (kind, name, applied_at_step) tuples
    diff = [("update", "cancel_order", 2)]
    checks, _ = match_sequence(steps, block, refs={"order_id": "abc"}, agent_diff=diff)
    assert checks[0]["passed"] is True


def test_ordered_violation_ref_before_visit():
    steps = [
        _step(1, action_type="click", state_after={"orders": [{"id": "abc", "status": "cancelled"}]}),
        _step(2, path="/orders/abc"),
    ]
    block = SequenceBlock.model_validate(
        {"ordered": [{"visit": "/orders/{order_id}"}, {"ref": "cancel_order"}]}
    )
    diff = [("update", "cancel_order", 1)]
    checks, _ = match_sequence(steps, block, refs={"order_id": "abc"}, agent_diff=diff)
    assert checks[0]["passed"] is False


def test_unordered_present():
    steps = [_step(1, path="/products/a"), _step(2, path="/products/b")]
    block = SequenceBlock.model_validate(
        {"unordered": [{"visit": "/products/a"}, {"visit": "/products/b"}]}
    )
    checks, _ = match_sequence(steps, block, refs={}, agent_diff=[])
    assert checks[0]["passed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_match_sequence.py -v
```

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement sequence sub-matcher**

In `webagentbench/eval_core/match_trajectory.py`, replace the `match_sequence` stub with:

```python
def _event_first_step(
    event,
    steps: list[dict[str, Any]],
    refs: dict[str, Any],
    diff: list[tuple[str, str, int]],
) -> int | None:
    """Return the earliest step number where this event occurs, or None."""
    if event.visit is not None:
        pattern = re.compile(_resolve_path(event.visit, refs))
        for s in steps:
            if pattern.fullmatch(s.get("path") or ""):
                return s.get("step")
        return None
    if event.ref is not None:
        for kind, name, step_num in diff:
            del kind
            if name == event.ref:
                return step_num
        return None
    if event.interaction is not None:
        # interaction by role name; resolution happens at the call site
        return None
    return None


def match_sequence(
    steps: list[dict[str, Any]],
    block: SequenceBlock,
    refs: dict[str, Any],
    agent_diff: list[tuple[str, str, int]],
) -> tuple[list[dict], list[dict]]:
    checks: list[dict] = []
    neg: list[dict] = []

    if block.ordered:
        positions = [_event_first_step(e, steps, refs, agent_diff) for e in block.ordered]
        passed = all(p is not None for p in positions) and \
                 all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))
        checks.append({
            "kind": "trajectory.sequence.ordered",
            "desc": f"events occur in order: {[e.model_dump(exclude_none=True) for e in block.ordered]} (positions={positions})",
            "passed": passed,
            "_relax_key": "ordered",
        })

    for event in block.unordered:
        pos = _event_first_step(event, steps, refs, agent_diff)
        checks.append({
            "kind": "trajectory.sequence.unordered",
            "desc": f"event present: {event.model_dump(exclude_none=True)}",
            "passed": pos is not None,
            "_relax_key": "unordered",
        })

    return checks, neg
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_match_sequence.py -v
```

Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add webagentbench/eval_core/match_trajectory.py webagentbench/tests/test_match_sequence.py
git commit -m "feat(eval): sequence sub-matcher with ordered/unordered event resolution"
```

---

### Task A7: Relax block application

**Files:**
- Test: `webagentbench/tests/test_relax_block.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_relax_block.py
"""Verify relax: drops the right inherited checks without breaking the rest."""

from webagentbench.eval_core.match_trajectory import match_trajectory
from webagentbench.tasks.trajectory_schema import TrajectoryBlock


def _step(step, path):
    return {"step": step, "path": path, "url": None, "action_type": "navigate",
            "target_label": None, "target_role": None, "value": None, "state_after": None}


def test_relax_drops_route_check():
    block = TrajectoryBlock.model_validate({
        "routes": {"must_visit": [{"path": "/search"}, {"path": "/cart"}]},
        "relax": {"routes": ["/search"]},
    })
    steps = [_step(1, "/cart")]  # /search not visited
    checks, _ = match_trajectory(steps, block, role_map={}, refs={})
    # /search check should have been relaxed; only /cart remains and passes
    assert len(checks) == 1
    assert checks[0]["passed"] is True


def test_relax_does_not_drop_unrelated_checks():
    block = TrajectoryBlock.model_validate({
        "routes": {"must_visit": [{"path": "/search"}, {"path": "/cart"}]},
        "relax": {"routes": ["/admin"]},  # relaxing something not in the block
    })
    steps = [_step(1, "/search"), _step(2, "/cart")]
    checks, _ = match_trajectory(steps, block, role_map={}, refs={})
    assert len(checks) == 2
    assert all(c["passed"] for c in checks)
```

- [ ] **Step 2: Run test to verify it passes**

(`apply_relax` was implemented in Task A4; this test confirms the wiring through `match_trajectory`.)

```bash
pytest webagentbench/tests/test_relax_block.py -v
```

Expected: PASS (2/2).

- [ ] **Step 3: Commit**

```bash
git add webagentbench/tests/test_relax_block.py
git commit -m "test(eval): relax block drops the right inherited trajectory checks"
```

---

### Task A8: Wire trajectory through the orchestrator

**Files:**
- Modify: `webagentbench/eval_core/orchestrator.py:73-80`
- Test: `webagentbench/tests/test_orchestrator_trajectory.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_orchestrator_trajectory.py
"""Verify evaluate() uses trajectory when canonical_diff.trajectory is set."""

from types import SimpleNamespace

from webagentbench.eval_core.orchestrator import evaluate


class _MiniState:
    """Minimal state stub: empty diff, but trajectory check should fire."""
    _initial_state_copy = SimpleNamespace()


def _task_with_trajectory():
    return SimpleNamespace(
        env_id="amazon",
        canonical_diff={
            "create": [], "update": [], "delete": [], "invariant": [],
            "trajectory": {"routes": {"must_visit": [{"path": "/category/electronics"}]}},
        },
    )


def test_evaluate_passes_trajectory_to_matcher():
    task = _task_with_trajectory()
    # Trajectory matches the must_visit assertion
    traj = [{"step": 1, "url": "https://x/env/amazon/category/electronics",
             "thought": "", "action": {"action": "navigate"}, "raw_action": "",
             "targets": [], "status": "ok", "reward": 0.0, "elapsed_seconds": 0.1,
             "last_action_error": "", "state_after": None}]
    result = evaluate(task, _MiniState(), targets={}, trajectory=traj,
                      harness="browsergym")
    # The route check must appear in result['checks'] and have passed
    route_checks = [c for c in result.get("checks", []) if c.get("kind", "").startswith("trajectory.routes")]
    assert len(route_checks) == 1


def test_evaluate_no_trajectory_block_unchanged():
    """Tasks without trajectory: must score identically to today."""
    task = SimpleNamespace(env_id="amazon",
                           canonical_diff={"create": [], "update": [], "delete": [], "invariant": []})
    result = evaluate(task, _MiniState(), targets={}, trajectory=None)
    assert "checks" in result
    # No trajectory checks should appear
    traj_checks = [c for c in result.get("checks", []) if c.get("kind", "").startswith("trajectory")]
    assert traj_checks == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_orchestrator_trajectory.py -v
```

Expected: FAIL — `evaluate()` discards trajectory and the route check never runs.

- [ ] **Step 3: Modify the orchestrator**

In `webagentbench/eval_core/orchestrator.py`, change the `evaluate` function. Replace lines 73-80 (the `del trajectory` block) and add trajectory dispatch after `match_diff` returns. The full updated `evaluate` body:

```python
def evaluate(
    task: Any,
    server_state: Any,
    targets: Mapping[str, Any] | None = None,
    trajectory: Any = None,
    harness: str = "browser-use",
) -> dict[str, Any]:
    """Evaluate a WebAgentBench task via canonical_diff matching.

    The legacy ``eval.checks`` / ``negative_checks`` path has been removed.
    Every task must declare a ``canonical_diff`` block.

    If ``canonical_diff.trajectory`` is present, ``trajectory`` is normalized
    and matched alongside the state diff. ``harness`` selects the normalizer
    ("browsergym" or "browser-use"); browser-use is the default.
    """
    targets = dict(targets or {})
    canonical = get_field(task, "canonical_diff")

    if canonical is None:
        result = EvalResult(
            score=0.0, final_score=0.0, success=False,
            reasoning="Task has no canonical_diff block. Legacy eval.checks are no longer supported.",
            failures=[Failure("missing_canonical_diff", "No canonical_diff block present", {})],
        )
        return result.as_dict()

    initial = _initial_state(server_state)
    if initial is not None:
        try:
            agent_diff = compute_diff(initial, server_state)
        except TypeError:
            agent_diff = []
    else:
        agent_diff = []

    session_start = (
        get_field(task, "session_start", None)
        or (targets.get("session_start") if targets else None)
        or getattr(server_state, "session_start", None)
    )
    if isinstance(session_start, str):
        from datetime import datetime
        try:
            session_start = datetime.fromisoformat(session_start)
        except ValueError:
            session_start = None

    report = match_diff(agent_diff, canonical, targets, initial, server_state, session_start=session_start)

    # NEW: trajectory matching
    traj_block = canonical.get("trajectory") if isinstance(canonical, Mapping) else getattr(canonical, "trajectory", None)
    if traj_block is not None and trajectory is not None:
        from .trajectory_norm import normalize_trajectory
        from .match_trajectory import match_trajectory
        from webagentbench.tasks.trajectory_schema import TrajectoryBlock
        from webagentbench.tasks.role_map_loader import load_role_map

        env_id = get_field(task, "env_id", None) or "unknown"
        steps = normalize_trajectory(trajectory, harness=harness, env_id=env_id)
        # Build a minimal diff-event list (kind, name, step) by tagging diff
        # entries with the step at which their state_after first appears.
        diff_events = _tag_diff_events(agent_diff, steps)
        block = traj_block if isinstance(traj_block, TrajectoryBlock) else TrajectoryBlock.model_validate(traj_block)
        role_map = load_role_map(env_id)
        # Combine targets and bijection refs for placeholder resolution
        refs = {**targets, **getattr(report, "bijection_refs", {})}
        t_checks, t_neg = match_trajectory(steps, block, role_map, refs, diff_events)
        report.checks = list(report.checks) + t_checks
        report.negative_checks = list(report.negative_checks) + t_neg
        # Recompute pass/penalty score
        if hasattr(report, "recompute_score"):
            report.recompute_score()

    result = EvalResult(
        score=report.score, final_score=report.score, success=report.passed,
        reasoning=_format_reasoning(report),
        checks=report.checks, negative_checks=report.negative_checks,
        failures=report.failures, collateral=_collateral(server_state, initial),
        bijection_graphs=report.bijection_graphs,
    )
    return result.as_dict()


def _tag_diff_events(agent_diff: list, steps: list[dict]) -> list[tuple[str, str, int]]:
    """Best-effort: associate each diff entry with the step whose state_after
    first contains the diff's effect. Returns (kind, name, step) tuples.

    For Stage A this returns step=len(steps) for every diff entry — sequence
    ordering between diff refs is approximate until a per-entry tagger lands.
    """
    fallback_step = max((s.get("step") or 0) for s in steps) if steps else 0
    out: list[tuple[str, str, int]] = []
    for entry in agent_diff:
        name = (entry.get("name") if isinstance(entry, dict) else getattr(entry, "name", None)) or ""
        kind = (entry.get("kind") if isinstance(entry, dict) else getattr(entry, "kind", None)) or ""
        if name:
            out.append((kind, name, fallback_step))
    return out
```

Add the role-map loader stub (full impl arrives in Task A11 worked example):

```python
# webagentbench/tasks/role_map_loader.py
"""Load per-env role maps from YAML."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=8)
def load_role_map(env_id: str) -> dict[str, list[str]]:
    path = _ROOT / env_id / "role_map.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for role, labels in data.items():
        if isinstance(labels, list):
            out[str(role)] = [str(x) for x in labels]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_orchestrator_trajectory.py -v
```

Expected: PASS (2/2).

- [ ] **Step 5: Run the full eval test suite to confirm no regression**

```bash
pytest webagentbench/tests/ -x --ignore=webagentbench/tests/test_adversarial_battery.py -q
```

Expected: all existing tests still pass; trajectory tests now pass.

- [ ] **Step 6: Commit**

```bash
git add webagentbench/eval_core/orchestrator.py webagentbench/tasks/role_map_loader.py webagentbench/tests/test_orchestrator_trajectory.py
git commit -m "feat(eval): wire trajectory through orchestrator; remove discard"
```

---

### Task A9: Per-step state snapshots in BrowserGym harness

**Files:**
- Modify: `webagentbench/agent_eval.py:257-267`
- Test: integrated via Task A11 worked example.

- [ ] **Step 1: Locate the trajectory-append site**

```bash
grep -n "trajectory.append" webagentbench/agent_eval.py
```

Expected output: line 257.

- [ ] **Step 2: Add state snapshot capture**

In `webagentbench/agent_eval.py`, find where the env exposes the session id (search for `session_id` or `task_info`). The BG environment exposes session id via `step_info.get("task_info", {}).get("session_id")`. Add a snapshot fetch before appending to trajectory:

```python
# After: obs, reward, terminated, truncated, step_info = env.step(action)
state_after = None
session_id = step_info.get("task_info", {}).get("session_id") if isinstance(step_info, dict) else None
if session_id is not None:
    try:
        from webagentbench.app import session_manager  # singleton
        snap = session_manager.snapshot_state(session_id)
        if snap is not None:
            state_after = snap.model_dump()
    except Exception:
        state_after = None
```

Then add `"state_after": state_after,` to the `trajectory.append({...})` dict.

- [ ] **Step 3: Smoke-test by running one task**

```bash
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai \
    --tasks amazon_browse_category --seed 42 --no-headless 2>&1 | tail -30
```

Expected: episode runs to completion; the resulting trajectory JSON in `webagentbench/results/...` contains `state_after` fields.

```bash
python -c "import json,glob; d=json.load(open(sorted(glob.glob('webagentbench/results/**/*.json', recursive=True))[-1])); print('has state_after:', any('state_after' in s for s in d.get('runs',[{}])[0].get('trajectory',[])))"
```

- [ ] **Step 4: Commit**

```bash
git add webagentbench/agent_eval.py
git commit -m "feat(harness): record per-step state snapshots in BrowserGym trajectory"
```

---

### Task A10: Per-step state snapshots in browser-use harness

**Files:**
- Modify: `webagentbench/browseruse_eval.py` at `build_trajectory_step` call sites (lines 604, 846)
- Test: integrated via Task A11.

- [ ] **Step 1: Locate the call sites**

```bash
grep -n "build_trajectory_step\|session_id" webagentbench/browseruse_eval.py | head -20
```

- [ ] **Step 2: Add `state_after` parameter to `build_trajectory_step`**

In `webagentbench/browseruse_eval.py:291-340`, extend the signature:

```python
def build_trajectory_step(
    step_num: int,
    thinking: str,
    memory: str,
    actions: list[dict],
    dom_elements: dict[int, tuple | dict],
    url: str,
    status: str,
    elapsed: float,
    action_results: list[dict] | None = None,
    state_after: dict | None = None,   # NEW
) -> dict:
    ...
    # In the returned dict, add:
    #   "state_after": state_after,
```

- [ ] **Step 3: Pass snapshot at call sites**

At each `trajectory.append(build_trajectory_step(...))` call site, fetch the snapshot first. Browser-use's controller has access to the session id via the URL or a known session-context attr. Wire it as in Task A9:

```python
state_after = None
if session_id:
    try:
        from webagentbench.app import session_manager
        snap = session_manager.snapshot_state(session_id)
        if snap is not None:
            state_after = snap.model_dump()
    except Exception:
        state_after = None
trajectory.append(build_trajectory_step(..., state_after=state_after))
```

- [ ] **Step 4: Smoke-test**

```bash
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai \
    --harness browser-use --tasks amazon_browse_category --seed 42 2>&1 | tail -20
```

Expected: trajectory file contains `state_after` per step.

- [ ] **Step 5: Commit**

```bash
git add webagentbench/browseruse_eval.py
git commit -m "feat(harness): record per-step state snapshots in browser-use trajectory"
```

---

### Task A11: Worked example — `amazon_browse_category` end-to-end

**Files:**
- Modify: `webagentbench/tasks/amazon/amazon_browse_category.yaml`
- Create: `webagentbench/tasks/amazon/route_map.yaml`
- Create: `webagentbench/tasks/amazon/role_map.yaml`
- Create: `webagentbench/tests/trajectory_regression.py`
- Create: `webagentbench/tests/test_trajectory_amazon_browse_category.py`

- [ ] **Step 1: Add minimal Amazon vocabularies**

```yaml
# webagentbench/tasks/amazon/route_map.yaml
home:             "/"
category_listing: "/category/{slug}"
product_detail:   "/products/{id}"
search_results:   "/search"
cart:             "/cart"
orders:           "/orders"
order_detail:     "/orders/{id}"
```

```yaml
# webagentbench/tasks/amazon/role_map.yaml
search_input:  ["Search products", "Search", "Find items"]
sort_control:  ["Sort by", "Order by"]
filter_button: ["Filter", "Filters"]
add_to_cart:   ["Add to Cart", "Add to cart"]
checkout:      ["Proceed to Checkout", "Checkout"]
```

- [ ] **Step 2: Add `trajectory:` block to the task YAML**

In `webagentbench/tasks/amazon/amazon_browse_category.yaml`, append to `canonical_diff:`:

```yaml
canonical_diff:
  create:
  - entity: CartItem
    desc: Cheapest Electronics product added to cart
    properties:
      product_id: {expr: "x == target['cheapest_id']"}
      quantity: {eq: 1}
      product_name: {expr: "x == target['cheapest_name']"}
      unit_price: {any: true}
      variant_selections: {any: true}
      added_at: {any: true}
  invariant:
  - collection: state.cart_items
    filter: "a.product_id != target['cheapest_id']"
  trajectory:                                     # NEW
    routes:
      must_visit:
      - { path: "/category/electronics" }
```

- [ ] **Step 3: Build the regression harness**

```python
# webagentbench/tests/trajectory_regression.py
"""3-trajectory regression harness shared by all per-task trajectory tests.

Each task using a trajectory: block must pass:
  - happy_path:   real successful trajectory  → score > pass threshold
  - do_nothing:   empty trajectory             → score == 0.0
  - shortcut:     state-only mutation, no nav  → fails because trajectory check fails
"""
from __future__ import annotations

from typing import Any, Callable

from webagentbench.eval_core.orchestrator import evaluate


def assert_three_trajectory_regression(
    task: Any,
    happy_state_builder: Callable[[Any, dict], None],
    happy_trajectory: list[dict],
    initial_state: Any,
    targets: dict,
    pass_threshold: float = 0.5,
    harness: str = "browser-use",
) -> None:
    """Run all three regression trajectories and assert their expected outcomes.

    Caller is responsible for providing:
      - a state-mutating builder that applies the happy-path mutations
      - a recorded happy-path trajectory
      - the initial seeded state and targets
    """
    import copy

    # Happy path
    state_h = copy.deepcopy(initial_state)
    happy_state_builder(state_h, targets)
    res_h = evaluate(task, state_h, targets=targets, trajectory=happy_trajectory, harness=harness)
    assert res_h["score"] >= pass_threshold, f"happy path scored {res_h['score']:.2f}: {res_h.get('reasoning')}"

    # Do nothing
    state_n = copy.deepcopy(initial_state)
    res_n = evaluate(task, state_n, targets=targets, trajectory=[], harness=harness)
    assert res_n["score"] <= 0.0, f"do-nothing scored {res_n['score']:.2f}, expected 0"

    # Shortcut: state mutated correctly, but no trajectory steps
    state_s = copy.deepcopy(initial_state)
    happy_state_builder(state_s, targets)
    res_s = evaluate(task, state_s, targets=targets, trajectory=[], harness=harness)
    assert res_s["score"] < pass_threshold, (
        f"state-only shortcut scored {res_s['score']:.2f} — trajectory: block did not enforce process evidence"
    )
```

- [ ] **Step 4: Write the worked-example test**

```python
# webagentbench/tests/test_trajectory_amazon_browse_category.py
"""Worked example: amazon_browse_category passes 3-trajectory regression."""

from webagentbench.backend.state import SessionManager
from webagentbench.tasks._registry import get_task
from webagentbench.tests.trajectory_regression import assert_three_trajectory_regression


def _add_cheapest_item(state, targets):
    """Happy-path state mutation: add the cheapest Electronics item to cart."""
    state.add_to_cart(product_id=targets["cheapest_id"], quantity=1)


def test_amazon_browse_category_three_trajectory_regression():
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="amazon", task_id="amazon_browse_category", seed=42)
    initial = sm.get_initial_snapshot(sid)
    task = get_task("amazon_browse_category")

    # Happy-path trajectory: agent visits the Electronics category page
    happy_traj = [
        {"step": 1, "url": "https://x/env/amazon/", "thinking": "", "memory": "",
         "actions": [{"action": "click", "click": {"index": 1, "label": "Electronics"}}],
         "status": "ok", "elapsed": 0.5, "state_after": None},
        {"step": 2, "url": "https://x/env/amazon/category/electronics", "thinking": "",
         "memory": "", "actions": [{"action": "click", "click": {"index": 2, "label": "Add to Cart"}}],
         "status": "ok", "elapsed": 1.0, "state_after": None},
    ]

    assert_three_trajectory_regression(
        task=task,
        happy_state_builder=_add_cheapest_item,
        happy_trajectory=happy_traj,
        initial_state=initial,
        targets=dict(targets),
        pass_threshold=0.5,
    )
```

- [ ] **Step 5: Run the worked-example test**

```bash
pytest webagentbench/tests/test_trajectory_amazon_browse_category.py -v
```

Expected: PASS. The shortcut trajectory must score below 0.5 because the `trajectory.routes.must_visit /category/electronics` check fails for an empty trajectory.

- [ ] **Step 6: Run the existing canonical-diff test for the same task to confirm no regression**

```bash
pytest webagentbench/tests/test_amazon_browse_category_canonical_diff.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add webagentbench/tasks/amazon/route_map.yaml webagentbench/tasks/amazon/role_map.yaml \
        webagentbench/tasks/amazon/amazon_browse_category.yaml \
        webagentbench/tests/trajectory_regression.py \
        webagentbench/tests/test_trajectory_amazon_browse_category.py
git commit -m "feat(eval): trajectory: end-to-end worked example on amazon_browse_category"
```

---

### Task A12: Stage-A integration smoke test

- [ ] **Step 1: Run the full test suite**

```bash
pytest webagentbench/tests/ -x --ignore=webagentbench/tests/test_adversarial_battery.py -q 2>&1 | tail -20
```

Expected: all green.

- [ ] **Step 2: Run a one-task live eval to confirm the harness still functions**

```bash
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai \
    --harness browser-use --tasks amazon_browse_category --seed 42 2>&1 | tail -10
```

Expected: episode runs; no exceptions; result JSON contains both `checks` (with at least one `trajectory.*` entry) and `state_after` snapshots in trajectory.

- [ ] **Step 3: Tag stage-A complete**

```bash
git tag stage-a-trajectory-eval
```

---

## Stage B — Per-env vocabulary tables (PARALLEL × 7 envs)

### Task B-Dispatch: Spawn 7 parallel env-vocab agents

- [ ] **Step 1: Verify the worked example landed**

```bash
ls webagentbench/tasks/amazon/{route_map,role_map}.yaml
```

- [ ] **Step 2: Dispatch 7 agents in a single message**

For each env in `[gmail, robinhood, booking, lms, patient_portal, reddit]` (Amazon already done in Task A11), spawn an agent with this self-contained prompt template:

```
You are authoring trajectory-eval vocabularies for the WebAgentBench env "{env}".

Read these references first:
  - docs/superpowers/specs/2026-04-29-trajectory-component-eval-design.md (whole file)
  - webagentbench/tasks/amazon/route_map.yaml  (worked example)
  - webagentbench/tasks/amazon/role_map.yaml   (worked example)

Then explore:
  - webagentbench/tasks/{env}/*.yaml       (instruction_template field has the natural language)
  - webagentbench/environments/{env}/      (frontend; ARIA labels visible in JSX)
  - webagentbench/backend/routes/{env}.py  (URL routes)

Produce three files at webagentbench/tasks/{env}/:

1. route_map.yaml — symbolic-name → URL template. ~10–20 entries. Use {id}, {slug} placeholders for variable segments. Cover every URL pattern reachable from any task instruction.

2. role_map.yaml — semantic-role → list of ARIA labels seen in the env's frontend. ~20–30 roles. Cover every interactive element referenced by any task instruction (search box, sort, filter, primary action buttons, destructive buttons, navigation tabs).

3. verb_templates.yaml — instruction-verb → trajectory-fragment generator. ~10 entries covering: search_for, open_the, view_the, browse, navigate_to, compare, sort, filter, then_and, before_after.
   Format:
     verb_name:
       interactions: [{ action: ..., target_role: ..., value_contains: "{object}" }]
       routes:       [{ path: "{detail_route_for[object_kind]}" }]

Constraints:
  - Read at least 10 task YAMLs in this env to ground your vocabulary in actual instructions.
  - Every role you declare must correspond to an ARIA label that exists in the env's frontend (verify by grep through the JSX).
  - Do not invent routes; verify each path against webagentbench/backend/routes/{env}.py or the frontend router.

Commit the three files in a single commit:
  git commit -m "feat(eval): {env} trajectory vocabularies"

Output a summary of: roles defined, routes defined, verbs covered, any task instructions you couldn't map (those will be the long tail for human review).
```

Use the Agent tool with `subagent_type=general-purpose` for each, in a single message (parallel dispatch).

- [ ] **Step 3: Wait for all 7 to complete**

(Agents will return summaries; user notification fires per completion.)

- [ ] **Step 4: Run the vocabulary-coverage unit test on each env**

```bash
pytest webagentbench/tests/test_vocab_coverage.py -v 2>&1 | tail -30
```

(Test created in Task B-Coverage below.)

---

### Task B-Coverage: Vocab-coverage CI test

**Files:**
- Create: `webagentbench/tests/test_vocab_coverage.py`

- [ ] **Step 1: Write the coverage test**

```python
# webagentbench/tests/test_vocab_coverage.py
"""For every env that has a role_map.yaml, assert that every target_role
referenced in any task YAML resolves in the env's role_map. Drift = CI fail."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / "tasks"
ENVS = ["amazon", "booking", "gmail", "lms", "patient_portal", "reddit", "robinhood"]


@pytest.mark.parametrize("env", ENVS)
def test_role_map_covers_referenced_roles(env):
    env_dir = ROOT / env
    role_map_path = env_dir / "role_map.yaml"
    if not role_map_path.exists():
        pytest.skip(f"{env}: no role_map.yaml yet")
    role_map = yaml.safe_load(role_map_path.read_text()) or {}
    declared = set(role_map.keys())

    referenced: set[str] = set()
    for task_yaml in env_dir.glob("*.yaml"):
        if task_yaml.name in {"route_map.yaml", "role_map.yaml", "verb_templates.yaml"}:
            continue
        data = yaml.safe_load(task_yaml.read_text())
        if not isinstance(data, dict):
            continue
        traj = (data.get("canonical_diff") or {}).get("trajectory") or {}
        for sub in ("interactions",):
            for direction in ("must_include", "must_not_include"):
                for entry in (traj.get(sub) or {}).get(direction, []) or []:
                    role = entry.get("target_role")
                    if role:
                        referenced.add(role)

    missing = referenced - declared
    assert not missing, f"{env}: roles referenced in tasks but missing from role_map.yaml: {sorted(missing)}"
```

- [ ] **Step 2: Run it**

```bash
pytest webagentbench/tests/test_vocab_coverage.py -v
```

Expected: PASS for amazon (worked example), SKIP for envs whose vocab hasn't landed yet.

- [ ] **Step 3: Commit**

```bash
git add webagentbench/tests/test_vocab_coverage.py
git commit -m "test(eval): CI guard — every referenced target_role resolves"
```

---

## Stage C — Vocabulary review gate (SERIAL, ~5 min per env)

### Task C-Review: Spot-review per env

- [ ] **Step 1: For each env, open and skim**

```bash
for env in gmail robinhood booking lms patient_portal reddit; do
  echo "=== $env ==="
  cat webagentbench/tasks/$env/route_map.yaml
  echo "---"
  cat webagentbench/tasks/$env/role_map.yaml
  echo
done
```

- [ ] **Step 2: For each env, ask explicitly**

> "{env} vocabularies look good?"

If user requests changes, edit the env's vocab file, re-run `pytest webagentbench/tests/test_vocab_coverage.py::test_role_map_covers_referenced_roles[{env}] -v`, and re-ask.

Only after user approves all 7 envs does Stage D begin.

---

## Stage D — Trajectory block generation (PARALLEL × 7 envs, sharded)

### Task D1: Generator pipeline implementation

**Files:**
- Create: `webagentbench/tasks/trajectory_generator.py`
- Test: `webagentbench/tests/test_trajectory_generator.py`

- [ ] **Step 1: Write the failing test**

```python
# webagentbench/tests/test_trajectory_generator.py
"""Verify the verb extractor and template applier produce expected blocks."""

from webagentbench.tasks.trajectory_generator import generate_trajectory_block


def test_search_for_instruction():
    instr = 'Search for "laptop" and add it to cart.'
    block = generate_trajectory_block(env_id="amazon", instruction=instr,
                                       targets={"target.search_q": "laptop"})
    assert block is not None
    inter = block["interactions"]["must_include"]
    assert any(p["target_role"] == "search_input" for p in inter)


def test_browse_category_instruction():
    instr = "Browse the Electronics category and find the cheapest item."
    block = generate_trajectory_block(env_id="amazon", instruction=instr, targets={})
    assert block is not None
    paths = [r["path"] for r in block["routes"]["must_visit"]]
    assert any("category" in p.lower() for p in paths)


def test_no_process_verbs_returns_none():
    instr = "Add product X to cart."
    block = generate_trajectory_block(env_id="amazon", instruction=instr, targets={})
    assert block is None  # nothing to verify beyond final state
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest webagentbench/tests/test_trajectory_generator.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the generator**

```python
# webagentbench/tasks/trajectory_generator.py
"""Mechanical generator: instruction text + per-env vocab → trajectory: block.

Step 1: extract verb+object pairs from the instruction.
Step 2: look up each verb in the env's verb_templates.yaml.
Step 3: resolve placeholders against targets and the env's route_map / role_map.
Step 4: deduplicate and emit the canonical YAML block.

Returns None when the instruction contains no recognised process verb.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent

_VERB_PATTERNS = {
    "search_for":  re.compile(r"\bsearch for\b\s+['\"]?(?P<obj>[^'\".,;]+)", re.I),
    "browse":      re.compile(r"\bbrowse(?: the)?\s+['\"]?(?P<obj>[^'\".,;]+?)(?:\s+category)?(?=[\s.,;]|$)", re.I),
    "open_the":    re.compile(r"\bopen the\s+['\"]?(?P<obj>[^'\".,;]+)", re.I),
    "view_the":    re.compile(r"\bview(?: the)?\s+['\"]?(?P<obj>[^'\".,;]+)", re.I),
    "navigate_to": re.compile(r"\b(?:navigate to|go to)\s+['\"]?(?P<obj>[^'\".,;]+)", re.I),
    "compare":     re.compile(r"\bcompare\b\s+(?P<obj>.+?)(?=[.;]|$)", re.I),
    "sort":        re.compile(r"\bsort(?: by)?\b", re.I),
    "filter":      re.compile(r"\bfilter\b", re.I),
    "confirm_then":re.compile(r"\bconfirm\b.+\bthen\b", re.I),
}


@lru_cache(maxsize=8)
def _load(env_id: str, name: str) -> dict[str, Any]:
    path = _ROOT / env_id / f"{name}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _resolve(s: str, refs: dict[str, Any]) -> str:
    def sub(m):
        key = m.group(1)
        return str(refs.get(key, m.group(0)))
    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}", sub, s)


def _apply_template(verb: str, obj: str | None, env_id: str, targets: dict) -> dict[str, Any]:
    templates = _load(env_id, "verb_templates")
    template = templates.get(verb)
    if not template:
        return {}
    out: dict[str, Any] = {"interactions": [], "routes": []}
    refs = {**targets, "object": obj or ""}
    for inter in template.get("interactions", []) or []:
        out["interactions"].append({
            k: (_resolve(v, refs) if isinstance(v, str) else v)
            for k, v in inter.items()
        })
    for route in template.get("routes", []) or []:
        out["routes"].append({
            k: (_resolve(v, refs) if isinstance(v, str) else v)
            for k, v in route.items()
        })
    return out


def generate_trajectory_block(
    env_id: str, instruction: str, targets: dict[str, Any]
) -> dict[str, Any] | None:
    """Return a trajectory: block dict, or None if no process evidence is needed."""
    interactions: list[dict] = []
    routes: list[dict] = []
    matched_any = False
    for verb, pattern in _VERB_PATTERNS.items():
        for match in pattern.finditer(instruction):
            matched_any = True
            obj = match.groupdict().get("obj", "").strip() if match.groupdict() else None
            applied = _apply_template(verb, obj, env_id, targets)
            interactions.extend(applied.get("interactions", []))
            routes.extend(applied.get("routes", []))
    if not matched_any:
        return None
    block: dict[str, Any] = {}
    if routes:
        block["routes"] = {"must_visit": _dedupe(routes)}
    if interactions:
        block["interactions"] = {"must_include": _dedupe(interactions)}
    return block or None


def _dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        key = tuple(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest webagentbench/tests/test_trajectory_generator.py -v
```

Expected: PASS (3/3) — assumes Amazon `verb_templates.yaml` exists with `search_for` and `browse` entries (will be created in Stage B).

- [ ] **Step 5: Commit**

```bash
git add webagentbench/tasks/trajectory_generator.py webagentbench/tests/test_trajectory_generator.py
git commit -m "feat(eval): trajectory: block generator from instruction + env vocab"
```

---

### Task D2: Per-env trajectory generation (PARALLEL × 7 envs)

- [ ] **Step 1: Dispatch 7 parallel agents, one per env**

Each agent prompt:

```
You are generating trajectory: blocks for the {env} environment in WebAgentBench.

Read first:
  - docs/superpowers/specs/2026-04-29-trajectory-component-eval-design.md (Generator pipeline section)
  - webagentbench/tasks/{env}/route_map.yaml
  - webagentbench/tasks/{env}/role_map.yaml
  - webagentbench/tasks/{env}/verb_templates.yaml
  - webagentbench/tasks/trajectory_generator.py
  - webagentbench/tests/trajectory_regression.py
  - webagentbench/tests/test_trajectory_amazon_browse_category.py (worked example)

For each task in webagentbench/tasks/{env}/*.yaml whose instruction_template contains any process verb (then, review, read, search, filter, sort, compare, confirm, verify, before, after, open the, view the, browse, navigate to):

  1. Run trajectory_generator.generate_trajectory_block(env_id, instruction, targets) to produce a candidate block.
  2. If None: skip this task (no process evidence needed).
  3. If non-None:
     a. Append the block under canonical_diff.trajectory in the YAML.
     b. Create webagentbench/tests/test_trajectory_{task_id}.py mirroring the worked example, with a happy-path trajectory and a happy_state_builder lambda that mutates state to satisfy the canonical_diff create/update entries.
     c. Run pytest on the new test. If it fails the 3-trajectory regression, surface the task in a per-env review queue (write the task_id and failure reason to webagentbench/results/trajectory_review_queue_{env}.txt) and revert the YAML edit.
     d. If it passes: commit (one commit per task).

Shard work to ≤8 parallel workers (use Bash background). Run all generated regression tests before declaring completion.

Produce a final summary:
  - tasks attempted: N
  - blocks generated: M
  - tests passing: P
  - review queue: Q tasks (with reasons)
```

Dispatch all 7 in a single message via Agent tool, `subagent_type=general-purpose`, parallel.

- [ ] **Step 2: Per-env review queue triage**

```bash
ls webagentbench/results/trajectory_review_queue_*.txt
```

For each non-empty queue file, surface to user with the task list and failure reasons.

- [ ] **Step 3: Confirm Stage-D completion**

```bash
pytest webagentbench/tests/test_trajectory_*.py -v 2>&1 | tail -20
```

All trajectory tests pass.

---

## Stage E — Degradation variant relax pass (PARALLEL × 7 envs)

### Task E1: Per-env variant relaxation

- [ ] **Step 1: Dispatch 7 parallel agents**

Each agent prompt:

```
You are adding `relax:` overrides for {env} degradation variants.

Background reading:
  - docs/superpowers/specs/2026-04-29-trajectory-component-eval-design.md (Degradation handling section)
  - webagentbench/injector/variants/  (where variants live)

For each variant YAML targeting an {env} task that now has a trajectory: block:

  - If the variant is `seed` or `network` layer: do nothing (inert).
  - If the variant is `server` layer: do nothing (bijection handles ID changes).
  - If the variant is `client` layer:
      1. Inspect what the client injection does (relabels element? hides it? adds decoy?).
      2. If it relabels an element to a label not in role_map.yaml: ADD that new label to the role_map's existing role's label-set. Do NOT add to relax — the role still resolves.
      3. If it hides an affordance the trajectory: requires (interaction or route): add the affected role/path to canonical_diff.trajectory.relax for the variant. The base task's trajectory: is inherited; relax drops the now-impossible check.

Run pytest webagentbench/tests/test_trajectory_*.py per env after edits.

Commit per variant: "fix(variants): {variant_id} trajectory relax for client-layer hide"
```

- [ ] **Step 2: Confirm**

```bash
pytest webagentbench/tests/ -k "trajectory" -v 2>&1 | tail -10
```

---

## Stage F — CI integration and full sweep

### Task F1: CI integration

**Files:**
- Modify: `.github/workflows/*.yml` (whichever runs the test suite)
- Or modify: `pyproject.toml` if pytest is invoked elsewhere

- [ ] **Step 1: Locate CI**

```bash
ls .github/workflows/ 2>/dev/null && cat .github/workflows/*.yml 2>/dev/null | grep -A2 "pytest\|test"
```

- [ ] **Step 2: Ensure trajectory tests run**

If CI uses `pytest webagentbench/tests/`, no change needed (the new tests are picked up). If CI lists specific test files, append:
  - `webagentbench/tests/test_trajectory_*.py`
  - `webagentbench/tests/test_vocab_coverage.py`
  - `webagentbench/tests/test_trajectory_norm.py`
  - `webagentbench/tests/test_match_*.py`
  - `webagentbench/tests/test_orchestrator_trajectory.py`
  - `webagentbench/tests/test_trajectory_schema.py`
  - `webagentbench/tests/test_session_snapshot.py`
  - `webagentbench/tests/test_relax_block.py`
  - `webagentbench/tests/test_trajectory_generator.py`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/
git commit -m "ci: include trajectory eval tests in CI"
```

---

### Task F2: Full-sweep proof of correctness

- [ ] **Step 1: Restart server and run full Gmail sweep**

```bash
HARNESS=browser-use WORKERS=8 ./scripts/run_gmail_sweep.sh
```

- [ ] **Step 2: Compare against gpt-5.4 Gmail baseline**

```bash
python -m webagentbench.result_utils diff \
    --base webagentbench/results/baselines/gpt54_gmail_browseruse.json \
    --new  webagentbench/results/$(ls -t webagentbench/results/ | head -1) \
    --by trajectory_block_present 2>&1 | tail -30
```

- [ ] **Step 3: Document deltas**

Create `docs/guides/trajectory-eval-baseline-deltas.md` with:
  - Baseline pass rate before trajectory eval
  - New pass rate
  - Per-task deltas (especially: tasks that previously passed by state-only shortcut)
  - Spot-check 3 tasks where the agent now scores lower; verify the lower score is correct (process evidence genuinely missing)

- [ ] **Step 4: Commit**

```bash
git add docs/guides/trajectory-eval-baseline-deltas.md
git commit -m "docs(eval): trajectory eval baseline deltas — proof of correctness"
```

- [ ] **Step 5: Tag complete**

```bash
git tag stage-f-trajectory-eval
```

---

## Self-Review

**Spec coverage:**
- Schema extension → Task A3
- Per-env vocabulary tables → Stage B (B-Dispatch + B-Coverage)
- Generator pipeline → Task D1
- 3-trajectory regression suite → Task A11 (`trajectory_regression.py`)
- Degradation handling: server-layer (bijection refs) → Task A4 `_resolve_path`; client-layer (role lookup) → Task A5; relax → Task A7
- Full snapshots → Tasks A1, A9, A10
- Variant override `relax:` → Task A3 schema, A7 test
- Stages A–F mapped to tasks A1–F2 with the right serial/parallel structure

**Placeholder scan:** none found.

**Type consistency:**
- `TrajectoryStep` keys consistent across A2 (normalizer output) and A4/A5/A6 (matcher input) — `step`, `path`, `url`, `action_type`, `target_label`, `target_role`, `value`, `state_after`.
- `RoutesBlock`/`InteractionsBlock`/`SequenceBlock`/`RelaxBlock` schema names match between A3 and matcher imports.
- `match_trajectory(steps, block, role_map, refs, agent_diff)` signature matches between A4 stub, A5 fill-in, A6 fill-in, A8 orchestrator call.
- `_relax_key` field consistently named in A4 routes matcher, A5 interactions matcher, A6 sequence matcher, A7 relax application.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-29-trajectory-component-eval.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task in Stage A (12 tasks, serial), review between, then orchestrate Stages B–F's parallel fan-out.
2. **Inline Execution** — Execute Stage A tasks here in this session with checkpoints; Stages B–F still need parallel dispatch either way.

Which approach?
