import { CodeBlock } from "@/components/docs/CodeBlock";

export default function TrainingDocsPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Training Pipeline
      </p>

      <h1 className="text-2xl font-medium tracking-tight mb-3">
        Training Pipeline
      </h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-12 max-w-[580px]">
        How LLMOS fine-tunes web agents using trajectories collected from the simulator and the
        real benchmark browser — from raw episodes to a deployed model.
      </p>

      {/* Overview */}
      <section className="mb-12">
        <h2 id="overview" className="text-lg font-medium tracking-tight mb-4">
          Overview
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          The pipeline runs in three sequential stages, each building on the outputs of the last:
        </p>
        <ol className="list-decimal list-inside space-y-2 text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          <li>
            <span className="font-medium text-[var(--text-primary)]">Data Collection</span> —
            gather and filter trajectories from the LLMOS simulator and live WebAgentBench browser
            runs, then export them as conversation-format JSONL.
          </li>
          <li>
            <span className="font-medium text-[var(--text-primary)]">SFT (Supervised Fine-Tuning)</span> —
            train the base model on successful trajectories using next-token prediction on the
            assistant turns only.
          </li>
          <li>
            <span className="font-medium text-[var(--text-primary)]">DPO (Direct Preference Optimisation)</span> —
            fine-tune further using paired trajectories (good vs. bad) to push the model toward
            higher-scoring behaviours without a separate reward model.
          </li>
        </ol>
      </section>

      {/* Data Collection */}
      <section className="mb-12">
        <h2 id="data-collection" className="text-lg font-medium tracking-tight mb-4">
          Data Collection
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Training data comes from two complementary sources:
        </p>
        <ul className="list-disc list-inside space-y-2 text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          <li>
            <span className="font-medium text-[var(--text-primary)]">LLMOS Simulator</span> —
            the LLM-based UI simulator generates large volumes of synthetic trajectories cheaply.
            The collector analyses WebAgentBench failure reports to target the exact task types
            where the agent currently struggles.
          </li>
          <li>
            <span className="font-medium text-[var(--text-primary)]">WebAgentBench browser runs</span> —
            real Playwright episodes against the 15-page benchmark produce ground-truth trajectories
            with accurate scores, providing a higher-fidelity signal for the most important tasks.
          </li>
        </ul>
        <CodeBlock code={`# Collect from simulator (analyzes WAB failures)
python -m llmos collect --wab-results results/webagentbench/baseline.json \\
    --episodes 20 --output training/data/raw_episodes.jsonl

# Prepare training data
python training/prepare_data.py --llmos-dir llmos/runs/ \\
    --min-score 0.0 --output training/data/train.jsonl`} language="bash" />
      </section>

      {/* SFT Stage */}
      <section className="mb-12">
        <h2 id="sft" className="text-lg font-medium tracking-tight mb-4">
          SFT Stage
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Supervised fine-tuning trains the model to imitate successful trajectories. Each episode
          is serialised as a multi-turn conversation in OpenAI message format: system prompt,
          then alternating user (observation) and assistant (action) turns. Loss is computed on
          the assistant turns only, so the model learns to produce well-formed actions given the
          accessibility-tree observation.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Training runs on Qwen models via the Tinker cloud GPU API, which allocates on-demand
          A100 capacity and exposes an OpenAI-compatible endpoint for inference once the job
          completes.
        </p>
        <CodeBlock code={`# SFT on Qwen via Tinker API
python training/train_sft.py --data training/data/train.jsonl \\
    --model Qwen/Qwen3-30B-A3B`} language="bash" />
      </section>

      {/* DPO Stage */}
      <section className="mb-12">
        <h2 id="dpo" className="text-lg font-medium tracking-tight mb-4">
          DPO Stage
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Direct Preference Optimisation refines the SFT checkpoint using pairs of trajectories
          on the same task — one higher-scoring (chosen) and one lower-scoring (rejected). The
          model learns to prefer the chosen trajectory without needing a separate reward model,
          making DPO significantly cheaper than RLHF while still improving alignment with the
          benchmark scoring signal.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Pairs are generated automatically by <span className="font-mono text-[13px]">prepare_dpo.py</span>,
          which groups episodes by task, sorts by score, and produces (high, low) pairs from the
          collected runs.
        </p>
        <CodeBlock code={`# Prepare DPO pairs
python training/prepare_dpo.py ...

# DPO training
python training/train_dpo.py ...`} language="bash" />
      </section>

      {/* Tinker API */}
      <section className="mb-12">
        <h2 id="tinker" className="text-lg font-medium tracking-tight mb-4">
          Tinker API
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          All GPU-intensive training and inference runs through the Tinker cloud GPU API. Tinker
          provides three capabilities used by the pipeline:
        </p>
        <ul className="list-disc list-inside space-y-2 text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          <li>
            <span className="font-medium text-[var(--text-primary)]">On-demand GPU allocation</span> —
            A100 nodes are spun up only for the duration of a training job, keeping costs
            proportional to compute actually used.
          </li>
          <li>
            <span className="font-medium text-[var(--text-primary)]">OpenAI-compatible inference</span> —
            after a training job completes, the resulting checkpoint is automatically deployed
            behind an endpoint that speaks the OpenAI Chat Completions API, so the existing
            agent code requires no changes to call the fine-tuned model.
          </li>
          <li>
            <span className="font-medium text-[var(--text-primary)]">Model registry</span> —
            trained checkpoints are versioned in Tinker&apos;s model registry, making it easy to
            roll back to a previous checkpoint or run A/B evaluations between versions.
          </li>
        </ul>
      </section>

      {/* Model Targets */}
      <section className="mb-12">
        <h2 id="models" className="text-lg font-medium tracking-tight mb-4">
          Model Targets
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          The pipeline currently targets two Qwen model families:
        </p>
        <ul className="list-disc list-inside space-y-2 text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          <li>
            <span className="font-mono text-[13px] font-medium text-[var(--text-primary)]">Qwen/Qwen3-30B-A3B</span> —
            a Mixture-of-Experts architecture that activates 3B parameters per forward pass while
            retaining a 30B parameter pool. This gives strong reasoning capability at inference
            cost closer to a dense 3B model, making it the primary training target.
          </li>
          <li>
            <span className="font-mono text-[13px] font-medium text-[var(--text-primary)]">Qwen/Qwen2.5-72B-Instruct</span> —
            a dense 72B instruction-tuned model used as a high-capacity baseline. Benchmarking
            against this model provides an upper bound on how much headroom remains for the
            smaller MoE checkpoint after fine-tuning.
          </li>
        </ul>
      </section>
    </>
  );
}
