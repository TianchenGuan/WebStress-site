import { Link } from "react-router-dom";
import { HAS_LIVE_DEMO, LIVE_DEMO_URL } from "../lib/config";

const STATS: { value: string; label: string; sub?: string }[] = [
  { value: "519", label: "Paired tasks", sub: "clean + intervention" },
  { value: "7", label: "Environments", sub: "self-hosted web apps" },
  { value: "7", label: "Cognitive primitives" },
  { value: "519", label: "Intervention variants", sub: "1 per base task" },
  { value: "6 / 3", label: "Text / vision agents" },
  { value: "Human-140", label: "Human panel", sub: "cold + warm" },
];

const KEY_RESULTS: { headline: string; detail: string }[] = [
  {
    headline: "Text agents lose 18–28 pp under intervention.",
    detail: "Every text-mode agent drops between 17.9 and 27.6 percentage points on the paired intervention condition. Backtracking and verification are the most-affected primitives across model families.",
  },
  {
    headline: "Text failures are mostly belief failures.",
    detail: "75% of failed text-mode runs end with the agent declaring done on a task whose external state never reached the goal — a fabricated-success toast over a silently dropped write is the dominant failure pattern.",
  },
  {
    headline: "Vision failures are more action failures.",
    detail: "Vision-only agents invert the picture: 57% of failures are action failures (the agent gets stuck retrying the action surface) and overreach drops below 1%, because the agent rarely reaches the point where positive criteria pass at all.",
  },
  {
    headline: "Warm humans lose only 5.7 pp.",
    detail: "Warm human references on the same intervention catalog drop from 80.7% to 75.0% pass rate — a 3–5× smaller drop than text agents, and roughly 10× smaller than vision agents.",
  },
];

export default function Home() {
  return (
    <div>
      {/* Hero */}
      <section className="border-b border-border">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <p className="text-xs uppercase tracking-widest text-accent mb-4">
            NeurIPS 2026 submission · under review
          </p>
          <h1 className="text-4xl md:text-5xl leading-tight max-w-4xl">
            Diagnosing web-agent failures with{" "}
            <span className="text-accent">matched clean / intervention tasks</span>.
          </h1>
          <p className="mt-6 max-w-prose text-lg text-ink/80 leading-relaxed">
            WebStress runs each task twice: once in a clean environment and once
            with a controlled intervention that targets one primary cognitive
            primitive. The paired drop between the two runs estimates how
            sensitive an agent is to that primitive, while the rest of the
            instruction, environment, and scoring rule are held fixed.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a className="btn-primary" href="#paper">Paper</a>
            <a className="btn" href="https://github.com/Arvid-pku/WebStress" target="_blank" rel="noreferrer">Code</a>
            <Link className="btn" to="/tasks">Explore Tasks</Link>
            {HAS_LIVE_DEMO && (
              <a className="btn" href={`${LIVE_DEMO_URL}/launch`} target="_blank" rel="noreferrer">
                Try the live demo&nbsp;<span aria-hidden>→</span>
              </a>
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

      {/* What it does */}
      <section className="max-w-6xl mx-auto px-6 py-14">
        <h2 className="text-2xl mb-4">Why paired clean / intervention?</h2>
        <p className="text-ink/85 max-w-prose leading-relaxed">
          An end-to-end task score tells you that a 15-step booking failed; it
          doesn't tell you whether the agent misread the page, lost a sub-goal,
          or trusted a fake confirmation. Holding the base task fixed and
          varying one stressor at a time turns <em>"agent A scores 40%"</em>{" "}
          into <em>"agent A loses 27 pp on backtracking and 18 pp on verification,
          almost nothing on planning."</em> That is the signal a developer or
          trainer needs to know which capability to fix.
        </p>
        <p className="text-ink/85 max-w-prose leading-relaxed mt-4">
          Runs are graded against live backend state, not the rendered DOM, so a
          forged "Saved" toast over a silently dropped write counts as a failure.
        </p>
      </section>

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
            Beyond Task Success: Probing Cognitive Primitives in Web Agents
          </p>
          <p className="text-sm text-muted mt-1">Anonymous submission to NeurIPS 2026 · under review</p>
          <p className="text-sm text-ink/75 mt-3 leading-relaxed">
            Cognitive primitives such as planning, exploration, and backtracking
            are widely regarded as core to competent web agents. WebStress casts
            capability evaluation as a controlled comparison: each task is
            paired with a targeted intervention, and the paired drop estimates
            sensitivity to one primary target primitive.
          </p>
          <p className="mt-4 text-sm text-muted">
            Citation: anonymous until decision. License: TBD pending de-anonymisation.
          </p>
        </div>
      </section>
    </div>
  );
}
