from __future__ import annotations

from shared.format import SCROLL_HINT_TEXT, SYSTEM_PROMPT, TreeNode, render_indexed_tree
from shared.playwright_adapter import _mark_scroll_hint
from webagentbench.agent import (
    _build_fallback_summary as _build_history_fallback_summary,
    _extract_action,
    trim_messages as _trim_messages,
)


def _serialize_action_for_history(action: dict) -> str:
    """Serialize an action dict to compact JSON, stripping the 'thought' key."""
    import json
    clean = {k: v for k, v in action.items() if k != "thought"}
    return json.dumps(clean, separators=(",", ":"))


class _FakePage:
    def __init__(self, metrics: dict[str, int | bool]) -> None:
        self._metrics = metrics

    def evaluate(self, _script: str) -> dict[str, int | bool]:
        return self._metrics


def test_render_indexed_tree_uses_neutral_viewport_hint() -> None:
    root = TreeNode(role="root", has_more_below=True)

    tree_text, _ = render_indexed_tree(root)

    assert SCROLL_HINT_TEXT in tree_text
    assert "more content below" not in tree_text
    assert "Prefer explicit controls" in SYSTEM_PROMPT
    assert "viewport continues below" in SYSTEM_PROMPT
    assert 'Respond with a JSON object containing "thought" and one action' in SYSTEM_PROMPT


def test_scroll_hint_stays_generic_for_scrollable_pages() -> None:
    root = TreeNode(role="root")

    _mark_scroll_hint(
        _FakePage(
            {
                "scrollTop": 0,
                "clientHeight": 100,
                "scrollHeight": 300,
            }
        ),
        root,
    )

    assert root.has_more_below is True


def test_history_fallback_summary_prefers_facts_over_thoughts() -> None:
    messages = [
        {"role": "assistant", "content": "click('a30')"},
        {
            "role": "user",
            "content": (
                'Last action: click(\'a30\')\n'
                '[a1] main "Inbox"\n'
                '  [a2] tab "Updates" selected\n'
                '  [a3] text "1–15 of 15"\n'
                '  [a4] textbox "Email subject" value="Atlas"\n'
                '  [a5] checkbox "Needs follow-up" checked\n'
            ),
        },
    ]

    summary = _build_history_fallback_summary(messages)

    assert 'Latest route/view: main "Inbox"' in summary
    assert "click('a30')" in summary  # recent outcome captured
    assert 'Current selection state: tab "Updates" selected' in summary
    assert 'Current field values: textbox "Email subject" value="Atlas"' in summary
    assert 'probably the inbox' not in summary


def test_serialize_action_for_history_drops_thought_text() -> None:
    serialized = _serialize_action_for_history(
        {"thought": "maybe click the inbox", "action": "click", "ref": 7}
    )

    assert serialized == '{"action":"click","ref":7}'
    assert "thought" not in serialized


def test_trim_messages_inserts_factual_memory_marker() -> None:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": 'Task: Audit the inbox\n\n[1] main "Inbox"'},
        {"role": "assistant", "content": '{"thought":"open it","action":"click","ref":10}'},
        {
            "role": "user",
            "content": 'Result: Clicked [10] link "Open thread Budget"\n\n[1] main "Thread view"\n  [2] button "Back to inbox"\n',
        },
        {"role": "assistant", "content": '{"thought":"go back","action":"click","ref":2}'},
        {
            "role": "user",
            "content": 'Result: Clicked [2] button "Back to inbox"\n\n[1] main "Inbox"\n  [2] tab "Primary" selected\n',
        },
        {"role": "assistant", "content": '{"thought":"search","action":"press","key":"Enter","ref":3}'},
        {
            "role": "user",
            "content": 'Result: Pressed Enter\n\n[1] main "Search"\n  [2] textbox "Search mail" value="budget"\n',
        },
    ]

    trimmed = _trim_messages(messages, max_input_tokens=120, client=None)

    assert any("Compressed factual state" in msg["content"] for msg in trimmed)
    assert any('textbox "Search mail" value="budget"' in msg["content"] for msg in trimmed)


def test_extract_action_quotes_numeric_bid_arguments() -> None:
    assert _extract_action("click(75)") == 'click("75")'
    assert _extract_action("drag_and_drop(1, 2)") == 'drag_and_drop("1", "2")'
    assert _extract_action("fill(18, 30)") == 'fill("18", "30")'
