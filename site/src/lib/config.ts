// Public URL of the hosted WebStress demo (a FastAPI app + 7 environment
// SPAs deployed as a Hugging Face Docker Space). Empty string disables
// the "Try in live demo" links across the site — flip it on once the
// Space is up. See ../../../demo/DEPLOY.md for the deploy recipe.
export const LIVE_DEMO_URL: string =
  // import.meta.env.VITE_LIVE_DEMO_URL ?? ""
  "https://tianchenguan-webstress-demo.hf.space";

/**
 * Build a deep-link into the launcher that lands the visitor with the
 * given task pre-selected. The launcher reads `?task=<id>`, `?cond=`,
 * and `?seed=` from the URL on page load.
 *
 *   liveDemoTaskUrl("gmail_star_email")
 *     → ".../launch?task=gmail_star_email&seed=42"
 *   liveDemoTaskUrl("gmail_star_email", "intervention")
 *     → ".../launch?task=...&cond=intervention&seed=42"
 *
 * The visitor still has to click the Launch button — we deliberately
 * don't auto-launch (so they can flip clean ↔ intervention or change
 * the seed before committing).
 */
export function liveDemoTaskUrl(
  taskId?: string,
  cond?: "clean" | "intervention",
  seed: number = 42,
): string {
  if (!LIVE_DEMO_URL) return "";
  if (!taskId) return `${LIVE_DEMO_URL}/launch`;
  const params = new URLSearchParams();
  params.set("task", taskId);
  if (cond === "intervention") params.set("cond", "intervention");
  params.set("seed", String(seed));
  return `${LIVE_DEMO_URL}/launch?${params.toString()}`;
}

export const HAS_LIVE_DEMO: boolean = Boolean(LIVE_DEMO_URL);
