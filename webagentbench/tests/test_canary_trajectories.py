"""Gmail canary trajectory suite.

Simulates correct API-level actions to verify that:
  1. Core easy Gmail tasks are still solvable (score = 1.0).
  2. Managed retry variants fire exactly where expected and remain solvable.
  3. Managed decoy / exploration variants inject the intended state without
     breaking the benchmark contract.

These tests intentionally track the current task and variant inventory rather
than older primitive-name canaries.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from webagentbench.app import app
from webagentbench.injector.middleware import clear_all_degradations
from webagentbench.runner import controller_headers, ensure_controller_secret


SEED = 42


@pytest.fixture(autouse=True)
def _clean():
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client():
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _session(client: TestClient, task_id: str, seed: int = SEED, **kw) -> dict:
    r = client.post(
        "/api/env/gmail/session",
        json={"task_id": task_id, "seed": seed, **kw},
        headers=controller_headers(),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _eval(client: TestClient, sid: str, task_id: str, benchmark_state=None) -> dict:
    payload = {"session_id": sid, "task_id": task_id}
    if benchmark_state is not None:
        payload["benchmark_state"] = benchmark_state
    r = client.post("/api/env/gmail/evaluate", json=payload, headers=controller_headers())
    assert r.status_code == 200, r.text
    return r.json()


def _ref(sid: str) -> dict:
    return {"Referer": f"http://testserver/env/gmail/inbox?session={sid}"}


def _star(client: TestClient, sid: str, email_id: str):
    return client.post(
        f"/api/env/gmail/emails/{email_id}/star",
        json={"session_id": sid},
        headers=_ref(sid),
    )


def _send(client: TestClient, sid: str, **kw):
    return client.post(
        "/api/env/gmail/send",
        json={"session_id": sid, **kw},
        headers=_ref(sid),
    )


def _delete(client: TestClient, sid: str, email_id: str):
    return client.post(
        f"/api/env/gmail/emails/{email_id}/delete",
        json={"session_id": sid},
        headers=_ref(sid),
    )


def _forward(client: TestClient, sid: str, email_id: str, to, body: str = "", cc=None):
    payload = {"session_id": sid, "to": to, "body": body}
    if cc is not None:
        payload["cc"] = cc
    return client.post(
        f"/api/env/gmail/emails/{email_id}/forward",
        json=payload,
        headers=_ref(sid),
    )


def _search(client: TestClient, sid: str, q: str):
    return client.get(
        f"/api/env/gmail/search?session_id={sid}&q={q}",
        headers=_ref(sid),
    )


def _emails(client: TestClient, sid: str, label: str = "inbox", page_size: int = 25):
    return client.get(
        f"/api/env/gmail/emails?session_id={sid}&label={label}&page_size={page_size}",
        headers=_ref(sid),
    )


def _filters(client: TestClient, sid: str):
    return client.get(
        f"/api/env/gmail/filters?session_id={sid}",
        headers=_ref(sid),
    )


def _delete_filter(client: TestClient, sid: str, filter_id: str):
    return client.delete(
        f"/api/env/gmail/filters/{filter_id}?session_id={sid}",
        headers=_ref(sid),
    )


def _create_label(client: TestClient, sid: str, name: str, color: str = "#1a73e8"):
    return client.post(
        "/api/env/gmail/labels",
        json={"session_id": sid, "name": name, "color": color},
        headers=_ref(sid),
    )


def _create_filter(
    client: TestClient,
    sid: str,
    *,
    name: str,
    query: str,
    from_addresses: list[str],
    add_labels: list[str],
    archive: bool,
):
    return client.post(
        "/api/env/gmail/filters",
        json={
            "session_id": sid,
            "name": name,
            "query": query,
            "from_addresses": from_addresses,
            "add_labels": add_labels,
            "archive": archive,
        },
        headers=_ref(sid),
    )


class TestStandardCanaries:
    def test_star_email(self, client: TestClient):
        s = _session(client, "gmail_star_email")
        _star(client, s["session_id"], s["resolved_targets"]["target_email_id"])
        ev = _eval(client, s["session_id"], "gmail_star_email")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_reply_simple(self, client: TestClient):
        s = _session(client, "gmail_reply_simple")
        sid = s["session_id"]
        target_id = s["resolved_targets"]["target_email_id"]
        _send(
            client,
            sid,
            to=["bob.martinez@company.test"],
            subject="Re: Meeting Tomorrow at 2pm",
            body="I'll be there. Thanks!",
            in_reply_to=target_id,
        )
        ev = _eval(client, sid, "gmail_reply_simple")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_compose_new(self, client: TestClient):
        s = _session(client, "gmail_compose_new")
        _send(
            client,
            s["session_id"],
            to=["alice@thornton.com"],
            subject="Weekly Report",
            body="Hi Alice, please find the weekly report attached. Best regards.",
        )
        ev = _eval(client, s["session_id"], "gmail_compose_new")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_delete_spam(self, client: TestClient):
        s = _session(client, "gmail_delete_spam")
        _delete(client, s["session_id"], s["resolved_targets"]["spam_email_id"])
        ev = _eval(client, s["session_id"], "gmail_delete_spam")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_forward_email(self, client: TestClient):
        s = _session(client, "gmail_forward_email")
        _forward(
            client,
            s["session_id"],
            s["resolved_targets"]["target_email_id"],
            to=["dave@thornton.com"],
            body="Please review this invoice.",
        )
        ev = _eval(client, s["session_id"], "gmail_forward_email")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_search_and_star(self, client: TestClient):
        s = _session(client, "gmail_search_and_star")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        search = _search(client, sid, "Q4 Budget Summary")
        assert search.status_code == 200
        items = search.json()["items"]
        assert any(item["id"] == target for item in items)

        _star(client, sid, target)
        ev = _eval(client, sid, "gmail_search_and_star")
        assert ev["success"] is True
        assert ev["score"] == 1.0


class TestRetryVariants:
    def test_star_retry_requires_second_write(self, client: TestClient):
        s = _session(
            client,
            "gmail_star_email",
            variant_filename="gmail_star_email__star_retry.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        r1 = _star(client, sid, target)
        assert r1.status_code == 503

        r2 = _star(client, sid, target)
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_star_email")
        assert ev["success"] is True

    def test_reply_send_retry_requires_second_send(self, client: TestClient):
        s = _session(
            client,
            "gmail_reply_simple",
            variant_filename="gmail_reply_simple__send_retry.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        r1 = _send(
            client,
            sid,
            to=["bob.martinez@company.test"],
            subject="Re: Meeting Tomorrow at 2pm",
            body="I'll be there. Thanks!",
            in_reply_to=target,
        )
        assert r1.status_code == 503

        ev_before = _eval(client, sid, "gmail_reply_simple")
        assert ev_before["success"] is False

        r2 = _send(
            client,
            sid,
            to=["bob.martinez@company.test"],
            subject="Re: Meeting Tomorrow at 2pm",
            body="I'll be there. Thanks!",
            in_reply_to=target,
        )
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_reply_simple")
        assert ev["success"] is True

    def test_compose_send_retry_requires_second_send(self, client: TestClient):
        s = _session(
            client,
            "gmail_compose_new",
            variant_filename="gmail_compose_new__send_retry.yaml",
        )
        sid = s["session_id"]

        r1 = _send(
            client,
            sid,
            to=["alice@thornton.com"],
            subject="Weekly Report",
            body="Hi Alice, please find the weekly report attached. Best regards.",
        )
        assert r1.status_code == 503

        ev_before = _eval(client, sid, "gmail_compose_new")
        assert ev_before["success"] is False

        r2 = _send(
            client,
            sid,
            to=["alice@thornton.com"],
            subject="Weekly Report",
            body="Hi Alice, please find the weekly report attached. Best regards.",
        )
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_compose_new")
        assert ev["success"] is True

    def test_forward_retry_requires_second_forward(self, client: TestClient):
        s = _session(
            client,
            "gmail_forward_email",
            variant_filename="gmail_forward_email__forward_retry.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        r1 = _forward(
            client,
            sid,
            target,
            to=["dave@thornton.com"],
            body="Please review this invoice.",
        )
        assert r1.status_code == 503

        ev_before = _eval(client, sid, "gmail_forward_email")
        assert ev_before["success"] is False

        r2 = _forward(
            client,
            sid,
            target,
            to=["dave@thornton.com"],
            body="Please review this invoice.",
        )
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_forward_email")
        assert ev["success"] is True

    def test_filter_retry_requires_second_filter_write(self, client: TestClient):
        s = _session(
            client,
            "gmail_filter_repair_chain",
            variant_filename="gmail_filter_repair_chain__filter_retry.yaml",
        )
        sid = s["session_id"]

        label_resp = _create_label(client, sid, "Vendor/AcmeWidgets")
        assert label_resp.status_code == 200

        r1 = _create_filter(
            client,
            sid,
            name="Acme Widgets invoices",
            query="from:*@acmewidgets.com",
            from_addresses=["*@acmewidgets.com"],
            add_labels=["Vendor/AcmeWidgets"],
            archive=True,
        )
        assert r1.status_code == 503

        r2 = _create_filter(
            client,
            sid,
            name="Acme Widgets invoices",
            query="from:*@acmewidgets.com",
            from_addresses=["*@acmewidgets.com"],
            add_labels=["Vendor/AcmeWidgets"],
            archive=True,
        )
        assert r2.status_code == 200

        filters = _filters(client, sid).json()["items"]
        assert any(
            item["from_addresses"] == ["*@acmewidgets.com"]
            and item["archive"] is True
            and "Vendor/AcmeWidgets" in item["add_labels"]
            for item in filters
        )

        ev = _eval(client, sid, "gmail_filter_repair_chain")
        assert ev["success"] is True, ev["reasoning"][:200]


class TestDecoyAndExplorationVariants:
    def test_spam_twin_adds_lookalike_without_breaking_exact_delete(self, client: TestClient):
        s = _session(
            client,
            "gmail_delete_spam",
            variant_filename="gmail_delete_spam__spam_twin.yaml",
        )
        sid = s["session_id"]
        spam_id = s["resolved_targets"]["spam_email_id"]

        inbox = _emails(client, sid).json()["items"]
        assert any(item["id"] == spam_id for item in inbox)
        assert any(
            item["from_addr"] == "winner-support@prizecentral.net"
            and item["subject"] == "You Won $1,000,000!!! Follow-up"
            for item in inbox
        )

        r = _delete(client, sid, spam_id)
        assert r.status_code == 200

        ev = _eval(client, sid, "gmail_delete_spam")
        assert ev["success"] is True

    def test_budget_twin_adds_near_identical_search_result(self, client: TestClient):
        s = _session(
            client,
            "gmail_search_and_star",
            variant_filename="gmail_search_and_star__budget_twin.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        r = _search(client, sid, "Q4 Budget Summary")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(item["id"] == target for item in items)
        assert any(item["subject"] == "Q4 Budget Summary - Draft" for item in items)

        _star(client, sid, target)
        ev = _eval(client, sid, "gmail_search_and_star")
        assert ev["success"] is True

    def test_board_briefing_label_trap_exposes_archive_hint(self, client: TestClient):
        s = _session(
            client,
            "gmail_board_briefing_prep",
            variant_filename="gmail_board_briefing_prep__label_trap.yaml",
        )
        sid = s["session_id"]

        results = _search(client, sid, "Board Materials/Archive").json()["items"]
        assert any(item["from_name"] == "Email Rules" for item in results)

        archive = _emails(client, sid, label="Board Materials/Archive")
        assert archive.status_code == 200
        assert archive.json()["total"] >= 1

    def test_thread_archaeology_exploration_requires_search_retry(self, client: TestClient):
        s = _session(
            client,
            "gmail_thread_archaeology",
            variant_filename="gmail_thread_archaeology__exploration.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["thread_email_id"]
        q = s["resolved_targets"]["thread_subject"]

        inbox = _emails(client, sid).json()["items"]
        assert all(item["id"] != target for item in inbox[:25])

        r1 = _search(client, sid, q)
        r2 = _search(client, sid, q)
        r3 = _search(client, sid, q)

        assert r1.status_code == 200 and r1.json()["total"] == 0
        assert r2.status_code == 200 and r2.json()["total"] == 0
        assert r3.status_code == 200
        assert any(item["id"] == target for item in r3.json()["items"])
