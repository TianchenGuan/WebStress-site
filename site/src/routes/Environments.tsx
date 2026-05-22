import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { loadEnvironments } from "../lib/data";
import type { EnvironmentCard } from "../data/types";
import { ENV_ORDER, DIFFICULTY_ORDER } from "../lib/format";

export default function Environments() {
  const [cards, setCards] = useState<EnvironmentCard[] | null>(null);

  useEffect(() => {
    loadEnvironments().then(setCards).catch(() => setCards([]));
  }, []);

  if (!cards) return <div className="max-w-6xl mx-auto px-6 py-10 text-muted">Loading…</div>;

  const ordered = ENV_ORDER
    .map((e) => cards.find((c) => c.env_id === e))
    .filter((c): c is EnvironmentCard => Boolean(c));

  const maxTasks = Math.max(...ordered.map((c) => c.task_count), 1);

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl mb-2">The seven environments</h1>
        <p className="text-ink/75 max-w-prose">
          Each environment is a self-hosted clone of a real consumer-web
          platform: a React SPA backed by a FastAPI app with synthetic seed
          data. No production user data, payments, or live API calls.
        </p>
      </header>

      <div className="grid md:grid-cols-2 gap-5">
        {ordered.map((c) => (
          <Link
            key={c.env_id}
            to={`/environments/${c.env_id}`}
            className="card no-underline text-ink hover:border-accent transition"
          >
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="font-serif text-xl">{c.label}</h2>
              <span className="text-xs text-muted uppercase tracking-wider">
                {c.domain}
              </span>
            </div>
            <p className="text-sm text-ink/80 leading-relaxed mb-4">
              {c.description}
            </p>
            <div className="mb-3 text-sm">
              <span className="font-medium">{c.task_count}</span>{" "}
              <span className="text-muted">tasks</span>
            </div>
            <div className="space-y-1 text-xs">
              {DIFFICULTY_ORDER.map((d) => {
                const n = c.difficulty_counts[d] || 0;
                if (!n) return null;
                return (
                  <div key={d} className="flex items-center gap-2">
                    <span className="w-16 text-muted">{d}</span>
                    <div className="flex-1 bg-cream rounded h-2 overflow-hidden">
                      <div
                        className="h-2 bg-accent/60"
                        style={{ width: `${(n / maxTasks) * 100}%` }}
                      />
                    </div>
                    <span className="w-8 text-right text-muted">{n}</span>
                  </div>
                );
              })}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
