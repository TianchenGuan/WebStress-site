"""Environment-agnostic entity diff extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .access import dump_entity, iter_public_state_fields, unwrap


@dataclass(frozen=True)
class Create:
    entity: str
    entity_id: str
    fields: dict[str, Any]


@dataclass(frozen=True)
class Update:
    entity: str
    entity_id: str
    field_changes: dict[str, tuple[Any, Any]]


@dataclass(frozen=True)
class Delete:
    entity: str
    entity_id: str
    last_fields: dict[str, Any]


DiffEntry = Create | Update | Delete


def _strip_ignored(entity: Any, dumped: dict[str, Any]) -> dict[str, Any]:
    ignore = getattr(type(entity), "DIFF_IGNORE_FIELDS", ())
    if not ignore:
        return dumped
    return {k: v for k, v in dumped.items() if k not in ignore}


def collections_of(state: Any) -> dict[str, list[dict[str, Any]]]:
    """Return entity collections as ``{collection_name: [entity_dict, ...]}``.

    Structural discovery: list fields containing items with an ``id`` key are
    entity collections; primitive lists are ignored.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for name, value in iter_public_state_fields(state):
        if not isinstance(value, list):
            continue
        if not value:
            out[name] = []
            continue
        dumped: list[dict[str, Any]] = []
        for item in value:
            try:
                entity_dict = _strip_ignored(item, dump_entity(item))
            except TypeError:
                dumped = []
                break
            if "id" not in entity_dict:
                dumped = []
                break
            dumped.append(entity_dict)
        if dumped or not value:
            out[name] = dumped
    return out


def index_by_id(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(e["id"]): e for e in entities if "id" in e}


def compute_diff(initial: Any, final: Any) -> list[DiffEntry]:
    before_cols = collections_of(initial)
    after_cols = collections_of(final)
    entries: list[DiffEntry] = []

    for collection in sorted(set(before_cols) | set(after_cols)):
        before = index_by_id(before_cols.get(collection, []))
        after = index_by_id(after_cols.get(collection, []))

        for entity_id in sorted(set(after) - set(before)):
            entries.append(Create(collection, entity_id, after[entity_id]))
        for entity_id in sorted(set(before) - set(after)):
            entries.append(Delete(collection, entity_id, before[entity_id]))
        for entity_id in sorted(set(before) & set(after)):
            fields = set(before[entity_id]) | set(after[entity_id])
            changes = {
                name: (before[entity_id].get(name), after[entity_id].get(name))
                for name in fields
                if before[entity_id].get(name) != after[entity_id].get(name)
            }
            if changes:
                entries.append(Update(collection, entity_id, changes))
    return entries


def collection_map_for(state: Any) -> dict[str, str]:
    """Map entity class names and collection names to collection names.

    Uses Pydantic model_fields type annotations when available (works
    even for empty lists), falling back to runtime introspection.
    """
    from typing import get_args, get_origin

    mapping: dict[str, str] = {}
    raw = unwrap(state)

    if hasattr(type(raw), "model_fields"):
        for field_name, field_info in type(raw).model_fields.items():
            annotation = field_info.annotation
            if get_origin(annotation) is list:
                args = get_args(annotation)
                if args and hasattr(args[0], "__name__"):
                    mapping.setdefault(args[0].__name__, field_name)
            mapping[field_name] = field_name

    for name, value in iter_public_state_fields(state):
        if not isinstance(value, list):
            continue
        mapping[name] = name
        if not value:
            continue
        cls_name = type(value[0]).__name__
        mapping.setdefault(cls_name, name)
    return mapping


def collection_for(entity_type: str, state: Any = None, explicit: str | None = None) -> str:
    if explicit:
        return explicit.removeprefix("state.")
    mapping = collection_map_for(state) if state is not None else {}
    if entity_type in mapping:
        return mapping[entity_type]
    lower = entity_type.lower()
    if lower.endswith("s"):
        return lower
    if lower.endswith("y"):
        return lower[:-1] + "ies"
    return lower + "s"
