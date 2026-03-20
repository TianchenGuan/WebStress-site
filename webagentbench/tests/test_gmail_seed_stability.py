from __future__ import annotations

import random

import pytest

from webagentbench.backend.routes.gmail import SessionCreateRequest, create_session
from webagentbench.backend.seeder import _FallbackFaker
from webagentbench.backend.seeders.gmail import GmailSeedRunner
from webagentbench.backend.state import SessionManager
from webagentbench.app import build_manifest
from webagentbench.task_rendering import render_template
from webagentbench.tasks._registry import env_tasks, get_task


def _run_seed(task_id: str, seed: int = 42):
    task = get_task(task_id)
    rng = random.Random(seed)
    fake = _FallbackFaker(seed)
    fake.seed_instance(seed)
    return GmailSeedRunner().run(task, seed, fake, rng)


def test_thread_detective_seed_42_is_stable() -> None:
    _, targets = _run_seed("gmail_thread_detective")

    assert targets["sender_name"] == "Elena Patel"
    assert targets["other_sender_name"] == "Priya Rivera"
    assert targets["correct_time"] == "2:30 PM"


def test_seeded_timestamps_are_stable_for_same_seed() -> None:
    base_a, _ = _run_seed("gmail_thread_detective")
    base_b, _ = _run_seed("gmail_thread_detective")

    assert base_a["emails"][0].timestamp == base_b["emails"][0].timestamp


_GMAIL_TASK_IDS = [t.task_id for t in env_tasks("gmail")]


@pytest.mark.parametrize("task_id", _GMAIL_TASK_IDS)
def test_session_create_returns_rendered_task_data(task_id: str) -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(task_id=task_id, seed=42),
        session_manager=session_manager,
    )

    task = get_task(task_id)
    expected_instruction = render_template(
        task.instruction_template or task.instruction or "", payload["resolved_targets"]
    )

    assert payload["resolved_targets"]
    assert "{target." not in payload["instruction"]
    assert payload["instruction"] == expected_instruction
    assert payload["title"] == task.title


def test_manifest_marks_unimplemented_envs_unavailable() -> None:
    manifest = build_manifest()
    envs = {env["env_id"]: env for env in manifest["environments"]}

    assert envs["gmail"]["available"] is True
    assert envs["robinhood"]["available"] is False
    assert envs["project-manager"]["available"] is False
    assert envs["social-media"]["available"] is False
    assert envs["amazon"]["available"] is False
