"""Tests for Judge's programmatic evaluation (no LLM calls)."""

import pytest

from llmos.core.judge import Judge


@pytest.fixture
def judge():
    """Create a Judge with LLM disabled (tests programmatic eval only)."""
    # We can't instantiate Judge without a config file normally,
    # so we test the static/pure methods directly.
    j = Judge.__new__(Judge)
    j.max_steps_per_episode = 50
    j.use_llm = False
    return j


class TestCheckCondition:
    def test_equals(self, judge):
        assert judge._check_condition("hello", "equals", "hello")
        assert not judge._check_condition("hello", "equals", "world")

    def test_contains_string(self, judge):
        assert judge._check_condition("hello world", "contains", "world")
        assert not judge._check_condition("hello", "contains", "world")

    def test_contains_list(self, judge):
        assert judge._check_condition([1, 2, 3], "contains", 2)
        assert not judge._check_condition([1, 2, 3], "contains", 4)

    def test_exists(self, judge):
        assert judge._check_condition("something", "exists", None)
        assert not judge._check_condition(None, "exists", None)

    def test_not_exists(self, judge):
        assert judge._check_condition(None, "not_exists", None)
        assert not judge._check_condition("something", "not_exists", None)

    def test_greater_than(self, judge):
        assert judge._check_condition(10, "greater_than", 5)
        assert not judge._check_condition(3, "greater_than", 5)

    def test_less_than(self, judge):
        assert judge._check_condition(3, "less_than", 5)
        assert not judge._check_condition(10, "less_than", 5)

    def test_greater_than_type_error(self, judge):
        assert not judge._check_condition("abc", "greater_than", 5)

    def test_unknown_operator(self, judge):
        assert not judge._check_condition("a", "teleport", "b")


class TestGetValueByPath:
    def test_simple_path(self, judge):
        obj = {"meta": {"tick": 5}}
        assert judge._get_value_by_path(obj, "meta.tick") == 5

    def test_empty_path(self, judge):
        obj = {"a": 1}
        assert judge._get_value_by_path(obj, "") == obj

    def test_list_index(self, judge):
        obj = {"items": [{"name": "a"}, {"name": "b"}]}
        assert judge._get_value_by_path(obj, "items.1.name") == "b"

    def test_missing_key(self, judge):
        obj = {"a": 1}
        assert judge._get_value_by_path(obj, "b.c") is None

    def test_out_of_bounds(self, judge):
        obj = {"items": [1, 2]}
        assert judge._get_value_by_path(obj, "items.5") is None

    def test_non_int_index(self, judge):
        obj = {"items": [1, 2]}
        assert judge._get_value_by_path(obj, "items.abc") is None


class TestProgrammaticEvaluation:
    def test_state_match_all_pass(self, judge):
        criteria = {
            "type": "state_match",
            "conditions": [
                {"path": "meta.tick", "operator": "equals", "value": 5},
                {"path": "meta.status", "operator": "equals", "value": "completed"},
            ],
        }
        state = {"meta": {"tick": 5, "status": "completed"}}
        result = judge._programmatic_evaluate(criteria, state, [])
        assert result is not None
        assert result["success"] is True
        assert result["score"] == 1.0

    def test_state_match_partial(self, judge):
        criteria = {
            "type": "state_match",
            "conditions": [
                {"path": "meta.tick", "operator": "equals", "value": 5, "weight": 1.0},
                {"path": "meta.status", "operator": "equals", "value": "completed", "weight": 1.0},
            ],
        }
        state = {"meta": {"tick": 5, "status": "running"}}
        result = judge._programmatic_evaluate(criteria, state, [])
        assert result is not None
        assert result["success"] is False
        assert result["score"] == 0.0  # 50% -> 0.0 in [-1, 1] mapping

    def test_state_match_all_fail(self, judge):
        criteria = {
            "type": "state_match",
            "conditions": [
                {"path": "meta.tick", "operator": "equals", "value": 99},
            ],
        }
        state = {"meta": {"tick": 5}}
        result = judge._programmatic_evaluate(criteria, state, [])
        assert result is not None
        assert result["success"] is False
        assert result["score"] == -1.0

    def test_unknown_criteria_type(self, judge):
        criteria = {"type": "custom_check"}
        result = judge._programmatic_evaluate(criteria, {}, [])
        assert result is None


class TestHeuristicEvaluation:
    def test_no_actions(self, judge):
        state = {"meta": {"tick": 0, "status": "running"}}
        result = judge._heuristic_evaluate({}, state, [])
        assert result is not None
        assert result["success"] is False
        assert result["score"] == -1.0

    def test_explicit_failure(self, judge):
        state = {"meta": {"tick": 5, "status": "failed"}}
        result = judge._heuristic_evaluate({}, state, [{"action": {}}])
        assert result is not None
        assert result["success"] is False

    def test_timeout(self, judge):
        state = {"meta": {"tick": 50, "status": "failed"}}
        result = judge._heuristic_evaluate({}, state, [{"action": {}}])
        assert result is not None
        assert result["score"] == -0.5  # Partial penalty for timeout

    def test_completed_returns_none(self, judge):
        """completed status returns None to defer to other evaluators."""
        state = {"meta": {"tick": 5, "status": "completed"}}
        result = judge._heuristic_evaluate({}, state, [{"action": {}}])
        assert result is None

    def test_running_with_actions_returns_none(self, judge):
        """Normal running state with actions returns None."""
        state = {"meta": {"tick": 5, "status": "running"}}
        result = judge._heuristic_evaluate({}, state, [{"action": {}}])
        assert result is None
