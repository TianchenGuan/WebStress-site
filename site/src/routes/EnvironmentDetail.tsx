import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loadEnvironments, loadTasks } from "../lib/data";
import type { EnvironmentCard, TaskEntry, Environment } from "../data/types";
import {
  DIFFICULTY_ORDER,
  ENV_LABELS,
  ENV_ORDER,
  PRIMITIVE_LABELS,
  PRIMITIVE_ORDER,
  pillColorForDifficulty,
  pillColorForPrimitive,
  shortenInstruction,
} from "../lib/format";
import Pill from "../components/Pill";

export default function EnvironmentDetail() {
  const { env } = useParams();
  const [cards, setCards] = useState<EnvironmentCard[] | null>(null);
  const [tasks, setTasks] = useState<TaskEntry[] | null>(null);

  useEffect(() => {
    loadEnvironments().then(setCards).catch(() => setCards([]));
    loadTasks().then(setTasks).catch(() => setTasks([]));
  }, []);

  const isValid = (e: string): e is Environment =>
    ENV_ORDER.includes(e as Environment);

  const card = useMemo(() => cards?.find((c) => c.env_id === env) || null, [cards, env]);
  const relevant = useMemo(() => {
    if (!tasks || !env || !isValid(env)) return [];
    return tasks
      .filter((t) => t.env_id === env)
      .sort((a, b) => a.task_id.localeCompare(b.task_id));
  }, [tasks, env]);

  if (!cards || !tasks) return <div className="max-w-6xl mx-auto px-6 py-10 text-muted">Loading…</div>;
  if (!env || !isValid(env) || !card) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-10">
        <h1 className="text-2xl mb-4">Environment not found</h1>
        <p className="text-muted">
          Choose one from <Link to="/environments">the environments overview</Link>.
        </p>
      </div>
    );
  }

  const totalPrim = Object.values(card.primitive_counts).reduce((a, b) => a + (b || 0), 0);

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <Link to="/environments" className="text-xs text-muted no-underline hover:text-accent">
        ← Back to environments
      </Link>

      <header className="mt-3 mb-8">
        <h1 className="text-3xl font-serif">{card.label}</h1>
        <p className="text-xs uppercase tracking-wider text-muted mt-1">{card.domain}</p>
        <p className="text-ink/80 mt-4 leading-relaxed max-w-prose">{card.description}</p>
      </header>

      <section className="grid md:grid-cols-2 gap-5 mb-8">
        <div className="card">
          <h2 className="text-sm uppercase tracking-wider text-muted mb-3">
            Difficulty distribution
          </h2>
          <div className="space-y-2">
            {DIFFICULTY_ORDER.map((d) => {
              const n = card.difficulty_counts[d] || 0;
              const pct = card.task_count ? (n / card.task_count) * 100 : 0;
              return (
                <div key={d} className="flex items-center gap-2 text-sm">
                  <span className="w-20 capitalize text-ink/80">{d}</span>
                  <div className="flex-1 bg-cream rounded h-2.5 overflow-hidden">
                    <div className="h-2.5 bg-accent/70" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-8 text-right text-muted">{n}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="card">
          <h2 className="text-sm uppercase tracking-wider text-muted mb-3">
            Primary primitive mix
          </h2>
          <div className="space-y-2">
            {PRIMITIVE_ORDER.map((p) => {
              const n = card.primitive_counts[p] || 0;
              if (!n) return null;
              const pct = totalPrim ? (n / totalPrim) * 100 : 0;
              return (
                <div key={p} className="flex items-center gap-2 text-sm">
                  <span className="w-32 text-ink/80">{PRIMITIVE_LABELS[p]}</span>
                  <div className="flex-1 bg-cream rounded h-2.5 overflow-hidden">
                    <div className="h-2.5 bg-coral/70" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-8 text-right text-muted">{n}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-xl mb-4">All {ENV_LABELS[env]} tasks ({relevant.length})</h2>
        <div className="card p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-cream/60 text-left border-b border-border text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Task</th>
                <th className="px-4 py-3">Difficulty</th>
                <th className="px-4 py-3">Primary primitive</th>
                <th className="px-4 py-3">Intervention family</th>
              </tr>
            </thead>
            <tbody>
              {relevant.map((t) => (
                <tr key={t.task_id} className="border-b border-border last:border-b-0 hover:bg-cream/40">
                  <td className="px-4 py-3 align-top">
                    <Link to={`/tasks/${t.task_id}`} className="font-mono text-xs text-ink no-underline hover:text-accent">
                      {t.task_id}
                    </Link>
                    <div className="text-[13px] text-ink/70 mt-1 max-w-xl">
                      {shortenInstruction(t.public_instruction, 140)}
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <Pill className={pillColorForDifficulty(t.difficulty)}>{t.difficulty}</Pill>
                  </td>
                  <td className="px-4 py-3 align-top">
                    {t.primary_primitive ? (
                      <Pill className={pillColorForPrimitive(t.primary_primitive)}>
                        {PRIMITIVE_LABELS[t.primary_primitive]}
                      </Pill>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3 align-top text-ink/80">
                    {t.intervention_family || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
