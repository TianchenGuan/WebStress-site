// Hand-picked playable demos for the public site.
//
// The hosted HF Space backend can launch any of the 519 tasks, but the
// site only surfaces "Play now" CTAs on the curated set below — these
// are tasks chosen from the Human-140 panel using annotator post-task
// comments (fun_value + clarity, no suspected bugs / ambiguity flags)
// and biased toward shorter, more accessible tasks so a visitor can
// finish one in a few minutes.
//
// To curate: edit FEATURED_DEMOS. Each entry must reference a real
// task_id present in tasks_index.json. The site does not enforce this
// at build time — a typo just yields a "task not found" message on the
// card. `homepage: true` promotes the entry into the homepage Featured
// Demos strip (cap at 3-4 entries).

export type FeaturedDemo = {
  task_id: string;
  /** Which condition the Play button opens. Clean is friendlier; pick
   *  "intervention" only when the stressor itself is the point of the
   *  demo (and the clean run is too vanilla to be interesting). */
  cond: "clean" | "intervention";
  /** Optional second condition to expose alongside the primary — when
   *  both are interesting and we want the visitor to compare. */
  show_paired?: boolean;
  /** 1-2 sentences shown on the card. < 200 chars. */
  blurb: string;
  /** Promote to homepage strip. Keep total ≤ 4 to avoid clutter. */
  homepage?: boolean;
};

export const FEATURED_DEMOS: FeaturedDemo[] = [
  // ── Easy on-ramps (1-2 min) ─────────────────────────────────────────
  {
    task_id: "pp_schedule_pcp_followup",
    cond: "clean",
    blurb:
      "Schedule a follow-up appointment with your primary care provider. Single-step backtracking — a gentle on-ramp to the patient-portal environment.",
    homepage: true,
  },
  {
    task_id: "lms_read_urgent_announcement",
    cond: "clean",
    blurb:
      "Find and acknowledge the urgent announcement in your LMS dashboard. Short grounding task — the simplest task in the LMS catalog.",
  },
  {
    task_id: "gmail_update_contact",
    cond: "clean",
    blurb:
      "Update a contact's saved details in Gmail. Verification primitive — the agent must read the latest info, not the cached one.",
  },
  {
    task_id: "rh_deposit_funds",
    cond: "clean",
    blurb:
      "Deposit funds into your Robinhood account. Backtracking — the deposit flow has a confirmation step you can't shortcut.",
  },
  {
    task_id: "reddit_create_text_post",
    cond: "clean",
    blurb:
      "Create a text post in a target subreddit. Easy task — but the intervention variant on this one is interesting: try clean first, then flip to intervention.",
    show_paired: true,
  },

  // ── Medium / hard showcases ─────────────────────────────────────────
  {
    task_id: "amazon_buy_highest_rated",
    cond: "clean",
    blurb:
      "Find and buy the highest-rated product in a given category. An annotator literally called it 'one of the few tasks that can be demonstrated cleanly.'",
    homepage: true,
  },
  {
    task_id: "amazon_compare_and_buy_cheapest",
    cond: "clean",
    blurb:
      "Compare products across an Amazon search and buy the cheapest one above a minimum rating bar. Grounding under a multi-attribute constraint.",
  },

  // ── Intervention showcase ───────────────────────────────────────────
  {
    task_id: "pp_wellness_visit_prep",
    cond: "intervention",
    show_paired: true,
    blurb:
      "Prepare for an annual wellness visit by scheduling the right mix of immunizations and screenings. The intervention adds plausible-looking decoys — feel the planning stressor first-hand.",
    homepage: true,
  },

  // ── Frontier challenges (for visitors who want to commit) ───────────
  {
    task_id: "gmail_cross_functional_distribution",
    cond: "clean",
    blurb:
      "Parse a structured monthly status email into five labeled sections and forward each section to the right downstream team. Frontier state-tracking task — annotators rated this one of the cleanest frontier tasks in the panel.",
    homepage: true,
  },
  {
    task_id: "booking_frontier_loyalty_maximizer",
    cond: "clean",
    blurb:
      "Book three discounted properties across three cities to maximize your Genius Level 2 benefits. Long-horizon grounding — pace yourself.",
  },
];

export const FEATURED_TASK_IDS: Set<string> = new Set(
  FEATURED_DEMOS.map((d) => d.task_id),
);

export const HOMEPAGE_FEATURED: FeaturedDemo[] = FEATURED_DEMOS.filter(
  (d) => d.homepage,
);
