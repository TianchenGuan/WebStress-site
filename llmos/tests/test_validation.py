"""Tests for llmos.utils.validation."""

import pytest

from llmos.utils.validation import (
    validate_action_complete,
    validate_instruction,
    validate_judge_output,
    get_action_type_required_fields,
)


class TestValidateActionComplete:
    def test_valid_click(self):
        ok, errors = validate_action_complete({"action_type": "click", "bid": 1})
        assert ok
        assert errors == []

    def test_valid_fill(self):
        ok, errors = validate_action_complete({"action_type": "fill", "bid": 1, "text": "hello"})
        assert ok

    def test_valid_scroll(self):
        ok, errors = validate_action_complete({"action_type": "scroll", "bid": 1, "direction": "down"})
        assert ok

    def test_valid_finish(self):
        ok, errors = validate_action_complete({"action_type": "finish", "success": True})
        assert ok

    def test_valid_noop(self):
        ok, errors = validate_action_complete({"action_type": "noop"})
        assert ok

    def test_missing_action_type(self):
        ok, errors = validate_action_complete({"bid": 1})
        assert not ok
        assert any("action_type" in e for e in errors)

    def test_missing_required_field(self):
        ok, errors = validate_action_complete({"action_type": "fill", "bid": 1})
        assert not ok
        assert any("text" in e for e in errors)

    def test_keyboard_press(self):
        ok, errors = validate_action_complete({"action_type": "keyboard_press", "key": "Enter"})
        assert ok


class TestGetActionTypeRequiredFields:
    def test_known_types(self):
        assert "bid" in get_action_type_required_fields("click")
        assert "text" in get_action_type_required_fields("fill")
        assert "key" in get_action_type_required_fields("keyboard_press")
        assert get_action_type_required_fields("noop") == []

    def test_unknown_type(self):
        assert get_action_type_required_fields("teleport") == []


class TestValidateInstruction:
    """These tests depend on schemas/instruction.json existing."""

    def test_valid_instruction(self):
        instruction = {
            "task_id": "test_1",
            "instruction": "Click the button",
            "initial_state_template": "desktop",
            "difficulty": "easy",
            "category": "app_interaction",
        }
        ok, errors = validate_instruction(instruction)
        assert ok, f"Errors: {errors}"

    def test_minimal_instruction(self):
        instruction = {
            "task_id": "test_2",
            "instruction": "Do something",
            "initial_state_template": "desktop",
        }
        ok, errors = validate_instruction(instruction)
        assert ok, f"Errors: {errors}"
