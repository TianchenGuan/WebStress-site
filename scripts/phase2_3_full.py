#!/usr/bin/env python3
"""
Comprehensive Phase 2+3 testing for ALL tasks.

Phase 2 (no-action baseline): Every task must score < 0.5 with zero agent actions.
Phase 3 (correct-action): Execute correct actions from targets, verify score >= 0.9.

Usage:
  WEBAGENTBENCH_CONTROLLER_SECRET=test_secret_123 python -m webagentbench.app --port 8080
  python scripts/phase2_3_full.py [--env lms|pp|all] [--workers 8]
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import yaml

BASE = "http://127.0.0.1:8080"
SECRET = "test_secret_123"
SEED = 42


def _client():
    return httpx.Client(base_url=BASE, timeout=30,
                        headers={"X-WAB-Controller-Secret": SECRET})


def _session(client, env, task_id):
    r = client.post(f"/api/env/{env}/session",
                    json={"task_id": task_id, "seed": SEED})
    r.raise_for_status()
    d = r.json()
    return d["session_id"], d.get("resolved_targets", {})


def _check(client, env, sid, task_id):
    r = client.post(f"/api/env/{env}/evaluate",
                    json={"session_id": sid, "task_id": task_id})
    r.raise_for_status()
    return r.json()


def _act(client, env, sid, method, path, body=None):
    payload = dict(body or {})
    payload["session_id"] = sid
    if method == "GET":
        r = client.get(f"/api/env/{env}/{path}", params={"session_id": sid})
    elif method == "PUT":
        r = client.put(f"/api/env/{env}/{path}", json=payload)
    else:
        r = client.post(f"/api/env/{env}/{path}", json=payload)
    r.raise_for_status()
    return r.json()


def discover_tasks(env):
    d = Path(f"webagentbench/tasks/{env}")
    tasks = []
    for f in sorted(d.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        data = yaml.safe_load(f.read_text())
        tasks.append(data["task_id"])
    return tasks


# ── Phase 2: no-action → score < 0.5 ────────────────────────────

def test_no_action(env, task_id):
    with _client() as c:
        try:
            sid, _ = _session(c, env, task_id)
            ev = _check(c, env, sid, task_id)
            score = ev.get("score", 0)
            checks = ev.get("checks", ev.get("check_results", []))
            passed = sum(1 for ch in checks if ch.get("passed"))
            return {
                "task_id": task_id, "score": score,
                "passed": passed, "total": len(checks),
                "status": "ok" if score < 0.5 else "VACUOUS",
            }
        except Exception as e:
            return {"task_id": task_id, "score": -1, "status": "crash",
                    "error": str(e)[:100]}


# ── Phase 3: correct action → score >= 0.9 ──────────────────────

def _auto_lms(c, env, sid, t, tid):
    """Try to auto-execute correct LMS actions. Returns True if executed."""
    # Module tasks
    if "next_available_module_id" in t and "module" in tid:
        mid = t["next_available_module_id"]
        mod = _act(c, env, sid, "GET", f"modules/{mid}")
        items = mod.get("module", {}).get("content_items", [])
        for i in range(len(items)):
            try: _act(c, env, sid, "POST", f"modules/{mid}/items/{i}/complete")
            except Exception: pass
        try: _act(c, env, sid, "POST", f"modules/{mid}/complete")
        except Exception: pass
        return True

    # Drop course
    if tid == "lms_drop_course" and "target_course_id" in t:
        _act(c, env, sid, "POST", f"courses/{t['target_course_id']}/drop")
        return True

    # Mark all announcements
    if tid == "lms_mark_all_announcements_read":
        _act(c, env, sid, "POST", "announcements/mark_all_read")
        return True

    # Read urgent announcement
    if "urgent_announcement_id" in t and "read" in tid:
        _act(c, env, sid, "POST", f"announcements/{t['urgent_announcement_id']}/read")
        return True

    # Discussion post
    if "target_discussion_id" in t and "post" in tid and "reply" not in tid:
        _act(c, env, sid, "POST", f"discussions/{t['target_discussion_id']}/posts",
             {"body": "This is my substantive contribution to this discussion topic."})
        return True

    # Discussion reply
    if "target_discussion_id" in t and "reply" in tid:
        disc = _act(c, env, sid, "GET", f"discussions/{t['target_discussion_id']}")
        posts = [p for p in disc.get("posts", []) if p.get("parent_post_id") is None]
        for p in posts[:3]:
            _act(c, env, sid, "POST",
                 f"discussions/{t['target_discussion_id']}/posts/{p['id']}/reply",
                 {"body": "Great perspective, I agree and want to add my thoughts."})
        return True

    # Submit assignment (simple)
    if tid == "lms_submit_assignment" and "target_assignment_id" in t and "file_name" in t:
        _act(c, env, sid, "POST", f"assignments/{t['target_assignment_id']}/submit",
             {"file_name": t["file_name"]})
        return True

    # Conditional: score_below_70
    if "score_below_70" in t:
        if t["score_below_70"] == "true" and "unsubmitted_hw_id" in t:
            _act(c, env, sid, "POST", f"assignments/{t['unsubmitted_hw_id']}/submit",
                 {"file_name": "improvement.pdf"})
        elif "latest_announcement_id" in t:
            _act(c, env, sid, "POST", f"announcements/{t['latest_announcement_id']}/read")
        return True

    # Compare courses → drop lower
    if "lower_grade_course_id" in t and "compare" in tid:
        _act(c, env, sid, "POST", f"courses/{t['lower_grade_course_id']}/drop")
        return True

    # Identify dropped homework → resubmit lowest
    if "lowest_homework_id" in t and "identify" in tid:
        _act(c, env, sid, "POST", f"assignments/{t['lowest_homework_id']}/submit",
             {"file_name": "redo_lowest.pdf"})
        return True

    return False


def _auto_pp(c, env, sid, t, tid):
    """Try to auto-execute correct PP actions."""
    if "new_phone" in t and "phone" in tid:
        _act(c, env, sid, "POST", "profile/demographics", {"phone": t["new_phone"]})
        return True

    if tid == "pp_mark_all_read":
        _act(c, env, sid, "POST", "messages/mark-all-read")
        return True

    if "target_apt_id" in t and "cancel" in tid and "reschedule" not in tid:
        _act(c, env, sid, "POST", f"appointments/{t['target_apt_id']}/cancel")
        return True

    if "target_rx_id" in t and "refill" in tid:
        _act(c, env, sid, "POST", f"medications/{t['target_rx_id']}/refill")
        return True

    if "target_rx_id" in t and ("renewal" in tid or "renew" in tid):
        _act(c, env, sid, "POST", f"medications/{t['target_rx_id']}/renewal")
        return True

    if "pcp_id" in t and tid in ("pp_message_pcp", "pp_message_correct_provider"):
        _act(c, env, sid, "POST", "messages/send", {
            "provider_id": t["pcp_id"], "subject": "Follow-up",
            "body": "Hello, following up regarding my care.",
            "category": "clinical"})
        return True

    if "default_pharmacy_id" in t and "default_pharmacy" in tid:
        # Find a non-default pharmacy
        pharmacies = _act(c, env, sid, "GET", "pharmacies").get("items", [])
        non_default = [p for p in pharmacies if not p.get("is_default")]
        if non_default:
            _act(c, env, sid, "POST",
                 f"profile/pharmacy/{non_default[0]['id']}/set-default")
        return True

    return False


def test_correct_action(env, task_id):
    with _client() as c:
        try:
            sid, targets = _session(c, env, task_id)
            if env == "lms":
                ok = _auto_lms(c, env, sid, targets, task_id)
            else:
                ok = _auto_pp(c, env, sid, targets, task_id)
            if not ok:
                return {"task_id": task_id, "status": "skip", "score": -1}
            ev = _check(c, env, sid, task_id)
            score = ev.get("score", 0)
            checks = ev.get("checks", ev.get("check_results", []))
            failed = [ch.get("desc", "?")[:60] for ch in checks if not ch.get("passed")]
            return {
                "task_id": task_id, "score": score,
                "status": "ok" if score >= 0.9 else "FAIL",
                "failed": failed[:3],
            }
        except Exception as e:
            return {"task_id": task_id, "status": "crash", "score": -1,
                    "error": str(e)[:100]}


# ── Run ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="all", choices=["lms", "patient_portal", "pp", "all"])
    parser.add_argument("-w", "--workers", type=int, default=8)
    args = parser.parse_args()

    envs = []
    if args.env in ("lms", "all"):
        envs.append(("lms", discover_tasks("lms")))
    if args.env in ("patient_portal", "pp", "all"):
        envs.append(("patient_portal", discover_tasks("patient_portal")))

    # Phase 2
    print("=" * 65)
    print(f"PHASE 2: No-action baseline — score < 0.5 for ALL tasks")
    print("=" * 65)

    all_p2 = []
    for env, tasks in envs:
        results = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(test_no_action, env, tid): tid for tid in tasks}
            for f in as_completed(futs):
                results.append(f.result())
        results.sort(key=lambda r: r["task_id"])
        ok = sum(1 for r in results if r["status"] == "ok")
        bad = [r for r in results if r["status"] != "ok"]
        print(f"\n  {env}: {ok}/{len(results)}")
        for r in bad:
            print(f"    {r['status']:8s} {r['task_id']}  score={r['score']:.2f}"
                  f"  ({r.get('passed',0)}/{r.get('total',0)} checks)")
        all_p2.extend(results)

    p2_ok = sum(1 for r in all_p2 if r["status"] == "ok")

    # Phase 3
    print(f"\n{'=' * 65}")
    print(f"PHASE 3: Correct actions — score >= 0.9")
    print("=" * 65)

    all_p3 = []
    for env, tasks in envs:
        results = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(test_correct_action, env, tid): tid for tid in tasks}
            for f in as_completed(futs):
                results.append(f.result())
        results.sort(key=lambda r: r["task_id"])
        executed = [r for r in results if r["status"] != "skip"]
        skipped = len(results) - len(executed)
        ok = sum(1 for r in executed if r["status"] == "ok")
        bad = [r for r in executed if r["status"] not in ("ok", "skip")]
        print(f"\n  {env}: {ok}/{len(executed)} pass ({skipped} skipped)")
        for r in bad:
            line = f"    {r['status']:8s} {r['task_id']}  score={r['score']:.2f}"
            if r.get("failed"):
                line += f"  fails={r['failed']}"
            if r.get("error"):
                line += f"  err={r['error'][:60]}"
            print(line)
        all_p3.extend(results)

    p3_exec = [r for r in all_p3 if r["status"] != "skip"]
    p3_ok = sum(1 for r in p3_exec if r["status"] == "ok")
    p3_skip = len(all_p3) - len(p3_exec)

    print(f"\n{'=' * 65}")
    print(f"Phase 2 (no-action < 0.5):  {p2_ok}/{len(all_p2)}")
    print(f"Phase 3 (correct >= 0.9):   {p3_ok}/{len(p3_exec)} ({p3_skip} skipped)")
    print("=" * 65)

    if p2_ok < len(all_p2):
        sys.exit(1)


if __name__ == "__main__":
    main()
