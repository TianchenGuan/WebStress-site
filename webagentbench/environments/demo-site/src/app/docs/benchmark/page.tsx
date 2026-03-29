import { CodeBlock } from "@/components/docs/CodeBlock";

export default function BenchmarkDocsPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Benchmark
      </p>

      <h1 className="text-2xl font-medium tracking-tight mb-3">
        Benchmark
      </h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-12 max-w-[580px]">
        Task structure, the Gmail environment, difficulty tiers, version history, and how to run
        WebAgentBench.
      </p>

      {/* Task Structure */}
      <section className="mb-12">
        <h2 id="task-structure" className="text-lg font-medium tracking-tight mb-4">
          Task Structure
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Each task is defined as a YAML document with four top-level sections. Together they
          specify what the agent must do, what the environment looks like, and how success is
          measured.
        </p>

        <div className="flex flex-col gap-4">
          {/* metadata */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">metadata</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
                Identifies the task: <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">id</code>,{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">page</code>,{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">difficulty</code>, and the list of{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">primitives</code> the task exercises. The
                primitives list links each task to the cognitive taxonomy and is used by the results
                dashboard to break down performance by skill area.
              </p>
            </div>
          </div>

          {/* instruction */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">instruction</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                A natural-language template shown to the agent. Placeholders of the form{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">{"{{target.field}}"}</code> are
                resolved against the seed&apos;s target object at runtime. This keeps the instruction
                human-readable in the YAML while remaining parametric across fixture variations.
              </p>
              <CodeBlock code={`Find the most recent email from {{target.sender}} and reply
with the meeting time {{target.time}}.`} language="yaml" />
            </div>
          </div>

          {/* seed */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">seed</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                Drives the fixture generator. Contains three sub-sections:
              </p>
              <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
                <table className="w-full">
                  <thead>
                    <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                      <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Key</th>
                      <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Purpose</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-[var(--border)]">
                      <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">actors</td>
                      <td className="px-4 py-2.5 text-[var(--text-secondary)]">Named people with roles (e.g. target sender, distractor sender). Resolved to random names and addresses at generation time.</td>
                    </tr>
                    <tr className="border-b border-[var(--border)]">
                      <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">steps</td>
                      <td className="px-4 py-2.5 text-[var(--text-secondary)]">Ordered list of seeder operations that build the initial inbox state — compose email, label, archive, etc.</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">distractors</td>
                      <td className="px-4 py-2.5 text-[var(--text-secondary)]">Additional emails or UI elements injected to test attention and filtering. Controlled by count and similarity parameters.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* eval */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">eval</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
                Defines the scoring criteria as two lists. <strong className="font-medium text-[var(--text-primary)]">Positive checks</strong> are
                assertions that must be true for the agent to receive credit — each contributes{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">1 / total</code> to the base score.{" "}
                <strong className="font-medium text-[var(--text-primary)]">Negative checks</strong> are
                guard-rail assertions — behaviours the agent must avoid — each carrying an explicit
                penalty subtracted from the base score.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Gmail Environment */}
      <section className="mb-12">
        <h2 id="gmail-environment" className="text-lg font-medium tracking-tight mb-4">
          Gmail Environment
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          The Gmail page is a fully interactive React simulation of Gmail. It supports composing,
          replying, forwarding, labelling, archiving, starring, and searching — enough surface area
          to host tasks that span multiple cognitive primitives simultaneously.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          Unlike a simple mock, the Gmail simulation maintains a live in-memory state so the agent&apos;s
          actions have observable consequences: a sent email appears in Sent, an archived thread
          leaves the inbox, and a label persists across navigation.
        </p>

        <h3 className="text-[14px] font-medium text-[var(--text-primary)] mb-3">
          Fixture Generation Pipeline
        </h3>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Stage</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">What happens</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">1. Actor generation</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Seed actor roles are resolved to random names, email addresses, and avatar colours. The same role always maps to the same identity within a fixture so evals are deterministic.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">2. Seeder steps</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Each step in the seed is executed against an empty inbox: compose emails with templated bodies, apply labels, set read/unread state, archive threads, etc.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">3. Distractor injection</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Distractor emails are generated from the distractor spec and inserted at randomised positions in the inbox to avoid positional bias.</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">4. Target resolution</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">All <code className="font-mono text-[12px] text-[var(--text-primary)] bg-[var(--surface)] px-1 py-0.5 rounded">{"{{target.*}}"}</code> placeholders in the instruction template are resolved against the finalised fixture, producing the exact string shown to the agent.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Difficulty Tiers */}
      <section className="mb-12">
        <h2 id="difficulty-tiers" className="text-lg font-medium tracking-tight mb-4">
          Difficulty Tiers
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Tasks are grouped into four difficulty tiers based on expected step count and the number
          of cognitive primitives exercised simultaneously. The tiers are calibrated against
          human baselines, not model performance.
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Tier</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Steps</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Primitives</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Description</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Easy</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">5 – 10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Single-primitive</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Isolated skill test. Straightforward instruction, minimal distractors, short action chain.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Medium</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">10 – 20</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">2 – 3 primitives</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Requires combining skills such as memory with attention, or patience with backtracking.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Hard</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">20 – 35</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Complex reasoning</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Multi-step plans, conditional logic, and adversarial distractors designed to mislead.</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Expert</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">30 – 50</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">All primitives</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Full-coverage gauntlet. Requires near-perfect planning, resistance to distraction, and recovery from dead ends.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Version History */}
      <section className="mb-12">
        <h2 id="version-history" className="text-lg font-medium tracking-tight mb-4">
          Version History
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          WebAgentBench has gone through ten versioned releases. Major milestones are listed below;
          see <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">webagentbench/CHANGELOG.md</code> for the full per-release notes.
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Version</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Pages</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Summary</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v1</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Initial release. Core page set with basic task definitions and programmatic scoring.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v2 – v4</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Iterative scoring refinement: negative checks added in v2, trajectory modifier in v3, calibrated weights in v4.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v5</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">12</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Major redesign. Two new pages, unified YAML task format, and the actor/seed/distractor fixture pipeline.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v6 – v8</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">15</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Frontier pages targeting LLM weak spots: adversarial checkout, deep wizard form, and the Gmail environment introduced in v6.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v9</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">15</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Hardening release. Tightened eval criteria, distractor density increased, seed stability test suite added.</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">15</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Shared-runtime release. Unified indexed accessibility-tree format across simulator and real browser; all pages migrated to the shared adapter.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Running the Benchmark */}
      <section className="mb-12">
        <h2 id="running" className="text-lg font-medium tracking-tight mb-4">
          Running the Benchmark
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          WebAgentBench evaluations are driven by{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">webagentbench/agent_eval.py</code>. It
          spins up a local FastAPI server, initialises each page with a seeded fixture, then runs
          the agent against the live DOM via Playwright.
        </p>
        <CodeBlock code={`# Evaluate on all 15 pages
python -m webagentbench.agent_eval --model gpt-4o --provider openai

# Specific pages only
python -m webagentbench.agent_eval --model gpt-4o --provider openai \\
    --pages dark_checkout wizard_form gmail

# With visible browser (useful for debugging)
python -m webagentbench.agent_eval --model gpt-4o --provider openai --no-headless`} language="bash" />
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mt-5">
          Results are written to{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">results/webagentbench/results.json</code>{" "}
          and can be visualised with{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">python -m webagentbench.visualize results/webagentbench/results.json</code>.
        </p>
      </section>
    </>
  );
}
