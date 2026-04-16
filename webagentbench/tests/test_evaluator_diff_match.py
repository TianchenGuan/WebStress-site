"""Unit tests for match_diff — non-bijection cases only (Task 4)."""

from webagentbench.evaluator_diff import match_diff, Create, Update
from webagentbench.tasks.canonical_diff import CanonicalDiff


def _diff(d: dict) -> CanonicalDiff:
    return CanonicalDiff.model_validate(d)


def test_single_create_matches():
    cd = _diff({
        "create": [{
            "entity": "emails",
            "properties": {"subject": {"eq": "hello"}, "is_read": {"eq": False}},
        }],
    })
    agent_diff = [Create(entity="emails", entity_id="e1",
                         fields={"subject": "hello", "is_read": False})]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is True
    assert report.score == 1.0


def test_single_create_fails_when_property_mismatches():
    cd = _diff({
        "create": [{
            "entity": "emails",
            "properties": {"subject": {"eq": "hello"}},
        }],
    })
    agent_diff = [Create(entity="emails", entity_id="e1",
                         fields={"subject": "goodbye"})]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is False


def test_invariant_blocks_change():
    cd = _diff({
        "invariant": [{"collection": "state.contacts", "preserve": "ALL"}],
    })
    agent_diff = [Update(entity="contacts", entity_id="c1",
                         field_changes={"name": ("old", "new")})]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is False


def test_no_change_and_no_required_creates_passes():
    cd = _diff({
        "invariant": [{"collection": "state.emails", "preserve": "ALL"}],
    })
    report = match_diff([], cd, targets={}, initial=None, final=None)
    assert report.passed is True


def test_excess_create_fails_as_unaccounted():
    cd = _diff({
        "create": [{
            "entity": "emails",
            "properties": {"subject": {"eq": "wanted"}},
        }],
    })
    agent_diff = [
        Create(entity="emails", entity_id="e1", fields={"subject": "wanted"}),
        Create(entity="emails", entity_id="e2", fields={"subject": "extra"}),
    ]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is False
    assert any("unaccounted" in f.kind.lower() or "unaccounted" in f.description.lower()
               for f in report.failures), f"failures: {report.failures}"


# ── Task 5: Bijection matching ──────────────────────────────────────
#
# The bijection variable ``v`` is bound per-slot and exposed to ``{expr: ...}``
# predicates via ``PredicateScope.bijection_var``. The scalar ``{eq: "v"}``
# form compares literally against the string ``"v"`` (no special-casing), so
# these tests use ``{expr: "x == v"}`` to exercise the actual v-binding path.


def test_bijection_saturated_passes():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {
                "vaccine_ref": {"expr": "x == v"},
                "status": {"eq": "scheduled"},
            },
        }],
    })
    targets = {"due_ids": ["imm_1", "imm_2"]}
    agent_diff = [
        Create(entity="appointments", entity_id="a1",
               fields={"vaccine_ref": "imm_1", "status": "scheduled"}),
        Create(entity="appointments", entity_id="a2",
               fields={"vaccine_ref": "imm_2", "status": "scheduled"}),
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=None)
    assert report.passed is True, f"failures: {report.failures}"


def test_bijection_unsaturated_fails():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": ["imm_1", "imm_2"]}
    agent_diff = [
        Create(entity="appointments", entity_id="a1",
               fields={"vaccine_ref": "imm_1"}),
        # Missing imm_2
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=None)
    assert report.passed is False


def test_bijection_empty_target_requires_zero_creates():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": []}
    report = match_diff([], cd, targets=targets, initial=None, final=None)
    assert report.passed is True


def test_bijection_excess_fails():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": ["imm_1"]}
    agent_diff = [
        Create(entity="appointments", entity_id="a1",
               fields={"vaccine_ref": "imm_1"}),
        Create(entity="appointments", entity_id="a2",
               fields={"vaccine_ref": "imm_1"}),
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=None)
    assert report.passed is False
