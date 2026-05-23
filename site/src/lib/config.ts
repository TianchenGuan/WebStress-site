// Public URL of the hosted WebStress demo (a FastAPI app + 7 environment
// SPAs deployed as a Hugging Face Docker Space). Empty string disables
// the "Try in live demo" links across the site — flip it on once the
// Space is up. See ../../../demo/DEPLOY.md for the deploy recipe.
export const LIVE_DEMO_URL: string =
  // import.meta.env.VITE_LIVE_DEMO_URL ?? ""
  "https://tianchenguan-webstress-demo.hf.space";

/**
 * One-click launch URL for the hosted demo. Hitting this URL creates a
 * session server-side and returns a tiny launching screen that opens
 * the benchmark SPA in a new tab and redirects the current tab to the
 * control panel — bypassing the chooser UI at /launch entirely.
 *
 *   liveDemoTaskUrl("gmail_star_email")
 *     → ".../play?task=gmail_star_email&cond=clean&seed=42"
 *   liveDemoTaskUrl("gmail_star_email", "intervention")
 *     → ".../play?task=...&cond=intervention&seed=42"
 */
export function liveDemoTaskUrl(
  taskId?: string,
  cond: "clean" | "intervention" = "clean",
  seed: number = 42,
): string {
  if (!LIVE_DEMO_URL) return "";
  if (!taskId) return `${LIVE_DEMO_URL}/launch`;
  const params = new URLSearchParams();
  params.set("task", taskId);
  params.set("cond", cond);
  params.set("seed", String(seed));
  return `${LIVE_DEMO_URL}/play?${params.toString()}`;
}

export const HAS_LIVE_DEMO: boolean = Boolean(LIVE_DEMO_URL);
