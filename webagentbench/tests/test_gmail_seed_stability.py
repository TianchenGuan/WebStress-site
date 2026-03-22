from __future__ import annotations

import random
import subprocess
import sys

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


def test_seed_builders_import_without_circular_import() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from webagentbench.tasks._seed_builders import BUILDER_REGISTRY; print(len(BUILDER_REGISTRY))",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) > 0


def test_label_workflow_project_ids_exclude_wrong_review_decoy() -> None:
    _, targets = _run_seed("gmail_label_workflow_setup")

    assert targets["wrong_review_id"] not in targets["project_email_ids"]
    assert set(targets["review_email_ids"]).issubset(set(targets["project_email_ids"]))


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
