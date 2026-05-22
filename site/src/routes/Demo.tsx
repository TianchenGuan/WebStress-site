import { HAS_LIVE_DEMO, LIVE_DEMO_URL } from "../lib/config";

export default function Demo() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <h1 className="text-3xl mb-2">Live demo</h1>
      <p className="text-ink/75 max-w-prose mb-6">
        WebStress ships seven self-hosted web environments — Gmail, Amazon,
        Reddit, Robinhood, Booking, LMS, Patient Portal — and a paired
        intervention catalog. The live demo lets you pick any of the 519
        base tasks and try it yourself, in either the clean condition or
        the matched intervention condition, against a real FastAPI
        backend.
      </p>

      {HAS_LIVE_DEMO ? (
        <div className="card mb-6 bg-accent-soft/30 border-accent/40">
          <p className="text-sm text-ink/85 leading-relaxed mb-4">
            The launcher walks you through picking an environment, a task,
            and a condition. It opens two browser tabs: the benchmark tab
            (what an agent would see) and the control tab (instruction
            plus Record / Evaluate / Reset buttons).
          </p>
          <a
            href={`${LIVE_DEMO_URL}/launch`}
            target="_blank"
            rel="noreferrer"
            className="btn-primary"
          >
            Open the live launcher&nbsp;<span aria-hidden>→</span>
          </a>
        </div>
      ) : (
        <div className="card mb-6 bg-cream border-border">
          <p className="text-sm text-ink/85 leading-relaxed">
            The hosted demo is offline at the moment. You can still run
            WebStress locally — see <a href="/docs/setup">docs / setup</a>.
          </p>
        </div>
      )}

      <h2 className="text-xl mt-10 mb-3">What the demo does and doesn't do</h2>
      <ul className="text-sm text-ink/85 leading-relaxed list-disc pl-5 space-y-1.5">
        <li>
          <span className="text-sage">✓</span> Serves the seven environment
          SPAs with deterministic seeded state per session.
        </li>
        <li>
          <span className="text-sage">✓</span> Lets you record your own play
          trace via the two-tab control UI. Traces stay client-side and
          aren't uploaded.
        </li>
        <li>
          <span className="text-sage">✓</span> Exposes both <em>clean</em>{" "}
          and <em>intervention</em> conditions of every task — useful if
          you want to feel what a given stressor family is like.
        </li>
        <li>
          <span className="text-accent">✗</span> Does <em>not</em> run agent
          evaluations. Agents need the Browser-Use or BrowserGym harness
          plus a provider API key — that goes through the local repo.
        </li>
        <li>
          <span className="text-accent">✗</span> Does <em>not</em> persist
          sessions across container restarts. Each visitor gets a fresh
          seed; no PII is retained.
        </li>
      </ul>

      <h2 className="text-xl mt-10 mb-3">Responsible use</h2>
      <p className="text-sm text-ink/85 leading-relaxed">
        WebStress interventions are designed for sandbox benchmark
        environments. They should not be used to build deceptive
        interfaces or agents that exploit real users. The released
        stressor catalog (phishing-style email bodies, fabricated-success
        HTTP responses, look-alike decoys) is intended as a defensive
        evaluation harness and is bounded by the demo's local sandbox.
      </p>

      <p className="mt-10 text-xs text-muted">
        Hosting: a Docker Space on Hugging Face's free CPU-basic tier.
        Goes to sleep after ~48 h of inactivity and cold-starts (15–30 s)
        on the next visit.
      </p>
    </div>
  );
}
