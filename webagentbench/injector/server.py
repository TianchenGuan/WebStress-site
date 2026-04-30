"""Server injection layer: feature flags applied to environment state.

Targets Planning, State Tracking, and Backtracking primitives.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any


def _rh_normalize_notification_type(raw_type: Any) -> str:
    if not raw_type:
        return "security_alert"
    notification_type = str(raw_type)
    if notification_type in {
        "order_fill",
        "price_alert",
        "dividend",
        "earnings",
        "transfer_complete",
        "security_alert",
        "recurring_investment",
        "tax_document",
        "margin_call",
        "corporate_action",
    }:
        return notification_type
    return {
        "account": "security_alert",
        "alert": "price_alert",
        "alerts": "price_alert",
        "market": "price_alert",
        "order": "order_fill",
        "orders": "order_fill",
        "price": "price_alert",
        "recurring": "recurring_investment",
        "system": "security_alert",
        "tax": "tax_document",
        "transfer": "transfer_complete",
        "watchlist": "price_alert",
        "dividend_notice": "dividend",
        "earnings_alert": "earnings",
        "margin": "margin_call",
        "corporate": "corporate_action",
    }.get(notification_type, "security_alert")


def _lms_latest_timestamp(state: Any) -> datetime:
    fallback = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    latest = fallback
    for course in getattr(state, "courses", []):
        for candidate in (
            getattr(course, "drop_deadline", None),
            getattr(course, "final_exam_date", None),
        ):
            if candidate and candidate > latest:
                latest = candidate
    for assignment in getattr(state, "assignments", []):
        for candidate in (getattr(assignment, "due_at", None), getattr(assignment, "submitted_at", None)):
            if candidate and candidate > latest:
                latest = candidate
    for post in getattr(state, "discussion_posts", []):
        candidate = getattr(post, "timestamp", None)
        if candidate and candidate > latest:
            latest = candidate
    for ann in getattr(state, "announcements", []):
        candidate = getattr(ann, "posted_at", None)
        if candidate and candidate > latest:
            latest = candidate
    for review in getattr(state, "peer_reviews", []):
        candidate = getattr(review, "due_at", None)
        if candidate and candidate > latest:
            latest = candidate
    for event in getattr(state, "calendar_events", []):
        candidate = getattr(event, "start_datetime", None)
        if candidate and candidate > latest:
            latest = candidate
    return latest


def apply_server_injection(state: Any, params: dict[str, Any]) -> None:
    """Mutate server state to create degraded conditions."""
    action = params.get("action", "")
    mutated = False

    if action == "scramble_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "emails"):
            for email in state.emails:
                if hasattr(email, "timestamp"):
                    offset = rng.randint(-86400 * 7, 86400 * 7)
                    email.timestamp += timedelta(seconds=offset)
                    mutated = True
        elif hasattr(state, "courses") and hasattr(state, "assignments"):
            for course in getattr(state, "courses", []):
                for field in ("drop_deadline", "final_exam_date"):
                    value = getattr(course, field, None)
                    if value is not None:
                        setattr(course, field, value + timedelta(seconds=rng.randint(-86400 * 3, 86400 * 3)))
                        mutated = True
            for assignment in getattr(state, "assignments", []):
                if getattr(assignment, "due_at", None) is not None:
                    assignment.due_at += timedelta(seconds=rng.randint(-86400 * 4, 86400 * 4))
                    mutated = True
                if getattr(assignment, "submitted_at", None) is not None:
                    assignment.submitted_at += timedelta(seconds=rng.randint(-3600 * 12, 3600 * 12))
                    mutated = True
            for discussion in getattr(state, "discussions", []):
                if getattr(discussion, "due_at", None) is not None:
                    discussion.due_at += timedelta(seconds=rng.randint(-86400 * 4, 86400 * 4))
                    mutated = True
            for post in getattr(state, "discussion_posts", []):
                if getattr(post, "timestamp", None) is not None:
                    post.timestamp += timedelta(seconds=rng.randint(-3600 * 18, 3600 * 18))
                    mutated = True
                if getattr(post, "updated_at", None) is not None:
                    post.updated_at += timedelta(seconds=rng.randint(-3600 * 18, 3600 * 18))
                    mutated = True
            for ann in getattr(state, "announcements", []):
                if getattr(ann, "posted_at", None) is not None:
                    ann.posted_at += timedelta(seconds=rng.randint(-86400 * 5, 86400 * 5))
                    mutated = True
            for review in getattr(state, "peer_reviews", []):
                if getattr(review, "due_at", None) is not None:
                    review.due_at += timedelta(seconds=rng.randint(-86400 * 3, 86400 * 3))
                    mutated = True
            for event in getattr(state, "calendar_events", []):
                if getattr(event, "start_datetime", None) is not None:
                    delta = timedelta(seconds=rng.randint(-86400 * 4, 86400 * 4))
                    event.start_datetime += delta
                    mutated = True
                    if getattr(event, "end_datetime", None) is not None:
                        event.end_datetime += delta
                        mutated = True

    elif action == "shuffle_contacts":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "contacts"):
            rng.shuffle(state.contacts)
            mutated = True

    elif action == "hide_prerequisite":
        label_name = params.get("label_name")
        if label_name and hasattr(state, "labels"):
            state.labels = [lab for lab in state.labels if lab.name != label_name]
            mutated = True

    elif action == "inject_distractor_emails":
        count = params.get("count", 5)
        subject_prefix = params.get("subject_prefix", "")
        if hasattr(state, "emails") and state.emails:
            _REALISTIC_EMAILS = [
                {
                    "subject": "Quick follow-up on our earlier discussion",
                    "body": "Hey, just wanted to circle back on what we talked about this morning. I think we're aligned on the timeline but I want to double-check the resource allocation before I update the tracker. Can you confirm whether the Q3 numbers are final?",
                },
                {
                    "subject": "Updated timeline for the deliverables",
                    "body": "Hi team,\n\nI've pushed the design review to Thursday based on the feedback from stakeholders. Engineering milestones stay the same. Please flag any conflicts by EOD tomorrow so we can adjust.",
                },
                {
                    "subject": "Notes from today's sync",
                    "body": "Sharing notes from the sync:\n\n1. Dashboard redesign approved — dev starts next sprint\n2. API migration blocked on the auth team's review\n3. Hiring update: two offers out, one accepted\n\nLet me know if I missed anything.",
                },
                {
                    "subject": "Revised figures — please review",
                    "body": "Attached the updated projections with the corrected assumptions. Main change: we moved the infrastructure costs from OpEx to CapEx per finance's guidance. Net impact is about $40K lower quarterly burn.",
                },
                {
                    "subject": "Re: Action items from the meeting",
                    "body": "Following up on the three open items:\n\n- Contract review: legal says they need until Friday\n- Vendor selection: narrowed to two finalists, scheduling demos\n- Budget reallocation: waiting on director approval\n\nI'll send another update once legal comes back.",
                },
                {
                    "subject": "One more thing on the project scope",
                    "body": "I realized we didn't address the internationalization requirement in today's planning. If we're targeting EU launch in Q2, we need to budget for translation and compliance review. Adding it to the backlog for now.",
                },
                {
                    "subject": "Sharing the latest draft for your feedback",
                    "body": "Here's the v3 draft incorporating the comments from last round. I restructured section 2 and added the competitive analysis appendix. Would appreciate your review by Wednesday so we can finalize before the board presentation.",
                },
                {
                    "subject": "Heads up on the schedule change",
                    "body": "The all-hands got moved from Tuesday 3pm to Wednesday 10am due to a conflict with the leadership offsite. Same agenda, same Zoom link. Calendar invites updated.",
                },
                {
                    "subject": "Checking in on the open items",
                    "body": "Haven't heard back on the two items from last week — the vendor NDA and the staging environment access request. Are these still blocked or did they get resolved? Happy to help push things along if needed.",
                },
                {
                    "subject": "Summary of decisions from this morning",
                    "body": "Quick recap of what we decided:\n\n- Go with Option B for the pricing model\n- Delay the beta launch by two weeks to fix the onboarding flow\n- Hire a contractor for the data migration piece\n\nI'll update the project plan and share it by EOD.",
                },
            ]
            _REALISTIC_NAMES = [
                ("Jordan Park", "jordan.park@thornton.com"),
                ("Morgan Liu", "morgan.liu@thornton.com"),
                ("Casey Rivera", "casey.rivera@thornton.com"),
                ("Taylor Brooks", "taylor.brooks@thornton.com"),
                ("Riley Santos", "riley.santos@thornton.com"),
                ("Quinn Patel", "quinn.patel@thornton.com"),
                ("Drew Nakamura", "drew.nakamura@thornton.com"),
                ("Jamie Okafor", "jamie.okafor@thornton.com"),
                ("Alex Drummond", "alex.drummond@thornton.com"),
                ("Avery Kim", "avery.kim@thornton.com"),
            ]
            rng = random.Random(params.get("seed", 42))
            template = state.emails[0]
            for i in range(count):
                distractor = template.model_copy(deep=True)
                distractor.id = f"email_{rng.randint(10000, 99999)}"
                distractor.thread_id = f"thread_{rng.randint(10000, 99999)}"
                entry = _REALISTIC_EMAILS[i % len(_REALISTIC_EMAILS)]
                distractor.subject = f"{subject_prefix}{entry['subject']}"
                name, addr = _REALISTIC_NAMES[i % len(_REALISTIC_NAMES)]
                distractor.from_name = name
                distractor.from_addr = addr
                distractor.body = entry["body"]
                distractor.is_read = rng.random() > 0.4  # 60% read, 40% unread
                offset = rng.randint(-3600 * 48, 3600 * 2)
                distractor.timestamp += timedelta(seconds=offset)
                state.emails.insert(rng.randint(0, len(state.emails)), distractor)
                mutated = True

    elif action == "corrupt_state":
        # Modify an email field to create inconsistency agent must detect
        email_id = params.get("email_id")
        field = params.get("field", "subject")
        new_value = params.get("value", "CORRUPTED")
        if email_id and hasattr(state, "emails"):
            for email in state.emails:
                if email.id == email_id:
                    setattr(email, field, new_value)
                    mutated = True
                    break

    # --- Robinhood server actions ---

    elif action == "scramble_order_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "orders"):
            for order in state.orders:
                if hasattr(order, "created_at") and order.created_at:
                    offset = rng.randint(-86400 * 3, 86400 * 3)
                    order.created_at += timedelta(seconds=offset)
                    mutated = True

    elif action == "scramble_notification_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "notifications"):
            for notif in state.notifications:
                if hasattr(notif, "timestamp") and notif.timestamp:
                    offset = rng.randint(-86400 * 5, 86400 * 5)
                    notif.timestamp += timedelta(seconds=offset)
                    mutated = True

    elif action == "shuffle_positions":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "positions"):
            rng.shuffle(state.positions)
            mutated = True

    elif action == "hide_watchlist":
        name = params.get("watchlist_name")
        if name and hasattr(state, "watchlists"):
            state.watchlists = [w for w in state.watchlists if w.name != name]
            mutated = True

    elif action in {"inject_notifications", "inject_distractor_notifications"}:
        if hasattr(state, "add_notification"):
            for spec in params.get("notifications", []) or []:
                state.add_notification(
                    type=spec.get("type", "deal_alert"),
                    title=spec.get("title", "Notification"),
                    message=spec.get("message", spec.get("body", "")),
                    related_id=spec.get("related_id"),
                )
                mutated = True
        elif hasattr(state, "notifications"):
            from webagentbench.backend.models.robinhood import Notification
            from webagentbench.backend.models.base import utc_now
            rng = random.Random(params.get("seed", 42))
            _NOTIF_TEMPLATES = [
                ("system", "Account Update", "Your account settings have been reviewed."),
                ("price_alert", "Price Movement", "A stock in your watchlist moved significantly."),
                ("order_fill", "Order Update", "An order status has changed. Check your orders."),
                ("dividend", "Dividend Notice", "A dividend payment is being processed."),
                ("transfer", "Transfer Update", "A transfer status has been updated."),
            ]
            custom_notifications = params.get("notifications") or []
            if not custom_notifications and params.get("messages"):
                custom_notifications = [
                    {"title": "Notification", "message": message}
                    for message in params.get("messages", [])
                ]
            if not custom_notifications:
                count = int(params.get("count", 5))
                custom_types = params.get("types") or []
                for i in range(count):
                    if custom_types:
                        ntype = custom_types[i % len(custom_types)]
                        title = f"{ntype.replace('_', ' ').title()} Update"
                        msg = f"A {ntype.replace('_', ' ')} notification requires review."
                    else:
                        ntype, title, msg = _NOTIF_TEMPLATES[i % len(_NOTIF_TEMPLATES)]
                    custom_notifications.append({"type": ntype, "title": title, "message": msg})
            for spec in custom_notifications:
                ntype = _rh_normalize_notification_type(spec.get("type", spec.get("category", "system")))
                title = spec.get("title", "Notification")
                msg = spec.get("message", spec.get("body", ""))
                state.notifications.append(Notification(
                    id=f"notif_noise_{rng.randint(10000, 99999)}",
                    type=ntype,
                    title=title,
                    message=msg,
                    timestamp=utc_now() - timedelta(hours=rng.randint(1, 72)),
                    is_read=spec.get("is_read", rng.random() > 0.5),
                ))
            mutated = True

    elif action in {"add_lms_correction_notice", "inject_lms_correction_notice"}:
        if hasattr(state, "courses") and hasattr(state, "announcements"):
            from webagentbench.backend.models.lms import Announcement, DiscussionPost
            rng = random.Random(params.get("seed", 42))

            def pick_course() -> Any:
                course_id = params.get("course_id")
                if course_id and hasattr(state, "get_course"):
                    course = state.get_course(course_id)
                    if course is not None:
                        return course
                course_code = params.get("course_code")
                if course_code and hasattr(state, "get_course_by_code"):
                    course = state.get_course_by_code(course_code)
                    if course is not None:
                        return course
                course_title = params.get("course_title")
                if course_title:
                    for course in state.courses:
                        if course.title == course_title:
                            return course
                return state.courses[0] if state.courses else None

            course = pick_course()
            if course is not None:
                notice_type = str(params.get("type", "announcement")).lower()
                created_at = params.get("posted_at")
                if not created_at:
                    created_at = _lms_latest_timestamp(state) + timedelta(minutes=int(params.get("minutes_offset", 20)))
                title = params.get("title", f"Correction: {getattr(course, 'course_code', course.title)}")
                body = params.get("body", "Correction: please use the latest course update.")

                if notice_type == "discussion_post" and hasattr(state, "discussions"):
                    discussion_id = params.get("discussion_id")
                    discussion = None
                    if discussion_id and hasattr(state, "get_discussion"):
                        discussion = state.get_discussion(discussion_id)
                    if discussion is None and params.get("discussion_title"):
                        discussion = next(
                            (d for d in state.discussions if d.title == params.get("discussion_title")),
                            None,
                        )
                    if discussion is not None:
                        post_id = f"post_noise_{rng.randint(10000, 99999)}"
                        state.discussion_posts.append(DiscussionPost(
                            id=post_id,
                            discussion_id=discussion.id,
                            author_id=params.get("author_id", getattr(course, "instructor_id", state.student.id)),
                            author_name=params.get("author_name", getattr(course, "instructor_name", "Instructor")),
                            body=body,
                            timestamp=created_at,
                            is_anonymous=bool(params.get("is_anonymous", False)),
                        ))
                        mutated = True
                else:
                    ann_id = params.get("id", f"ann_noise_{rng.randint(10000, 99999)}")
                    state.announcements.append(Announcement(
                        id=ann_id,
                        course_id=course.id,
                        title=title,
                        body=body,
                        posted_at=created_at,
                        is_read=bool(params.get("is_read", False)),
                        priority=params.get("priority", "normal"),
                    ))
                    mutated = True

    if mutated and hasattr(state, "touch"):
        state.touch()
