"""Tests for llmos.utils.rendering."""

import copy
import pytest

from llmos.utils.rendering import (
    render_observation,
    render_ui_as_text,
    extract_focusable_elements,
    summarize_state,
)


class TestRenderObservation:
    def test_removes_hidden_state(self, sample_state):
        obs = render_observation(sample_state)
        assert "hidden_state" not in obs

    def test_removes_random_seed(self, sample_state):
        obs = render_observation(sample_state)
        assert "random_seed" not in obs.get("meta", {})

    def test_preserves_meta(self, sample_state):
        obs = render_observation(sample_state)
        assert obs["meta"]["tick"] == 5
        assert obs["meta"]["status"] == "running"

    def test_filters_invisible_nodes(self, sample_state):
        obs = render_observation(sample_state)
        # The hidden_widget should be filtered out
        ui = obs["ui"]
        bids = _collect_bids(ui)
        assert "hidden_widget" not in bids

    def test_filters_minimized_window_contents(self, sample_state):
        obs = render_observation(sample_state)
        ui = obs["ui"]
        bids = _collect_bids(ui)
        # The minimized window itself may appear but its children should be gone
        assert "calc_display" not in bids

    def test_filters_hidden_files(self, sample_state):
        obs = render_observation(sample_state)
        fs = obs.get("filesystem", {})
        assert "/home/user/.secrets" not in fs

    def test_does_not_modify_original(self, sample_state):
        original = copy.deepcopy(sample_state)
        render_observation(sample_state)
        assert sample_state == original

    def test_filters_outside_viewport(self):
        state = {
            "meta": {"tick": 0, "status": "running"},
            "ui": {
                "bid": "root",
                "tag": "desktop",
                "visible": True,
                "children": [
                    {
                        "bid": "offscreen",
                        "tag": "div",
                        "visible": True,
                        "bounds": {"x": 5000, "y": 5000, "width": 100, "height": 100},
                    },
                    {
                        "bid": "onscreen",
                        "tag": "div",
                        "visible": True,
                        "bounds": {"x": 100, "y": 100, "width": 200, "height": 200},
                    },
                ],
            },
        }
        obs = render_observation(state, apply_occlusion=False)
        bids = _collect_bids(obs["ui"])
        assert "offscreen" not in bids
        assert "onscreen" in bids

    def test_filesystem_filter_by_display(self, sample_state):
        """Only files under displayed paths should be visible."""
        obs = render_observation(sample_state, filter_filesystem_by_display=True)
        fs = obs.get("filesystem", {})
        # Window has current_path="/home/user/Documents", so those files should appear
        assert "/home/user/Documents/readme.txt" in fs


class TestRenderUiAsText:
    def test_basic_rendering(self, sample_state):
        text = render_ui_as_text(sample_state)
        assert "root" in text
        assert "Start" in text

    def test_includes_bid(self, sample_state):
        text = render_ui_as_text(sample_state)
        assert "[start_btn]" in text

    def test_renders_nested(self, sample_state):
        text = render_ui_as_text(sample_state)
        assert "file1" in text
        assert "readme.txt" in text


class TestExtractFocusableElements:
    def test_finds_buttons(self, sample_state):
        elements = extract_focusable_elements(sample_state)
        bids = [e["bid"] for e in elements]
        assert "start_btn" in bids
        assert "close_btn" in bids

    def test_finds_inputs(self):
        state = {
            "ui": {
                "bid": "root",
                "tag": "div",
                "children": [
                    {"bid": "input1", "tag": "input", "role": "textbox", "value": "hello"},
                    {"bid": "cb1", "tag": "checkbox", "role": "checkbox", "checked": True},
                ],
            }
        }
        elements = extract_focusable_elements(state)
        bids = [e["bid"] for e in elements]
        assert "input1" in bids
        assert "cb1" in bids


class TestSummarizeState:
    def test_basic_summary(self, sample_state):
        summary = summarize_state(sample_state)
        assert summary["tick"] == 5
        assert summary["status"] == "running"
        assert "ui_elements" in summary
        assert summary["ui_elements"] > 0
        assert summary["files"] == 3


# ── helpers ─────────────────────────────────────────────────────────

def _collect_bids(node: dict) -> set:
    """Collect all bids in a UI tree."""
    bids = set()
    if not isinstance(node, dict):
        return bids
    bid = node.get("bid")
    if bid is not None:
        bids.add(bid)
    for child in node.get("children", []):
        bids.update(_collect_bids(child))
    return bids
