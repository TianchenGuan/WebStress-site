"""Tests for LLMClient JSON parsing (robust fallback)."""

import json
import pytest

from llmos.utils.llm_client import (
    LLMClient,
    _strip_thinking_tags,
    _strip_markdown_code_fences,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestStripThinkingTags:
    def test_no_tags(self):
        assert _strip_thinking_tags('{"a": 1}') == '{"a": 1}'

    def test_think_tags_before_json(self):
        text = '<think>Let me reason about this...</think>\n{"action_type": "click", "bid": 3}'
        result = _strip_thinking_tags(text)
        assert result == '{"action_type": "click", "bid": 3}'

    def test_multiline_think_tags(self):
        text = '<think>\nStep 1: look at the UI\nStep 2: click Settings\n</think>\n{"a": 1}'
        result = _strip_thinking_tags(text)
        assert result == '{"a": 1}'

    def test_empty_think_tags(self):
        text = '<think></think>{"a": 1}'
        result = _strip_thinking_tags(text)
        assert result == '{"a": 1}'

    def test_no_json_after_think(self):
        text = "<think>thinking only</think>"
        result = _strip_thinking_tags(text)
        assert result == ""


class TestStripMarkdownCodeFences:
    def test_no_fences(self):
        assert _strip_markdown_code_fences('{"a": 1}') == '{"a": 1}'

    def test_json_fences(self):
        text = '```json\n{"a": 1}\n```'
        assert _strip_markdown_code_fences(text) == '{"a": 1}'

    def test_plain_fences(self):
        text = '```\n{"a": 1}\n```'
        assert _strip_markdown_code_fences(text) == '{"a": 1}'

    def test_no_closing_fence(self):
        text = '```json\n{"a": 1}'
        assert _strip_markdown_code_fences(text) == '{"a": 1}'

    def test_multiline_json(self):
        text = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = _strip_markdown_code_fences(text)
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Unit tests for _parse_json via LLMClient instance
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    """Create an LLMClient with a minimal config for testing."""
    config = {
        "llm": {
            "default_provider": "openai",
            "openai": {"api_key": "test-key", "default_model": "gpt-4o"},
        }
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return LLMClient(config_path=str(config_path))


class TestParseJson:
    def test_clean_json(self, client):
        result = client._parse_json('{"action_type": "click", "bid": 3}')
        assert result == {"action_type": "click", "bid": 3}

    def test_markdown_fenced_json(self, client):
        text = '```json\n{"action_type": "noop"}\n```'
        result = client._parse_json(text)
        assert result == {"action_type": "noop"}

    def test_json_embedded_in_prose(self, client):
        text = 'Here is the action:\n{"action_type": "click", "bid": 5}\nDone.'
        result = client._parse_json(text)
        assert result == {"action_type": "click", "bid": 5}

    def test_think_wrapped_json(self, client):
        text = '<think>I need to click Settings</think>\n{"thought": "click settings", "action": {"action_type": "click", "bid": 3}}'
        result = client._parse_json(text)
        assert result["action"]["action_type"] == "click"

    def test_think_and_markdown_combined(self, client):
        text = '<think>reasoning here</think>\n```json\n{"action_type": "fill", "bid": 2, "text": "hello"}\n```'
        result = client._parse_json(text)
        assert result == {"action_type": "fill", "bid": 2, "text": "hello"}

    def test_list_response(self, client):
        text = '[{"action_type": "click", "bid": 1}]'
        result = client._parse_json(text)
        assert isinstance(result, list)
        assert result[0]["action_type"] == "click"

    def test_malformed_input_raises(self, client):
        with pytest.raises(json.JSONDecodeError):
            client._parse_json("this is not json at all")

    def test_empty_input_raises(self, client):
        with pytest.raises(json.JSONDecodeError):
            client._parse_json("")

    def test_whitespace_only_raises(self, client):
        with pytest.raises(json.JSONDecodeError):
            client._parse_json("   \n  ")

    def test_json_with_trailing_text(self, client):
        text = '{"action_type": "noop"} some trailing text'
        result = client._parse_json(text)
        assert result == {"action_type": "noop"}

    def test_json_with_leading_text(self, client):
        text = 'The action is: {"action_type": "hover", "bid": 7}'
        result = client._parse_json(text)
        assert result == {"action_type": "hover", "bid": 7}

    def test_nested_json(self, client):
        text = '{"thought": "test", "action": {"action_type": "fill", "bid": 1, "text": "data"}}'
        result = client._parse_json(text)
        assert result["action"]["action_type"] == "fill"

    def test_think_tags_only_raises(self, client):
        with pytest.raises(json.JSONDecodeError):
            client._parse_json("<think>only thinking, no json</think>")
