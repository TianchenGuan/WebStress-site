// Public URL of the hosted WebStress demo (a FastAPI app + 7 environment
// SPAs deployed as a Hugging Face Docker Space). Empty string disables
// the "Try in live demo" links across the site — flip it on once the
// Space is up. See ../../../demo/DEPLOY.md for the deploy recipe.
export const LIVE_DEMO_URL: string =
  // import.meta.env.VITE_LIVE_DEMO_URL ?? ""
  "https://tianchenguan-webstress-demo.hf.space";

/**
 * Single-tab fallback URL — drops the visitor on the /play launching
 * screen, which then tries to popup the benchmark tab. Used when we
 * can't run JS (e.g. server-rendered emails) or as a fallback link.
 *
 * For the actual "Play" buttons on featured cards, prefer
 * {@link playDemo} — it opens both tabs synchronously inside the
 * user-gesture click handler, bypassing popup blockers.
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

/**
 * One-click launch: opens the benchmark SPA and the control panel in
 * two new tabs, both bound to the same backend session.
 *
 * How it works: we generate a client-request UUID and synchronously
 * call `window.open` twice with `mode=bench` and `mode=control`.
 * Both URLs hit the same `/play` endpoint, which uses the shared
 * `cid` as a dedup key — whichever tab arrives first creates the
 * session and stores it under that cid, the second one reuses it.
 *
 * Both `window.open`s happen inside the user's click gesture (no
 * `await` between click and open), so the popup blocker treats them
 * as user-initiated and lets both through.
 *
 * Returns `false` if the demo URL isn't configured or `window.open`
 * was blocked outright (so the caller can render a fallback link).
 */
export function playDemo(
  taskId: string,
  cond: "clean" | "intervention" = "clean",
  seed: number = 42,
): boolean {
  if (!LIVE_DEMO_URL) return false;
  const cid =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `cid-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const base = new URLSearchParams({
    task: taskId,
    cond,
    seed: String(seed),
    cid,
  });
  const benchUrl = `${LIVE_DEMO_URL}/play?${base}&mode=bench`;
  const controlUrl = `${LIVE_DEMO_URL}/play?${base}&mode=control`;
  // Open both synchronously — no await between them so the user-gesture
  // token applies to both window.open calls.
  const benchWin = window.open(benchUrl, "_blank", "noopener");
  const controlWin = window.open(controlUrl, "_blank", "noopener");
  return Boolean(benchWin && controlWin);
}

export const HAS_LIVE_DEMO: boolean = Boolean(LIVE_DEMO_URL);
