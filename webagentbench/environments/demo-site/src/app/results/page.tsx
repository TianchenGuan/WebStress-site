"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchSummary, type ResultSummary, type TaskResult } from "@/lib/results";
import { DifficultyBar } from "@/components/ui/DifficultyBar";

type SortKey = "title" | "difficulty" | "score" | "steps" | "success";
type SortDir = "asc" | "desc";

const DIFF_ORDER: Record<string, number> = {
  easy: 0,
  medium: 1,
  hard: 2,
  expert: 3,
};

function sorted(tasks: TaskResult[], key: SortKey, dir: SortDir) {
  const cmp = (a: TaskResult, b: TaskResult) => {
    let av: number | string;
    let bv: number | string;
    if (key === "difficulty") {
      av = DIFF_ORDER[a.difficulty] ?? 99;
      bv = DIFF_ORDER[b.difficulty] ?? 99;
    } else if (key === "success") {
      av = a.success ? 1 : 0;
      bv = b.success ? 1 : 0;
    } else {
      av = a[key];
      bv = b[key];
    }
    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return 0;
  };
  return [...tasks].sort(cmp);
}

export default function ResultsPage() {
  const [data, setData] = useState<ResultSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("title");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  useEffect(() => {
    fetchSummary().then((d) => {
      setData(d);
      setLoading(false);
    });
  }, []);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  if (loading) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <p className="font-mono text-sm text-[var(--text-tertiary)]">Loading...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <p className="font-mono text-xs tracking-[3px] uppercase text-[var(--text-tertiary)] mb-8">
          Results
        </p>
        <p className="text-[var(--text-secondary)]">No results available.</p>
      </div>
    );
  }

  // compute pass rate per difficulty
  const diffGroups: Record<string, { total: number; passed: number }> = {};
  for (const t of data.tasks) {
    const g = diffGroups[t.difficulty] || { total: 0, passed: 0 };
    g.total++;
    if (t.success) g.passed++;
    diffGroups[t.difficulty] = g;
  }
  const diffBars = Object.entries(diffGroups)
    .sort((a, b) => (DIFF_ORDER[a[0]] ?? 99) - (DIFF_ORDER[b[0]] ?? 99))
    .map(([label, g]) => ({ label, value: g.total > 0 ? g.passed / g.total : 0 }));

  const tasks = sorted(data.tasks, sortKey, sortDir);

  const thClass =
    "text-left font-mono text-xs tracking-[1px] uppercase text-[var(--text-tertiary)] py-2 cursor-pointer select-none hover:text-[var(--text-secondary)] transition-colors";

  return (
    <div className="max-w-[720px] mx-auto px-12 pt-[120px] pb-24">
      <p className="font-mono text-xs tracking-[3px] uppercase text-[var(--text-tertiary)] mb-8">
        Results
      </p>

      {/* model + metadata */}
      <h1 className="text-2xl font-medium tracking-tight mb-1">
        {data.agent.model}
      </h1>
      <p className="text-[14px] text-[var(--text-tertiary)] mb-10">
        {data.aggregate.total_tasks} tasks &middot; {data.version}
      </p>

      {/* aggregate stats */}
      <div className="flex gap-16 mb-12">
        <div>
          <p className="font-mono text-[32px] font-medium tracking-tight text-[var(--text-primary)]">
            {(data.aggregate.success_rate * 100).toFixed(0)}%
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">pass rate</p>
        </div>
        <div>
          <p className="font-mono text-[32px] font-medium tracking-tight text-[var(--text-primary)]">
            {data.aggregate.avg_score.toFixed(2)}
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">avg score</p>
        </div>
      </div>

      {/* difficulty bar */}
      <div className="mb-12">
        <p className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)] mb-4">
          Pass rate by difficulty
        </p>
        <DifficultyBar items={diffBars} />
      </div>

      <hr className="border-[var(--border)] mb-8" />

      {/* task table */}
      <table className="w-full text-[14px] border-collapse">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className={thClass} onClick={() => toggleSort("title")}>
              Task{sortKey === "title" ? (sortDir === "asc" ? " \u2191" : " \u2193") : ""}
            </th>
            <th className={thClass} onClick={() => toggleSort("difficulty")}>
              Diff{sortKey === "difficulty" ? (sortDir === "asc" ? " \u2191" : " \u2193") : ""}
            </th>
            <th className={thClass} onClick={() => toggleSort("score")}>
              Score{sortKey === "score" ? (sortDir === "asc" ? " \u2191" : " \u2193") : ""}
            </th>
            <th className={thClass} onClick={() => toggleSort("steps")}>
              Steps{sortKey === "steps" ? (sortDir === "asc" ? " \u2191" : " \u2193") : ""}
            </th>
            <th className={thClass} onClick={() => toggleSort("success")}>
              Status{sortKey === "success" ? (sortDir === "asc" ? " \u2191" : " \u2193") : ""}
            </th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr
              key={t.task_id}
              className="border-b border-[var(--border)] hover:bg-[var(--surface)] transition-colors"
            >
              <td className="py-3 pr-4">
                <Link
                  href={`/results/${t.task_id}`}
                  className="text-[var(--text-primary)] no-underline hover:text-[var(--accent)] transition-colors"
                >
                  {t.title}
                </Link>
              </td>
              <td className="py-3 pr-4 font-mono text-[13px] text-[var(--text-secondary)]">
                {t.difficulty}
              </td>
              <td className="py-3 pr-4">
                <div className="flex items-center gap-2">
                  <div className="w-[48px] h-[3px] bg-[var(--border)] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.max(0, Math.min(100, t.score * 100))}%`,
                        background: t.success ? "var(--green)" : t.score > 0.5 ? "oklch(70% 0.12 85)" : "var(--red)",
                      }}
                    />
                  </div>
                  <span
                    className="font-mono text-[13px]"
                    style={{ color: t.success ? "var(--green)" : t.score > 0.5 ? "oklch(70% 0.12 85)" : "var(--red)" }}
                  >
                    {t.score.toFixed(2)}
                  </span>
                </div>
              </td>
              <td className="py-3 pr-4 font-mono text-[13px] text-[var(--text-secondary)]">
                {t.steps}
              </td>
              <td className="py-3">
                <span
                  className={`font-mono text-[10px] tracking-[1px] uppercase px-2 py-0.5 rounded ${
                    t.success
                      ? "text-[var(--green)]"
                      : "text-[var(--red)]"
                  }`}
                  style={{
                    background: t.success
                      ? "oklch(78% 0.12 155 / 0.1)"
                      : "oklch(72% 0.14 25 / 0.1)",
                  }}
                >
                  {t.success ? "pass" : "fail"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
