import { useEffect, useState } from "react";
import { loadResults } from "../lib/data";
import type { ResultsSummary } from "../data/types";
import { PRIMITIVE_LABELS, PRIMITIVE_ORDER } from "../lib/format";

const HUGGINGFACE_ORG_URL = "https://huggingface.co/PrimBench";

function deltaCell(d: number): string {
  if (d <= 0) return "bg-sage/15 text-sage";
  if (d < 10) return "bg-gold/10 text-[#a8801f]";
  if (d < 20) return "bg-accent/15 text-accent";
  if (d < 30) return "bg-coral/20 text-coral";
  return "bg-coral/30 text-coral font-medium";
}

export default function Results() {
  const [data, setData] = useState<ResultsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadResults()
      .then(setData)
      .catch((e) => setError(String(e?.message ?? e)));
  }, []);

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

      {/* HuggingFace dataset CTA — always visible, even before data loads */}
      <section className="card mb-10 bg-accent-soft/30 border-accent/40">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1 min-w-[18rem]">
            <h2 className="text-sm uppercase tracking-wider text-accent mb-2">
              Raw trajectories + scored runs
            </h2>
            <p className="text-sm text-ink/85 leading-relaxed mb-3">
              The aggregated tables on this page are computed from per-trajectory
              JSON bundles released under the{" "}
              <a
                href={HUGGINGFACE_ORG_URL}
                target="_blank"
                rel="noreferrer"
                className="text-accent underline-offset-2 hover:underline"
              >
                PrimBench
              </a>{" "}
              organization on Hugging Face. Each model's full 519-clean +
              519-intervention sweep — including action traces, evaluator
              verdicts, and the rule-based failure-mode classifier output —
              ships as a Parquet dataset you can pull directly with{" "}
              <code>datasets.load_dataset</code>.
            </p>
            <a
              href={HUGGINGFACE_ORG_URL}
              target="_blank"
              rel="noreferrer"
              className="btn-primary inline-flex items-center gap-2"
            >
              <span aria-hidden>🤗</span> Browse PrimBench on Hugging Face&nbsp;
              <span aria-hidden>→</span>
            </a>
          </div>
          <div className="text-xs text-muted leading-relaxed flex-1 min-w-[16rem] max-w-[22rem]">
            <strong className="text-ink">What's there:</strong>
            <ul className="mt-1.5 space-y-0.5 list-disc pl-5">
              <li>
                <code>primbench-results-v3</code> — scored agent runs (172k
                trajectories).
              </li>
              <li>
                <code>primbench-results-v2</code> — earlier snapshot kept for
                reproducibility.
              </li>
              <li>
                Per-annotator human panels (gated; request access from the org
                page).
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Headline cards — render from JSON if loaded, static fallback otherwise */}
      <section className="grid md:grid-cols-4 gap-4 mb-10">
        <HeadlineCard
          label="Text agents"
          value={
            data
              ? `${data.headline.text_drop_range_pp[0]}–${data.headline.text_drop_range_pp[1]} pp`
              : "17.9–27.6 pp"
          }
          sub="Total drop under intervention."
        />
        <HeadlineCard
          label="Text failures"
          value={data ? `${data.headline.text_belief_failure_share_pct}%` : "75%"}
          sub="Belief failures (declared done on unmutated backend)."
        />
        <HeadlineCard
          label="Vision failures"
          value={
            data ? `${data.headline.vision_action_failure_share_pct}%` : "57%"
          }
          sub="Action failures (stuck on the action surface)."
        />
        <HeadlineCard
          label="Warm humans"
          value={data ? `${data.headline.warm_human_drop_pp} pp` : "5.7 pp"}
          sub="Pass-rate drop under the same intervention catalog."
        />
      </section>

      {error && !data && (
        <div className="card mb-8 bg-cream border-border">
          <p className="text-sm text-ink/80">
            Detailed per-(model, primitive) table couldn't load
            (<code className="text-xs">{error}</code>). Headline numbers
            shown above are static; the full per-cell breakdown lives in
            the paper and the linked Hugging Face dataset.
          </p>
        </div>
      )}

      {data && (
        <>
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
                      <th key={p} className="px-3 py-3 text-right">
                        {PRIMITIVE_LABELS[p].split(" ")[0]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.agents.map((row, i) => {
                    const isFirstVision =
                      row.harness === "vision" && data.agents[i - 1]?.harness === "text";
                    return (
                      <tr
                        key={row.model}
                        className={`border-b border-border ${isFirstVision ? "border-t-2 border-t-ink/40" : ""}`}
                      >
                        <td className="px-4 py-3 font-mono text-[12px]">{row.model}</td>
                        <td className={`px-3 py-3 text-right ${deltaCell(row.total_delta_p)}`}>
                          {row.total_iv_pass.toFixed(1)}
                          <div className="text-[10px] opacity-70">
                            ↓{row.total_delta_p.toFixed(1)}
                          </div>
                        </td>
                        {PRIMITIVE_ORDER.map((p) => {
                          const c = row.per_primitive?.[p];
                          if (!c)
                            return (
                              <td key={p} className="px-3 py-3 text-right text-muted">
                                —
                              </td>
                            );
                          return (
                            <td key={p} className={`px-3 py-3 text-right ${deltaCell(c.delta_p)}`}>
                              {c.iv_pass.toFixed(1)}
                              <div className="text-[10px] opacity-70">
                                {c.delta_p >= 0 ? "↓" : "↑"}
                                {Math.abs(c.delta_p).toFixed(1)}
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
              Rule-based classifier output over the {(
                data.failure_class_by_harness.text.n +
                data.failure_class_by_harness.vision.n
              ).toLocaleString()}{" "}
              failed intervention trajectories. Text and vision harnesses fail
              in opposite ways.
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
          {data.figures.length > 0 && (
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
          )}
        </>
      )}

      <p className="mt-8 text-xs text-muted">
        Detailed per-(env, primitive, model) numbers and the rule-based
        failure-mode classifier definition appear in the paper appendix. The
        raw trajectories backing every cell on this page are on{" "}
        <a
          href={HUGGINGFACE_ORG_URL}
          target="_blank"
          rel="noreferrer"
          className="text-accent hover:underline"
        >
          Hugging Face / PrimBench
        </a>.
      </p>
    </div>
  );
}

function HeadlineCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className="stat-num text-accent mt-1">{value}</div>
      <div className="text-sm text-ink/80 mt-2">{sub}</div>
    </div>
  );
}
