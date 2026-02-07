"""Tests for llmos.utils.patching."""

import copy
import pytest

from llmos.utils.patching import (
    find_node_by_bid,
    find_parent_of_bid,
    bid_exists,
    apply_update,
    apply_delete,
    apply_append,
    apply_insert,
    apply_id_patch,
    validate_ops,
    build_bid_index,
    build_parent_index,
)


# ── find_node_by_bid ────────────────────────────────────────────────

class TestFindNodeByBid:
    def test_find_root(self, sample_ui_tree):
        node = find_node_by_bid(sample_ui_tree, "root")
        assert node is not None
        assert node["tag"] == "desktop"

    def test_find_nested(self, sample_ui_tree):
        node = find_node_by_bid(sample_ui_tree, "close_btn")
        assert node is not None
        assert node["text"] == "X"

    def test_find_leaf(self, sample_ui_tree):
        node = find_node_by_bid(sample_ui_tree, "file1")
        assert node is not None
        assert node["text"] == "readme.txt"

    def test_not_found(self, sample_ui_tree):
        assert find_node_by_bid(sample_ui_tree, "nonexistent") is None

    def test_empty_tree(self):
        assert find_node_by_bid({}, "any") is None

    def test_non_dict(self):
        assert find_node_by_bid("not a dict", "any") is None


# ── find_parent_of_bid ──────────────────────────────────────────────

class TestFindParentOfBid:
    def test_find_parent(self, sample_ui_tree):
        result = find_parent_of_bid(sample_ui_tree, "start_btn")
        assert result is not None
        parent, idx = result
        assert parent["bid"] == "taskbar"
        assert idx == 0

    def test_root_has_no_parent(self, sample_ui_tree):
        result = find_parent_of_bid(sample_ui_tree, "root")
        assert result is None

    def test_not_found(self, sample_ui_tree):
        result = find_parent_of_bid(sample_ui_tree, "nonexistent")
        assert result is None


# ── apply_update ────────────────────────────────────────────────────

class TestApplyUpdate:
    def test_update_text(self, sample_state_copy):
        ok = apply_update(sample_state_copy, "file1", {"text": "updated.txt"})
        assert ok
        node = find_node_by_bid(sample_state_copy["ui"], "file1")
        assert node["text"] == "updated.txt"

    def test_update_adds_new_property(self, sample_state_copy):
        ok = apply_update(sample_state_copy, "file1", {"selected": True})
        assert ok
        node = find_node_by_bid(sample_state_copy["ui"], "file1")
        assert node["selected"] is True

    def test_update_nonexistent(self, sample_state_copy):
        ok = apply_update(sample_state_copy, "missing", {"text": "x"})
        assert not ok


# ── apply_delete ────────────────────────────────────────────────────

class TestApplyDelete:
    def test_delete_node(self, sample_state_copy):
        ok = apply_delete(sample_state_copy, "file2")
        assert ok
        assert find_node_by_bid(sample_state_copy["ui"], "file2") is None

    def test_delete_nonexistent(self, sample_state_copy):
        ok = apply_delete(sample_state_copy, "missing")
        assert not ok


# ── apply_append ────────────────────────────────────────────────────

class TestApplyAppend:
    def test_append_child(self, sample_state_copy):
        new_node = {"bid": "file3", "tag": "div", "text": "new_file.txt", "visible": True}
        ok = apply_append(sample_state_copy, "content_area", new_node)
        assert ok
        node = find_node_by_bid(sample_state_copy["ui"], "file3")
        assert node is not None
        assert node["text"] == "new_file.txt"

    def test_append_creates_children_list(self, sample_state_copy):
        # start_btn has no children
        new_node = {"bid": "icon", "tag": "img", "visible": True}
        ok = apply_append(sample_state_copy, "start_btn", new_node)
        assert ok
        btn = find_node_by_bid(sample_state_copy["ui"], "start_btn")
        assert len(btn["children"]) == 1

    def test_append_nonexistent_parent(self, sample_state_copy):
        ok = apply_append(sample_state_copy, "missing", {"bid": "x", "visible": True})
        assert not ok


# ── apply_insert ────────────────────────────────────────────────────

class TestApplyInsert:
    def test_insert_at_beginning(self, sample_state_copy):
        new_node = {"bid": "file0", "tag": "div", "text": "first_file.txt", "visible": True}
        ok = apply_insert(sample_state_copy, "content_area", 0, new_node)
        assert ok
        parent = find_node_by_bid(sample_state_copy["ui"], "content_area")
        assert parent["children"][0]["bid"] == "file0"

    def test_insert_clamps_index(self, sample_state_copy):
        new_node = {"bid": "file99", "tag": "div", "visible": True}
        ok = apply_insert(sample_state_copy, "content_area", 999, new_node)
        assert ok
        parent = find_node_by_bid(sample_state_copy["ui"], "content_area")
        assert parent["children"][-1]["bid"] == "file99"


# ── apply_id_patch ──────────────────────────────────────────────────

class TestApplyIdPatch:
    def test_mixed_ops(self, sample_state_copy):
        ops = [
            {"op": "update", "bid": "file1", "props": {"text": "changed.txt"}},
            {"op": "delete", "bid": "file2"},
            {"op": "append", "parent_bid": "content_area", "node": {"bid": "file3", "tag": "div", "visible": True}},
            {"op": "hidden_update", "key": "test_key", "value": True},
            {"op": "meta_update", "key": "custom", "value": 42},
        ]
        result = apply_id_patch(sample_state_copy, ops)
        assert result is sample_state_copy  # In-place
        assert find_node_by_bid(result["ui"], "file1")["text"] == "changed.txt"
        assert find_node_by_bid(result["ui"], "file2") is None
        assert find_node_by_bid(result["ui"], "file3") is not None
        assert result["hidden_state"]["test_key"] is True
        assert result["meta"]["custom"] == 42

    def test_unknown_op_raises(self, sample_state_copy):
        with pytest.raises(ValueError, match="Unknown operation type"):
            apply_id_patch(sample_state_copy, [{"op": "fly"}])

    def test_non_dict_op_raises(self, sample_state_copy):
        with pytest.raises(TypeError):
            apply_id_patch(sample_state_copy, ["not a dict"])

    def test_empty_ops(self, sample_state_copy):
        original = copy.deepcopy(sample_state_copy)
        apply_id_patch(sample_state_copy, [])
        assert sample_state_copy == original

    def test_filesystem_update(self, sample_state_copy):
        ops = [
            {"op": "filesystem_update", "path": "/new/file.txt", "props": {"content": "hi"}},
        ]
        apply_id_patch(sample_state_copy, ops)
        assert "/new/file.txt" in sample_state_copy["filesystem"]
        assert sample_state_copy["filesystem"]["/new/file.txt"]["content"] == "hi"


# ── validate_ops ────────────────────────────────────────────────────

class TestValidateOps:
    def test_valid_ops(self):
        ops = [
            {"op": "update", "bid": 1, "props": {"text": "x"}},
            {"op": "delete", "bid": 2},
            {"op": "append", "parent_bid": 1, "node": {"bid": 3, "visible": True}},
        ]
        errors = validate_ops(ops)
        assert errors == []

    def test_missing_op_field(self):
        errors = validate_ops([{"bid": 1}])
        assert any("missing 'op'" in e for e in errors)

    def test_unknown_op(self):
        errors = validate_ops([{"op": "fly"}])
        assert any("unknown op type" in e for e in errors)

    def test_missing_required_field(self):
        errors = validate_ops([{"op": "update", "bid": 1}])
        assert any("props" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_ops(["string_op"])
        assert any("not a dictionary" in e for e in errors)


# ── build_bid_index ─────────────────────────────────────────────────

class TestBuildBidIndex:
    def test_index_contains_all_nodes(self, sample_ui_tree):
        index = build_bid_index(sample_ui_tree)
        assert "root" in index
        assert "taskbar" in index
        assert "start_btn" in index
        assert "close_btn" in index
        assert "file1" in index
        assert "file2" in index

    def test_index_returns_correct_node(self, sample_ui_tree):
        index = build_bid_index(sample_ui_tree)
        assert index["file1"]["text"] == "readme.txt"
        assert index["start_btn"]["text"] == "Start"


# ── build_parent_index ──────────────────────────────────────────────

class TestBuildParentIndex:
    def test_parent_index(self, sample_ui_tree):
        index = build_parent_index(sample_ui_tree)
        assert "start_btn" in index
        parent, idx = index["start_btn"]
        assert parent["bid"] == "taskbar"
        assert idx == 0

    def test_root_not_in_parent_index(self, sample_ui_tree):
        index = build_parent_index(sample_ui_tree)
        assert "root" not in index
