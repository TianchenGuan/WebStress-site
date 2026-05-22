import { Link } from "react-router-dom";

const DOC_LINKS: { to: string; label: string; description: string }[] = [
  { to: "/docs/setup", label: "Setup", description: "Install Python + Node deps, build the seven SPAs, launch the backend." },
];

const EXTERNAL_LINKS: { href: string; label: string; description: string }[] = [
  { href: "https://github.com/Arvid-pku/WebStress#readme", label: "README", description: "Top-level repo overview, quickstart, repo layout." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/webstress/README.md", label: "Benchmark internals", description: "FastAPI app layout, environment SPAs, controller endpoints, evaluator." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/docs/guides/task-design.md", label: "Task design guide", description: "How to design a new base task, instruction grammar, seed builders." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/docs/guides/environment-design.md", label: "Environment design guide", description: "How to build a new self-hosted environment SPA + backend." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/docs/guides/canonical-diff-authoring-protocol.md", label: "Canonical-diff scoring", description: "How tasks are graded against backend state (positive obligations + negative invariants)." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/docs/guides/eval-hardening-playbook.md", label: "Eval hardening playbook", description: "Predicate idioms for writing robust evaluator rules." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/docs/guides/degradation-design.md", label: "Intervention design", description: "How interventions compose across the four injection layers." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/webstress/human/GUIDELINES.md", label: "Human study protocol", description: "Recording instrument, trace cleaning rules, post-task rating rubric." },
  { href: "https://github.com/Arvid-pku/WebStress/blob/main/webstress/docs/RUNNING_SWEEPS.md", label: "Running paper-grade sweeps", description: "Browser-Use harness, slurm templates, per-model viewports." },
];

export default function Docs() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl mb-2">Documentation</h1>
        <p className="text-ink/75 max-w-prose">
          WebStress documentation is maintained alongside the source code on
          GitHub. The site mirrors a small subset of it; deeper references
          (canonical-diff protocol, human protocol, sweep recipes) live in the
          repo so they stay in lock-step with the runtime.
        </p>
      </header>

      <section className="mb-10">
        <h2 className="text-xl mb-3">On this site</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {DOC_LINKS.map((d) => (
            <Link key={d.to} to={d.to} className="card no-underline text-ink hover:border-accent transition">
              <h3 className="text-lg font-serif mb-1">{d.label}</h3>
              <p className="text-sm text-ink/75">{d.description}</p>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl mb-3">In the repository</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {EXTERNAL_LINKS.map((d) => (
            <a
              key={d.href}
              href={d.href}
              target="_blank"
              rel="noreferrer"
              className="card no-underline text-ink hover:border-accent transition"
            >
              <h3 className="text-lg font-serif mb-1">
                {d.label} <span className="text-xs text-muted">↗</span>
              </h3>
              <p className="text-sm text-ink/75">{d.description}</p>
            </a>
          ))}
        </div>
      </section>

      <section className="mt-10 card">
        <h2 className="text-sm uppercase tracking-wider text-muted mb-2">
          Responsible use
        </h2>
        <p className="text-sm text-ink/85 leading-relaxed">
          WebStress interventions are designed for sandbox benchmark
          environments. They should not be used to build deceptive interfaces
          or agents that exploit real users. The released stressor catalog
          (phishing-style email bodies, fabricated-success HTTP responses,
          look-alike decoys) is bounded by the local sandbox and reflects
          publicly-known failure patterns; the assets are intended as a
          defensive evaluation harness and not as templates for live-traffic
          attacks. See the paper's Caveats section for the full list.
        </p>
      </section>
    </div>
  );
}
