import Link from "next/link";

const cards = [
  {
    href: "/docs/scoring",
    title: "Scoring",
    desc: "How evaluation works — base score, penalties, trajectory modifier, and the full formula.",
  },
  {
    href: "/docs/primitives",
    title: "Cognitive Primitives",
    desc: "The 12-primitive taxonomy for diagnosing where and why web agents fail.",
  },
  {
    href: "/docs/architecture",
    title: "Architecture",
    desc: "Sandwich architecture, unified agent format, state visibility, and the episode loop.",
  },
  {
    href: "/docs/benchmark",
    title: "Benchmark",
    desc: "Task structure, the Gmail environment, fixtures, version history, and how to run it.",
  },
  {
    href: "/docs/training",
    title: "Training Pipeline",
    desc: "SFT and DPO finetuning on Qwen models using simulator and browser trajectories.",
  },
];

export default function DocsLandingPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation
      </p>
      <h1 className="text-[clamp(1.8rem,3vw,2.5rem)] font-medium tracking-tight leading-[1.2] mb-4">
        LLMOS Documentation
      </h1>
      <p className="text-[16px] text-[var(--text-secondary)] leading-[1.75] max-w-[540px] mb-12">
        LLMOS is a research framework for training web agents. It has three subsystems: an LLM-based
        UI simulator, a browser benchmark (WebAgentBench), and a training pipeline for finetuning
        language models on agent trajectories.
      </p>

      <div className="flex flex-col gap-3">
        {cards.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="group block border border-[var(--border)] rounded-xl p-5 no-underline hover:border-[var(--text-tertiary)] transition-colors"
          >
            <p className="text-[15px] font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors mb-1">
              {c.title}
            </p>
            <p className="text-[13px] text-[var(--text-secondary)] leading-[1.6]">
              {c.desc}
            </p>
          </Link>
        ))}
      </div>
    </>
  );
}
