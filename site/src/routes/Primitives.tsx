import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { loadPrimitives } from "../lib/data";
import type { PrimitiveCard } from "../data/types";
import { PRIMITIVE_ORDER, pillColorForPrimitive } from "../lib/format";

export default function Primitives() {
  const [cards, setCards] = useState<PrimitiveCard[] | null>(null);

  useEffect(() => {
    loadPrimitives().then(setCards).catch(() => setCards([]));
  }, []);

  if (!cards) return <div className="max-w-6xl mx-auto px-6 py-10 text-muted">Loading…</div>;

  const ordered = PRIMITIVE_ORDER
    .map((p) => cards.find((c) => c.primitive === p))
    .filter((c): c is PrimitiveCard => Boolean(c));

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl mb-2">The seven cognitive primitives</h1>
        <p className="text-ink/75 max-w-prose">
          WebStress decomposes web-agent competence into seven primitives. Each
          intervention variant declares one <strong>primary target primitive</strong>{" "}
          disjoint from the primitives the base task already exercises, so the
          paired drop estimates the agent's sensitivity to that single capability.
        </p>
      </header>

      <div className="grid md:grid-cols-2 gap-5">
        {ordered.map((c) => (
          <div key={c.primitive} className="card">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xl font-serif">
                <Link to={`/primitives/${c.primitive}`} className="no-underline text-ink hover:text-accent">
                  {c.label}
                </Link>
              </h2>
              <span className={`pill ${pillColorForPrimitive(c.primitive)}`}>
                {c.task_count} tasks · {c.intervention_count} variants
              </span>
            </div>
            <p className="text-sm text-ink/85 leading-relaxed mb-3">{c.definition}</p>
            <p className="text-xs uppercase tracking-wider text-muted mb-1">
              What it targets
            </p>
            <p className="text-sm text-ink/75 leading-relaxed mb-3">
              {c.what_it_targets}
            </p>
            <p className="text-xs uppercase tracking-wider text-muted mb-1">
              Typical stressor families
            </p>
            <p className="text-sm text-ink/75">
              {c.typical_families.map((f, i) => (
                <span key={f}>
                  <code>{f}</code>
                  {i < c.typical_families.length - 1 && ", "}
                </span>
              ))}
            </p>
            <div className="mt-4 pt-3 border-t border-border text-sm">
              <Link to={`/primitives/${c.primitive}`} className="text-accent">
                See tasks targeting {c.label.toLowerCase()} →
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
