// Public URL of the hosted WebStress demo (a FastAPI app + 7 environment
// SPAs deployed as a Hugging Face Docker Space). Empty string disables
// the "Try in live demo" links across the site — flip it on once the
// Space is up. See ../../../demo/DEPLOY.md for the deploy recipe.
export const LIVE_DEMO_URL: string =
  // import.meta.env.VITE_LIVE_DEMO_URL ?? ""
  "https://tianchenguan-webstress-demo.hf.space";

export function liveDemoTaskUrl(): string {
  // The launcher doesn't currently parse `?task=` from the URL, so we
  // just open the launcher at the root and let the visitor pick. Once
  // the launcher learns to deep-link, switch this to:
  //   `${LIVE_DEMO_URL}/launch?task=${encodeURIComponent(taskId)}`
  if (!LIVE_DEMO_URL) return "";
  return `${LIVE_DEMO_URL}/launch`;
}

export const HAS_LIVE_DEMO: boolean = Boolean(LIVE_DEMO_URL);
