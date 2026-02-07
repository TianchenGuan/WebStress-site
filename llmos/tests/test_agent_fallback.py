"""Tests for Agent graceful fallback on parse/validation failure."""

import json
from unittest.mock import MagicMock, patch
import pytest

from llmos.core.agent import Agent


@pytest.fixture
def mock_agent(tmp_path):
    """Create an Agent with a mocked LLM client."""
    config = {
        "llm": {
            "default_provider": "openai",
            "openai": {"api_key": "test-key", "default_model": "gpt-4o"},
            "roles": {},
        },
        "simulator": {},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    mock_client = MagicMock()
    agent = Agent(
        llm_client=mock_client,
        config_path=str(config_path),
        action_space="minimal",
    )
    agent.reset("Click the Settings button")
    return agent, mock_client


@pytest.fixture
def observation():
    """Minimal observation for testing."""
    return {
        "meta": {"tick": 1, "status": "running"},
        "ui": {
            "bid": "root",
            "tag": "desktop",
            "role": "application",
            "visible": True,
            "children": [
                {
                    "bid": "btn1",
                    "tag": "button",
                    "role": "button",
                    "text": "Settings",
                    "visible": True,
                }
            ],
        },
    }


class TestAgentFallbackOnParseFailure:
    def test_noop_on_unparseable_response(self, mock_agent, observation):
        """Agent returns noop when LLM returns non-JSON garbage."""
        agent, mock_client = mock_agent
        mock_client.complete.side_effect = json.JSONDecodeError("fail", "", 0)

        action = agent.act(observation)
        assert action["action_type"] == "noop"
        assert "_parse_error" in action["_llm_data"]

    def test_noop_on_invalid_action_structure(self, mock_agent, observation):
        """Agent returns noop when LLM returns JSON without valid action_type."""
        agent, mock_client = mock_agent
        mock_client.complete.return_value = {"thought": "hmm", "action": {"not_action_type": "bad"}}

        action = agent.act(observation)
        assert action["action_type"] == "noop"

    def test_noop_on_disallowed_action(self, mock_agent, observation):
        """Agent returns noop when LLM returns an action not in allowed set."""
        agent, mock_client = mock_agent
        # send_msg_to_user is not in "minimal" action space
        mock_client.complete.return_value = {
            "thought": "ask user",
            "action": {"action_type": "send_msg_to_user", "text": "hello"},
        }

        action = agent.act(observation)
        assert action["action_type"] == "noop"

    def test_handles_list_response(self, mock_agent, observation):
        """Agent handles [{}] list wrapper from LLM."""
        agent, mock_client = mock_agent
        mock_client.complete.return_value = [
            {"thought": "click it", "action": {"action_type": "click", "bid": "btn1"}}
        ]

        action = agent.act(observation)
        assert action["action_type"] == "click"
        assert action["bid"] == "btn1"

    def test_handles_wrapper_format(self, mock_agent, observation):
        """Agent handles {"action": {...}} wrapper format."""
        agent, mock_client = mock_agent
        mock_client.complete.return_value = {
            "thought": "click settings",
            "action": {"action_type": "click", "bid": "btn1"},
        }

        action = agent.act(observation)
        assert action["action_type"] == "click"
        assert action["bid"] == "btn1"

    def test_handles_flat_action_format(self, mock_agent, observation):
        """Agent handles flat action (no 'action' wrapper key)."""
        agent, mock_client = mock_agent
        mock_client.complete.return_value = {"action_type": "click", "bid": "btn1"}

        action = agent.act(observation)
        assert action["action_type"] == "click"

    def test_noop_on_empty_list_response(self, mock_agent, observation):
        """Agent returns noop on empty list response."""
        agent, mock_client = mock_agent
        mock_client.complete.return_value = []

        action = agent.act(observation)
        assert action["action_type"] == "noop"

    def test_noop_on_value_error(self, mock_agent, observation):
        """Agent returns noop when ValueError is raised during parsing."""
        agent, mock_client = mock_agent
        mock_client.complete.side_effect = ValueError("Unknown provider: bad")

        action = agent.act(observation)
        assert action["action_type"] == "noop"
        assert "_parse_error" in action["_llm_data"]

    def test_llm_data_preserved_on_success(self, mock_agent, observation):
        """_llm_data is attached on successful action."""
        agent, mock_client = mock_agent
        mock_client.complete.return_value = {
            "thought": "click settings",
            "action": {"action_type": "click", "bid": "btn1"},
        }

        action = agent.act(observation)
        assert "_llm_data" in action
        assert action["_llm_data"]["role"] == "agent"
        assert "_parse_error" not in action["_llm_data"]

    def test_conversation_history_updated_on_fallback(self, mock_agent, observation):
        """Conversation history is updated even on fallback to noop."""
        agent, mock_client = mock_agent
        mock_client.complete.side_effect = json.JSONDecodeError("fail", "", 0)

        agent.act(observation)
        # Should have 2 entries: user message + assistant noop response
        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0]["role"] == "user"
        assert agent.conversation_history[1]["role"] == "assistant"
