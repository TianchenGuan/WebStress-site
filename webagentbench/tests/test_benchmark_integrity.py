from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from webagentbench.agent_eval import run_episode
from webagentbench.backend.routes.gmail import SessionCreateRequest, create_session
from webagentbench.backend.state import SessionManager
from webagentbench.injector.server import apply_server_injection
from webagentbench.tasks._evaluator import evaluate
from webagentbench.tasks._schema import Check, EvalConfig, NegativeCheck


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
