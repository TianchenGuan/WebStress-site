"""Protocol regression checks for Gmail filter canonical_diff exactness."""

from pathlib import Path

import yaml


FILTER_LIST_FIELDS = {
    "from_addresses",
    "subject_keywords",
    "label_requirements",
    "add_labels",
}


def test_filter_collection_fields_use_exact_set_predicates():
    """Explicit Gmail filter criteria/actions should not accept extras."""
    issues: list[str] = []
    for task_path in sorted(Path("webagentbench/tasks/gmail").glob("*.yaml")):
        data = yaml.safe_load(task_path.read_text())
        for idx, entry in enumerate((data.get("canonical_diff") or {}).get("create") or []):
            if entry.get("entity") != "filters":
                continue
            props = entry.get("properties") or {}
            for field in FILTER_LIST_FIELDS:
                predicate = props.get(field)
                if isinstance(predicate, dict) and "superset" in predicate:
                    issues.append(f"{task_path.name}: create[{idx}].properties.{field}")

    assert not issues, "loose filter predicates found: " + ", ".join(issues)
