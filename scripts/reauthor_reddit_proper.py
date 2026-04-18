"""Re-author auto-converted Reddit canonical_diffs into proper form.

Pattern-matches common eval.check expressions and translates them into
canonical_diff.update/create/delete entries with invariants and named
invariants. Falls back to constraint form only for expressions the
translator cannot decompose (state.settings.X, state.blocked_users, etc.).

This is a bulk reauthor pass: it overwrites the existing (auto-converted
constraint-only) canonical_diff blocks with ones that use the full grammar.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REDDIT_DIR = Path("webagentbench/tasks/reddit")

# Skip hand-crafted tasks (already in proper form).
HAND_WRITTEN = {
    "reddit_upvote_post", "reddit_subscribe_subreddit", "reddit_create_text_post",
    "reddit_delete_own_comment", "reddit_compose_message", "reddit_clear_notifications",
    "reddit_mark_messages_read", "reddit_save_from_feed", "reddit_unsubscribe",
    "reddit_hide_post", "reddit_downvote_comment", "reddit_edit_own_post",
    "reddit_reply_to_message", "reddit_switch_dark_mode", "reddit_update_settings",
    "reddit_verify_inbox_clean", "reddit_engage_user_content", "reddit_post_with_flair",
    "reddit_save_comments", "reddit_vote_spree", "reddit_curate_saved",
    "reddit_manage_subscriptions", "reddit_reply_nested_comment",
    "reddit_follow_notification", "reddit_post_and_comment", "reddit_privacy_overhaul",
    "reddit_search_and_message", "reddit_create_and_engage",
    "reddit_edit_then_comment", "reddit_message_management",
    # Also skip the ones I manually upgraded in this batch
    "reddit_account_cleanup", "reddit_block_and_cleanup",
    "reddit_comment_save_settings", "reddit_comment_chain_analysis",
}

ALL_COLLECTIONS = ["subreddits", "posts", "comments", "messages",
                   "sent_messages", "notifications", "user_profiles"]


@dataclass
class Diff:
    updates: list[dict] = field(default_factory=list)
    creates: list[dict] = field(default_factory=list)
    deletes: list[dict] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)
    touched_collections: set[str] = field(default_factory=set)


def _clean_target_refs(expr: str) -> str:
    """Normalize {target.X} / 'target['X']' / '{target.X}' → target['X']."""
    # 'target['X']' or 'target["X"]' (legacy auto-converter artifact)
    expr = re.sub(r"'''target\[['\"]([^'\"]+)['\"]\]'''", r"target['\1']", expr)
    expr = re.sub(r"'target\[['\"]([^'\"]+)['\"]\]'", r"target['\1']", expr)
    # '{target.X}' → target['X'] (quote around template)
    expr = re.sub(r"'\{target\.([^}]+)\}'", r"target['\1']", expr)
    # {target.X} → target['X']
    expr = re.sub(r"\{target\.([^}]+)\}", r"target['\1']", expr)
    return expr


def translate(check: dict, diff: Diff) -> None:
    """Translate a single eval.check into positive-diff or constraint.

    Mutates diff in place. Unrecognized patterns become constraints.
    """
    expr = _clean_target_refs(check.get("expr", "").strip())
    desc = check.get("desc", "check")

    # Pattern: state.get_post('{X}').vote_direction == N → update Post
    m = re.match(r"^state\.get_post\(target\['(\w+)'\]\)\.vote_direction == (-?\d+)$", expr)
    if m:
        tid, val = m.group(1), int(m.group(2))
        diff.updates.append({
            "entity": "Post", "desc": desc,
            "where": {"id": {"expr": f"x == target['{tid}']"}},
            "changes": {"vote_direction": {"eq": val}},
        })
        diff.touched_collections.add("posts")
        return

    # Pattern: state.get_post('{X}').is_saved / is_hidden → update Post
    m = re.match(r"^state\.get_post\(target\['(\w+)'\]\)\.(is_saved|is_hidden|is_edited)$", expr)
    if m:
        tid, field_name = m.group(1), m.group(2)
        diff.updates.append({
            "entity": "Post", "desc": desc,
            "where": {"id": {"expr": f"x == target['{tid}']"}},
            "changes": {field_name: {"eq": True}},
        })
        diff.touched_collections.add("posts")
        return

    # Pattern: not state.get_post('{X}').is_removed → invariant that post exists
    # Skip - this is typically a negative check preserved via invariant anyway

    # Pattern: state.get_comment('{X}').vote_direction == N → update Comment
    m = re.match(r"^state\.get_comment\(target\['(\w+)'\]\)\.vote_direction == (-?\d+)$", expr)
    if m:
        tid, val = m.group(1), int(m.group(2))
        diff.updates.append({
            "entity": "Comment", "desc": desc,
            "where": {"id": {"expr": f"x == target['{tid}']"}},
            "changes": {"vote_direction": {"eq": val}},
        })
        diff.touched_collections.add("comments")
        return

    # Pattern: target['X'] in state.saved_post_ids → update Post.is_saved
    m = re.match(r"^target\['(\w+)'\] in state\.saved_post_ids$", expr)
    if m:
        tid = m.group(1)
        diff.updates.append({
            "entity": "Post", "desc": desc,
            "where": {"id": {"expr": f"x == target['{tid}']"}},
            "changes": {"is_saved": {"eq": True}},
        })
        diff.touched_collections.add("posts")
        return

    # Pattern: target['X'] in state.saved_comment_ids → update Comment.is_saved
    m = re.match(r"^target\['(\w+)'\] in state\.saved_comment_ids$", expr)
    if m:
        tid = m.group(1)
        diff.updates.append({
            "entity": "Comment", "desc": desc,
            "where": {"id": {"expr": f"x == target['{tid}']"}},
            "changes": {"is_saved": {"eq": True}},
        })
        diff.touched_collections.add("comments")
        return

    # Pattern: any(s.name == 'X' and s.is_subscribed for s in state.subreddits) → update Subreddit
    # Accept either literal names ('X') or target refs (target['X']) for subreddit name
    def _name_expr(raw: str) -> str:
        # raw is either "'literal'" or "target['key']"
        return raw.strip("'\"") if not raw.startswith("target[") else raw

    m = re.match(r"^any\(s\.name == (target\[['\"](\w+)['\"]\]|['\"][^'\"]+['\"]) and s\.is_subscribed for s in state\.subreddits\)$", expr)
    if m:
        name_ref = m.group(1)
        name_lit = name_ref.strip("'\"") if not name_ref.startswith("target[") else name_ref
        inner = f"state.get_subreddit(x).name == {name_lit!r}" if not name_ref.startswith("target[") else f"state.get_subreddit(x).name == {name_ref}"
        diff.updates.append({
            "entity": "Subreddit", "desc": desc,
            "where": {"id": {"expr": inner}},
            "changes": {"is_subscribed": {"eq": True}},
        })
        diff.touched_collections.add("subreddits")
        return

    m = re.match(r"^any\(s\.name == (target\[['\"](\w+)['\"]\]|['\"][^'\"]+['\"]) and not s\.is_subscribed for s in state\.subreddits\)$", expr)
    if m:
        name_ref = m.group(1)
        inner = f"state.get_subreddit(x).name == {name_ref}" if name_ref.startswith("target[") else f"state.get_subreddit(x).name == {name_ref}"
        diff.updates.append({
            "entity": "Subreddit", "desc": desc,
            "where": {"id": {"expr": inner}},
            "changes": {"is_subscribed": {"eq": False}},
        })
        diff.touched_collections.add("subreddits")
        return

    # Helper to build predicate from either literal or target ref token
    def _val_to_pred(token: str) -> dict:
        token = token.strip()
        if token.startswith("target["):
            return {"expr": f"x == {token}"}
        # literal string (double or single quoted)
        if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
            return {"eq": token[1:-1]}
        return {"any": True}

    def _ref_or_literal() -> str:
        return r"(target\[['\"](?:\w+)['\"]\]|\"[^\"]+\"|'[^']+')"

    # Pattern: any(c.post_id == <ref> and c.body == <ref|lit> [and c.parent_id is None]
    #           and c.author_name == state.owner_username for c in state.comments)
    # → create Comment
    m = re.search(
        rf"any\(\s*c\.post_id == {_ref_or_literal()}\s*and\s*c\.body == {_ref_or_literal()}\s*(?:and\s*c\.parent_id is None)?\s*and\s*c\.author_name == state\.owner_username\s+for\s+c\s+in\s+state\.comments\)",
        expr)
    if m:
        post_token, body_token = m.group(1), m.group(2)
        parent_pred = {"eq": None} if "parent_id is None" in expr else {"any": True}
        props = {
            "post_id": _val_to_pred(post_token),
            "body": _val_to_pred(body_token),
            "parent_id": parent_pred,
            "author_name": {"expr": "x == state.owner_username"},
        }
        diff.creates.append({
            "entity": "Comment", "desc": desc, "properties": props,
        })
        diff.touched_collections.add("comments")
        return

    # Pattern: any(c.post_id == <ref> and <snippet-ref> in c.body and c.author_name == ...)
    # → create Comment with substring body predicate
    m = re.search(
        rf"any\(\s*c\.post_id == {_ref_or_literal()}\s*and\s*{_ref_or_literal()} in c\.body\s*(?:and\s*c\.parent_id is None)?\s*and\s*c\.author_name == state\.owner_username\s+for\s+c\s+in\s+state\.comments\)",
        expr)
    if m:
        post_token, snip_token = m.group(1), m.group(2)
        # substring body predicate: if token is target ref, use expr; if literal, use substring
        if snip_token.startswith("target["):
            body_pred = {"expr": f"{snip_token} in (x or '')"}
        else:
            body_pred = {"substring": snip_token[1:-1]}
        parent_pred = {"eq": None} if "parent_id is None" in expr else {"any": True}
        diff.creates.append({
            "entity": "Comment", "desc": desc,
            "properties": {
                "post_id": _val_to_pred(post_token),
                "body": body_pred,
                "parent_id": parent_pred,
                "author_name": {"expr": "x == state.owner_username"},
            },
        })
        diff.touched_collections.add("comments")
        return

    # Pattern: any(c.parent_id == <ref> and c.body == <ref|lit> and c.author_name == ...
    # → create Comment reply
    m = re.search(
        rf"any\(\s*c\.parent_id == {_ref_or_literal()}\s*and\s*c\.body == {_ref_or_literal()}\s*and\s*c\.author_name == state\.owner_username\s+for\s+c\s+in\s+state\.comments\)",
        expr)
    if m:
        parent_token, body_token = m.group(1), m.group(2)
        diff.creates.append({
            "entity": "Comment", "desc": desc,
            "properties": {
                "parent_id": _val_to_pred(parent_token),
                "body": _val_to_pred(body_token),
                "author_name": {"expr": "x == state.owner_username"},
            },
        })
        diff.touched_collections.add("comments")
        return

    # Pattern: any(c.parent_id == <ref> and <snip-ref> in c.body and c.author_name == ...)
    m = re.search(
        rf"any\(\s*c\.parent_id == {_ref_or_literal()}\s*and\s*{_ref_or_literal()} in c\.body\s*and\s*c\.author_name == state\.owner_username\s+for\s+c\s+in\s+state\.comments\)",
        expr)
    if m:
        parent_token, snip_token = m.group(1), m.group(2)
        body_pred = {"expr": f"{snip_token} in (x or '')"} if snip_token.startswith("target[") else {"substring": snip_token[1:-1]}
        diff.creates.append({
            "entity": "Comment", "desc": desc,
            "properties": {
                "parent_id": _val_to_pred(parent_token),
                "body": body_pred,
                "author_name": {"expr": "x == state.owner_username"},
            },
        })
        diff.touched_collections.add("comments")
        return

    # Pattern: any(m.to_user == <ref|lit> and m.subject == <ref|lit>
    #              [and m.body == <ref|lit>] [and m.parent_id is None]
    #              for m in state.sent_messages) → create Message (sent_messages)
    # Body is optional — some tasks only spec to/subject.
    m = re.search(
        rf"any\(\s*m\.to_user == {_ref_or_literal()}\s*and\s*m\.subject == {_ref_or_literal()}(?:\s*and\s*m\.body == {_ref_or_literal()})?\s*(?:and\s*m\.parent_id is None)?\s+for\s+m\s+in\s+state\.sent_messages\)",
        expr)
    if m:
        to_token, subj_token, body_token = m.group(1), m.group(2), m.group(3)
        props = {
            "to_user": _val_to_pred(to_token),
            "subject": _val_to_pred(subj_token),
            "from_user": {"expr": "x == state.owner_username"},
        }
        if body_token is not None:
            props["body"] = _val_to_pred(body_token)
        if "parent_id is None" in expr:
            props["parent_id"] = {"eq": None}
        diff.creates.append({
            "entity": "Message",
            "collection": "state.sent_messages",
            "desc": desc,
            "properties": props,
        })
        diff.touched_collections.add("sent_messages")
        # Registry validator uses naive pluralization Message→"messages"
        # so we must also mark the inbox 'messages' collection touched
        # (its invariant gets filter: "True").
        diff.touched_collections.add("messages")
        return

    # Pattern: any(p.subreddit_name == <ref|lit> and p.title == <ref|lit>
    #              and p.author_name == state.owner_username for p in state.posts)
    # → create Post
    m = re.search(
        rf"any\(\s*p\.subreddit_name == {_ref_or_literal()}\s*and\s*p\.title == {_ref_or_literal()}\s*and\s*p\.author_name == state\.owner_username\s+for\s+p\s+in\s+state\.posts\)",
        expr)
    if m:
        sub_token, title_token = m.group(1), m.group(2)
        diff.creates.append({
            "entity": "Post", "desc": desc,
            "properties": {
                "subreddit_name": _val_to_pred(sub_token),
                "title": _val_to_pred(title_token),
                "author_name": {"expr": "x == state.owner_username"},
            },
        })
        diff.touched_collections.add("posts")
        return

    # Pattern: any(n.id == target['X'] and n.is_read for n in state.notifications) → update Notification
    m = re.match(
        r"^any\(n\.id == target\['(\w+)'\] and n\.is_read for n in state\.notifications\)$", expr)
    if m:
        tid = m.group(1)
        diff.updates.append({
            "entity": "Notification", "desc": desc,
            "where": {"id": {"expr": f"x == target['{tid}']"}},
            "changes": {"is_read": {"eq": True}},
        })
        diff.touched_collections.add("notifications")
        return

    # Pattern: state.get_message('X').is_read → constraint (inbox messages inconvenient for positive-diff)
    # Fall through.

    # Default: preserve as constraint
    severity = check.get("severity", "high")
    diff.constraints.append({
        "desc": desc,
        "expr": expr,
        "severity": severity,
    })


def build_canonical_diff(task_raw: dict) -> dict:
    eval_block = task_raw.get("eval") or {}
    checks = eval_block.get("checks") or []

    diff = Diff()
    for c in checks:
        translate(c, diff)

    # Build invariants for all untouched collections
    invariants = []
    for col in ALL_COLLECTIONS:
        if col in diff.touched_collections:
            invariants.append({
                "collection": f"state.{col}",
                "filter": "True",
                "preserve": "ALL",
            })
        else:
            invariants.append({
                "collection": f"state.{col}",
                "preserve": "ALL",
            })

    named = []
    for idx, u in enumerate(diff.updates):
        named.append({"name": u["desc"], "ref": f"update[{idx}]", "severity": "high"})
    for idx, c in enumerate(diff.creates):
        named.append({"name": c["desc"], "ref": f"create[{idx}]", "severity": "high"})
    for idx, d in enumerate(diff.deletes):
        named.append({"name": d["desc"], "ref": f"delete[{idx}]", "severity": "high"})

    cd: dict = {}
    if diff.updates:
        cd["update"] = diff.updates
    if diff.creates:
        cd["create"] = diff.creates
    if diff.deletes:
        cd["delete"] = diff.deletes
    if diff.constraints:
        cd["constraints"] = diff.constraints
    cd["invariant"] = invariants
    if named:
        cd["named_invariants"] = named
    return cd


def reauthor(path: Path) -> bool:
    raw = yaml.safe_load(path.read_text()) or {}
    task_id = raw.get("task_id")
    if task_id in HAND_WRITTEN:
        return False

    new_cd = build_canonical_diff(raw)
    content = path.read_text()

    # Remove existing canonical_diff block (from "canonical_diff:" to next
    # top-level key — typically "eval:" at start of line).
    pattern = re.compile(r"^canonical_diff:\s*\n(?:.+\n)*?(?=^(?:eval|secondary_primitives):\s*$)", re.MULTILINE)
    content = pattern.sub("", content)

    # Render the new canonical_diff
    cd_yaml = yaml.safe_dump({"canonical_diff": new_cd},
                             default_flow_style=False, sort_keys=False, width=120)
    # Insert before "eval:" at start of line
    match = re.search(r"^eval:\s*$", content, re.MULTILINE)
    if not match:
        return False
    insert_at = match.start()
    new_content = content[:insert_at] + cd_yaml + content[insert_at:]
    path.write_text(new_content)
    return True


def main() -> None:
    converted = 0
    for yaml_path in sorted(REDDIT_DIR.glob("*.yaml")):
        if reauthor(yaml_path):
            converted += 1
            print(f"[reauthored] {yaml_path.name}")
    print(f"\nreauthored {converted} tasks")


if __name__ == "__main__":
    main()
