"""Tests for browser-use eval helper functions.

Tests are written TDD-style -- the module under test does not exist yet.
Run with: pytest tests/webagentbench/test_browseruse_eval.py -v
"""

from __future__ import annotations

import json

import pytest

from webagentbench.browseruse_eval import (
    action_to_trajectory_format,
    build_trajectory_step,
    dom_element_to_target,
    mask_observations,
    parse_agent_output,
)


# =========================================================================
# 1. mask_observations
# =========================================================================

class TestMaskObservations:
    """Test observation masking for context window management."""

    @staticmethod
    def _obs(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def _act(content: str) -> dict:
        return {"role": "assistant", "content": content}

    # --- basic behaviour ---

    def test_keeps_first_observation(self):
        msgs = [self._obs("goal: do X"), self._act("ok")]
        result = mask_observations(msgs, window=10)
        assert result[0]["content"] == "goal: do X"

    def test_masks_middle_observations(self):
        # 1 goal + 15 obs/act pairs => obs indices: 0, 2, 4, ..., 28
        # 16 total user messages. window=5 => keep first + last 5 => mask 10.
        msgs = [self._obs("goal")]
        for i in range(15):
            msgs.append(self._act(f"action_{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=5)

        # First observation kept
        assert result[0]["content"] == "goal"

        # Count masked
        masked = [m for m in result if m["content"] == "[observation omitted]"]
        # 16 user msgs total, keep first + last 5 = 6 kept => 10 masked
        assert len(masked) == 10

    def test_assistant_messages_never_masked(self):
        msgs = [self._obs("goal")]
        for i in range(20):
            msgs.append(self._act(f"action_{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)

        assistant_msgs = [m for m in result if m["role"] == "assistant"]
        assert all(m["content"].startswith("action_") for m in assistant_msgs)
        assert len(assistant_msgs) == 20

    def test_no_masking_when_within_window(self):
        msgs = [self._obs("goal"), self._act("a1"), self._obs("obs1")]
        result = mask_observations(msgs, window=10)
        # Only 2 user msgs, window=10 => 2 <= 10+1 => no masking
        assert result == msgs

    def test_exactly_window_plus_one_no_masking(self):
        # window=3, 4 user msgs => 4 <= 3+1 => no masking
        msgs = [self._obs("goal")]
        for i in range(3):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)
        assert result == msgs

    def test_last_window_observations_kept(self):
        msgs = [self._obs("goal")]
        for i in range(10):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)

        # Last 3 user obs should be kept (obs_7, obs_8, obs_9)
        user_msgs = [m for m in result if m["role"] == "user"]
        kept = [m for m in user_msgs if m["content"] != "[observation omitted]"]
        # First + last 3 = 4 kept
        assert len(kept) == 4
        assert kept[0]["content"] == "goal"
        assert kept[-1]["content"] == "obs_9"
        assert kept[-2]["content"] == "obs_8"
        assert kept[-3]["content"] == "obs_7"

    def test_default_window_is_10(self):
        msgs = [self._obs("goal")]
        for i in range(12):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        # 13 user msgs, default window=10 => keep first + last 10 => mask 2
        result = mask_observations(msgs)
        masked = [m for m in result if m["content"] == "[observation omitted]"]
        assert len(masked) == 2

    # --- edge cases ---

    def test_empty_list(self):
        assert mask_observations([]) == []

    def test_single_observation(self):
        msgs = [self._obs("goal")]
        assert mask_observations(msgs, window=5) == msgs

    def test_preserves_message_count(self):
        msgs = [self._obs("goal")]
        for i in range(8):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)
        assert len(result) == len(msgs)


# =========================================================================
# 2. parse_agent_output
# =========================================================================

class TestParseAgentOutput:
    """Test parsing of agent structured JSON output."""

    def test_valid_json(self):
        raw = json.dumps({
            "thinking": "I need to click compose",
            "memory": "On inbox page",
            "next_goal": "Click compose button",
            "action": [{"click": {"index": 33}}],
        })
        result = parse_agent_output(raw)
        assert result["thinking"] == "I need to click compose"
        assert result["memory"] == "On inbox page"
        assert result["next_goal"] == "Click compose button"
        assert result["action"] == [{"click": {"index": 33}}]

    def test_done_action(self):
        raw = json.dumps({
            "thinking": "Task complete",
            "memory": "",
            "next_goal": "",
            "action": [{"done": {"text": "finished", "success": True}}],
        })
        result = parse_agent_output(raw)
        assert result["action"][0]["done"]["success"] is True
        assert result["action"][0]["done"]["text"] == "finished"

    def test_multi_action_list(self):
        raw = json.dumps({
            "thinking": "Two steps",
            "memory": "",
            "next_goal": "",
            "action": [
                {"click": {"index": 10}},
                {"input_text": {"index": 11, "text": "hi"}},
            ],
        })
        result = parse_agent_output(raw)
        assert len(result["action"]) == 2
        assert "click" in result["action"][0]
        assert "input_text" in result["action"][1]

    def test_plain_text_fallback_click(self):
        result = parse_agent_output("click 33")
        assert result["thinking"] == ""
        assert result["memory"] == ""
        assert result["next_goal"] == ""
        assert result["action"] == [{"click": {"index": 33}}]

    def test_malformed_json_best_effort(self):
        # Truncated JSON -- should not raise, should return best-effort
        raw = '{"thinking": "partial", "action": [{"click": {"index": 5}}'
        result = parse_agent_output(raw)
        assert isinstance(result, dict)
        # Should have action key at minimum
        assert "action" in result

    def test_empty_input(self):
        result = parse_agent_output("")
        assert isinstance(result, dict)
        assert "action" in result

    def test_returns_all_four_keys(self):
        raw = json.dumps({
            "thinking": "t",
            "memory": "m",
            "next_goal": "ng",
            "action": [{"scroll_down": {"amount": 300}}],
        })
        result = parse_agent_output(raw)
        assert set(result.keys()) >= {"thinking", "memory", "next_goal", "action"}

    def test_json_with_extra_whitespace(self):
        raw = '  \n  {"thinking": "x", "memory": "", "next_goal": "", "action": []}  \n  '
        result = parse_agent_output(raw)
        assert result["thinking"] == "x"

    def test_json_wrapped_in_markdown_code_block(self):
        raw = '```json\n{"thinking": "t", "memory": "m", "next_goal": "n", "action": [{"click": {"index": 1}}]}\n```'
        result = parse_agent_output(raw)
        assert result["action"] == [{"click": {"index": 1}}]


# =========================================================================
# 3. action_to_trajectory_format
# =========================================================================

class TestActionToTrajectoryFormat:
    """Test conversion from browser-use action dict to replay format."""

    def test_click(self):
        result = action_to_trajectory_format({"click": {"index": 33}})
        assert result == {"action": "click", "ref": "33"}

    def test_input_text(self):
        result = action_to_trajectory_format(
            {"input_text": {"index": 35, "text": "hello"}}
        )
        assert result == {"action": "fill", "ref": "35", "value": "hello"}

    def test_select_option(self):
        result = action_to_trajectory_format(
            {"select_option": {"index": 7, "option": "CA"}}
        )
        assert result == {"action": "select", "ref": "7", "value": "CA"}

    def test_scroll_down(self):
        result = action_to_trajectory_format({"scroll_down": {"amount": 300}})
        assert result == {"action": "scroll", "direction": "down"}

    def test_scroll_up(self):
        result = action_to_trajectory_format({"scroll_up": {"amount": 300}})
        assert result == {"action": "scroll", "direction": "up"}

    def test_go_back(self):
        result = action_to_trajectory_format({"go_back": {}})
        assert result == {"action": "back"}

    def test_done(self):
        result = action_to_trajectory_format(
            {"done": {"text": "done", "success": True}}
        )
        assert result == {"action": "finish", "answer": "done"}

    def test_done_with_longer_text(self):
        result = action_to_trajectory_format(
            {"done": {"text": "The total is $5,420", "success": True}}
        )
        assert result["action"] == "finish"
        assert result["answer"] == "The total is $5,420"

    def test_index_coerced_to_string(self):
        # Ref must be a string in the replay format
        result = action_to_trajectory_format({"click": {"index": 0}})
        assert result["ref"] == "0"
        assert isinstance(result["ref"], str)

    def test_unknown_action_returns_dict(self):
        # Unknown actions should not crash, should return something reasonable
        result = action_to_trajectory_format({"hover": {"index": 5}})
        assert isinstance(result, dict)
        assert "action" in result


# =========================================================================
# 4. dom_element_to_target
# =========================================================================

class TestDomElementToTarget:
    """Test DOM element to replay target conversion."""

    # --- role mapping ---

    def test_button_role(self):
        result = dom_element_to_target("button", {}, "Click me")
        assert result["role"] == "button"

    def test_link_role(self):
        result = dom_element_to_target("a", {}, "Home")
        assert result["role"] == "link"

    def test_input_role(self):
        result = dom_element_to_target("input", {}, "")
        assert result["role"] == "textbox"

    def test_textarea_role(self):
        result = dom_element_to_target("textarea", {}, "")
        assert result["role"] == "textbox"

    def test_select_role(self):
        result = dom_element_to_target("select", {}, "")
        assert result["role"] == "combobox"

    def test_article_role(self):
        result = dom_element_to_target("article", {}, "")
        assert result["role"] == "article"

    def test_unknown_tag_uses_tag_name(self):
        result = dom_element_to_target("div", {}, "")
        assert result["role"] == "div"

    # --- name priority ---

    def test_aria_label_highest_priority(self):
        result = dom_element_to_target(
            "button",
            {"aria-label": "Compose a new message", "placeholder": "ignored"},
            "Compose",
        )
        assert result["name"] == "Compose a new message"

    def test_placeholder_second_priority(self):
        result = dom_element_to_target(
            "input", {"placeholder": "Search mail"}, ""
        )
        assert result["name"] == "Search mail"

    def test_text_content_fallback(self):
        result = dom_element_to_target("button", {}, "Submit")
        assert result["name"] == "Submit"

    def test_empty_name_when_nothing_available(self):
        result = dom_element_to_target("div", {}, "")
        assert result["name"] == ""

    # --- combined ---

    def test_full_example_from_spec(self):
        result = dom_element_to_target(
            "button",
            {"aria-label": "Compose a new message"},
            "Compose",
        )
        assert result == {"role": "button", "name": "Compose a new message"}


# =========================================================================
# 5. build_trajectory_step
# =========================================================================

class TestBuildTrajectoryStep:
    """Test building a single trajectory step for the demo site."""

    @staticmethod
    def _dom_elements():
        """Fake DOM elements dict keyed by index."""
        return {
            33: ("button", {"aria-label": "Compose"}, "Compose"),
            35: ("input", {"placeholder": "To"}, ""),
        }

    def test_basic_structure(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="I should click compose",
            memory="On inbox",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=2.5,
        )
        assert result["step"] == 1
        assert result["thought"] == "I should click compose"
        assert result["status"] == "success"
        assert result["elapsed_seconds"] == 2.5

    def test_action_uses_first_action(self):
        result = build_trajectory_step(
            step_num=2,
            thinking="Fill the To field",
            memory="Compose open",
            actions=[
                {"input_text": {"index": 35, "text": "alice@example.com"}},
                {"click": {"index": 33}},
            ],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/compose?session=abc&agent_mode=1",
            status="success",
            elapsed=1.2,
        )
        assert result["action"]["action"] == "fill"
        assert result["action"]["ref"] == "35"

    def test_targets_from_dom_elements(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="Click compose",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.5,
        )
        assert result["targets"]["role"] == "button"
        assert result["targets"]["name"] == "Compose"

    def test_replay_path_extraction(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.1,
        )
        assert result["replay_path"] == "/inbox"

    def test_result_path_equals_replay_path(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.1,
        )
        assert result["result_path"] == result["replay_path"]

    def test_required_keys_present(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="t",
            memory="m",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=1.0,
        )
        required = {
            "step", "thought", "action", "targets",
            "status", "elapsed_seconds", "replay_path", "result_path",
        }
        assert required.issubset(set(result.keys()))

    def test_deeper_url_path(self):
        result = build_trajectory_step(
            step_num=3,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/settings/labels?session=abc&agent_mode=1",
            status="success",
            elapsed=0.3,
        )
        assert result["replay_path"] == "/settings/labels"

    def test_root_url_path(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/?session=abc",
            status="success",
            elapsed=0.1,
        )
        assert result["replay_path"] == "/"

    def test_missing_dom_element_for_action_index(self):
        # Action references index 99 which is not in dom_elements
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 99}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.1,
        )
        # Should not crash; targets should be a dict (possibly empty or with defaults)
        assert isinstance(result["targets"], dict)

    def test_done_action_no_dom_lookup(self):
        # done action has no index -- should not crash
        result = build_trajectory_step(
            step_num=5,
            thinking="Finished",
            memory="",
            actions=[{"done": {"text": "All done", "success": True}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.2,
        )
        assert result["action"]["action"] == "finish"
        assert isinstance(result["targets"], dict)


# =========================================================================
# Additional tests from PR review (Gap fixes)
# =========================================================================

class TestReviewGaps:
    """Tests added from PR review to close coverage gaps."""

    # Gap 2: think action type
    def test_think_action(self):
        result = action_to_trajectory_format({"think": {}})
        assert result == {"action": "think"}

    # Gap 1: plain-text fallback branches
    def test_plain_text_input(self):
        result = parse_agent_output('input 35 "hello world"')
        assert result["action"] == [{"input_text": {"index": 35, "text": "hello world"}}]

    def test_plain_text_scroll_up(self):
        result = parse_agent_output("scroll up")
        assert result["action"] == [{"scroll_up": {"amount": 300}}]

    def test_plain_text_scroll_default_down(self):
        result = parse_agent_output("scroll down")
        assert result["action"] == [{"scroll_down": {"amount": 300}}]

    def test_plain_text_go_back(self):
        result = parse_agent_output("go_back")
        assert result["action"] == [{"go_back": {}}]

    def test_plain_text_done(self):
        result = parse_agent_output("done Task complete")
        assert result["action"] == [{"done": {"text": "Task complete", "success": True}}]

    # Gap 3: empty actions list
    def test_build_step_empty_actions(self):
        step = build_trajectory_step(
            step_num=1, thinking="", memory="", actions=[],
            dom_elements={}, url="http://localhost/env/gmail/inbox",
            status="", elapsed=1.0,
        )
        assert step["action"] == {"action": "unknown"}
        assert step["targets"] == {}

    # Gap 4: dict-style dom_elements
    def test_build_step_dict_dom_elements(self):
        step = build_trajectory_step(
            step_num=1, thinking="", memory="",
            actions=[{"click": {"index": 5}}],
            dom_elements={5: {"tag_name": "button", "attributes": {"aria-label": "Send"}, "text": "Send"}},
            url="http://localhost/env/gmail/compose",
            status="", elapsed=1.0,
        )
        assert step["targets"]["role"] == "button"
        assert step["targets"]["name"] == "Send"

    # Gap 8: uppercase tag name normalization
    def test_dom_target_uppercase_tag(self):
        result = dom_element_to_target("BUTTON", {"aria-label": "Submit"})
        assert result["role"] == "button"

    def test_dom_target_mixed_case_tag(self):
        result = dom_element_to_target("Input", {"placeholder": "Search"})
        assert result["role"] == "textbox"

    # Gap 9: done action without text key
    def test_done_action_no_text_key(self):
        result = action_to_trajectory_format({"done": {"success": True}})
        assert result == {"action": "finish", "answer": ""}

    # Gap 7: mask_observations does not mutate input
    def test_mask_observations_no_mutation(self):
        original = [
            {"role": "user", "content": "goal"},
            {"role": "assistant", "content": "act"},
            {"role": "user", "content": "obs"},
        ]
        import copy
        snapshot = copy.deepcopy(original)
        mask_observations(original, window=1)
        assert original == snapshot
