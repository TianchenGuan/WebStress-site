"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import OpenAI from "@lobehub/icons/es/OpenAI";
import Qwen from "@lobehub/icons/es/Qwen";
import {
  fetchSummary,
  fetchModelIndex,
  type ResultSummary,
  type TaskResult,
  type ModelIndex,
} from "@/lib/results";
import { DifficultyBar } from "@/components/ui/DifficultyBar";

type SortKey = "title" | "difficulty" | "score" | "steps" | "success";
type SortDir = "asc" | "desc";

interface ModelEntry {
  id: string;
  label: string;
  provider: string;
  tasks: number;
}

interface ProviderGroup {
  provider: string;
  providerLabel: string;
  icon: React.ReactNode;
  models: ModelEntry[];
}

const DIFF_ORDER: Record<string, number> = {
  easy: 0, medium: 1, hard: 2, expert: 3, frontier: 4,
};

const PROVIDER_META: Record<string, { label: string; icon: (size: number) => React.ReactNode }> = {
  openai: { label: "OpenAI", icon: (s) => <OpenAI size={s} /> },
  vllm: { label: "Alibaba / Qwen", icon: (s) => <Qwen.Color size={s} /> },
};

function providerIcon(provider: string, size: number) {
  return PROVIDER_META[provider]?.icon(size) ?? null;
}

function sorted(tasks: TaskResult[], key: SortKey, dir: SortDir) {
  return [...tasks].sort((a, b) => {
    let av: number | string, bv: number | string;
    if (key === "difficulty") { av = DIFF_ORDER[a.difficulty] ?? 99; bv = DIFF_ORDER[b.difficulty] ?? 99; }
    else if (key === "success") { av = a.success ? 1 : 0; bv = b.success ? 1 : 0; }
    else { av = a[key]; bv = b[key]; }
    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return 0;
  });
}

function groupByProvider(models: ModelEntry[]): ProviderGroup[] {
  const groups: Record<string, ModelEntry[]> = {};
  for (const m of models) (groups[m.provider] ??= []).push(m);
  return Object.entries(groups).map(([provider, entries]) => ({
    provider,
    providerLabel: PROVIDER_META[provider]?.label ?? provider,
    icon: providerIcon(provider, 20),
    models: entries,
  }));
}

function ModelCard({ model, summary, active, onClick }: {
  model: ModelEntry; summary: ResultSummary | null; active: boolean; onClick: () => void;
}) {
  const rate = summary?.aggregate.success_rate;
  const avg = summary?.aggregate.avg_score;
  return (
    <button onClick={onClick} className={`relative text-left rounded-2xl px-5 py-4 transition-all duration-200 border ${
      active
        ? "bg-[var(--surface-raised)] border-[var(--accent)] shadow-[0_0_0_1px_var(--accent)]"
        : "bg-[var(--surface)] border-transparent hover:border-[var(--border)] hover:bg-[var(--surface-raised)]"
    }`}>
      <div className="flex items-center gap-2.5 mb-2">
        {providerIcon(model.provider, 18)}
        <span className="text-[14px] font-medium text-[var(--text-primary)]">{model.label}</span>
      </div>
      <div className="flex items-center gap-4 text-[12px] text-[var(--text-tertiary)]">
        <span>{model.tasks} tasks</span>
        {rate != null && <span className="font-mono">{(rate * 100).toFixed(0)}% pass</span>}
        {avg != null && <span className="font-mono">{avg.toFixed(2)} avg</span>}
      </div>
    </button>
  );
}

function SortableHeader({ label, sortKey, currentKey, currentDir, onToggle, className }: {
  label: string; sortKey: SortKey; currentKey: SortKey; currentDir: SortDir; onToggle: (k: SortKey) => void; className?: string;
}) {
  const active = currentKey === sortKey;
  return (
    <th className={`text-left text-[12px] font-medium py-2 cursor-pointer select-none transition-colors ${
      active ? "text-[var(--text-primary)]" : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
    } ${className ?? ""}`} onClick={() => onToggle(sortKey)}>
      {label}{active ? (currentDir === "asc" ? " \u2191" : " \u2193") : ""}
    </th>
  );
}

export default function ResultsPageWrapper() {
  return (
    <Suspense fallback={<div className="max-w-[960px] mx-auto px-12 pt-[120px]"><p className="text-sm text-[var(--text-tertiary)]">Loading results...</p></div>}>
      <ResultsPage />
    </Suspense>
  );
}

function ResultsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [models, setModels] = useState<ModelIndex | null>(null);
  const [activeModel, setActiveModel] = useState("");
  const [summaries, setSummaries] = useState<Record<string, ResultSummary>>({});
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("title");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  useEffect(() => {
    fetchModelIndex().then(async (idx) => {
      if (!idx) { setLoading(false); return; }
      setModels(idx);
      const urlModel = searchParams.get("model");
      const validIds = idx.models.map((m) => m.id);
      setActiveModel(urlModel && validIds.includes(urlModel) ? urlModel : idx.default);
      const loaded: Record<string, ResultSummary> = {};
      await Promise.all(idx.models.map(async (m) => {
        const s = await fetchSummary(m.id);
        if (s) loaded[m.id] = s;
      }));
      setSummaries(loaded);
      setLoading(false);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function selectModel(id: string) {
    setActiveModel(id);
    router.replace(`/results?model=${id}`, { scroll: false });
  }

  const data = summaries[activeModel] ?? null;
  const providerGroups = useMemo(() => models ? groupByProvider(models.models) : [], [models]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("asc"); }
  }

  if (loading) return (
    <div className="max-w-[960px] mx-auto px-12 pt-[120px]">
      <p className="text-sm text-[var(--text-tertiary)]">Loading results...</p>
    </div>
  );

  if (!models || Object.keys(summaries).length === 0) return (
    <div className="max-w-[960px] mx-auto px-12 pt-[120px]">
      <p className="text-[var(--text-secondary)]">No results available.</p>
    </div>
  );

  const diffBars = (() => {
    if (!data) return [];
    const groups: Record<string, { total: number; passed: number }> = {};
    for (const t of data.tasks) {
      const g = (groups[t.difficulty] ??= { total: 0, passed: 0 });
      g.total++; if (t.success) g.passed++;
    }
    return Object.entries(groups)
      .sort((a, b) => (DIFF_ORDER[a[0]] ?? 99) - (DIFF_ORDER[b[0]] ?? 99))
      .map(([label, g]) => ({ label, value: g.total > 0 ? g.passed / g.total : 0 }));
  })();

  const tasks = data ? sorted(data.tasks, sortKey, sortDir) : [];

  return (
    <div className="max-w-[960px] mx-auto px-12 pt-[120px] pb-24">
      <h1 className="text-2xl font-medium tracking-tight mb-2">Benchmark Results</h1>
      <p className="text-[14px] text-[var(--text-tertiary)] mb-10">
        Select a model to explore task-level performance.
      </p>

      {/* Model selector grouped by provider */}
      <div className="space-y-6 mb-12">
        {providerGroups.map((group) => (
          <div key={group.provider}>
            <div className="flex items-center gap-2 mb-3">
              {group.icon}
              <span className="text-[12px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">
                {group.providerLabel}
              </span>
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
              {group.models.map((m) => (
                <ModelCard key={m.id} model={m} summary={summaries[m.id] ?? null}
                  active={activeModel === m.id} onClick={() => selectModel(m.id)} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Active model detail */}
      {data && (<>
        <hr className="border-[var(--border)] mb-8" />
        <div className="flex items-start justify-between mb-10">
          <div className="flex items-center gap-3">
            {providerIcon(data.agent.provider ?? activeModel, 28)}
            <div>
              <h2 className="text-xl font-medium tracking-tight">{data.agent.model}</h2>
              <p className="text-[13px] text-[var(--text-tertiary)]">
                {data.aggregate.total_tasks} tasks &middot; {data.version}
              </p>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="bg-[var(--surface)] rounded-2xl px-5 py-3 text-center">
              <p className="font-mono text-[28px] font-medium tracking-tight text-[var(--text-primary)]">
                {(data.aggregate.success_rate * 100).toFixed(0)}%
              </p>
              <p className="text-[11px] text-[var(--text-tertiary)]">pass rate</p>
            </div>
            <div className="bg-[var(--surface)] rounded-2xl px-5 py-3 text-center">
              <p className="font-mono text-[28px] font-medium tracking-tight text-[var(--text-primary)]">
                {data.aggregate.avg_score.toFixed(2)}
              </p>
              <p className="text-[11px] text-[var(--text-tertiary)]">avg score</p>
            </div>
          </div>
        </div>

        {diffBars.length > 0 && (
          <div className="mb-10">
            <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-4">Pass rate by difficulty</p>
            <DifficultyBar items={diffBars} />
          </div>
        )}

        <hr className="border-[var(--border)] mb-8" />
        <div className="flex items-center justify-between mb-6">
          <p className="text-[12px] font-medium text-[var(--text-tertiary)]">All tasks</p>
          <Link href="/results/negative-checks"
            className="text-[12px] text-[var(--text-secondary)] no-underline hover:text-[var(--text-primary)] transition-colors">
            View negative checks →
          </Link>
        </div>

        <table className="w-full text-[14px] border-separate border-spacing-y-1">
          <thead>
            <tr>
              <SortableHeader label="Task" sortKey="title" currentKey={sortKey} currentDir={sortDir} onToggle={toggleSort} className="pl-3" />
              <SortableHeader label="Diff" sortKey="difficulty" currentKey={sortKey} currentDir={sortDir} onToggle={toggleSort} />
              <SortableHeader label="Score" sortKey="score" currentKey={sortKey} currentDir={sortDir} onToggle={toggleSort} />
              <SortableHeader label="Steps" sortKey="steps" currentKey={sortKey} currentDir={sortDir} onToggle={toggleSort} />
              <SortableHeader label="Status" sortKey="success" currentKey={sortKey} currentDir={sortDir} onToggle={toggleSort} className="pr-3" />
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.task_id} className="group hover:bg-[var(--surface)] transition-colors [&>td:first-child]:rounded-l-xl [&>td:last-child]:rounded-r-xl">
                <td className="py-3 pr-4 pl-3">
                  <Link href={`/results/${t.task_id}?model=${activeModel}`}
                    className="text-[var(--text-primary)] no-underline hover:text-[var(--accent)] transition-colors">
                    {t.title}
                  </Link>
                </td>
                <td className="py-3 pr-4 text-[13px] text-[var(--text-secondary)]">{t.difficulty}</td>
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    <div className="w-[48px] h-[3px] bg-[var(--border)] rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{
                        width: `${Math.max(0, Math.min(100, t.score * 100))}%`,
                        background: t.success ? "var(--green)" : t.score > 0.5 ? "var(--amber)" : "var(--red)",
                      }} />
                    </div>
                    <span className="font-mono text-[13px]" style={{
                      color: t.success ? "var(--green)" : t.score > 0.5 ? "var(--amber)" : "var(--red)",
                    }}>{t.score.toFixed(2)}</span>
                  </div>
                </td>
                <td className="py-3 pr-4 text-[13px] text-[var(--text-secondary)]">{t.steps}</td>
                <td className="py-3 pr-3">
                  <span className={`text-[10px] font-medium px-2.5 py-0.5 rounded-full ${t.success ? "text-[var(--green)]" : "text-[var(--red)]"}`}
                    style={{ background: t.success ? "oklch(78% 0.14 155 / 0.1)" : "oklch(72% 0.15 25 / 0.1)" }}>
                    {t.success ? "Pass" : "Fail"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </>)}
    </div>
  );
}
