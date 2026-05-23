import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loadTasks } from "../lib/data";
import type { TaskEntry } from "../data/types";
import {
  ENV_LABELS,
  PRIMITIVE_LABELS,
  pillColorForDifficulty,
  pillColorForPrimitive,
} from "../lib/format";
import { HAS_LIVE_DEMO, LIVE_DEMO_URL, liveDemoTaskUrl } from "../lib/config";
import { FEATURED_TASK_IDS } from "../lib/featured";
import Pill from "../components/Pill";

export default function TaskDetail() {
  const { taskId } = useParams();
  const [tasks, setTasks] = useState<TaskEntry[] | null>(null);

  useEffect(() => {
    loadTasks().then(setTasks).catch(() => setTasks([]));
  }, []);

  const entry = useMemo(
    () => tasks?.find((t) => t.task_id === taskId) || null,
    [tasks, taskId],
  );

  if (!tasks) {
    return <div className="max-w-4xl mx-auto px-6 py-10 text-muted">Loading…</div>;
  }
  if (!entry) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        <h1 className="text-2xl mb-4">Task not found</h1>
        <p className="text-muted">
          No task with id <code>{taskId}</code>. Try the{" "}
          <Link to="/tasks">task explorer</Link>.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <Link to="/tasks" className="text-xs text-muted no-underline hover:text-accent">
        ← Back to task explorer
      </Link>

      <header className="mt-3 mb-6">
        <h1 className="font-serif text-3xl leading-tight">{entry.title}</h1>
        <div className="font-mono text-sm text-muted mt-2">{entry.task_id}</div>
      </header>

      <div className="flex flex-wrap gap-2 mb-6">
        <Pill className="bg-accent-soft/40 border-accent-soft text-ink">
          {ENV_LABELS[entry.env_id]}
        </Pill>
        <Pill className={pillColorForDifficulty(entry.difficulty)}>
          {entry.difficulty}
        </Pill>
        {entry.primary_primitive && (
          <Pill className={pillColorForPrimitive(entry.primary_primitive)}>
            primary: {PRIMITIVE_LABELS[entry.primary_primitive]}
          </Pill>
        )}
        {entry.human140 && (
          <Pill className="bg-sage/15 border-sage/40 text-sage">Human-140</Pill>
        )}
        {entry.duplicate_audit && (
          <Pill className="bg-navy/10 border-navy/40 text-navy">Duplicate audit</Pill>
        )}
      </div>

      {HAS_LIVE_DEMO && FEATURED_TASK_IDS.has(entry.task_id) && (
        <section className="card mb-6 bg-accent-soft/30 border-accent/40">
          <h2 className="text-sm uppercase tracking-wider text-accent mb-2">
            Try this task live
          </h2>
          <p className="text-sm text-ink/85 leading-relaxed mb-3">
            This task is in the curated demo set. One click creates a
            seeded session on the hosted FastAPI backend, opens the
            benchmark SPA in a new tab, and turns this tab into a small
            control panel with the instruction and a score button.
          </p>
          <div className="flex flex-wrap gap-2">
            <a
              href={liveDemoTaskUrl(entry.task_id, "clean")}
              target="_blank"
              rel="noreferrer"
              className="btn-primary"
            >
              Play clean&nbsp;<span aria-hidden>→</span>
            </a>
            {entry.has_intervention && (
              <a
                href={liveDemoTaskUrl(entry.task_id, "intervention")}
                target="_blank"
                rel="noreferrer"
                className="btn"
              >
                Play intervention&nbsp;<span aria-hidden>→</span>
              </a>
            )}
          </div>
        </section>
      )}

      {HAS_LIVE_DEMO && !FEATURED_TASK_IDS.has(entry.task_id) && (
        <section className="card mb-6 bg-cream border-border">
          <p className="text-sm text-ink/80 leading-relaxed">
            This task isn't in the curated{" "}
            <Link to="/demo">demo set</Link> on the hosted backend.
            To try it, either{" "}
            <Link to="/docs/setup">run WebStress locally</Link> or open
            the launcher and pick it manually:
          </p>
          <a
            href={`${LIVE_DEMO_URL}/launch?task=${encodeURIComponent(entry.task_id)}&seed=42`}
            target="_blank"
            rel="noreferrer"
            className="btn mt-3"
          >
            Open in launcher&nbsp;<span aria-hidden>→</span>
          </a>
        </section>
      )}

      <section className="card mb-6">
        <h2 className="text-sm uppercase tracking-wider text-muted mb-2">
          Public instruction
        </h2>
        <p className="text-ink/90 leading-relaxed whitespace-pre-wrap">
          {entry.public_instruction}
        </p>
        {entry.public_instruction.includes("{target.") && (
          <p className="mt-3 text-xs text-muted">
            Placeholders like <code>{`{target.x}`}</code> are resolved at run
            time from the latent ground truth and never shown to the agent or
            the human annotator — they appear here for completeness.
          </p>
        )}
      </section>

      {entry.has_intervention && (
        <section className="card mb-6">
          <h2 className="text-sm uppercase tracking-wider text-muted mb-2">
            Paired intervention
          </h2>
          <div className="text-xs text-muted mb-3 font-mono">{entry.variant_id}</div>
          {entry.target_primitive && (
            <div className="mb-3 text-sm">
              <span className="text-muted">Primary target primitive: </span>
              <Pill className={pillColorForPrimitive(entry.target_primitive)}>
                {PRIMITIVE_LABELS[entry.target_primitive]}
              </Pill>
            </div>
          )}
          {entry.intervention_layer && (
            <div className="mb-3 text-sm">
              <span className="text-muted">Injection layer: </span>
              <code>{entry.intervention_layer}</code>
            </div>
          )}
          {entry.intervention_family && (
            <div className="mb-3 text-sm">
              <span className="text-muted">Stressor family: </span>
              <code>{entry.intervention_family}</code>
            </div>
          )}
          {entry.intervention_summary_public && (
            <p className="text-ink/85 leading-relaxed mt-2">
              {entry.intervention_summary_public}
            </p>
          )}
        </section>
      )}

      <section className="card mb-6">
        <h2 className="text-sm uppercase tracking-wider text-muted mb-3">
          Budget & metadata
        </h2>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-muted">Expected steps</dt>
            <dd className="font-medium">{entry.expected_steps || "—"}</dd>
          </div>
          <div>
            <dt className="text-muted">Wall-clock budget</dt>
            <dd className="font-medium">{entry.time_limit_seconds || "—"} s</dd>
          </div>
          <div>
            <dt className="text-muted">Secondary primitives</dt>
            <dd className="font-medium">
              {entry.secondary_primitives.length
                ? entry.secondary_primitives.map((p) => PRIMITIVE_LABELS[p]).join(", ")
                : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Source</dt>
            <dd className="font-mono text-xs break-all">{entry.source_path}</dd>
          </div>
        </dl>
      </section>

      <p className="text-xs text-muted">
        Evaluator predicates (the canonical-diff positive obligations and
        negative invariants used to score this task) are intentionally hidden
        on this site — they live in the source YAML and are loaded directly by
        the evaluator at run time so agents cannot learn the target shape from
        a browse-only inspection.
      </p>
    </div>
  );
}
