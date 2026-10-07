import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { HAS_LIVE_DEMO } from "../lib/config";
import { HOMEPAGE_FEATURED } from "../lib/featured";
import { loadResults, loadTasks } from "../lib/data";
import type { AgentRow, ResultsSummary, TaskEntry } from "../data/types";
import { ENV_LABELS, pillColorForDifficulty } from "../lib/format";
import { playDemo } from "../lib/config";
import Pill from "../components/Pill";

const ARXIV_URL = "https://arxiv.org/abs/2609.35814";
const ARXIV_BIBTEX_URL = "https://arxiv.org/bibtex/2609.35814";
const GITHUB_URL = "https://github.com/Arvid-pku/BreakingWeb";

const STATS: { value: string; label: string; sub?: string }[] = [
  { value: "519", label: "Paired tasks", sub: "clean + intervention" },
  { value: "7", label: "Environments", sub: "self-hosted web apps" },
  { value: "29", label: "Intervention families" },
  { value: "7", label: "Cognitive primitives", sub: "primary recovery demand" },
  { value: "6 / 3", label: "Text / vision agents" },
  { value: "Human-140", label: "Human panel", sub: "cold + warm" },
];

const KEY_RESULTS: { headline: string; detail: string }[] = [
  {
    headline: "Text agents lose 18–28 pp under intervention.",
    detail: "Every text-mode agent drops between 17.9 and 27.6 percentage points in pass rate on the intervention condition. Backtracking and verification interventions cost the most across model families.",
  },
  {
    headline: "Most text failures are belief failures.",
    detail: "75% of classified text-mode intervention failures end with the agent declaring success although the required goal state was not reached.",
  },
  {
    headline: "Vision failures are action failures.",
    detail: "For screenshot-only agents, 57% of classified intervention failures are action failures: the agent gets stuck on the action surface before any success criterion is met.",
  },
  {
    headline: "Warm humans lose 5.7 pp.",
    detail: "On Human-140, warm human pass rate decreases from 80.7% to 75.0%, a drop of 5.7 percentage points.",
  },
];

export default function Home() {
  const [tasks, setTasks] = useState<TaskEntry[] | null>(null);
  const [results, setResults] = useState<ResultsSummary | null>(null);
  useEffect(() => {
    loadTasks().then(setTasks).catch(() => setTasks([]));
    loadResults().then(setResults).catch(() => setResults(null));
  }, []);
  const featuredEntries = useMemo(() => {
    if (!tasks) return [];
    const byId = new Map(tasks.map((t) => [t.task_id, t]));
    return HOMEPAGE_FEATURED.map((d) => ({ demo: d, entry: byId.get(d.task_id) || null }));
  }, [tasks]);
  const leaderboard = useMemo<AgentRow[]>(() => {
    if (!results) return [];
    return [...results.agents].sort((a, b) => b.total_iv_pass - a.total_iv_pass);
  }, [results]);

  return (
    <div>
      {/* Hero */}
      <section className="border-b border-border">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <p className="text-xs uppercase tracking-widest text-accent mb-4">
            arXiv:2609.35814 · 2026
          </p>
          <h1 className="text-4xl md:text-5xl leading-tight max-w-4xl">
            Constructing challenging browser-use tasks by{" "}
            <span className="text-accent">controlled environment interventions</span>.
          </h1>
          <p className="mt-6 max-w-prose text-lg text-ink/80 leading-relaxed">
            BreakingWeb runs each task twice: once in a clean self-hosted web
            app and once with a controlled, recoverable intervention, while the
            instruction, environment, and scoring rule are held fixed. The paired performance drop measures the cost of the intervention. Primitive labels describe the primary recovery demand; recovery may involve multiple capabilities.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a className="btn-primary" href={ARXIV_URL} target="_blank" rel="noreferrer">Paper</a>
            <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer">Code</a>
            <Link className="btn" to="/tasks">Explore Tasks</Link>
            {HAS_LIVE_DEMO && (
              <Link className="btn" to="/demo">
                Play featured demos&nbsp;<span aria-hidden>→</span>
              </Link>
            )}
            <Link className="btn" to="/results">View Results</Link>
            <Link className="btn" to="/docs">Documentation</Link>
          </div>
        </div>
      </section>

      {/* Stat strip */}
      <section className="border-b border-border bg-white">
        <div className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-2 md:grid-cols-6 gap-6">
          {STATS.map((s) => (
            <div key={s.label}>
              <div className="stat-num text-accent">{s.value}</div>
              <div className="text-sm font-medium text-ink mt-1">{s.label}</div>
              {s.sub && <div className="text-xs text-muted">{s.sub}</div>}
            </div>
          ))}
        </div>
      </section>

      {/* Leaderboard */}
      {leaderboard.length > 0 && (
        <section className="max-w-6xl mx-auto px-6 py-14">
          <div className="flex items-baseline justify-between flex-wrap gap-2 mb-3">
            <h2 className="text-2xl">Leaderboard</h2>
            <Link to="/results" className="text-sm text-accent no-underline hover:underline">
              Per-primitive breakdown&nbsp;→
            </Link>
          </div>
          <p className="text-sm text-muted mb-4 max-w-prose">
            Pass rate on the full 519-pair set at seed 42, sorted by intervention
            pass rate. Runs are graded against the live backend state, so a forged
            "Saved" toast over a silently dropped write counts as a failure.
          </p>
          <div className="card p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-cream/60 text-left border-b border-border text-xs uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-4 py-3">#</th>
                  <th className="px-4 py-3">Agent</th>
                  <th className="px-4 py-3">Observation</th>
                  <th className="px-4 py-3 text-right">Clean pass %</th>
                  <th className="px-4 py-3 text-right">Intervention pass %</th>
                  <th className="px-4 py-3 text-right">Drop (pp)</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((row, i) => (
                  <tr key={row.model} className="border-b border-border last:border-b-0">
                    <td className="px-4 py-3 text-muted">{i + 1}</td>
                    <td className="px-4 py-3 font-mono text-[13px]">{row.model.replace(/^v-/, "")}</td>
                    <td className="px-4 py-3">
                      <Pill className={row.harness === "text" ? "bg-accent-soft/40 border-accent-soft text-ink" : "bg-navy/10 border-navy/30 text-navy"}>
                        {row.harness === "text" ? "text (a11y tree)" : "vision (screenshots)"}
                      </Pill>
                    </td>
                    <td className="px-4 py-3 text-right">{row.total_clean_pass.toFixed(1)}</td>
                    <td className="px-4 py-3 text-right font-medium">{row.total_iv_pass.toFixed(1)}</td>
                    <td className="px-4 py-3 text-right text-accent">↓{row.total_delta_p.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Featured demos */}
      {HAS_LIVE_DEMO && featuredEntries.length > 0 && (
        <section className="bg-cream/40 border-y border-border">
          <div className="max-w-6xl mx-auto px-6 py-14">
            <div className="flex items-baseline justify-between flex-wrap gap-2 mb-6">
              <h2 className="text-2xl">Featured demos</h2>
              <Link to="/demo" className="text-sm text-accent no-underline hover:underline">
                See all featured&nbsp;→
              </Link>
            </div>
            <p className="text-ink/75 max-w-prose mb-6 text-sm leading-relaxed">
              One click launches the task on the hosted backend.
            </p>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
              {featuredEntries.map(({ demo, entry }) => (
                <div key={demo.task_id} className="card flex flex-col">
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {entry?.env_id && (
                      <Pill className="bg-accent-soft/40 border-accent-soft text-ink">
                        {ENV_LABELS[entry.env_id]}
                      </Pill>
                    )}
                    {entry?.difficulty && (
                      <Pill className={pillColorForDifficulty(entry.difficulty)}>
                        {entry.difficulty}
                      </Pill>
                    )}
                  </div>
                  <h3 className="text-base leading-snug mb-2">
                    <Link
                      to={`/tasks/${demo.task_id}`}
                      className="no-underline hover:text-accent"
                    >
                      {entry?.title ?? demo.task_id}
                    </Link>
                  </h3>
                  <p className="text-sm text-ink/75 leading-relaxed flex-1 mb-4">
                    {demo.blurb}
                  </p>
                  <button
                    type="button"
                    onClick={() => playDemo(demo.task_id, demo.cond)}
                    className="btn-primary text-sm self-start"
                  >
                    Play&nbsp;<span aria-hidden>→</span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Key results */}
      <section className="bg-white border-y border-border">
        <div className="max-w-6xl mx-auto px-6 py-14">
          <h2 className="text-2xl mb-8">Key findings</h2>
          <div className="grid md:grid-cols-2 gap-5">
            {KEY_RESULTS.map((r) => (
              <div key={r.headline} className="card">
                <h3 className="text-lg mb-2 leading-snug">{r.headline}</h3>
                <p className="text-sm text-ink/75 leading-relaxed">{r.detail}</p>
              </div>
            ))}
          </div>
          <p className="mt-6 text-sm text-muted">
            Full per-(model, primitive) breakdown on the{" "}
            <Link to="/results">results page</Link>; per-primitive deep dive on{" "}
            <Link to="/primitives">primitives</Link>.
          </p>
        </div>
      </section>

      {/* Paper card */}
      <section id="paper" className="max-w-6xl mx-auto px-6 py-14">
        <h2 className="text-2xl mb-4">Read the paper</h2>
        <div className="card max-w-3xl">
          <p className="text-base font-medium">
            <a href={ARXIV_URL} target="_blank" rel="noreferrer" className="no-underline hover:text-accent">
              Constructing Challenging Browser-Use Tasks by Controlled Environment Interventions
            </a>
          </p>
          <p className="text-sm text-muted mt-1">Xunjian Yin et al. · arXiv:2609.35814 · 2026</p>
          <p className="text-sm text-ink/75 mt-3 leading-relaxed">
            BreakingWeb constructs challenging browser-use tasks by applying
            controlled, recoverable interventions to self-hosted web environments.
            Each clean/intervention pair preserves the user instruction, latent
            target, and backend success criterion. The paired performance drop measures the cost of the intervention. Primitive labels describe the primary recovery demand; recovery may involve multiple capabilities.
          </p>
          <p className="mt-4 text-sm">
            <a href={ARXIV_URL} target="_blank" rel="noreferrer" className="text-accent hover:underline">arXiv</a>
            <span className="mx-2 text-muted">·</span>
            <a href={ARXIV_BIBTEX_URL} target="_blank" rel="noreferrer" className="text-accent hover:underline">BibTeX</a>
            <span className="mx-2 text-muted">·</span>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="text-accent hover:underline">Code</a>
          </p>
        </div>
      </section>
    </div>
  );
}
