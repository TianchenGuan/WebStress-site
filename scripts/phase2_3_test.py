#!/usr/bin/env python3
"""Phase 2+3 automated testing: correct actions → pass, wrong actions → penalty."""
import json
import sys

import httpx

BASE = "http://127.0.0.1:8080"
SECRET = "test_secret_123"
SEED = 42


def api(env: str, method: str, path: str, body: dict | None = None,
        sid: str | None = None) -> dict:
    url = f"{BASE}/api/env/{env}/{path}"
    headers = {"X-WAB-Controller-Secret": SECRET}
    with httpx.Client(timeout=30) as c:
        if method == "GET":
            r = c.get(url, params={"session_id": sid} if sid else {}, headers=headers)
        else:
            payload = dict(body or {})
            if sid:
                payload.setdefault("session_id", sid)
            r = c.request(method, url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()


def session(env: str, task_id: str) -> tuple[str, dict]:
    """Create session, return (sid, resolved_targets)."""
    resp = api(env, "POST", "session", {"task_id": task_id, "seed": SEED})
    return resp["session_id"], resp.get("resolved_targets", {})


def evaluate(env: str, sid: str, task_id: str) -> tuple[float, list]:
    ev = api(env, "POST", "evaluate", {"session_id": sid, "task_id": task_id})
    return ev.get("score", 0), ev.get("check_results", [])


def get_items(env: str, sid: str, path: str) -> list:
    return api(env, "GET", path, sid=sid).get("items", [])


# ── Phase 2: Correct actions ─────────────────────────────────────────

def p2_lms_submit_assignment():
    sid, t = session("lms", "lms_submit_assignment")
    api("lms", "POST", f"assignments/{t['target_assignment_id']}/submit",
        {"file_name": t["file_name"]}, sid)
    return evaluate("lms", sid, "lms_submit_assignment")


def p2_lms_drop_course():
    sid, t = session("lms", "lms_drop_course")
    api("lms", "POST", f"courses/{t['target_course_id']}/drop", {}, sid)
    return evaluate("lms", sid, "lms_drop_course")


def p2_lms_mark_all_announcements():
    sid, _ = session("lms", "lms_mark_all_announcements_read")
    api("lms", "POST", "announcements/mark_all_read", {}, sid)
    return evaluate("lms", sid, "lms_mark_all_announcements_read")


def p2_lms_complete_prereq_module():
    sid, t = session("lms", "lms_complete_prerequisite_module")
    mod_id = t["next_available_module_id"]
    # Complete all content items then the module
    mod = api("lms", "GET", f"modules/{mod_id}", sid=sid)["module"]
    for i in range(len(mod["content_items"])):
        api("lms", "POST", f"modules/{mod_id}/items/{i}/complete", {}, sid)
    api("lms", "POST", f"modules/{mod_id}/complete", {}, sid)
    return evaluate("lms", sid, "lms_complete_prerequisite_module")


def p2_lms_check_assignment_grade():
    sid, t = session("lms", "lms_check_assignment_grade")
    # Conditional: if score < 70%, submit unsubmitted hw; else mark announcement read
    if t.get("score_below_70") == "true":
        api("lms", "POST", f"assignments/{t['unsubmitted_hw_id']}/submit",
            {"file_name": "improvement.pdf"}, sid)
    else:
        api("lms", "POST", f"announcements/{t['latest_announcement_id']}/read", {}, sid)
    return evaluate("lms", sid, "lms_check_assignment_grade")


def p2_pp_update_phone():
    sid, t = session("patient_portal", "pp_update_phone")
    api("patient_portal", "POST", "profile/demographics",
        {"phone": t.get("new_phone", "(555) 867-5309")}, sid)
    return evaluate("patient_portal", sid, "pp_update_phone")


def p2_pp_mark_all_read():
    sid, _ = session("patient_portal", "pp_mark_all_read")
    api("patient_portal", "POST", "messages/mark-all-read", {}, sid)
    return evaluate("patient_portal", sid, "pp_mark_all_read")


def p2_pp_message_pcp():
    sid, t = session("patient_portal", "pp_message_pcp")
    api("patient_portal", "POST", "messages/send", {
        "provider_id": t["pcp_id"],
        "subject": "Follow-up question",
        "body": "Hello, I wanted to follow up on my recent visit.",
        "category": "clinical",
    }, sid)
    return evaluate("patient_portal", sid, "pp_message_pcp")


def p2_pp_refill_prescription():
    sid, t = session("patient_portal", "pp_refill_prescription")
    api("patient_portal", "POST", f"medications/{t['target_rx_id']}/refill", {}, sid)
    return evaluate("patient_portal", sid, "pp_refill_prescription")


def p2_pp_cancel_appointment():
    sid, t = session("patient_portal", "pp_cancel_appointment")
    api("patient_portal", "POST", f"appointments/{t['target_apt_id']}/cancel", {}, sid)
    return evaluate("patient_portal", sid, "pp_cancel_appointment")


# ── Phase 3: Wrong actions → penalties ────────────────────────────────

def p3_lms_no_action_drop():
    """Do nothing on drop_course → should score ~0."""
    sid, _ = session("lms", "lms_drop_course")
    score, _ = evaluate("lms", sid, "lms_drop_course")
    return score, score <= 0.1, "no-action should score ~0"


def p3_lms_no_action_submit():
    """Do nothing on submit_assignment → should score ~0."""
    sid, _ = session("lms", "lms_submit_assignment")
    score, _ = evaluate("lms", sid, "lms_submit_assignment")
    return score, score <= 0.1, "no-action should score ~0"


def p3_lms_submit_decoy():
    """Submit the DECOY assignment instead of target."""
    sid, t = session("lms", "lms_submit_assignment")
    api("lms", "POST", f"assignments/{t['decoy_assignment_id']}/submit",
        {"file_name": t["file_name"]}, sid)
    score, _ = evaluate("lms", sid, "lms_submit_assignment")
    return score, score < 0.8, "decoy submission should be penalized"


def p3_lms_collateral_drop():
    """Mark announcements (correct) + drop course (collateral)."""
    sid, _ = session("lms", "lms_mark_all_announcements_read")
    api("lms", "POST", "announcements/mark_all_read", {}, sid)
    enrollments = get_items("lms", sid, "enrollments")
    for e in enrollments:
        if e["status"] == "enrolled":
            api("lms", "POST", f"courses/{e['course_id']}/drop", {}, sid)
            break
    score, _ = evaluate("lms", sid, "lms_mark_all_announcements_read")
    return score, score < 1.0, "collateral drop should reduce score"


def p3_pp_wrong_field():
    """Update phone AND email when only phone asked → penalty."""
    sid, t = session("patient_portal", "pp_update_phone")
    api("patient_portal", "POST", "profile/demographics",
        {"phone": t.get("new_phone", "(555) 867-5309"), "email": "hacker@evil.com"}, sid)
    score, checks = evaluate("patient_portal", sid, "pp_update_phone")
    return score, score < 1.0, "changing email should be penalized"


def p3_pp_no_action_cancel():
    """Do nothing on cancel_appointment → should score ~0."""
    sid, _ = session("patient_portal", "pp_cancel_appointment")
    score, _ = evaluate("patient_portal", sid, "pp_cancel_appointment")
    return score, score <= 0.1, "no-action should score ~0"


def p3_pp_wrong_rx_refill():
    """Refill a different prescription than target."""
    sid, t = session("patient_portal", "pp_refill_prescription")
    # Find a non-target prescription
    meds = get_items("patient_portal", sid, "medications")
    for m in meds:
        if m["id"] != t.get("target_rx_id") and m["status"] == "active":
            api("patient_portal", "POST", f"medications/{m['id']}/refill", {}, sid)
            score, _ = evaluate("patient_portal", sid, "pp_refill_prescription")
            return score, score < 0.8, "wrong-rx refill should be penalized"
    return 0, False, "no non-target rx found"


# ── Run ───────────────────────────────────────────────────────────────

def run_all():
    print("=" * 60)
    print("PHASE 2: Correct actions → checks pass")
    print("=" * 60)

    p2 = [
        ("LMS submit_assignment", p2_lms_submit_assignment),
        ("LMS drop_course", p2_lms_drop_course),
        ("LMS mark_all_announcements", p2_lms_mark_all_announcements),
        ("LMS complete_prereq_module", p2_lms_complete_prereq_module),
        ("LMS check_assignment_grade", p2_lms_check_assignment_grade),
        ("PP update_phone", p2_pp_update_phone),
        ("PP mark_all_read", p2_pp_mark_all_read),
        ("PP message_pcp", p2_pp_message_pcp),
        ("PP refill_prescription", p2_pp_refill_prescription),
        ("PP cancel_appointment", p2_pp_cancel_appointment),
    ]

    p2_pass = 0
    for name, fn in p2:
        try:
            score, checks = fn()
            failed = [c for c in checks if not c.get("passed")]
            if score >= 0.9 and not failed:
                print(f"  PASS  {name}  score={score:.2f}")
                p2_pass += 1
            else:
                print(f"  FAIL  {name}  score={score:.2f}")
                for c in failed[:3]:
                    print(f"        X {c.get('desc', '?')[:80]}")
        except Exception as e:
            print(f"  CRASH {name}  {e}")

    print(f"\nPhase 2: {p2_pass}/{len(p2)}")

    print(f"\n{'=' * 60}")
    print("PHASE 3: Wrong actions → penalties fire")
    print("=" * 60)

    p3 = [
        ("LMS no-action drop", p3_lms_no_action_drop),
        ("LMS no-action submit", p3_lms_no_action_submit),
        ("LMS submit decoy", p3_lms_submit_decoy),
        ("LMS collateral drop", p3_lms_collateral_drop),
        ("PP wrong field", p3_pp_wrong_field),
        ("PP no-action cancel", p3_pp_no_action_cancel),
        ("PP wrong rx refill", p3_pp_wrong_rx_refill),
    ]

    p3_pass = 0
    for name, fn in p3:
        try:
            score, ok, reason = fn()
            if ok:
                print(f"  PASS  {name}  score={score:.2f} ({reason})")
                p3_pass += 1
            else:
                print(f"  FAIL  {name}  score={score:.2f} ({reason})")
        except Exception as e:
            print(f"  CRASH {name}  {e}")

    print(f"\nPhase 3: {p3_pass}/{len(p3)}")
    total = p2_pass + p3_pass
    total_tests = len(p2) + len(p3)
    print(f"\nTOTAL: {total}/{total_tests}")
    if total < total_tests:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
