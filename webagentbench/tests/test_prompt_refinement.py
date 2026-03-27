from __future__ import annotations

from shared.format import SCROLL_HINT_TEXT, SYSTEM_PROMPT, TreeNode, render_indexed_tree
from shared.playwright_adapter import _mark_scroll_hint
from webagentbench.agent_eval import _build_history_fallback_summary, _serialize_action_for_history, _trim_messages


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
        {"role": "assistant", "content": '{"thought":"I think this is probably the inbox","action":"click","ref":30}'},
        {
            "role": "user",
            "content": (
                'Result: Clicked [30] button "Back to inbox"\n\n'
                '[1] main "Inbox"\n'
                '  [2] tab "Updates" selected\n'
                '  [3] text "1–15 of 15"\n'
                '  [4] textbox "Email subject" value="Atlas"\n'
                '  [5] checkbox "Needs follow-up" checked\n'
            ),
        },
    ]

    summary = _build_history_fallback_summary(messages)

    assert 'Latest route/view: main "Inbox"' in summary
    assert 'Recent verified outcomes: Clicked button "Back to inbox"' in summary
    assert 'Current selection state: tab "Updates" selected' in summary
    assert 'Current field values: textbox "Email subject" value="Atlas"' in summary
    assert '[30]' not in summary
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
