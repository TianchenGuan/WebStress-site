from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from webagentbench.agent_eval import run_episode
from webagentbench.app import MANIFEST_FINGERPRINT
from webagentbench.backend.routes.gmail import SessionCreateRequest, create_session
from webagentbench.backend.state import SessionManager
from webagentbench.browsergym_task import WebAgentBenchTask
from webagentbench.injector.middleware import (
    _normalize_progressive_stages,
    _progressive_delay_ms,
)
from webagentbench.injector.server import apply_server_injection
from webagentbench.tasks._evaluator import evaluate
from webagentbench.tasks._schema import Check, EvalConfig, NegativeCheck
from webagentbench.tasks._registry import get_task


def test_create_session_rejects_variant_task_mismatch() -> None:
    session_manager = SessionManager()

    with pytest.raises(HTTPException) as exc:
        create_session(
            SessionCreateRequest(
                task_id="gmail_board_briefing_prep",
                variant_filename="gmail_compliance_settings__patience.yaml",
            ),
            session_manager=session_manager,
        )

    assert exc.value.status_code == 400


def test_create_session_stores_seed_and_degradation_metadata() -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id="gmail_board_briefing_prep",
            seed=42,
            variant_filename="gmail_board_briefing__grounding.yaml",
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])

    assert state.seed == 42
    assert state.degradation["variant_id"] == "gmail_board_briefing__grounding_v1"
    assert state.degradation["base_task_id"] == "gmail_board_briefing_prep"
    assert state.degradation["variant_filename"] == "gmail_board_briefing__grounding.yaml"


def test_create_session_accepts_string_based_confusing_decoys_variants() -> None:
    session_manager = SessionManager()

    for task_id, variant_filename in [
        ("gmail_thread_version_conflict", "gmail_thread_version_conflict__grounding.yaml"),
        ("gmail_thread_detective", "gmail_thread_detective__exploration.yaml"),
    ]:
        payload = create_session(
            SessionCreateRequest(
                task_id=task_id,
                seed=42,
                variant_filename=variant_filename,
            ),
            session_manager=session_manager,
        )

        state = session_manager.get(payload["session_id"])
        assert state.degradation["variant_filename"] == variant_filename


class _TimestampState:
    def __init__(self) -> None:
        self.emails = [
            SimpleNamespace(
                timestamp=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
            )
        ]
        self.touched = False

    def touch(self) -> None:
        self.touched = True


def test_scramble_timestamps_preserves_datetime_values() -> None:
    state = _TimestampState()

    apply_server_injection(state, {"action": "scramble_timestamps", "seed": 7})

    assert isinstance(state.emails[0].timestamp, datetime)
    assert state.touched is True


class _EvalTask:
    eval = EvalConfig(
        checks=[Check(expr="True", desc="positive passes")],
        negative_checks=[
            NegativeCheck(expr="False", desc="penalty A", penalty=0.7),
            NegativeCheck(expr="False", desc="penalty B", penalty=0.6),
        ],
    )


def test_evaluator_caps_negative_penalties() -> None:
    result = evaluate(
        _EvalTask(),
        server_state=SimpleNamespace(),
        targets={},
        trajectory=[],
    )

    assert result["score"] == pytest.approx(0.05)
    assert "capped at 0.95" in result["reasoning"]


class _BenchmarkStateTask:
    eval = EvalConfig(
        checks=[
            Check(
                expr=(
                    "any(event.get('type') == 'search_submit' and 'budget' in "
                    "str(event.get('detail', {}).get('query', '')).lower() "
                    "for event in state.benchmark_state.get('events', []))"
                ),
                desc="search event recorded",
            )
        ],
        negative_checks=[],
    )


def test_evaluator_can_check_client_benchmark_state_events() -> None:
    result = evaluate(
        _BenchmarkStateTask(),
        server_state=SimpleNamespace(
            benchmark_state={
                "events": [
                    {
                        "type": "search_submit",
                        "detail": {"query": 'subject:"Q4 Budget Summary"'},
                    }
                ]
            }
        ),
        targets={},
        trajectory=[],
    )

    assert result["success"] is True
    assert result["score"] == pytest.approx(1.0)


def test_browsergym_task_rejects_stale_server_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    task = WebAgentBenchTask(seed=42, task_id="gmail_search_and_star", server_port=8099)

    monkeypatch.setattr("webagentbench.runner.wait_for_server", lambda host, port, timeout=2: True)
    monkeypatch.setattr(
        "webagentbench.browsergym_task._http_json",
        lambda url, **kwargs: {
            "status": "ok",
            "manifest_fingerprint": "stale-server",
        },
    )

    with pytest.raises(RuntimeError, match="does not match the local benchmark manifest"):
        task._ensure_server()

    monkeypatch.setattr(
        "webagentbench.browsergym_task._http_json",
        lambda url, **kwargs: {
            "status": "ok",
            "manifest_fingerprint": MANIFEST_FINGERPRINT,
        },
    )

    task._ensure_server()


def test_thread_detective_ignores_quoted_conflicting_times() -> None:
    result = evaluate(
        get_task("gmail_thread_detective"),
        server_state=SimpleNamespace(
            sent=[
                SimpleNamespace(
                    to=["sofia.rivera@vertexlab.test"],
                    body=(
                        "11:00 AM works on my side, so let's confirm that.\n\n"
                        "On 3/2/2026, 3:20:00 AM, Sofia Rivera wrote:\n"
                        "Could we use 4:00 PM for the Cedar policy review?"
                    ),
                    in_reply_to="email_123",
                    thread_id="thread_456",
                )
            ]
        ),
        targets={
            "sender_email": "sofia.rivera@vertexlab.test",
            "correct_time": "11:00 AM",
            "wrong_times": ["4:00 PM", "2:30 PM"],
            "most_recent_thread_id": "thread_456",
        },
        trajectory=[],
    )

    assert result["success"] is True
    assert result["score"] == pytest.approx(1.0)


def test_progressive_delay_respects_after_call_thresholds() -> None:
    stages = [
        {"after_call": 0, "delay_ms": 1000},
        {"after_call": 3, "delay_ms": 3000},
        {"after_call": 8, "delay_ms": 5000},
    ]

    assert _progressive_delay_ms(1, stages, 0) == 1000
    assert _progressive_delay_ms(3, stages, 0) == 1000
    assert _progressive_delay_ms(4, stages, 0) == 3000
    assert _progressive_delay_ms(8, stages, 0) == 3000
    assert _progressive_delay_ms(9, stages, 0) == 5000


def test_progressive_stage_aliases_normalize_to_after_call_thresholds() -> None:
    assert _normalize_progressive_stages(
        [
            {"requests": 2, "delay_ms": 2000},
            {"requests": 3, "delay_ms": 4000},
        ],
        0,
    ) == [
        {"after_call": 0, "delay_ms": 2000},
        {"after_call": 2, "delay_ms": 4000},
    ]

    assert _normalize_progressive_stages(
        [
            {"call_number": 1, "delay_ms": 1000},
            {"call_number": 2, "delay_ms": 2000},
            {"call_number": 3, "delay_ms": 3000},
        ],
        0,
    ) == [
        {"after_call": 0, "delay_ms": 1000},
        {"after_call": 1, "delay_ms": 2000},
        {"after_call": 2, "delay_ms": 3000},
    ]

    assert _normalize_progressive_stages(
        [
            {"until_count": 2, "delay_ms": 1000},
            {"until_count": 4, "delay_ms": 3000},
            {"delay_ms": 2000},
        ],
        0,
    ) == [
        {"after_call": 0, "delay_ms": 1000},
        {"after_call": 2, "delay_ms": 3000},
        {"after_call": 4, "delay_ms": 2000},
    ]


class _SeedAwareEnv:
    def __init__(self) -> None:
        self.seen_seed = None

    def reset(self, seed=None):
        self.seen_seed = seed
        return {"goal": "Test goal"}, {"task_info": {"task_id": "dummy"}}

    def step(self, action):
        return (
            {"last_action_error": ""},
            0.0,
            True,
            False,
            {"task_info": {"evaluation": {"score": 0.0, "success": False, "reasoning": "done"}}},
        )


class _OneShotAgent:
    conversation: list[dict] = []

    def reset(self, obs):
        self.conversation = [{"role": "user", "content": str(obs)}]

    def act(self, obs):
        return "send_msg_to_user('done')"


def test_run_episode_passes_seed_and_marks_terminated_run_completed() -> None:
    env = _SeedAwareEnv()
    episode = run_episode(
        env,
        _OneShotAgent(),
        episode_seed=123,
        max_steps=1,
        verbose=False,
    )

    assert env.seen_seed == 123
    assert episode["completed"] is True
    assert episode["trajectory"][0]["raw_action"] == "send_msg_to_user('done')"
    assert episode["trajectory"][0]["action"] == {"action": "finish", "answer": "done"}
    assert episode["trajectory"][0]["status"] == "FINISH"
