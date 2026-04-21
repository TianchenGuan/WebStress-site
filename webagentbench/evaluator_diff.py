"""Backward-compatibility shim — delegates to webagentbench.eval_core.

All evaluator logic has moved to webagentbench/eval_core/. This module
re-exports the public symbols so existing tests and tools continue to
work without mass import rewrites.
"""

from __future__ import annotations

from webagentbench.eval_core.diff import (
    Create,
    Delete,
    DiffEntry,
    Update,
    collection_for as _collection_for,
    collection_map_for as _build_collection_map,
    compute_diff,
)
from webagentbench.eval_core.matcher import (
    MatchReport as EvalReport,
    SEVERITY_PENALTY as _SEVERITY_PENALTY,
    match_diff,
)
from webagentbench.eval_core.predicates import (
    PredicateScope,
    eval_predicate,
)
from webagentbench.eval_core.safe_eval import (
    SAFE_BUILTINS as _SAFE_BUILTINS,
    SafeEvalError,
    safe_eval,
)
from webagentbench.eval_core.types import Failure

__all__ = [
    "PredicateScope",
    "eval_predicate",
    "Create",
    "Update",
    "Delete",
    "DiffEntry",
    "compute_diff",
    "Failure",
    "EvalReport",
    "match_diff",
]


def _eval_target_expr(
    expr_source: str,
    targets: dict,
    initial=None,
    final=None,
):
    """Compat wrapper for preview.py — delegates to eval_core.safe_eval."""
    return safe_eval(expr_source, {"target": targets, "initial": initial, "state": final})
