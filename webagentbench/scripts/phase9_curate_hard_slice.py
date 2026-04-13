#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"
VARIANTS_DIR = ROOT / "injector" / "variants"

ACTIVE_ENVS = ("amazon", "booking", "gmail", "reddit", "robinhood")
VARIANT_ENVS = {"amazon", "booking", "reddit"}
TARGET_DIFFICULTIES = {"hard", "expert", "frontier"}

MANAGED_V2_SUFFIXES = {
    "address_shadow_v2",
    "order_shadow_v2",
    "cart_shadow_v2",
    "product_shadow_v2",
    "return_retry_v2",
    "review_retry_v2",
    "wishlist_retry_v2",
    "cart_retry_v2",
    "address_retry_v2",
    "order_cancel_retry_v2",
    "checkout_retry_v2",
    "saved_list_shadow_v2",
    "message_shadow_v2",
    "review_shadow_v2",
    "payment_shadow_v2",
    "property_shadow_v2",
    "saved_list_retry_v2",
    "message_retry_v2",
    "payment_retry_v2",
    "preferences_retry_v2",
    "settings_retry_v2",
    "account_retry_v2",
    "reservation_retry_v2",
    "subreddit_shadow_v2",
    "user_shadow_v2",
    "notification_shadow_v2",
    "block_retry_v2",
    "notification_retry_v2",
    "comment_retry_v2",
    "subscription_retry_v2",
    "engagement_retry_v2",
}


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def task_blob(task: dict[str, Any]) -> str:
    chunks = [
        task.get("task_id", ""),
        task.get("title", ""),
        task.get("instruction_template", "") or task.get("instruction", "") or "",
    ]
    return " ".join(str(chunk) for chunk in chunks).lower()


def contains_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def target_ref(task: dict[str, Any], *keys: str, fallback: str = "") -> str:
    targets = (task.get("seed") or {}).get("targets") or task.get("targets") or {}
    for key in keys:
        if key in targets:
            return f"{{target.{key}}}"
    return fallback


def first_target_ref_containing(task: dict[str, Any], needle: str) -> str:
    targets = (task.get("seed") or {}).get("targets") or task.get("targets") or {}
    for key in targets:
        if needle in key:
            return f"{{target.{key}}}"
    return ""


def clean_float(value: float) -> float:
    return round(float(value), 2)


def first_step_param(
    task: dict[str, Any],
    key: str,
    *,
    uses: set[str] | None = None,
    default: Any = None,
) -> Any:
    for step in (task.get("seed") or {}).get("steps", []):
        if uses is not None and step.get("use") not in uses:
            continue
        params = step.get("params") or {}
        if key in params:
            return params[key]
    return default


def load_tasks() -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for env in ACTIVE_ENVS:
        for path in sorted((TASKS_DIR / env).glob("*.yaml")):
            raw = yaml.safe_load(path.read_text()) or {}
            if raw.get("difficulty") not in TARGET_DIFFICULTIES:
                continue
            raw["_path"] = path
            tasks[raw["task_id"]] = raw
    return tasks


def load_variants() -> defaultdict[str, list[str]]:
    by_base: defaultdict[str, list[str]] = defaultdict(list)
    for path in sorted(VARIANTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        base = raw.get("base_task_id") or path.stem.split("__", 1)[0]
        by_base[base].append(path.name)
    return by_base


def normalize_primitives(task: dict[str, Any]) -> bool:
    ordered = unique(list(task.get("primary_primitives") or []) + list(task.get("secondary_primitives") or []))
    if not ordered:
        return False
    primary = [ordered[0]]
    secondary = [ordered[1]] if len(ordered) > 1 else []
    changed = task.get("primary_primitives") != primary or (task.get("secondary_primitives") or []) != secondary
    task["primary_primitives"] = primary
    if secondary:
        task["secondary_primitives"] = secondary
    else:
        task.pop("secondary_primitives", None)
    return changed


def add_negative_check(
    task: dict[str, Any],
    *,
    expr: str,
    desc: str,
    penalty: float = 0.1,
) -> bool:
    ev = task.setdefault("eval", {})
    negs = ev.setdefault("negative_checks", [])
    for item in negs:
        if not isinstance(item, dict):
            continue
        if item.get("expr") == expr or item.get("desc") == desc:
            return False
    negs.append({"expr": expr, "desc": desc, "penalty": penalty})
    return True


def amazon_negative_candidates(task: dict[str, Any]) -> list[dict[str, Any]]:
    text = task_blob(task)
    allow = {
        "return": contains_any(text, "return", "refund", "replace"),
        "review": contains_any(text, "review", "rating"),
        "wishlist": contains_any(text, "wishlist"),
        "cart": contains_any(text, "cart"),
        "address": contains_any(text, "address", "shipping", "destination"),
        "payment": contains_any(text, "payment", "visa", "mastercard", "card"),
        "cancel": contains_any(text, "cancel"),
        "settings": contains_any(text, "setting", "account", "password", "profile"),
    }
    candidates: list[dict[str, Any]] = []
    if not allow["return"]:
        candidates.append({
            "expr": "not any(e.action.startswith('amazon.return.') for e in state.audit_log)",
            "desc": "No off-task returns were opened or updated",
            "penalty": 0.1,
        })
    if not allow["review"]:
        candidates.append({
            "expr": "not any(e.action == 'amazon.review.add' for e in state.audit_log)",
            "desc": "No off-task reviews were submitted",
            "penalty": 0.1,
        })
    if not allow["wishlist"]:
        candidates.append({
            "expr": "not any(e.action.startswith('amazon.wishlist.') for e in state.audit_log)",
            "desc": "No off-task wishlist mutations were made",
            "penalty": 0.1,
        })
    if not allow["address"]:
        candidates.append({
            "expr": "not any(e.action.startswith('amazon.address.') for e in state.audit_log)",
            "desc": "No off-task address changes were made",
            "penalty": 0.1,
        })
    if not allow["payment"]:
        candidates.append({
            "expr": "not any(e.action.startswith('amazon.payment.') for e in state.audit_log)",
            "desc": "No off-task payment-method changes were made",
            "penalty": 0.1,
        })
    if not allow["cancel"]:
        candidates.append({
            "expr": "not any(e.action == 'amazon.order.cancel' for e in state.audit_log)",
            "desc": "No off-task order cancellations were made",
            "penalty": 0.1,
        })
    if not allow["settings"]:
        candidates.append({
            "expr": "not any(e.action == 'amazon.settings.update' for e in state.audit_log)",
            "desc": "No off-task account settings were changed",
            "penalty": 0.1,
        })
    return candidates


def booking_negative_candidates(task: dict[str, Any]) -> list[dict[str, Any]]:
    text = task_blob(task)
    allow = {
        "reservation": contains_any(text, "book", "booking", "reservation", "rebook", "trip", "hotel", "stay"),
        "cancel": contains_any(text, "cancel"),
        "modify": contains_any(text, "modify", "change", "wrong date", "dates"),
        "message": contains_any(text, "message", "concierge", "reply"),
        "review": contains_any(text, "review"),
        "saved_list": contains_any(text, "saved list", "saved-list", "favorites", "list"),
        "payment": contains_any(text, "payment", "visa", "mastercard", "wallet", "card"),
        "account": contains_any(text, "account", "profile", "phone", "email"),
        "settings": contains_any(text, "setting", "security", "language", "2fa", "dark mode"),
        "preferences": contains_any(text, "preference", "bed type", "dietary", "room type"),
        "notifications": contains_any(text, "notification"),
    }
    candidates: list[dict[str, Any]] = []
    if not allow["message"]:
        candidates.append({
            "expr": "not any(e.action == 'message.send' for e in state.audit_log)",
            "desc": "No off-task hotel messages were sent",
            "penalty": 0.1,
        })
    if not allow["review"]:
        candidates.append({
            "expr": "not any(e.action == 'review.add' for e in state.audit_log)",
            "desc": "No off-task reviews were submitted",
            "penalty": 0.1,
        })
    if not allow["saved_list"]:
        candidates.append({
            "expr": "not any(e.action.startswith('saved_list.') for e in state.audit_log)",
            "desc": "No off-task saved-list mutations were made",
            "penalty": 0.1,
        })
    if not allow["payment"]:
        candidates.append({
            "expr": "not any(e.action.startswith('payment.') for e in state.audit_log)",
            "desc": "No off-task payment-method changes were made",
            "penalty": 0.1,
        })
    if not allow["account"]:
        candidates.append({
            "expr": "not any(e.action.startswith('account.') for e in state.audit_log)",
            "desc": "No off-task account changes were made",
            "penalty": 0.1,
        })
    if not allow["settings"]:
        candidates.append({
            "expr": "not any(e.action == 'settings.update' for e in state.audit_log)",
            "desc": "No off-task settings changes were made",
            "penalty": 0.1,
        })
    if not allow["preferences"]:
        candidates.append({
            "expr": "not any(e.action == 'preferences.update' for e in state.audit_log)",
            "desc": "No off-task travel preference changes were made",
            "penalty": 0.1,
        })
    if not allow["cancel"]:
        candidates.append({
            "expr": "not any(e.action == 'reservation.cancel' for e in state.audit_log)",
            "desc": "No off-task reservations were cancelled",
            "penalty": 0.1,
        })
    if not allow["modify"]:
        candidates.append({
            "expr": "not any(e.action == 'reservation.modify' for e in state.audit_log)",
            "desc": "No off-task reservations were modified",
            "penalty": 0.1,
        })
    if not allow["notifications"]:
        candidates.append({
            "expr": "not any(e.action.startswith('notification.') or e.action == 'notifications.read_all' for e in state.audit_log)",
            "desc": "No off-task notification handling was done",
            "penalty": 0.1,
        })
    if not allow["reservation"]:
        candidates.append({
            "expr": "not any(e.action == 'reservation.create' for e in state.audit_log)",
            "desc": "No off-task reservations were created",
            "penalty": 0.1,
        })
    return candidates


def gmail_negative_candidates(task: dict[str, Any]) -> list[dict[str, Any]]:
    if task["task_id"] == "gmail_quarterly_closeout":
        return [
            {
                "expr": "all(e.id == '{target.spam_id}' for e in state.deleted)",
                "desc": "Only the spam email was moved to trash",
                "penalty": 0.1,
            },
            {
                "expr": "all(m.forwarded_from_id in {target.update_ids} and m.to == ['{target.team_digest_email}'] and len(m.cc) == 0 and len(m.bcc) == 0 for m in state.sent)",
                "desc": "Only the two update forwards went to the digest inbox",
                "penalty": 0.15,
            },
            {
                "expr": "not any(e.action == 'gmail.contact.delete' and e.payload.get('contact_id') not in ['{target.stale_a_id}', '{target.stale_b_id}'] for e in state.audit_log)",
                "desc": "No non-stale contacts were deleted",
                "penalty": 0.1,
            },
            {
                "expr": "sum(1 for e in state.audit_log if e.action == 'gmail.label.create') == 2 and not any(e.action in {'gmail.label.update', 'gmail.label.delete'} for e in state.audit_log)",
                "desc": "Only the two requested labels were created",
                "penalty": 0.1,
            },
            {
                "expr": "sum(1 for e in state.audit_log if e.action == 'gmail.filter.create') == 1 and not any(e.action == 'gmail.filter.delete' for e in state.audit_log)",
                "desc": "Only the vendor filter was added",
                "penalty": 0.1,
            },
        ]

    text = task_blob(task)
    eval_blob = yaml.safe_dump(task.get("eval") or {}, sort_keys=False).lower()
    combined = f"{text}\n{eval_blob}"
    allow = {
        "send": contains_any(combined, "state.sent", "gmail.send", "reply", "compose", "send", "email sent"),
        "forward": contains_any(combined, "forward", "forwarded_from"),
        "delete": contains_any(combined, "delete", "trash", "spam"),
        "archive": contains_any(combined, "archive"),
        "label": contains_any(combined, "label"),
        "filter": contains_any(combined, "filter"),
        "contact": contains_any(combined, "contact"),
        "settings": contains_any(combined, "settings.update", "setting", "theme", "signature", "vacation responder"),
        "star": contains_any(combined, "star", "is_starred"),
    }
    candidates: list[dict[str, Any]] = []
    if not allow["filter"]:
        candidates.append({
            "expr": "not any(e.action.startswith('gmail.filter.') for e in state.audit_log)",
            "desc": "No off-task Gmail filters were changed",
            "penalty": 0.1,
        })
    if not allow["label"]:
        candidates.append({
            "expr": "not any(e.action.startswith('gmail.label.') for e in state.audit_log)",
            "desc": "No off-task labels were created or edited",
            "penalty": 0.1,
        })
    if not allow["contact"]:
        candidates.append({
            "expr": "not any(e.action.startswith('gmail.contact.') for e in state.audit_log)",
            "desc": "No off-task contact edits were made",
            "penalty": 0.1,
        })
    if not allow["settings"]:
        candidates.append({
            "expr": "not any(e.action == 'gmail.settings.update' for e in state.audit_log)",
            "desc": "No off-task mailbox settings were changed",
            "penalty": 0.1,
        })
    if not allow["delete"]:
        candidates.append({
            "expr": "not any(e.action == 'gmail.email.delete' for e in state.audit_log)",
            "desc": "No off-task emails were deleted",
            "penalty": 0.1,
        })
    if not allow["archive"]:
        candidates.append({
            "expr": "not any(e.action == 'gmail.email.archive' for e in state.audit_log)",
            "desc": "No off-task emails were archived",
            "penalty": 0.1,
        })
    if not allow["forward"]:
        candidates.append({
            "expr": "not any(e.action == 'gmail.email.forward' for e in state.audit_log)",
            "desc": "No off-task forwards were sent",
            "penalty": 0.1,
        })
    if not allow["star"]:
        candidates.append({
            "expr": "not any(e.action == 'gmail.email.star' for e in state.audit_log)",
            "desc": "No off-task stars were toggled",
            "penalty": 0.1,
        })
    if not allow["send"]:
        candidates.append({
            "expr": "not any(e.action == 'gmail.send' for e in state.audit_log)",
            "desc": "No off-task outbound emails were sent",
            "penalty": 0.1,
        })
    return candidates


def reddit_negative_candidates(task: dict[str, Any]) -> list[dict[str, Any]]:
    text = task_blob(task)
    allow = {
        "post": contains_any(text, "create post", "post in r/", "post ", "content", "resubmit"),
        "comment": contains_any(text, "comment", "reply ", "thread"),
        "message": contains_any(text, "message", "dm", "inbox"),
        "notification": contains_any(text, "notification"),
        "settings": contains_any(text, "settings", "theme", "email", "compact", "sort", "privacy"),
        "block": contains_any(text, "block"),
        "hide": contains_any(text, "hide"),
    }
    candidates: list[dict[str, Any]] = []
    if not allow["post"]:
        candidates.append({
            "expr": "not any(e.action.startswith('reddit.post.') and e.action != 'reddit.post.vote' and e.action != 'reddit.post.save' and e.action != 'reddit.post.unsave' and e.action != 'reddit.post.hide' and e.action != 'reddit.post.unhide' for e in state.audit_log)",
            "desc": "No off-task posts were created, edited, or deleted",
            "penalty": 0.1,
        })
    if not allow["comment"]:
        candidates.append({
            "expr": "not any(e.action.startswith('reddit.comment.') and e.action != 'reddit.comment.vote' and e.action != 'reddit.comment.save' and e.action != 'reddit.comment.unsave' for e in state.audit_log)",
            "desc": "No off-task comments were created, edited, or deleted",
            "penalty": 0.1,
        })
    if not allow["message"]:
        candidates.append({
            "expr": "not any(e.action.startswith('reddit.message.') for e in state.audit_log)",
            "desc": "No off-task direct-message actions were taken",
            "penalty": 0.1,
        })
    if not allow["notification"]:
        candidates.append({
            "expr": "not any(e.action.startswith('reddit.notification.') for e in state.audit_log)",
            "desc": "No off-task notification actions were taken",
            "penalty": 0.1,
        })
    if not allow["settings"]:
        candidates.append({
            "expr": "not any(e.action == 'reddit.settings.update' for e in state.audit_log)",
            "desc": "No off-task Reddit settings were changed",
            "penalty": 0.1,
        })
    if not allow["block"]:
        candidates.append({
            "expr": "not any(e.action.startswith('reddit.user.block') or e.action.startswith('reddit.user.unblock') for e in state.audit_log)",
            "desc": "No off-task user blocks were changed",
            "penalty": 0.1,
        })
    if not allow["hide"]:
        candidates.append({
            "expr": "not any(e.action in {'reddit.post.hide', 'reddit.post.unhide'} for e in state.audit_log)",
            "desc": "No off-task posts were hidden or unhidden",
            "penalty": 0.1,
        })
    return candidates


def robinhood_negative_candidates(task: dict[str, Any]) -> list[dict[str, Any]]:
    text = task_blob(task)
    allow = {
        "order": contains_any(text, "buy", "sell", "rebalance", "trade", "order"),
        "cancel": contains_any(text, "cancel"),
        "options": contains_any(text, "option", "covered call", "call", "put", "spread"),
        "watchlist": contains_any(text, "watchlist"),
        "transfer": contains_any(text, "transfer", "deposit", "withdraw", "bank"),
        "recurring": contains_any(text, "recurring"),
        "alert": contains_any(text, "alert"),
        "settings": contains_any(text, "setting", "2fa", "security"),
        "bank": contains_any(text, "bank", "link"),
    }
    candidates: list[dict[str, Any]] = []
    if not allow["watchlist"]:
        candidates.append({
            "expr": "not any(e.action.startswith('robinhood.watchlist.') for e in state.audit_log)",
            "desc": "No off-task watchlist changes were made",
            "penalty": 0.1,
        })
    if not allow["transfer"]:
        candidates.append({
            "expr": "not any(e.action.startswith('robinhood.transfer.') for e in state.audit_log)",
            "desc": "No off-task transfers were initiated",
            "penalty": 0.1,
        })
    if not allow["recurring"]:
        candidates.append({
            "expr": "not any(e.action.startswith('robinhood.recurring.') for e in state.audit_log)",
            "desc": "No off-task recurring-investment changes were made",
            "penalty": 0.1,
        })
    if not allow["alert"]:
        candidates.append({
            "expr": "not any(e.action.startswith('robinhood.alert.') for e in state.audit_log)",
            "desc": "No off-task price alerts were created or deleted",
            "penalty": 0.1,
        })
    if not allow["options"]:
        candidates.append({
            "expr": "not any(e.action.startswith('robinhood.options.order.') for e in state.audit_log)",
            "desc": "No off-task options trades were placed",
            "penalty": 0.1,
        })
    if not allow["cancel"]:
        candidates.append({
            "expr": "not any(e.action == 'robinhood.order.cancel' for e in state.audit_log)",
            "desc": "No off-task equity orders were cancelled",
            "penalty": 0.1,
        })
    if not allow["settings"]:
        candidates.append({
            "expr": "not any(e.action in {'robinhood.settings.update', 'robinhood.security.2fa'} for e in state.audit_log)",
            "desc": "No off-task account settings were changed",
            "penalty": 0.1,
        })
    if not allow["bank"]:
        candidates.append({
            "expr": "not any(e.action.startswith('robinhood.bank.') for e in state.audit_log)",
            "desc": "No off-task bank-link changes were made",
            "penalty": 0.1,
        })
    return candidates


def strengthen_negative_checks(task: dict[str, Any]) -> bool:
    negs = ((task.get("eval") or {}).get("negative_checks") or [])
    if len(negs) != 3:
        return False
    env = task["env_id"]
    if env == "amazon":
        candidates = amazon_negative_candidates(task)
    elif env == "booking":
        candidates = booking_negative_candidates(task)
    elif env == "gmail":
        candidates = gmail_negative_candidates(task)
    elif env == "reddit":
        candidates = reddit_negative_candidates(task)
    elif env == "robinhood":
        candidates = robinhood_negative_candidates(task)
    else:
        return False

    changed = False
    for candidate in candidates:
        changed |= add_negative_check(task, **candidate)
        if len((task.get("eval") or {}).get("negative_checks") or []) >= 5:
            break
    return changed


def seed_injection(action: str, **params: Any) -> dict[str, Any]:
    return {"layer": "seed", "params": {"action": action, **params}}


def network_error(
    url_pattern: str,
    *,
    methods: list[str],
    error_count: int = 1,
    error_status: int = 503,
    error_message: str = "Temporary failure. Retry the request.",
) -> dict[str, Any]:
    return {
        "layer": "network",
        "params": {
            "action": "error_then_success",
            "url_pattern": url_pattern,
            "methods": methods,
            "error_count": error_count,
            "error_status": error_status,
            "error_message": error_message,
            "behavior": {"mode": "once"},
        },
    }


def variant(
    task_id: str,
    suffix: str,
    primitive: str,
    description: str,
    injections: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "variant_id": f"{task_id}__{suffix}",
        "base_task_id": task_id,
        "target_primitive": primitive,
        "description": description,
        "injections": injections,
    }


def amazon_product_info(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": target_ref(
            task,
            "replace_name",
            "product_1",
            "product_2",
            "gift_product",
            "product_name",
            "best_value_name",
            fallback=str(first_step_param(task, "name", uses={"featured_product"}, default="Target Product")),
        ),
        "brand": str(first_step_param(task, "brand", uses={"featured_product"}, default="Brand")),
        "category": str(
            first_step_param(
                task,
                "category",
                uses={"featured_product", "product_catalog"},
                default="Electronics",
            )
        ),
        "price": float(first_step_param(task, "price", uses={"featured_product"}, default=49.99)),
        "rating": float(first_step_param(task, "rating", uses={"featured_product"}, default=4.7)),
    }


def booking_property_info(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": target_ref(
            task,
            "target_prop_name",
            "hotel_name",
            "property_name",
            "winner_name",
            "bcn_winner_name",
            "rome_winner_name",
            fallback=str(first_step_param(task, "name", uses={"featured_property", "compare_properties"}, default="Target Property")),
        ),
        "city": target_ref(
            task,
            "city",
            fallback=str(first_step_param(task, "city", uses={"featured_property", "compare_properties"}, default="Rome")),
        ),
        "country": str(first_step_param(task, "country", uses={"featured_property", "compare_properties"}, default="Italy")),
        "price": float(first_step_param(task, "price", uses={"featured_property", "compare_properties"}, default=240.0)),
        "review_score": float(first_step_param(task, "review_score", uses={"featured_property", "compare_properties"}, default=8.8)),
    }


def reddit_primary_subreddit(task: dict[str, Any]) -> str:
    return target_ref(
        task,
        "join",
        "join1",
        "join2",
        "subreddit_name",
        "user_sub",
        "comment_sub",
        "save_sub",
        "save_subreddit",
        "hide_sub",
        "sub1",
        "leave_sub",
        fallback=str(first_step_param(task, "subreddit", default="MachineLearning")),
    )


def reddit_primary_title(task: dict[str, Any]) -> str:
    explicit = target_ref(
        task,
        "post_title",
        "target_post_title",
        "post1_title",
        "post2_title",
        "user_post",
        "user_post_title",
        "save_title",
        "save2_title",
        "ask_title",
        "wn_title",
        "prog_title",
        "py_title",
        "ml_title",
        "comment_post_title",
        "comment_target_title",
        "hide_title",
        "create_title",
        "new_post_title",
        "new_title",
        "vote_title",
        "upvote_title",
        "downvote_title",
        "comment_title",
        "edit_title",
        "edit_post_title",
        "message_post_title",
        "msg_post_title",
        "search_title",
        "p1_title",
        "pf_title",
        "gm_title",
        "movie_title",
        "til_title",
        "tech_title",
        "pt",
        fallback="",
    )
    return explicit or first_target_ref_containing(task, "title") or "Interesting discussion thread"


def reddit_primary_user(task: dict[str, Any]) -> str:
    return target_ref(
        task,
        "from_user",
        "reply1_from",
        "reply2_from",
        "block_user",
        "user",
        "msg_to",
        "new_to",
        "reply_author",
        "mt",
        fallback="NeuralNexus",
    )


def reddit_primary_subject(task: dict[str, Any]) -> str:
    return target_ref(
        task,
        "message_subject",
        "reply1_sub",
        "reply2_sub",
        "delete_subject",
        "delete_sub",
        "msg_sub",
        "new_subject",
        "ms",
        fallback="Community message",
    )


def current_variant_families(existing: list[str]) -> set[str]:
    out: set[str] = set()
    for name in existing:
        stem = Path(name).stem
        if "__" not in stem:
            continue
        out.add(stem.split("__", 1)[1])
    return out


def remove_existing_managed_v2_variants() -> None:
    for path in sorted(VARIANTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        base = raw.get("base_task_id") or path.stem.split("__", 1)[0]
        env = str(base).split("_", 1)[0]
        if env not in VARIANT_ENVS:
            continue
        suffix = path.stem.split("__", 1)[1] if "__" in path.stem else ""
        if suffix in MANAGED_V2_SUFFIXES:
            path.unlink()


def amazon_decoy_variant(task: dict[str, Any], existing: list[str]) -> dict[str, Any]:
    del existing
    tid = task["task_id"]
    text = task_blob(task)
    info = amazon_product_info(task)
    if contains_any(tid, "account", "address", "shipping", "destination", "gift_setup", "gift_orders"):
        recipient = target_ref(task, "new_name", "recipient_name", fallback="Sam Rivera")
        street = target_ref(task, "new_street", "street", fallback="742 Maple Avenue")
        city = target_ref(task, "new_city", "city", fallback="Portland")
        state_code = target_ref(task, "new_state", "state_code", fallback="OR")
        zip_code = target_ref(task, "new_zip", "zip", fallback="97201")
        return variant(
            tid,
            "address_shadow_v2",
            "grounding",
            "Addresses and cards include near-matches for the requested destination. The agent must still ship to the exact target address while avoiding the stale twin records.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "address",
                            "full_name": recipient,
                            "street_address": f"{street} Apt 2",
                            "city": city,
                            "state": state_code,
                            "zip_code": zip_code,
                        },
                        {
                            "type": "address",
                            "full_name": recipient,
                            "street_address": f"{street} Suite B",
                            "city": city,
                            "state": state_code,
                            "zip_code": zip_code,
                        },
                        {
                            "type": "payment_method",
                            "card_type": "Visa",
                            "last_four": "4243",
                            "expiry": "11/29",
                            "holder_name": recipient,
                        },
                    ],
                )
            ],
        )
    if contains_any(tid, "return", "reorder", "order", "cancel"):
        shadow_name = f"{info['name']} Travel Edition"
        return variant(
            tid,
            "order_shadow_v2",
            "state_tracking",
            "Order history contains a near-identical sibling product with a similar fulfillment state. The agent must act on the exact target order or replacement item, not the shadow order.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "product",
                            "name": shadow_name,
                            "brand": info["brand"],
                            "category": info["category"],
                            "price": clean_float(info["price"] * 0.93),
                            "rating": clean_float(max(info["rating"] - 0.2, 4.0)),
                            "description": "Similar model in a different form factor that should not be returned, reordered, or purchased here.",
                        },
                        {
                            "type": "order",
                            "product_name": shadow_name,
                            "quantity": 1,
                            "unit_price": clean_float(info["price"] * 0.93),
                            "status": "delivered",
                            "placed_hours_ago": 72,
                        },
                    ],
                )
            ],
        )
    if contains_any(tid, "wishlist", "cart"):
        return variant(
            tid,
            "cart_shadow_v2",
            "state_tracking",
            "The cart and wishlist include near-identical sibling items. The agent must move, remove, and purchase the exact target products instead of the shadow items.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "product",
                            "name": f"{info['name']} Plus",
                            "brand": info["brand"],
                            "category": info["category"],
                            "price": clean_float(info["price"] * 1.07),
                            "rating": clean_float(max(info["rating"] - 0.1, 4.1)),
                            "description": "A closely named upsell variant that should stay out of the final cart.",
                        },
                        {
                            "type": "cart_item",
                            "product_name": f"{info['name']} Plus",
                            "quantity": 1,
                            "unit_price": clean_float(info["price"] * 1.07),
                        },
                    ],
                )
            ],
        )
    return variant(
        tid,
        "product_shadow_v2",
        "grounding",
        "Search and comparison views include a near-identical sibling product with a slightly different price-rating tradeoff. The agent must still pick the exact task target.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "product",
                        "name": f"{info['name']} Max",
                        "brand": info["brand"],
                        "category": info["category"],
                        "price": clean_float(info["price"] * 1.09),
                        "rating": clean_float(max(info["rating"] - 0.1, 4.1)),
                        "description": "Lookalike product whose tradeoffs should not override the exact benchmark instruction.",
                    }
                ],
            )
        ],
    )


def amazon_retry_variant(task: dict[str, Any], existing: list[str]) -> dict[str, Any]:
    del existing
    tid = task["task_id"]
    text = task_blob(task)
    if contains_any(tid, "return", "replace"):
        return variant(
            tid,
            "return_retry_v2",
            "backtracking",
            "The first return submission fails transiently. The agent must verify the return exists and retry instead of assuming success.",
            [network_error("**/api/env/amazon/returns**", methods=["POST", "PUT"])],
        )
    if contains_any(tid, "review"):
        return variant(
            tid,
            "review_retry_v2",
            "verification",
            "The first review submission fails transiently. The agent must verify the review actually landed and retry if needed.",
            [network_error("**/api/env/amazon/products/*/reviews", methods=["POST"])],
        )
    if contains_any(tid, "wishlist"):
        return variant(
            tid,
            "wishlist_retry_v2",
            "backtracking",
            "The first wishlist mutation fails transiently. The agent must verify the wishlist state and retry instead of moving on.",
            [network_error("**/api/env/amazon/wishlist/**", methods=["POST"])],
        )
    if contains_any(tid, "cart") and not contains_any(tid, "checkout", "purchase", "buy", "order"):
        return variant(
            tid,
            "cart_retry_v2",
            "backtracking",
            "The first cart mutation fails transiently. The agent must confirm the cart changed and retry the add/update/remove action if it did not.",
            [network_error("**/api/env/amazon/cart**", methods=["POST", "PUT", "DELETE"])],
        )
    if contains_any(tid, "address", "shipping", "destination", "account"):
        return variant(
            tid,
            "address_retry_v2",
            "backtracking",
            "The first address write fails transiently. The agent must verify the exact address exists before trusting the write.",
            [network_error("**/api/env/amazon/addresses**", methods=["POST", "PUT", "DELETE"])],
        )
    if contains_any(tid, "cancel"):
        return variant(
            tid,
            "order_cancel_retry_v2",
            "backtracking",
            "The first cancel request fails transiently. The agent must verify the order status actually changed and retry if it did not.",
            [network_error("**/api/env/amazon/orders/*/cancel", methods=["POST"])],
        )
    return variant(
        tid,
        "checkout_retry_v2",
        "backtracking",
        "The first checkout attempt fails transiently. The agent must confirm the order was created and retry if not.",
        [network_error("**/api/env/amazon/checkout", methods=["POST"])],
    )


def booking_decoy_variant(task: dict[str, Any], existing: list[str]) -> dict[str, Any]:
    del existing
    tid = task["task_id"]
    info = booking_property_info(task)
    if contains_any(tid, "saved_list", "save_and_organize", "save_property", "favorites"):
        list_name = target_ref(task, "list_name", fallback="Family Favorites")
        return variant(
            tid,
            "saved_list_shadow_v2",
            "state_tracking",
            "Saved lists already contain a near-match list name and a sibling property in the same city. The agent must curate the exact intended list and properties.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {"type": "saved_list", "name": f"{list_name} Archive", "property_ids": []},
                        {
                            "type": "property",
                            "name": f"{info['name']} Suites",
                            "city": info["city"],
                            "country": info["country"],
                            "price": clean_float(info["price"] * 1.05),
                            "review_score": clean_float(max(info["review_score"] - 0.2, 7.8)),
                            "amenities": ["Free WiFi", "Restaurant"],
                        },
                    ],
                )
            ],
        )
    if contains_any(tid, "message", "concierge", "reply"):
        return variant(
            tid,
            "message_shadow_v2",
            "grounding",
            "Inbox threads include a stale same-property message that looks almost identical to the active request. The agent must answer or follow up on the exact hotel thread.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "message",
                            "property_name": info["name"],
                            "subject": "Follow-up on your stay details",
                            "body": "This is an old thread about a previous stay. It is not the active hotel message referenced in the task.",
                            "sender": "property",
                            "read": False,
                        }
                    ],
                )
            ],
        )
    if contains_any(tid, "review"):
        return variant(
            tid,
            "review_shadow_v2",
            "state_tracking",
            "Completed stays include a sibling property with a very similar name and score. The agent must review the exact completed stay named in the task, not the shadow stay.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "reservation",
                            "property_name": f"{info['name']} Annex",
                            "check_in": "2025-11-12",
                            "check_out": "2025-11-15",
                            "status": "completed",
                            "guests": 2,
                            "booked_days_ago": 120,
                        }
                    ],
                )
            ],
        )
    if contains_any(
        tid,
        "payment",
        "account",
        "profile",
        "settings",
        "security",
        "preference",
        "language",
        "2fa",
    ):
        return variant(
            tid,
            "payment_shadow_v2",
            "grounding",
            "Account surfaces include a near-match card and a same-city property decoy. The agent must update or use the exact requested account configuration rather than the shadow record.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "payment_method",
                            "card_type": "Visa",
                            "last_four": "4243",
                            "expiry": "11/29",
                            "holder_name": "Jordan Parker",
                        },
                        {
                            "type": "property",
                            "name": f"{info['name']} Residences",
                            "city": info["city"],
                            "country": info["country"],
                            "price": clean_float(info["price"] * 1.03),
                            "review_score": clean_float(max(info["review_score"] - 0.3, 7.7)),
                            "amenities": ["Free WiFi", "Restaurant"],
                        },
                    ],
                )
            ],
        )
    return variant(
        tid,
        "property_shadow_v2",
        "grounding",
        "Search results include a same-city sibling property with a nearly identical name and overlapping amenities. The agent must still book or compare the exact target hotel.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "property",
                        "name": f"{info['name']} Suites",
                        "city": info["city"],
                        "country": info["country"],
                        "price": clean_float(info["price"] * 1.04),
                        "review_score": clean_float(max(info["review_score"] - 0.2, 7.8)),
                        "amenities": ["Free WiFi", "Restaurant", "Air conditioning"],
                    }
                ],
            )
        ],
    )


def booking_retry_variant(task: dict[str, Any], existing: list[str]) -> dict[str, Any]:
    del existing
    tid = task["task_id"]
    if contains_any(tid, "review"):
        return variant(
            tid,
            "review_retry_v2",
            "verification",
            "The first review submission fails transiently. The agent must verify the review exists and retry if it does not.",
            [network_error("**/api/env/booking/reviews", methods=["POST"])],
        )
    if contains_any(tid, "message", "concierge", "reply"):
        return variant(
            tid,
            "message_retry_v2",
            "backtracking",
            "The first hotel-message send fails transiently. The agent must verify the message landed and retry if needed.",
            [network_error("**/api/env/booking/messages", methods=["POST"])],
        )
    if contains_any(tid, "saved_list", "save_and_organize", "save_property", "favorites"):
        return variant(
            tid,
            "saved_list_retry_v2",
            "backtracking",
            "The first saved-list write fails transiently. The agent must verify the list or property association exists and retry if it does not.",
            [network_error("**/api/env/booking/saved-lists**", methods=["POST", "DELETE"])],
        )
    if contains_any(tid, "payment", "wallet"):
        return variant(
            tid,
            "payment_retry_v2",
            "backtracking",
            "The first payment-method write fails transiently. The agent must verify the card or default-payment change actually stuck.",
            [network_error("**/api/env/booking/payment-methods**", methods=["POST", "DELETE"])],
        )
    if contains_any(tid, "preference"):
        return variant(
            tid,
            "preferences_retry_v2",
            "verification",
            "The first preferences update fails transiently. The agent must verify the preferences changed and retry if not.",
            [network_error("**/api/env/booking/preferences", methods=["PUT"])],
        )
    if contains_any(tid, "settings", "security", "language", "2fa"):
        return variant(
            tid,
            "settings_retry_v2",
            "verification",
            "The first settings update fails transiently. The agent must confirm the account settings changed and retry if needed.",
            [network_error("**/api/env/booking/settings", methods=["PUT"])],
        )
    if contains_any(tid, "account", "profile"):
        return variant(
            tid,
            "account_retry_v2",
            "verification",
            "The first account-profile write fails transiently. The agent must verify the profile change actually persisted.",
            [network_error("**/api/env/booking/account", methods=["PUT"])],
        )
    return variant(
        tid,
        "reservation_retry_v2",
        "backtracking",
        "The first reservation write fails transiently. The agent must verify the booking or reservation change exists before moving on.",
        [network_error("**/api/env/booking/reservations**", methods=["POST", "PUT"])],
    )


def reddit_subreddit_shadow_v2(task: dict[str, Any]) -> dict[str, Any]:
    subreddit = reddit_primary_subreddit(task)
    title = reddit_primary_title(task)
    return variant(
        task["task_id"],
        "subreddit_shadow_v2",
        "grounding",
        "A second lookalike community and a same-title crosspost appear beside the real subreddit. The agent must still act in the exact community named by the task.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "subreddit",
                        "name": f"{subreddit}official",
                        "display_name": f"r/{subreddit}official",
                        "description": "Official-sounding lookalike community.",
                        "subscribers": 88000,
                    },
                    {
                        "type": "post",
                        "subreddit": f"{subreddit}official",
                        "title": title,
                        "author": "crosspost_bot",
                        "score": 212,
                        "comments": 24,
                        "body": "Same title posted into the wrong, official-sounding subreddit.",
                    },
                ],
            )
        ],
    )


def reddit_user_shadow_v2(task: dict[str, Any]) -> dict[str, Any]:
    user = reddit_primary_user(task)
    subject = reddit_primary_subject(task)
    return variant(
        task["task_id"],
        "user_shadow_v2",
        "grounding",
        "Profiles, messages, and notifications include usernames that differ by punctuation or one extra token. The agent must verify the exact user before replying, messaging, or blocking.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "message",
                        "from_user": f"{user}-team",
                        "subject": subject,
                        "body": "This is a lookalike message thread from a similarly named account.",
                        "is_read": False,
                    },
                    {
                        "type": "notification",
                        "title": f"u/{user}_team replied",
                        "body": "A near-match username generated a lookalike notification. Verify the exact user before acting.",
                        "from_user": f"{user}_team",
                        "is_read": False,
                    },
                ],
            )
        ],
    )


def reddit_notification_shadow_v2(task: dict[str, Any]) -> dict[str, Any]:
    subreddit = reddit_primary_subreddit(task)
    title = reddit_primary_title(task)
    user = reddit_primary_user(task)
    return variant(
        task["task_id"],
        "notification_shadow_v2",
        "state_tracking",
        "Unread alerts emphasize a nearby crosspost and a lookalike user interaction. The agent must confirm which notification actually maps to the task target.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "notification",
                        "title": f'Crosspost activity on "{title}"',
                        "body": f'A same-title thread is trending in r/{subreddit}official. Confirm the real target before engaging.',
                        "subreddit_name": f"{subreddit}official",
                        "from_user": f"{user}_shadow",
                        "is_read": False,
                    },
                    {
                        "type": "notification",
                        "title": f"u/{user}_shadow replied",
                        "body": "Lookalike-user activity can appear beside the real target in the inbox.",
                        "subreddit_name": subreddit,
                        "from_user": f"{user}_shadow",
                        "is_read": False,
                    },
                ],
            )
        ],
    )


def reddit_decoy_variant(task: dict[str, Any], existing: list[str]) -> dict[str, Any]:
    families = current_variant_families(existing)
    if any("subreddit_collision" in family or "subreddit_twin" in family for family in families):
        return reddit_notification_shadow_v2(task)
    if any("user_impersonation" in family for family in families):
        return reddit_subreddit_shadow_v2(task)
    if any("thread_branch_collision" in family or "comment_twin" in family for family in families):
        return reddit_subreddit_shadow_v2(task)
    if any("post_collision" in family or "post_twin" in family for family in families):
        return reddit_user_shadow_v2(task)
    if any("notification_shadow" in family for family in families):
        return reddit_user_shadow_v2(task)
    return reddit_notification_shadow_v2(task)


def reddit_retry_variant(task: dict[str, Any], existing: list[str]) -> dict[str, Any]:
    del existing
    tid = task["task_id"]
    if contains_any(tid, "block"):
        return variant(
            tid,
            "block_retry_v2",
            "backtracking",
            "The first block request fails transiently. The agent must verify the user was actually blocked and retry if not.",
            [network_error("**/api/env/reddit/block/*", methods=["POST"])],
        )
    if contains_any(tid, "message", "inbox"):
        return variant(
            tid,
            "message_retry_v2",
            "backtracking",
            "The first messaging action fails transiently. The agent must verify the message or inbox state changed and retry if needed.",
            [network_error("**/api/env/reddit/messages**", methods=["POST", "DELETE"])],
        )
    if contains_any(tid, "notification"):
        return variant(
            tid,
            "notification_retry_v2",
            "verification",
            "The first notification-read action fails transiently. The agent must verify the unread count actually changed.",
            [network_error("**/api/env/reddit/notifications**", methods=["POST"])],
        )
    if contains_any(tid, "setting", "audit", "privacy"):
        return variant(
            tid,
            "settings_retry_v2",
            "verification",
            "The first settings update fails transiently. The agent must verify the Reddit settings actually changed and retry if not.",
            [network_error("**/api/env/reddit/settings", methods=["PUT"])],
        )
    if contains_any(tid, "comment", "reply", "thread"):
        return variant(
            tid,
            "comment_retry_v2",
            "backtracking",
            "The first comment or reply write fails transiently. The agent must verify the thread state changed and retry if needed.",
            [
                network_error("**/api/env/reddit/posts/*/comments", methods=["POST"]),
                network_error("**/api/env/reddit/comments/*", methods=["POST", "PUT", "DELETE"]),
            ],
        )
    if contains_any(tid, "subscribe", "community", "subreddit"):
        return variant(
            tid,
            "subscription_retry_v2",
            "backtracking",
            "The first subreddit-subscribe action fails transiently. The agent must verify the subscription state and retry if needed.",
            [network_error("**/api/env/reddit/r/*/subscribe", methods=["POST"])],
        )
    return variant(
        tid,
        "engagement_retry_v2",
        "backtracking",
        "The first post or engagement write fails transiently. The agent must verify the action landed and retry if it did not.",
        [network_error("**/api/env/reddit/posts**", methods=["POST", "PUT", "DELETE"])],
    )


def build_variants_for_task(task: dict[str, Any], existing: list[str]) -> list[dict[str, Any]]:
    env = task["env_id"]
    if env == "amazon":
        return [amazon_decoy_variant(task, existing), amazon_retry_variant(task, existing)]
    if env == "booking":
        return [booking_decoy_variant(task, existing), booking_retry_variant(task, existing)]
    if env == "reddit":
        return [reddit_decoy_variant(task, existing), reddit_retry_variant(task, existing)]
    return []


def write_task(task: dict[str, Any]) -> None:
    path = task["_path"]
    payload = {k: v for k, v in task.items() if not k.startswith("_")}
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, width=100))


def write_variant(payload: dict[str, Any]) -> None:
    out_path = VARIANTS_DIR / f"{payload['variant_id']}.yaml"
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, width=100))


def main() -> None:
    tasks = load_tasks()
    remove_existing_managed_v2_variants()
    variant_index = load_variants()
    changed_tasks = 0
    primitive_changed = 0
    neg_changed = 0

    for task in tasks.values():
        changed = False
        if normalize_primitives(task):
            primitive_changed += 1
            changed = True
        if strengthen_negative_checks(task):
            neg_changed += 1
            changed = True
        if changed:
            changed_tasks += 1
            write_task(task)

    generated_variants = 0
    for task_id, task in sorted(tasks.items()):
        if task["env_id"] not in VARIANT_ENVS:
            continue
        existing = variant_index.get(task_id, [])
        payloads = build_variants_for_task(task, existing)
        for payload in payloads:
            write_variant(payload)
            generated_variants += 1

    print(
        {
            "changed_tasks": changed_tasks,
            "primitive_changed": primitive_changed,
            "neg_changed": neg_changed,
            "generated_variants": generated_variants,
        }
    )


if __name__ == "__main__":
    main()
