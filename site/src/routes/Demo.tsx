import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadTasks } from "../lib/data";
import type { TaskEntry } from "../data/types";
import { ENV_LABELS, pillColorForDifficulty } from "../lib/format";
import { HAS_LIVE_DEMO, LIVE_DEMO_URL, playDemo } from "../lib/config";
import { FEATURED_DEMOS } from "../lib/featured";
import Pill from "../components/Pill";

export default function Demo() {
  const [tasks, setTasks] = useState<TaskEntry[] | null>(null);

  useEffect(() => {
    loadTasks().then(setTasks).catch(() => setTasks([]));
  }, []);

  const byId = useMemo(() => {
    if (!tasks) return null;
    return new Map(tasks.map((t) => [t.task_id, t]));
  }, [tasks]);

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <h1 className="text-3xl mb-2">Live demo</h1>
      <p className="text-ink/75 max-w-prose mb-8">
        Hand-picked tasks from the Human-140 panel that read cleanly on a
        first encounter. Each card opens a one-click launch — no chooser
        UI, no setup. The benchmark SPA opens in a new tab while this tab
        becomes a small control panel where you can see the task
        instruction and score your attempt.
      </p>

      {!HAS_LIVE_DEMO && (
        <div className="card mb-8 bg-cream border-border">
          <p className="text-sm text-ink/85 leading-relaxed">
            The hosted demo is offline at the moment. You can still run
            WebStress locally — see <Link to="/docs/setup">docs / setup</Link>.
          </p>
        </div>
      )}

      {HAS_LIVE_DEMO && (
        <div className="grid md:grid-cols-2 gap-5 mb-12">
          {FEATURED_DEMOS.map((demo) => {
            const entry = byId?.get(demo.task_id);
            if (byId && !entry) {
              return (
                <div key={demo.task_id} className="card border-accent/40 bg-cream">
                  <p className="text-sm text-accent">
                    Featured task <code>{demo.task_id}</code> not found in the
                    task index. Check{" "}
                    <code>site/src/lib/featured.ts</code>.
                  </p>
                </div>
              );
            }
            return (
              <DemoCard
                key={`${demo.task_id}-${demo.cond}`}
                demo={demo}
                entry={entry || null}
              />
            );
          })}
        </div>
      )}

      <section className="card mb-6 bg-accent-soft/30 border-accent/40">
        <h2 className="text-sm uppercase tracking-wider text-accent mb-2">
          Looking for the full task catalog?
        </h2>
        <p className="text-sm text-ink/85 leading-relaxed mb-3">
          The featured set above is curated. The full 519-task explorer
          lives at <Link to="/tasks">/tasks</Link> — every task is
          documented, but only featured ones expose a one-click play
          button. To run the others you can either spin up WebStress
          locally, or open the launcher and pick manually:
        </p>
        <a
          href={`${LIVE_DEMO_URL}/launch`}
          target="_blank"
          rel="noreferrer"
          className="btn"
        >
          Open the launcher (all 519)&nbsp;<span aria-hidden>→</span>
        </a>
      </section>

      <h2 className="text-xl mt-12 mb-3">What the demo does and doesn't do</h2>
      <ul className="text-sm text-ink/85 leading-relaxed list-disc pl-5 space-y-1.5">
        <li>
          <span className="text-sage">✓</span> Serves the seven environment
          SPAs with deterministic seeded state per session.
        </li>
        <li>
          <span className="text-sage">✓</span> Exposes both <em>clean</em>{" "}
          and <em>intervention</em> conditions — useful to feel what a
          given stressor family does to the task.
        </li>
        <li>
          <span className="text-sage">✓</span> Lets you record your own play
          trace via the control panel. Traces stay client-side and aren't
          uploaded.
        </li>
        <li>
          <span className="text-accent">✗</span> Does <em>not</em> run agent
          evaluations. Agents need the Browser-Use or BrowserGym harness
          plus a provider API key — that goes through the local repo.
        </li>
        <li>
          <span className="text-accent">✗</span> Does <em>not</em> persist
          sessions across container restarts. Each visitor gets a fresh
          seed; no PII is retained.
        </li>
      </ul>

      <h2 className="text-xl mt-10 mb-3">Responsible use</h2>
      <p className="text-sm text-ink/85 leading-relaxed">
        WebStress interventions are designed for sandbox benchmark
        environments. They should not be used to build deceptive
        interfaces or agents that exploit real users. The released
        stressor catalog (phishing-style email bodies, fabricated-success
        HTTP responses, look-alike decoys) is intended as a defensive
        evaluation harness and is bounded by the demo's local sandbox.
      </p>

      <p className="mt-10 text-xs text-muted">
        Hosting: a Docker Space on Hugging Face's free CPU-basic tier.
        Goes to sleep after ~48 h of inactivity and cold-starts (15–30 s)
        on the next visit.
      </p>
    </div>
  );
}

function DemoCard({
  demo,
  entry,
}: {
  demo: import("../lib/featured").FeaturedDemo;
  entry: TaskEntry | null;
}) {
  const title = entry?.title ?? demo.task_id;
  const env = entry?.env_id;
  const difficulty = entry?.difficulty;
  const condLabel = demo.cond === "intervention" ? "Intervention" : "Clean";
  const condChip =
    demo.cond === "intervention"
      ? "bg-coral/10 border-coral/30 text-coral"
      : "bg-sage/15 border-sage/40 text-sage";

  return (
    <div className="card flex flex-col">
      <div className="flex flex-wrap gap-2 mb-3">
        {env && (
          <Pill className="bg-accent-soft/40 border-accent-soft text-ink">
            {ENV_LABELS[env]}
          </Pill>
        )}
        {difficulty && (
          <Pill className={pillColorForDifficulty(difficulty)}>
            {difficulty}
          </Pill>
        )}
        <Pill className={condChip}>{condLabel}</Pill>
      </div>
      <h3 className="text-lg leading-snug mb-1.5">
        <Link to={`/tasks/${demo.task_id}`} className="no-underline hover:text-accent">
          {title}
        </Link>
      </h3>
      <p className="text-xs font-mono text-muted mb-3">{demo.task_id}</p>
      <p className="text-sm text-ink/80 leading-relaxed mb-5 flex-1">
        {demo.blurb}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => playDemo(demo.task_id, demo.cond)}
          className="btn-primary"
        >
          Play now ({demo.cond})&nbsp;<span aria-hidden>→</span>
        </button>
        {demo.show_paired && (
          <button
            type="button"
            onClick={() =>
              playDemo(
                demo.task_id,
                demo.cond === "intervention" ? "clean" : "intervention",
              )
            }
            className="btn"
          >
            {demo.cond === "intervention" ? "Clean" : "Intervention"}&nbsp;
            <span aria-hidden>→</span>
          </button>
        )}
      </div>
    </div>
  );
}
