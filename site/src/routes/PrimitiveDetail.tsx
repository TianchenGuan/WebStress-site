import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loadPrimitives, loadTasks } from "../lib/data";
import type { PrimitiveCard, TaskEntry, Primitive } from "../data/types";
import {
  ENV_LABELS,
  PRIMITIVE_LABELS,
  PRIMITIVE_ORDER,
  shortenInstruction,
  pillColorForPrimitive,
  pillColorForDifficulty,
} from "../lib/format";
import Pill from "../components/Pill";

export default function PrimitiveDetail() {
  const { primitive } = useParams();
  const [cards, setCards] = useState<PrimitiveCard[] | null>(null);
  const [tasks, setTasks] = useState<TaskEntry[] | null>(null);

  useEffect(() => {
    loadPrimitives().then(setCards).catch(() => setCards([]));
    loadTasks().then(setTasks).catch(() => setTasks([]));
  }, []);

  const isValid = (p: string): p is Primitive =>
    PRIMITIVE_ORDER.includes(p as Primitive);

  const card = useMemo(() => cards?.find((c) => c.primitive === primitive) || null, [cards, primitive]);
  const relevant = useMemo(() => {
    if (!tasks || !primitive || !isValid(primitive)) return [];
    return tasks
      .filter((t) => t.target_primitive === primitive)
      .sort((a, b) => a.task_id.localeCompare(b.task_id));
  }, [tasks, primitive]);

  if (!cards || !tasks) return <div className="max-w-6xl mx-auto px-6 py-10 text-muted">Loading…</div>;
  if (!primitive || !isValid(primitive) || !card) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-10">
        <h1 className="text-2xl mb-4">Primitive not found</h1>
        <p className="text-muted">
          Choose one from <Link to="/primitives">the primitives overview</Link>.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <Link to="/primitives" className="text-xs text-muted no-underline hover:text-accent">
        ← Back to primitives overview
      </Link>

      <header className="mt-3 mb-8">
        <span className={`pill ${pillColorForPrimitive(primitive)} mb-3`}>
          {card.task_count} tasks · {card.intervention_count} variants
        </span>
        <h1 className="text-3xl mt-2">{card.label}</h1>
      </header>

      <section className="card mb-6">
        <p className="text-ink/85 leading-relaxed mb-3">{card.definition}</p>
        <p className="text-xs uppercase tracking-wider text-muted mb-1">
          What kinds of agent failures it targets
        </p>
        <p className="text-sm text-ink/75 leading-relaxed mb-3">
          {card.what_it_targets}
        </p>
        <p className="text-xs uppercase tracking-wider text-muted mb-1">
          Typical stressor families
        </p>
        <div className="flex flex-wrap gap-1.5">
          {card.typical_families.map((f) => (
            <span key={f} className="pill bg-accent-soft/40 border-accent-soft text-ink">
              {f}
            </span>
          ))}
        </div>
      </section>

      {card.example_task_id && card.example_intervention_summary && (
        <section className="card mb-6">
          <h2 className="text-sm uppercase tracking-wider text-muted mb-2">
            Example intervention
          </h2>
          <Link to={`/tasks/${card.example_task_id}`} className="font-mono text-xs">
            {card.example_task_id}
          </Link>
          <p className="text-sm text-ink/85 leading-relaxed mt-2">
            {card.example_intervention_summary}
          </p>
        </section>
      )}

      <section>
        <h2 className="text-xl mb-4">
          Tasks targeting {card.label.toLowerCase()} ({relevant.length})
        </h2>
        <div className="card p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-cream/60 text-left border-b border-border text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Task</th>
                <th className="px-4 py-3">Env</th>
                <th className="px-4 py-3">Difficulty</th>
                <th className="px-4 py-3">Family</th>
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
                  <td className="px-4 py-3 align-top text-ink/80">{ENV_LABELS[t.env_id]}</td>
                  <td className="px-4 py-3 align-top">
                    <Pill className={pillColorForDifficulty(t.difficulty)}>
                      {t.difficulty}
                    </Pill>
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
