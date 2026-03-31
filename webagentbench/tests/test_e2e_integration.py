"""End-to-end integration tests for the WebAgentBench stress-test pipeline.

Uses Starlette TestClient to run the full ASGI app (including middleware)
in-process.  No browser required — these tests cover the server-side path
that is common to both human play and Playwright agents.

Tests verify:
  1. Standard session lifecycle (create → mutate → evaluate)
  2. Network degradation middleware (error_then_success returns 503s)
  3. Network degradation middleware (delay actually delays)
  4. Network degradation middleware (silent_fail returns fake 200)
  5. Client injection registration and retrieval
  6. Seed/server injections mutate state
  7. Task/variant mismatch rejection
  8. Session isolation (degradation in one session doesn't leak)
  9. Evaluation scoring with negative penalty cap
"""

from __future__ import annotations

import time

import pytest
from starlette.testclient import TestClient

from webagentbench.app import app
from webagentbench.injector.middleware import clear_all_degradations


@pytest.fixture(autouse=True)
def _clean_degradation_state():
    """Reset global degradation state between tests."""
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client():
    return TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────

def _create_session(client: TestClient, task_id: str = "gmail_star_email",
                    seed: int = 42, **extra) -> dict:
    payload = {"task_id": task_id, "seed": seed, **extra}
    resp = client.post("/api/env/gmail/session", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "session_id" in data
    return data


def _referer(session_id: str) -> dict:
    """Build a Referer header the middleware can extract session from."""
    return {"Referer": f"http://testserver/env/gmail/inbox?session={session_id}"}


# ── 1. Standard session lifecycle ────────────────────────────────────────

class TestStandardLifecycle:
    def test_create_list_evaluate_destroy(self, client: TestClient):
        session = _create_session(client)
        sid = session["session_id"]

        # List emails
        resp = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert resp.status_code == 200
        emails = resp.json()
        assert emails["total"] > 0

        # Star the target email
        target_id = session["resolved_targets"]["target_email_id"]
        resp = client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
        )
        assert resp.status_code == 200

        # Evaluate
        resp = client.post("/api/env/gmail/evaluate", json={
            "session_id": sid, "task_id": "gmail_star_email",
        })
        assert resp.status_code == 200
        result = resp.json()
        assert result["success"] is True
        assert result["score"] > 0.5

        # Destroy
        resp = client.delete(f"/api/env/gmail/session/{sid}")
        assert resp.status_code == 200

    def test_evaluation_fails_when_task_not_done(self, client: TestClient):
        session = _create_session(client)
        resp = client.post("/api/env/gmail/evaluate", json={
            "session_id": session["session_id"],
            "task_id": "gmail_star_email",
        })
        result = resp.json()
        # Email is not starred → check fails
        assert result["success"] is False
        assert result["score"] < 1.0


# ── 2. Network degradation: error_then_success ──────────────────────────

class TestNetworkErrorThenSuccess:
    """Verify the middleware returns 503 for the first N calls, then passes."""

    def test_503_fires_then_succeeds(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_error_then_success",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "error_count": 2,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]

        # First 2 GET calls should return 503
        r1 = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r1.status_code == 503, f"Call 1 expected 503, got {r1.status_code}"

        r2 = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r2.status_code == 503, f"Call 2 expected 503, got {r2.status_code}"

        # Call 3 should succeed
        r3 = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r3.status_code == 200, f"Call 3 expected 200, got {r3.status_code}"
        assert r3.json()["total"] > 0

    def test_intermittent_mode_fires_probabilistically(self, client: TestClient):
        """With probability=1.0 and a fixed seed, every call should error."""
        session = _create_session(client, degradation={
            "variant_id": "test_intermittent_error",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "behavior": {"mode": "intermittent", "probability": 1.0, "seed": 7},
                },
            }],
        })
        sid = session["session_id"]

        for i in range(3):
            r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
            assert r.status_code == 503, f"Call {i+1} expected 503 with p=1.0"


# ── 3. Network degradation: delay ───────────────────────────────────────

class TestNetworkDelay:
    def test_delay_adds_latency(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_delay",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "delay",
                    "url_pattern": "**/api/env/gmail/emails",
                    "delay_ms": 500,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]

        t0 = time.monotonic()
        r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed >= 0.4, f"Expected >=400ms delay, got {elapsed*1000:.0f}ms"


# ── 4. Network degradation: silent_fail ─────────────────────────────────

class TestNetworkSilentFail:
    def test_silent_fail_returns_fake_200(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_silent_fail",
            "base_task_id": "gmail_star_email",
            "target_primitive": "verification",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "silent_fail",
                    "url_pattern": "**/api/env/gmail/emails/*/star",
                    "methods": ["POST"],
                    "response_body": {"success": True, "fake": True},
                    "fail_count": 1,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]
        target_id = session["resolved_targets"]["target_email_id"]

        # First POST → silent fail (fake 200)
        r1 = client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
            headers=_referer(sid),
        )
        assert r1.status_code == 200
        assert r1.json().get("fake") is True  # got the fake body, not real

        # Second POST → real handler
        r2 = client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
            headers=_referer(sid),
        )
        assert r2.status_code == 200
        assert "email" in r2.json()  # real response has "email" key

    def test_silent_fail_post_budget_is_not_consumed_by_matching_get(self, client: TestClient):
        session = _create_session(
            client,
            task_id="gmail_create_label",
            degradation={
                "variant_id": "test_silent_fail_labels",
                "base_task_id": "gmail_create_label",
                "target_primitive": "verification",
                "description": "test",
                "injections": [{
                    "layer": "network",
                    "params": {
                        "action": "silent_fail",
                        "url_pattern": "**/api/env/gmail/labels",
                        "methods": ["POST"],
                        "response_body": {"label": {"id": "fake_label", "name": "Important Projects"}},
                        "fail_count": 1,
                        "behavior": {"mode": "once"},
                    },
                }],
            },
        )
        sid = session["session_id"]

        # Matching GET should not consume the one-shot POST failure.
        list_resp = client.get(
            f"/api/env/gmail/labels?session_id={sid}",
            headers=_referer(sid),
        )
        assert list_resp.status_code == 200

        first_post = client.post(
            "/api/env/gmail/labels",
            json={"session_id": sid, "name": "Important Projects", "color": "#1a73e8"},
            headers=_referer(sid),
        )
        assert first_post.status_code == 200
        assert first_post.json()["label"]["id"] == "fake_label"

        second_post = client.post(
            "/api/env/gmail/labels",
            json={"session_id": sid, "name": "Important Projects Real", "color": "#1a73e8"},
            headers=_referer(sid),
        )
        assert second_post.status_code == 200
        assert second_post.json()["label"]["id"] != "fake_label"


# ── 5. Client injection registration + retrieval ────────────────────────

class TestClientInjections:
    def test_client_injections_served_via_api(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_client",
            "base_task_id": "gmail_star_email",
            "target_primitive": "grounding",
            "description": "test",
            "injections": [{
                "layer": "client",
                "params": {
                    "action": "scramble_aria",
                    "selector": "[role='listitem'] [aria-label]",
                    "behavior": {"mode": "persistent"},
                },
            }],
        })
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/degradation/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        injections = data["client_injections"]
        assert len(injections) == 1
        assert injections[0]["params"]["action"] == "scramble_aria"

    def test_no_client_injections_for_standard_session(self, client: TestClient):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/degradation/{sid}")
        assert resp.status_code == 200
        assert resp.json()["client_injections"] == []


# ── 6. Seed/server injections mutate state ───────────────────────────────

class TestSeedServerInjections:
    def test_server_scramble_timestamps(self, client: TestClient):
        """Create two sessions: one standard, one with scrambled timestamps."""
        std = _create_session(client, seed=100)
        deg = _create_session(client, seed=100, degradation={
            "variant_id": "test_scramble",
            "base_task_id": "gmail_star_email",
            "target_primitive": "planning",
            "description": "test",
            "injections": [{
                "layer": "server",
                "params": {"action": "scramble_timestamps", "seed": 42},
            }],
        })

        # Fetch emails from both
        std_emails = client.get(
            f"/api/env/gmail/emails?session_id={std['session_id']}&label=inbox"
        ).json()["items"]
        deg_emails = client.get(
            f"/api/env/gmail/emails?session_id={deg['session_id']}&label=inbox"
        ).json()["items"]

        # Same task/seed should produce same emails, but timestamps differ
        assert len(std_emails) == len(deg_emails)
        if std_emails and deg_emails:
            std_ts = std_emails[0].get("timestamp")
            deg_ts = deg_emails[0].get("timestamp")
            assert std_ts != deg_ts, "Timestamps should differ after scramble"

    def test_server_inject_distractor_emails(self, client: TestClient):
        std = _create_session(client, seed=200)
        deg = _create_session(client, seed=200, degradation={
            "variant_id": "test_distractor",
            "base_task_id": "gmail_star_email",
            "target_primitive": "grounding",
            "description": "test",
            "injections": [{
                "layer": "server",
                "params": {
                    "action": "inject_distractor_emails",
                    "count": 3,
                    "subject_prefix": "URGENT: ",
                },
            }],
        })

        std_count = client.get(
            f"/api/env/gmail/emails?session_id={std['session_id']}&label=inbox"
        ).json()["total"]
        deg_count = client.get(
            f"/api/env/gmail/emails?session_id={deg['session_id']}&label=inbox"
        ).json()["total"]

        assert deg_count == std_count + 3


# ── 7. Task/variant mismatch rejection ──────────────────────────────────

class TestVariantMismatch:
    def test_rejects_wrong_base_task(self, client: TestClient):
        resp = client.post("/api/env/gmail/session", json={
            "task_id": "gmail_star_email",
            "degradation": {
                "variant_id": "wrong",
                "base_task_id": "gmail_board_briefing_prep",
                "target_primitive": "grounding",
                "description": "wrong task",
                "injections": [],
            },
        })
        assert resp.status_code == 400
        assert "bound to task" in resp.json()["detail"]

    def test_accepts_matching_base_task(self, client: TestClient):
        resp = client.post("/api/env/gmail/session", json={
            "task_id": "gmail_star_email",
            "degradation": {
                "variant_id": "ok",
                "base_task_id": "gmail_star_email",
                "target_primitive": "patience",
                "description": "test",
                "injections": [],
            },
        })
        assert resp.status_code == 200


# ── 8. Session isolation ────────────────────────────────────────────────

class TestSessionIsolation:
    def test_degradation_does_not_leak_across_sessions(self, client: TestClient):
        """Create one degraded session and one standard; standard must be clean."""
        degraded = _create_session(client, seed=300, degradation={
            "variant_id": "test_isolation",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "error_count": 99,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        standard = _create_session(client, seed=301)

        # Degraded session → 503
        r_deg = client.get(
            f"/api/env/gmail/emails?session_id={degraded['session_id']}&label=inbox"
        )
        assert r_deg.status_code == 503

        # Standard session → 200 (no leakage)
        r_std = client.get(
            f"/api/env/gmail/emails?session_id={standard['session_id']}&label=inbox"
        )
        assert r_std.status_code == 200

    def test_destroy_clears_degradation(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_destroy",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "error_count": 99,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]

        # 503 while active
        assert client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox").status_code == 503

        # Destroy
        client.delete(f"/api/env/gmail/session/{sid}")

        # After destroy, no degradation (session also gone → 404 from handler)
        r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r.status_code != 503  # either 200 (no middleware match) or 404 (session gone)


# ── 9. Real variant file integration ────────────────────────────────────

class TestRealVariantFiles:
    def test_patience_variant_delays_requests(self, client: TestClient):
        """Load the actual gmail_compliance_settings__patience.yaml variant."""
        session = _create_session(
            client,
            task_id="gmail_compliance_settings_audit",
            variant_filename="gmail_compliance_settings__patience.yaml",
        )
        sid = session["session_id"]
        assert session["degradation_active"] is True

        # The variant applies progressive delay: first 3 calls get 1000ms delay
        t0 = time.monotonic()
        r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        elapsed = time.monotonic() - t0

        assert r.status_code == 200
        # 1000ms delay on first call
        assert elapsed >= 0.8, f"Expected >=800ms delay, got {elapsed*1000:.0f}ms"

    def test_grounding_variant_registers_client_injections(self, client: TestClient):
        """Load the actual gmail_board_briefing__grounding.yaml variant."""
        session = _create_session(
            client,
            task_id="gmail_board_briefing_prep",
            variant_filename="gmail_board_briefing__grounding.yaml",
        )
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/degradation/{sid}")
        injections = resp.json()["client_injections"]
        assert len(injections) >= 1
        assert injections[0]["params"]["action"] == "scramble_aria"


# ── 10. Evaluation scoring ──────────────────────────────────────────────

class TestEvaluationScoring:
    def test_full_pass_scores_1(self, client: TestClient):
        session = _create_session(client)
        sid = session["session_id"]
        target_id = session["resolved_targets"]["target_email_id"]

        # Do the task: star the target email
        client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
        )

        result = client.post("/api/env/gmail/evaluate", json={
            "session_id": sid, "task_id": "gmail_star_email",
        }).json()

        assert result["success"] is True
        assert result["score"] >= 0.8  # 1.0 base - possible small negative penalty

    def test_session_metadata_persisted(self, client: TestClient):
        """Verify seed and degradation are accessible on the session."""
        session = _create_session(client, seed=42, degradation={
            "variant_id": "test_meta",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "meta test",
            "injections": [],
        })
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/session/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["seed"] == 42
        assert data["degradation"]["variant_id"] == "test_meta"
        assert data["degradation"]["target_primitive"] == "patience"
