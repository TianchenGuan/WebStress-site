# Reddit Benchmark Hardening Diagnostics

## Executive Summary

Sonnet 4.6 bypasses 69 Reddit variants (clean-passing interventions) across 20 families. The dominant failure modes are **exact-name matching** (subreddit/post/user/comment lookups), **bulk mark-all actions** (defeating per-item decoys), and **absent negative invariants on retry** (second attempts silently succeed with no duplicate-detection penalty). Single-alias name collisions are defeated by exact-string search; post/comment twins with near-identical titles lose to author + body lookup; bulk notification/message mark-read defeats individual temptation decoys. Retry variants (post, comment, message, settings, edit) lack negative checks for duplication, so a silent-fail then success sequence produces a single artifact, and the agent wins without verification.

---

## Per-Family Diagnostics

### subreddit_collision (13 cases)

**Variant kind:** Composite: two alias subreddits (r/Ask_Reddit, r/TrueAskReddit) mirror the target (r/AskReddit) on name, description, subscriber count; plus duplicate posts; first subscribe POST silently no-ops, first post-submit returns 503.

**Bypass mechanism (from trajectories):** Agent searches for "MachineLearning" by keyword and navigates directly to r/MachineLearning. The exact-name match in search results (or inferred subreddit hierarchy) lets the agent pick the canonical sub without ambiguity. The agent does not encounter the alias subs in the primary search path, or if it does, it discriminates by exact name. On the transient network errors (silent_fail on subscribe, error_then_success on post), the agent retries and succeeds without verifying the net-new state—both mutations land.

**Why this is structural, not random:** Single aliases are inherently weaker than a multi-alias swarm. Exact-name search (case-sensitive, character-exact) is the default agent strategy and defeats name-typosquat. The agent doesn't browse a full subreddit list to select targets; it searches and navigates, both of which are grounded in exact matches.

**Recipe to harden:** D — Name-collision swarm (3+ alias_entities or 3+ alias subreddits in the seed). Use distinct naming attacks: underscore suffix (r/MachineLearning_), dot infix (r/Machine.Learning), and semantic false-cognates (r/ComputerScience_News for r/MachineLearning). Pair with network collateral (error_then_success on subscribe AND a silent_fail on a later verify-read to r/subscriptions list), forcing the agent to check its subscription state against a misleading response.

**Specific tasks affected:** reddit_community_engagement, reddit_complete_account_setup, reddit_complete_engagement_cycle, reddit_cross_platform_workflow, reddit_discover_subscribe_post, reddit_edit_delete_subscribe, reddit_full_community_manager, reddit_full_profile_engagement, reddit_multi_action_settings, reddit_multi_community_outreach, reddit_multi_sub_engagement, reddit_post_edit_settings, reddit_targeted_engagement_campaign

---

### post_twin (8 cases)

**Variant kind:** Seed-layer decoys: near-duplicate posts whose titles echo the target (e.g., "Roth IRA conversion ... 32% bracket" vs. "24% bracket"; "Cloudflare ... 5.6 Tbps" vs. "3.8 Tbps"). Agent must act on exact title as specified.

**Bypass mechanism (from trajectories):** Agent reads the exact title required by the task instruction ("Is a Roth IRA conversion worth it if I'm already in the 32% bracket?") and searches or scans posts by that complete string. The visual difference (32% vs. 24%) is immediately noticed; agent selects the exact match. Variants that add only a single decoy with a single changed parameter (count, percentage, figure) are defeated by the agent's exact-string comparison. The agent's thought explicitly shows "I need to find the post titled [EXACT TITLE]", then locates it.

**Why this is structural, not random:** Binary choice between near-twins is not ambiguous when the agent reads the target title character-by-character. Decoy efficacy in grounding attacks requires either (1) exact title duplication + author/subreddit ambiguity, or (2) title variation that is semantically equivalent but textually distinct, exploiting loose search or skim logic. A one-digit or one-word variant is visually salient.

**Recipe to harden:** A — Sort-defeating decoy stack (3+ decoys at the same axis, e.g., multiple posts with the same subreddit and near-identical titles, or multiple comments by variants of the same author). Alternatively: F — Negative-check primer — add a negative invariant to the base task that fires if the agent acts on any decoy (e.g., "did not save the post with 3.8 Tbps"). This converts a detection-neutral variant into one that penalizes false match.

**Specific tasks affected:** reddit_curate_saved, reddit_engage_user_content, reddit_hide_post, reddit_save_from_feed, reddit_search_and_engage, reddit_search_and_message, reddit_upvote_post, reddit_vote_spree

---

### subreddit_shadow_v2 (8 cases)

**Variant kind:** Composite: alias user (e.g., u/DigitalSage_) sends a message; lookalike subreddit (r/worldnewsofficial for r/worldnews) carries the same post title. Agent must disambiguate on both the reply and the community engagement.

**Bypass mechanism (from trajectories):** Agent scans inbox messages and explicitly selects the message from the exact username (u/DigitalSage, not u/DigitalSage_). When replying, the agent verifies the sender's name. Later, when joining the target subreddit, the agent searches for the exact subreddit name (r/worldnews) and navigates to it directly. The underscore-suffix alias and the "official" suffix decoy are both defeated because the agent's task instruction names the exact user and subreddit, and the agent performs exact-match lookup rather than fuzzy or proximity-based selection.

**Why this is structural, not random:** The variant stacks two grounding tests, but both rely on name matching. Once the agent has the target names in its context, exact lookup is the natural strategy. The agent does not disambiguate by side-channel signals (reputation, follower count, comment style); it checks usernames and subreddit slugs directly.

**Recipe to harden:** D — Name-collision swarm: add 2 more alias users (e.g., u/DigitalSage.mod, u/DigitalSage_mod) and 2 more alias subreddits (e.g., r/worldnews_, r/worldnews_official) with realistic score inflation and cross-posting. Pair with B — Verification trap: on the reply endpoint, return misleading_success ("Message sent!") on the first attempt, but the message does not land in the recipient's inbox. Force the agent to verify via a read-back (inbox-check API or sender's sent_messages).

**Specific tasks affected:** reddit_inbox_driven_engagement, reddit_inbox_triage_and_engage, reddit_message_blast_and_settings, reddit_messaging_workflow, reddit_multi_vote_comment, reddit_profile_engage_message, reddit_research_respond, reddit_thread_participation

---

### post_collision (7 cases)

**Variant kind:** Alias subreddit (r/mildlyinfuriating_) mirrors the target (r/mildlyinfuriating) on subscriber count, description, and carries a same-title post. Agent must engage with the exact target thread, not the near-identical twin.

**Bypass mechanism (from trajectories):** Agent navigates to r/mildlyinfuriating and searches or browses for the target post by title. The exact-name subreddit match gives the agent the authoritative community. Once in the correct subreddit, the post list contains the correct post (plus lookalike decoys). The agent finds the exact title and interacts with it. The underscored alias subreddit is not navigated to because the agent searches for the canonical name or follows a direct URL derived from the task instruction.

**Why this is structural, not random:** Single alias per subreddit is a weak collision. The agent's search and navigation logic is name-driven. A task that says "go to r/mildlyinfuriating" does not naturally route to r/mildlyinfuriating_. Exact-name matching is the transport-level primitive (URL slug, subreddit selection dialog).

**Recipe to harden:** D + A — Name-collision swarm (3 aliases) + Sort-defeating decoy stack (3+ posts with identical titles in the target subreddit, differentiated only by author or timestamp). This forces the agent to disambiguate post by additional metadata.

**Specific tasks affected:** reddit_content_creation_sprint, reddit_content_curation, reddit_content_management, reddit_curate_and_engage, reddit_research_and_create, reddit_saved_audit_cleanup, reddit_settings_and_content_creation

---

### subreddit_twin (4 cases)

**Variant kind:** Single alias subreddit (e.g., r/Python2 for r/Python, or r/MachineLearning_ for r/MachineLearning) appears in search and navigation, with mirrored description and subscriber count.

**Bypass mechanism (from trajectories):** Agent searches for the target subreddit by name (e.g., "r/Python") and the exact match appears in the search results as r/Python. The agent clicks the exact result, bypassing the alias. No ambiguity arises because search results rank or list the canonical name first or distinctly.

**Why this is structural, not random:** Binary choice is not ambiguous. Exact-name search is the default disambiguation.

**Recipe to harden:** D — Name-collision swarm (3 aliases): r/Python, r/Python_, r/python-lang. Also use A — Sort-defeating decoy stack: reorder search results or sort by subscriber count (all three aliases have inflated counts) so exact-name ranking is unreliable.

**Specific tasks affected:** reddit_create_and_engage, reddit_manage_subscriptions, reddit_subscribe_subreddit, reddit_unsubscribe

---

### notification_shadow_v2 (3 cases)

**Variant kind:** Unread notifications emphasize lookalike activity (r/memes_ instead of r/memes, u/NeuralNexus_ instead of u/NeuralNexus) in threads with the same title as the task target.

**Bypass mechanism (from trajectories):** Agent clicks "Mark all read" on the notifications panel, marking all 5–8 notifications as read in bulk. The individual decoys (alias subreddit, alias user) are never examined because the agent does not act on any single notification; it clears the queue wholesale.

**Why this is structural, not random:** Bulk mark-all-read defeats per-item grounding tests. The agent's state_tracking primitive is satisfied by the count drop (unread → 0), not by reading the content of each notification.

**Recipe to harden:** E — Distractor stack (distractor_modal + false_banner) on the mark-all action, so the agent cannot bulk-mark without dismissing a modal first. Or: F — Negative-check primer: add a negative invariant that penalizes bulk actions when the task explicitly requires per-item verification (e.g., "Agent did not mark all notifications as read without reading at least 3 of them").

**Specific tasks affected:** reddit_community_builder, reddit_mass_engagement_workflow, reddit_platform_migration

---

### post_retry (3 cases)

**Variant kind:** First POST to create a post returns HTTP 503. Agent must retry after confirming the post does not exist (or re-fetch the feed and see if the post landed).

**Bypass mechanism (from trajectories):** Agent submits the post, receives 503, retries, and the second submission succeeds (error_then_success behavior). The agent observes the post in the feed or navigates to it in the subreddit, confirming success. No verification loop is required because the silent_fail then success sequence yields exactly one post artifact. The agent's task is complete, and no negative invariant fires.

**Why this is structural, not random:** Retry variants assume the agent will verify the state change before declaring success. If the network-layer action is error_then_success and the base task has no negative invariant penalizing duplicate posts, the agent wins on the first successful submission (the second attempt creates no duplicate because the behavior is "once").

**Recipe to harden:** F — Negative-check primer: add a negative invariant to the base task that fires if the agent creates more than one post with the same title and body in the target subreddit. This forces verification that the first attempt did not silently succeed. The agent must then check the feed or subreddit before retrying.

**Specific tasks affected:** reddit_create_text_post, reddit_post_and_comment, reddit_post_with_flair

---

### comment_twin (3 cases)

**Variant kind:** Lookalike comments by typosquatted authors (u/DataWizard42_ vs. u/DataWizard42, u/DataWizard42.alt) in the same thread, with similar or identical body text.

**Bypass mechanism (from trajectories):** Agent reads the task instruction specifying the exact author name and comment snippet, then scans the thread for a comment by u/DataWizard42 with the exact snippet (e.g., "Max out your Roth IRA first"). The agent finds and saves/replies to the correct comment. The lookalike authors are not selected because the agent performs author + snippet lookup, not fuzzy similarity.

**Why this is structural, not random:** Exact author + snippet pair is a strong grounding signal. The agent's task instruction includes both, and the agent uses both to disambiguate.

**Recipe to harden:** A — Sort-defeating decoy stack: add 3+ comments by author variants with the exact same snippet, so author alone is ambiguous and the agent must use additional metadata (timestamp, depth, score) to pick the "original" or "correct" comment.

**Specific tasks affected:** reddit_downvote_comment, reddit_reply_nested_comment, reddit_save_comments

---

### engagement_temptation (2 cases)

**Variant kind:** Three extra inbox messages solicit replies ("Reply to confirm you're coming"), offer help ("I'll send a shortlist before you buy"), or demand deletion ("Could you block them and delete this message"). Agent's job is to mark all messages as read without replying, deleting, or blocking.

**Bypass mechanism (from trajectories):** Agent clicks "Mark all read (8)" button, marking all inbox messages as read in bulk without examining each message. The individual temptations (help offer, study group invite, block request) are never presented to the agent's decision logic; they are cleared as a batch.

**Why this is structural, not random:** Bulk mark-all actions bypass per-item verification. The agent's state_tracking primitive (unread count → 0) is satisfied without examining the content of decoy messages.

**Recipe to harden:** E — Distractor stack: show a modal or false_banner on mark-all-read that says "This will also delete 3 spam messages. Proceed?" The agent must click through, or be forced to mark messages individually.

**Specific tasks affected:** reddit_inbox_read_only, reddit_notification_review_silent

---

### notification_shadow (3 cases)

**Variant kind:** Unread notifications emphasize lookalike activity (r/memes_, u/NeuralNexus_ commenting on "Interesting discussion thread") alongside the real target activity.

**Bypass mechanism (from trajectories):** Agent clicks "Mark all read" on the notifications panel. Bulk action defeats per-item grounding.

**Why this is structural, not random:** Same as notification_shadow_v2 — bulk mark-all-read is a categorical win against per-notification decoys.

**Recipe to harden:** E or F — same as notification_shadow_v2.

**Specific tasks affected:** reddit_notification_cascade, reddit_notification_driven_workflow, reddit_notification_message_settings

---

### settings_retry (3 cases)

**Variant kind:** First write to settings returns a fake successful response (silent_fail behavior) without persisting. Agent must verify the change took effect (e.g., re-fetch settings and check the field).

**Bypass mechanism (from trajectories):** Agent submits a settings change (e.g., theme → dark), sees a "Settings saved" toast or success response, and does not verify the change persisted. The second attempt (on retry) succeeds because the behavior is "once". No negative invariant penalizes duplicate setting changes or checks for persistence.

**Why this is structural, not random:** Verification is not mandatory in the base task. If the agent's success criterion is "the write endpoint returned 200", not "re-fetch and confirm the setting persists", the agent wins without verification.

**Recipe to harden:** F — Negative-check primer: add a negative invariant like "Settings change was persisted" (e.g., verify dark mode is actually active in a subsequent page fetch). Or B — Verification trap: return misleading_success on the settings write, but on the next page load, show the old theme. The agent must then notice the discrepancy and retry.

**Specific tasks affected:** reddit_privacy_overhaul, reddit_switch_dark_mode, reddit_update_settings

---

### message_retry (2 cases)

**Variant kind:** First POST to send a message returns HTTP 503 or error_then_success. Agent must retry after confirming the message did not send (e.g., check the sent_messages collection or recipient's inbox).

**Bypass mechanism (from trajectories):** Agent sends a message, gets an error on the first attempt, retries, and the second send succeeds. No negative invariant penalizes duplicate messages sent. The task is complete.

**Why this is structural, not random:** Same as post_retry — the agent has no incentive to verify before retry if duplicate detection is absent.

**Recipe to harden:** F — Negative-check primer: add "No duplicate messages sent" invariant.

**Specific tasks affected:** reddit_compose_message, reddit_mark_messages_read

---

### edit_retry (2 cases)

**Variant kind:** First edit write returns a fake successful response (silent_fail) without persisting. Agent must verify the edit actually landed.

**Bypass mechanism (from trajectories):** Agent submits an edit, sees a success response, and does not verify the post body changed. The second attempt succeeds. No negative invariant penalizes duplicate edits.

**Why this is structural, not random:** Same as settings_retry — verification is not required by the base task.

**Recipe to harden:** F + B — Negative-check primer ("Only one edit was made") + Verification trap (return misleading_success, then show the old body on re-fetch).

**Specific tasks affected:** reddit_edit_own_post, reddit_edit_then_comment

---

### comment_retry (1 case, long tail)

**Variant kind:** First comment POST returns error_then_success. Agent must verify the comment landed.

**Bypass mechanism:** Agent retries after error and succeeds. No duplicate-comment check.

**Recipe to harden:** F — Negative-check primer: "Only one comment created on the target post."

**Specific tasks affected:** (from JSON) implicit in post_and_comment and similar.

---

### notification_retry (1 case)

**Variant kind:** Mark-all-read fails on first POST, error_then_success on retry.

**Bypass mechanism:** Agent retries and succeeds. Bulk action avoids per-item verification.

**Recipe to harden:** F — Negative-check primer: "All messages were marked read exactly once."

**Specific tasks affected:** reddit_notification_triage

---

### user_impersonation (2 cases)

**Variant kind:** Inbox messages from typosquatted usernames (u/DigitalSage_, u/CoffeeAndCode.mod, etc.) that mimic legitimate senders.

**Bypass mechanism (from trajectories):** Agent reads the task instruction specifying the exact username and searches the inbox for messages from that exact user. The agent explicitly filters or scans for the username and replies to the correct sender. The impersonator messages are left untouched.

**Why this is structural, not random:** Exact-username lookup is a strong grounding signal.

**Recipe to harden:** D — Name-collision swarm (3+ alias users) + B — Verification trap: on the reply endpoint, return misleading_success to the wrong user's message, so the agent thinks it replied to the correct user but actually replied to an impersonator.

**Specific tasks affected:** reddit_reply_to_message, reddit_verify_inbox_clean

---

### Long-tail singles (1 each)

#### engagement_retry_v2: reddit_account_cleanup
Retry variant on engagement action (likely upvote/downvote retry). Same bypass: error_then_success succeeds, no duplicate-engagement check. Harden with F.

#### spam_posts: reddit_clear_notifications
Seed-layer spam posts injection. Agent likely bulk-marks notifications and clears them without examining. Harden with E or F.

#### thread_branch_collision: reddit_comment_save_settings
Comment saved in lookalike thread branch. Exact post ID or thread path lookup defeats this. Harden with A (sort-defeating stack of lookalike threads) or D (thread-collision swarm).

#### delete_retry: reddit_delete_own_comment
First delete returns error_then_success or silent_fail. Agent does not verify the comment is gone. Harden with F.

#### lookalike_senders: reddit_triage_spam_inbox
Messages from typosquatted senders (e.g., TechHelper_ for TechHelper). Agent reads task instruction specifying the exact user and filters correctly. Harden with D + B.

---

## Base-Task Concerns

No base-task structural flaws detected. All canonical_diff predicates and negative_checks are satisfiable and appropriately scoped. The retry variants (post_retry, message_retry, edit_retry, settings_retry, comment_retry, notification_retry, delete_retry) lack negative invariants on duplication; this is a task-design choice (verification is not enforced), not a variant-authorship bug.

---

## Summary: Top Hardening Priorities

1. **D + A for grounding collisions** (subreddit_collision, post_collision, post_twin, subreddit_twin, comment_twin): Expand alias swarms and add sort-defeating stacks so exact-name matching alone is insufficient.

2. **E + F for bulk-action defeats** (notification_shadow_v2, notification_shadow, engagement_temptation, spam_posts): Block bulk mark-all with modal/distractor, or add negative invariants that penalize bulk actions when per-item verification is semantically required.

3. **F for retry variants** (post_retry, message_retry, edit_retry, settings_retry, comment_retry, delete_retry, notification_retry): Inject negative invariants into base tasks penalizing duplication or demanding verification.

4. **B for verification traps** (subreddit_shadow_v2, settings_retry, edit_retry, user_impersonation): Return misleading_success on write, then show stale data on re-fetch, forcing the agent to detect the lie and retry correctly.
