import { useEffect, useState } from "react";
import { loadResults } from "../lib/data";
import type { ResultsSummary } from "../data/types";
import { PRIMITIVE_LABELS, PRIMITIVE_ORDER } from "../lib/format";

function deltaCell(d: number): string {
  if (d <= 0) return "bg-sage/15 text-sage";
  if (d < 10) return "bg-gold/10 text-[#a8801f]";
  if (d < 20) return "bg-accent/15 text-accent";
  if (d < 30) return "bg-coral/20 text-coral";
  return "bg-coral/30 text-coral font-medium";
}

export default function Results() {
  const [data, setData] = useState<ResultsSummary | null>(null);

  useEffect(() => {
    loadResults().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return <div className="max-w-6xl mx-auto px-6 py-10 text-muted">Loading…</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl mb-2">Results</h1>
        <p className="text-ink/75 max-w-prose">
          Headline numbers from the paper sweep: six Browser-Use text agents and
          three BrowserGym vision-based agents, evaluated on the full
          519-clean + 519-intervention pair set at seed 42. The paired drop
          estimates sensitivity to each primitive; cell shading scales with the
          drop magnitude in percentage points.
        </p>
      </header>

      {/* Headline cards */}
      <section className="grid md:grid-cols-4 gap-4 mb-10">
        <div className="card">
          <div className="text-xs uppercase tracking-wider text-muted">Text agents</div>
          <div className="stat-num text-accent mt-1">
            {data.headline.text_drop_range_pp[0]}–{data.headline.text_drop_range_pp[1]} pp
          </div>
          <div className="text-sm text-ink/80 mt-2">Total drop under intervention.</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase tracking-wider text-muted">Text failures</div>
          <div className="stat-num text-accent mt-1">
            {data.headline.text_belief_failure_share_pct}%
          </div>
          <div className="text-sm text-ink/80 mt-2">Belief failures (declared done on unmutated backend).</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase tracking-wider text-muted">Vision failures</div>
          <div className="stat-num text-accent mt-1">
            {data.headline.vision_action_failure_share_pct}%
          </div>
          <div className="text-sm text-ink/80 mt-2">Action failures (stuck on the action surface).</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase tracking-wider text-muted">Warm humans</div>
          <div className="stat-num text-accent mt-1">
            {data.headline.warm_human_drop_pp} pp
          </div>
          <div className="text-sm text-ink/80 mt-2">Pass-rate drop under the same intervention catalog.</div>
        </div>
      </section>

      {/* Per-(model, primitive) heatmap-style table */}
      <section className="mb-10">
        <h2 className="text-xl mb-3">Per-(model, primitive) intervention pass rate</h2>
        <p className="text-sm text-muted mb-3 max-w-prose">
          Each cell is the intervention pass rate (top, %) and the matched
          paired drop in pass rate (bottom, ↓ pp). Cell shading encodes the
          paired drop magnitude.
        </p>
        <div className="card p-0 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-cream/60 text-left border-b border-border uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Model</th>
                <th className="px-3 py-3 text-right">Total iv</th>
                {PRIMITIVE_ORDER.map((p) => (
                  <th key={p} className="px-3 py-3 text-right">{PRIMITIVE_LABELS[p].split(" ")[0]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.agents.map((row, i) => {
                const isFirstVision = row.harness === "vision" && data.agents[i - 1]?.harness === "text";
                return (
                  <tr key={row.model} className={`border-b border-border ${isFirstVision ? "border-t-2 border-t-ink/40" : ""}`}>
                    <td className="px-4 py-3 font-mono text-[12px]">{row.model}</td>
                    <td className={`px-3 py-3 text-right ${deltaCell(row.total_delta_p)}`}>
                      {row.total_iv_pass.toFixed(1)}
                      <div className="text-[10px] opacity-70">↓{row.total_delta_p.toFixed(1)}</div>
                    </td>
                    {PRIMITIVE_ORDER.map((p) => {
                      const c = row.per_primitive?.[p];
                      if (!c) return <td key={p} className="px-3 py-3 text-right text-muted">—</td>;
                      return (
                        <td key={p} className={`px-3 py-3 text-right ${deltaCell(c.delta_p)}`}>
                          {c.iv_pass.toFixed(1)}
                          <div className="text-[10px] opacity-70">
                            {c.delta_p >= 0 ? "↓" : "↑"}{Math.abs(c.delta_p).toFixed(1)}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Failure class */}
      <section className="mb-10">
        <h2 className="text-xl mb-3">Failure class by harness</h2>
        <p className="text-sm text-muted mb-3 max-w-prose">
          Rule-based classifier output over the 3,037 failed intervention
          trajectories. Text and vision harnesses fail in opposite ways.
        </p>
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="bg-cream/60 text-left border-b border-border text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Harness</th>
                <th className="px-4 py-3 text-right">n</th>
                <th className="px-4 py-3 text-right">Belief</th>
                <th className="px-4 py-3 text-right">Action</th>
                <th className="px-4 py-3 text-right">Overreach</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["text", data.failure_class_by_harness.text],
                  ["vision", data.failure_class_by_harness.vision],
                ] as const
              ).map(([name, row]) => (
                <tr key={name} className="border-b border-border last:border-b-0">
                  <td className="px-4 py-3 capitalize">{name}</td>
                  <td className="px-4 py-3 text-right text-muted">{row.n}</td>
                  <td className="px-4 py-3 text-right">{row.belief_pct}%</td>
                  <td className="px-4 py-3 text-right">{row.action_pct}%</td>
                  <td className="px-4 py-3 text-right">{row.overreach_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Paper figures */}
      <section>
        <h2 className="text-xl mb-3">From the paper</h2>
        <div className="space-y-6">
          {data.figures.map((f) => (
            <figure key={f.src} className="card">
              <img
                src={f.src}
                alt={f.caption}
                className="w-full h-auto rounded border border-border"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
              <figcaption className="text-sm text-ink/75 mt-3 leading-relaxed">
                {f.caption}
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <p className="mt-8 text-xs text-muted">
        Detailed per-(env, primitive, model) numbers and the rule-based
        failure-mode classifier definition appear in the paper appendix; this
        page summarizes the headline tables only.
      </p>
    </div>
  );
}
