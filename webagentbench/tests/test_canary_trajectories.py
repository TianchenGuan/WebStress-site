"""Canary trajectory suite — one standard + one stress task per primitive.

Simulates a *correct* agent via direct API calls (no LLM, no browser) to
verify that:
  1. Standard tasks are solvable (score = 1.0 with correct actions)
  2. Degraded tasks apply injections correctly (503s fire, silent fails
     intercept, distractors appear)
  3. Degraded tasks remain solvable when the agent retries/verifies

Run after every benchmark change.  If a canary fails, the benchmark is
broken — not the model.

Canary selection (simplest easy task per primitive):
  patience       → gmail_star_email
  verification   → gmail_reply_simple
  backtracking   → gmail_compose_new
  exploration    → gmail_delete_spam
  grounding      → gmail_forward_email
  state_tracking → gmail_forward_email
  planning       → gmail_search_and_star
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from webagentbench.app import app
from webagentbench.injector.middleware import clear_all_degradations


SEED = 42


@pytest.fixture(autouse=True)
def _clean():
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client():
    return TestClient(app)


# ── helpers ──────────────────────────────────────────────────────────────

def _session(client, task_id, seed=SEED, **kw):
    r = client.post("/api/env/gmail/session", json={"task_id": task_id, "seed": seed, **kw})
    assert r.status_code == 200, r.text
    return r.json()

def _eval(client, sid, task_id):
    r = client.post("/api/env/gmail/evaluate", json={"session_id": sid, "task_id": task_id})
    assert r.status_code == 200, r.text
    return r.json()

def _ref(sid):
    return {"Referer": f"http://testserver/env/gmail/inbox?session={sid}"}

def _star(client, sid, email_id):
    return client.post(f"/api/env/gmail/emails/{email_id}/star", json={"session_id": sid})

def _send(client, sid, **kw):
    return client.post("/api/env/gmail/send", json={"session_id": sid, **kw})

def _delete(client, sid, email_id):
    return client.post(f"/api/env/gmail/emails/{email_id}/delete", json={"session_id": sid})

def _forward(client, sid, email_id, to, body=""):
    return client.post(f"/api/env/gmail/emails/{email_id}/forward",
                       json={"session_id": sid, "to": to, "body": body})

def _search(client, sid, q):
    return client.get(f"/api/env/gmail/search?session_id={sid}&q={q}")

def _emails(client, sid, label="inbox"):
    return client.get(f"/api/env/gmail/emails?session_id={sid}&label={label}")


# ═══════════════════════════════════════════════════════════════════════════
# STANDARD CANARIES — verify correct actions → score 1.0
# ═══════════════════════════════════════════════════════════════════════════

class TestStandardCanaries:
    """Each test simulates the correct solution and checks score=1.0."""

    def test_star_email(self, client):
        s = _session(client, "gmail_star_email")
        _star(client, s["session_id"], s["resolved_targets"]["target_email_id"])
        ev = _eval(client, s["session_id"], "gmail_star_email")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_reply_simple(self, client):
        s = _session(client, "gmail_reply_simple")
        sid = s["session_id"]
        target_id = s["resolved_targets"]["target_email_id"]
        _send(client, sid,
              to=["bob.martinez@company.test"],
              subject="Re: Meeting Tomorrow at 2pm",
              body="I'll be there. Thanks!",
              in_reply_to=target_id)
        ev = _eval(client, sid, "gmail_reply_simple")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_compose_new(self, client):
        s = _session(client, "gmail_compose_new")
        _send(client, s["session_id"],
              to=["alice@company.test"],
              subject="Weekly Report",
              body="Hi Alice, please find the weekly report attached. Best regards.")
        ev = _eval(client, s["session_id"], "gmail_compose_new")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_delete_spam(self, client):
        s = _session(client, "gmail_delete_spam")
        _delete(client, s["session_id"], s["resolved_targets"]["spam_email_id"])
        ev = _eval(client, s["session_id"], "gmail_delete_spam")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_forward_email(self, client):
        s = _session(client, "gmail_forward_email")
        _forward(client, s["session_id"],
                 s["resolved_targets"]["target_email_id"],
                 to=["dave@company.test"],
                 body="Please review this invoice.")
        ev = _eval(client, s["session_id"], "gmail_forward_email")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_search_and_star(self, client):
        s = _session(client, "gmail_search_and_star")
        _star(client, s["session_id"], s["resolved_targets"]["target_email_id"])
        ev = _eval(client, s["session_id"], "gmail_search_and_star")
        assert ev["success"] is True
        assert ev["score"] == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# STRESS CANARIES — verify degradation fires, then correct solution works
# ═══════════════════════════════════════════════════════════════════════════

class TestStressPatience:
    """star_email + patience: first 2 star calls return 503."""

    def test_503_fires_on_star(self, client):
        s = _session(client, "gmail_star_email",
                     variant_filename="gmail_star_email__patience.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        # The variant configures error_count=2 on star AND error_count=1 on
        # the broader /emails pattern.  Both match the star URL, so the star
        # call collects errors from both injections.  Retry until success.
        r1 = _star(client, sid, target)
        assert r1.status_code == 503, f"Star call 1 should be 503, got {r1.status_code}"

        r2 = _star(client, sid, target)
        assert r2.status_code == 503, f"Star call 2 should be 503, got {r2.status_code}"

        # May need up to 2 more retries due to overlapping email-list injection
        for attempt in range(3, 6):
            r = _star(client, sid, target)
            if r.status_code == 200:
                break
        assert r.status_code == 200, f"Star call should eventually succeed, still {r.status_code} at attempt {attempt}"

        ev = _eval(client, sid, "gmail_star_email")
        assert ev["success"] is True, f"After retry, should pass: {ev['reasoning'][:200]}"

    def test_email_list_get_not_consumed_by_error_budget(self, client):
        """GET /emails passes through — methods filter preserves budget for writes."""
        s = _session(client, "gmail_star_email",
                     variant_filename="gmail_star_email__patience.yaml")
        sid = s["session_id"]

        r1 = _emails(client, sid)
        assert r1.status_code == 200, "GET email list should not consume error budget"

        r2 = _emails(client, sid)
        assert r2.status_code == 200, "Second GET email list should also succeed"


class TestStressVerification:
    """reply_simple + verification: first send silently fails."""

    def test_silent_fail_then_retry_passes(self, client):
        s = _session(client, "gmail_reply_simple",
                     variant_filename="gmail_reply_simple__verification.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        # First send: silent fail (fake 200, no state change)
        r1 = _send(client, sid,
                    to=["bob.martinez@company.test"],
                    subject="Re: Meeting Tomorrow at 2pm",
                    body="I'll be there. Thanks!",
                    in_reply_to=target)
        assert r1.status_code == 200, "Silent fail should return 200"

        # Verify send didn't actually work
        ev_before = _eval(client, sid, "gmail_reply_simple")
        assert ev_before["success"] is False, "After silent fail, eval should fail"

        # Retry: should succeed
        r2 = _send(client, sid,
                    to=["bob.martinez@company.test"],
                    subject="Re: Meeting Tomorrow at 2pm",
                    body="I'll be there. Thanks!",
                    in_reply_to=target)
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_reply_simple")
        assert ev["success"] is True, f"After retry, should pass: {ev['reasoning'][:200]}"


class TestStressBacktracking:
    """compose_new + backtracking: first 2 sends return 503."""

    def test_503_on_send_then_retry(self, client):
        s = _session(client, "gmail_compose_new",
                     variant_filename="gmail_compose_new__backtracking.yaml")
        sid = s["session_id"]

        payload = dict(to=["alice@company.test"], subject="Weekly Report",
                       body="Hi Alice, please find the weekly report attached. Best regards.")

        r1 = _send(client, sid, **payload)
        assert r1.status_code == 503, f"Send 1 should be 503, got {r1.status_code}"

        r2 = _send(client, sid, **payload)
        assert r2.status_code == 503, f"Send 2 should be 503, got {r2.status_code}"

        r3 = _send(client, sid, **payload)
        assert r3.status_code == 200, f"Send 3 should succeed, got {r3.status_code}"

        ev = _eval(client, sid, "gmail_compose_new")
        assert ev["success"] is True, f"After retry, should pass: {ev['reasoning'][:200]}"


class TestStressExploration:
    """delete_spam + exploration: first 2 deletes silently fail, distractors added."""

    def test_silent_delete_then_retry(self, client):
        s = _session(client, "gmail_delete_spam",
                     variant_filename="gmail_delete_spam__exploration.yaml")
        sid = s["session_id"]
        spam_id = s["resolved_targets"]["spam_email_id"]

        # First 2 deletes: silent fail
        r1 = _delete(client, sid, spam_id)
        assert r1.status_code == 200, "Silent fail returns 200"

        r2 = _delete(client, sid, spam_id)
        assert r2.status_code == 200, "Silent fail returns 200"

        # Verify spam not actually deleted
        ev_before = _eval(client, sid, "gmail_delete_spam")
        assert ev_before["success"] is False, "Spam should still be in inbox"

        # Third delete: succeeds
        r3 = _delete(client, sid, spam_id)
        assert r3.status_code == 200

        ev = _eval(client, sid, "gmail_delete_spam")
        assert ev["success"] is True, f"After retry, should pass: {ev['reasoning'][:200]}"

    def test_distractors_injected(self, client):
        s = _session(client, "gmail_delete_spam",
                     variant_filename="gmail_delete_spam__exploration.yaml")
        r = _emails(client, s["session_id"])
        assert r.status_code == 200
        emails = r.json()
        # Should have more emails than standard (5 URGENT distractors added)
        urgent_count = sum(1 for e in emails["items"]
                          if "URGENT" in e.get("subject", ""))
        assert urgent_count >= 3, f"Expected URGENT distractors, found {urgent_count}"


class TestStressGrounding:
    """forward_email + grounding: confusing decoy emails added."""

    def test_still_solvable_with_decoys(self, client):
        s = _session(client, "gmail_forward_email",
                     variant_filename="gmail_forward_email__grounding.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        _forward(client, sid, target, to=["dave@company.test"],
                 body="Please review this invoice.")
        ev = _eval(client, sid, "gmail_forward_email")
        assert ev["success"] is True

    def test_decoy_emails_present(self, client):
        s_standard = _session(client, "gmail_forward_email", seed=99)
        s_degraded = _session(client, "gmail_forward_email", seed=99,
                              variant_filename="gmail_forward_email__grounding.yaml")

        r_std = _emails(client, s_standard["session_id"])
        r_deg = _emails(client, s_degraded["session_id"])

        std_count = r_std.json()["total"]
        deg_count = r_deg.json()["total"]
        assert deg_count > std_count, (
            f"Degraded should have more emails (decoys). "
            f"Standard={std_count}, Degraded={deg_count}"
        )


class TestStressStateTracking:
    """forward_email + state_tracking: distractors + shuffled contacts."""

    def test_still_solvable_with_distractors(self, client):
        s = _session(client, "gmail_forward_email",
                     variant_filename="gmail_forward_email__state_tracking.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        _forward(client, sid, target, to=["dave@company.test"],
                 body="Please review this invoice.")
        ev = _eval(client, sid, "gmail_forward_email")
        assert ev["success"] is True

    def test_distractors_injected(self, client):
        s = _session(client, "gmail_forward_email",
                     variant_filename="gmail_forward_email__state_tracking.yaml")
        r = _emails(client, s["session_id"])
        emails = r.json()
        # state_tracking variant injects 5 distractors
        assert emails["total"] > 15, f"Expected extra distractors, got {emails['total']} total"


class TestStressPlanning:
    """search_and_star + planning: scrambled timestamps + first search returns empty."""

    def test_first_search_returns_stale_empty(self, client):
        s = _session(client, "gmail_search_and_star",
                     variant_filename="gmail_search_and_star__planning.yaml")
        sid = s["session_id"]

        # First search: stale_data returns empty
        r1 = _search(client, sid, "Q4 Budget Summary")
        assert r1.status_code == 200
        data = r1.json()
        assert data["total"] == 0, f"First search should return 0 (stale), got {data['total']}"

        # Second search: real results
        r2 = _search(client, sid, "Q4 Budget Summary")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["total"] >= 1, f"Second search should return results, got {data2['total']}"

    def test_still_solvable_after_retry(self, client):
        s = _session(client, "gmail_search_and_star",
                     variant_filename="gmail_search_and_star__planning.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        _star(client, sid, target)
        ev = _eval(client, sid, "gmail_search_and_star")
        assert ev["success"] is True
