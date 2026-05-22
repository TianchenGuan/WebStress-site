import { Link } from "react-router-dom";

export default function DocsSetup() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <Link to="/docs" className="text-xs text-muted no-underline hover:text-accent">
        ← Back to docs
      </Link>
      <h1 className="text-3xl mt-3 mb-6">Setup</h1>

      <section className="mb-8">
        <h2 className="text-lg mb-2">Prerequisites</h2>
        <ul className="text-sm text-ink/85 list-disc pl-5 space-y-1">
          <li>Python ≥ 3.10 (we use 3.11 in CI)</li>
          <li>Node ≥ 24 and <code>pnpm</code> (the env SPAs are a pnpm workspace)</li>
          <li>Chromium-based browser (Chrome / Edge / Brave); the harness uses Playwright Chromium</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-lg mb-2">Install</h2>
        <pre>{`git clone https://github.com/Arvid-pku/WebStress.git
cd WebStress

uv sync                                       # install Python deps
uv run playwright install chromium            # headless Chromium
pnpm -C webstress/environments install        # frontend deps

./scripts/webstress.sh build                  # build the 7 env SPAs (~5 min)
./scripts/webstress.sh dev                    # start backend + env dev servers`}</pre>
        <p className="text-sm text-ink/75 mt-3">
          The launcher is then served at{" "}
          <code>http://localhost:8080/launch</code>.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-lg mb-2">Run one task in dev mode</h2>
        <pre>{`./scripts/webstress.sh dev --env booking
# open http://localhost:8080/launch and pick a task.
# The launcher opens two browser tabs:
#   - a benchmark tab (what an agent sees), and
#   - a control tab (instruction, Record/Evaluate/Reset).`}</pre>
      </section>

      <section className="mb-8">
        <h2 className="text-lg mb-2">Evaluate an agent</h2>
        <pre>{`# Minimal evaluation with the BrowserGym harness
python -m webstress.agent_eval \\
    --model gpt-5.4 --provider openai \\
    --tasks gmail_star_email \\
    --seed 42

# The Browser-Use text harness used in the paper
python -m webstress.stock_browseruse_eval \\
    --model claude-opus-4-7 --provider anthropic \\
    --environments gmail amazon \\
    --seed 42`}</pre>
        <p className="text-sm text-ink/75 mt-3">
          Both write per-trajectory JSON under <code>results/</code>. The
          canonical-diff evaluator scores against the final backend state.
          Provider keys (Anthropic / OpenAI / Google) belong in your local{" "}
          <code>webstress/.env</code> — see{" "}
          <code>webstress/.env.example</code>.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-lg mb-2">Reproduce the paper sweep</h2>
        <pre>{`# 9 agents × 1,038 task-conditions each = ~9k trajectories at seed=42.
# slurm templates under scripts/sweep_templates/ adapt MODEL/PROVIDER.
LLMOS_ROOT=$PWD sbatch scripts/sweep_templates/stock_sweep.sbatch \\
    MODEL=claude-opus-4-7 PROVIDER=anthropic`}</pre>
        <p className="text-sm text-ink/75 mt-3">
          Detailed model snapshots, decoding settings, and per-model viewports
          for the vision harness are in the paper appendix.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-lg mb-2">Tests</h2>
        <pre>{`python -m pytest -q webstress/tests tests/webstress
python scripts/run_environment_tests.py`}</pre>
      </section>

      <p className="text-xs text-muted">
        If anything in this setup is out of date, the README in the repository
        is the source of truth.
      </p>
    </div>
  );
}
