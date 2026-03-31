from __future__ import annotations

import pytest

from starlette.testclient import TestClient

from webagentbench.app import app
from webagentbench.backend.routes.gmail import SessionCreateRequest, create_session, list_variants
from webagentbench.backend.state import SessionManager
from webagentbench.injector.middleware import clear_all_degradations


@pytest.fixture(autouse=True)
def _reset_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_variants_endpoint_only_exposes_yaml_backed_variants(client: TestClient) -> None:
    response = client.get("/api/env/gmail/variants")
    assert response.status_code == 200, response.text

    variants = response.json()
    assert isinstance(variants, list)
    assert variants, "expected at least one YAML-backed Gmail variant"

    assert all(v.get("source") == "yaml" for v in variants)
    assert not any(str(v.get("filename", "")).startswith("__auto__") for v in variants)
    assert any(
        v.get("filename") == "gmail_change_setting__exploration.yaml"
        and v.get("base_task_id") == "gmail_change_setting"
        and v.get("target_primitive") == "exploration"
        for v in variants
    )

    api_variants = list_variants()
    assert api_variants == variants


def test_new_yaml_variant_can_create_session() -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id="gmail_change_setting",
            variant_filename="gmail_change_setting__exploration.yaml",
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])
    assert state.degradation["variant_filename"] == "gmail_change_setting__exploration.yaml"
    assert state.degradation["base_task_id"] == "gmail_change_setting"
    assert state.degradation["target_primitive"] == "exploration"
