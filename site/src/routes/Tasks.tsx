import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadTasks } from "../lib/data";
import type { TaskEntry, Primitive, Environment, Difficulty } from "../data/types";
import {
  ENV_LABELS,
  ENV_ORDER,
  PRIMITIVE_LABELS,
  PRIMITIVE_ORDER,
  DIFFICULTY_ORDER,
  shortenInstruction,
  pillColorForPrimitive,
  pillColorForDifficulty,
} from "../lib/format";
import Pill from "../components/Pill";

const ALL = "all";

export default function Tasks() {
  const [tasks, setTasks] = useState<TaskEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [env, setEnv] = useState<Environment | typeof ALL>(ALL);
  const [primitive, setPrimitive] = useState<Primitive | typeof ALL>(ALL);
  const [difficulty, setDifficulty] = useState<Difficulty | typeof ALL>(ALL);
  const [family, setFamily] = useState<string>(ALL);
  const [human140, setHuman140] = useState<"any" | "yes" | "no">("any");
  const [audit, setAudit] = useState<"any" | "yes" | "no">("any");

  useEffect(() => {
    loadTasks().then(setTasks).catch((e) => setError(String(e)));
  }, []);

  const families = useMemo(() => {
    if (!tasks) return [];
    return Array.from(
      new Set(tasks.map((t) => t.intervention_family).filter((x): x is string => Boolean(x))),
    ).sort();
  }, [tasks]);

  const filtered = useMemo(() => {
    if (!tasks) return [];
    const q = search.trim().toLowerCase();
    return tasks.filter((t) => {
      if (env !== ALL && t.env_id !== env) return false;
      if (primitive !== ALL && t.primary_primitive !== primitive) return false;
      if (difficulty !== ALL && t.difficulty !== difficulty) return false;
      if (family !== ALL && t.intervention_family !== family) return false;
      if (human140 !== "any" && t.human140 !== (human140 === "yes")) return false;
      if (audit !== "any" && t.duplicate_audit !== (audit === "yes")) return false;
      if (q) {
        const hay = (
          t.task_id +
          " " +
          t.title +
          " " +
          t.public_instruction +
          " " +
          (t.intervention_summary_public || "")
        ).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [tasks, search, env, primitive, difficulty, family, human140, audit]);

  function clearAll() {
    setSearch("");
    setEnv(ALL);
    setPrimitive(ALL);
    setDifficulty(ALL);
    setFamily(ALL);
    setHuman140("any");
    setAudit("any");
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-10 text-accent">
        Failed to load tasks_index.json: {error}.
      </div>
    );
  }
  if (!tasks) {
    return <div className="max-w-6xl mx-auto px-6 py-10 text-muted">Loading…</div>;
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl mb-2">Task explorer</h1>
        <p className="text-ink/75 max-w-prose">
          {tasks.length} base tasks across 7 self-hosted environments. Each task ships
          with a matched intervention variant whose primary target is one cognitive
          primitive. Filter by environment, primitive, difficulty, stressor family,
          and human-panel inclusion.
        </p>
      </header>

      {/* Filters */}
      <div className="card mb-6">
        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs uppercase tracking-wider text-muted mb-1">
              Search
            </label>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="task id, title, or instruction…"
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
          <FilterSelect
            label="Environment"
            value={env}
            onChange={(v) => setEnv(v as Environment | typeof ALL)}
            options={[ALL, ...ENV_ORDER]}
            labelFor={(v) => (v === ALL ? "All environments" : ENV_LABELS[v as Environment])}
          />
          <FilterSelect
            label="Primary primitive"
            value={primitive}
            onChange={(v) => setPrimitive(v as Primitive | typeof ALL)}
            options={[ALL, ...PRIMITIVE_ORDER]}
            labelFor={(v) => (v === ALL ? "All primitives" : PRIMITIVE_LABELS[v as Primitive])}
          />
          <FilterSelect
            label="Difficulty"
            value={difficulty}
            onChange={(v) => setDifficulty(v as Difficulty | typeof ALL)}
            options={[ALL, ...DIFFICULTY_ORDER]}
            labelFor={(v) => (v === ALL ? "All difficulties" : (v as string))}
          />
          <FilterSelect
            label="Intervention family"
            value={family}
            onChange={(v) => setFamily(v)}
            options={[ALL, ...families]}
            labelFor={(v) => (v === ALL ? "All families" : v)}
          />
          <div className="grid grid-cols-2 gap-2">
            <FilterSelect
              label="Human-140"
              value={human140}
              onChange={(v) => setHuman140(v as "any" | "yes" | "no")}
              options={["any", "yes", "no"]}
              labelFor={(v) => (v === "any" ? "Any" : v === "yes" ? "Yes" : "No")}
            />
            <FilterSelect
              label="Dup. audit"
              value={audit}
              onChange={(v) => setAudit(v as "any" | "yes" | "no")}
              options={["any", "yes", "no"]}
              labelFor={(v) => (v === "any" ? "Any" : v === "yes" ? "Yes" : "No")}
            />
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between text-sm">
          <div className="text-muted">
            Showing <span className="font-medium text-ink">{filtered.length}</span> of{" "}
            {tasks.length} tasks
          </div>
          <button onClick={clearAll} className="text-accent text-xs underline">
            Clear filters
          </button>
        </div>
      </div>

      {/* Results table */}
      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-cream/60 text-left border-b border-border text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3">Task</th>
              <th className="px-4 py-3">Env</th>
              <th className="px-4 py-3">Difficulty</th>
              <th className="px-4 py-3">Target primitive</th>
              <th className="px-4 py-3">Intervention family</th>
              <th className="px-4 py-3">Panel</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 250).map((t) => (
              <tr key={t.task_id} className="border-b border-border last:border-b-0 hover:bg-cream/40">
                <td className="px-4 py-3 align-top">
                  <Link to={`/tasks/${t.task_id}`} className="font-mono text-xs text-ink no-underline hover:text-accent">
                    {t.task_id}
                  </Link>
                  <div className="text-[13px] text-ink/70 mt-1 max-w-xl">
                    {shortenInstruction(t.public_instruction, 180)}
                  </div>
                </td>
                <td className="px-4 py-3 align-top text-ink/80">{ENV_LABELS[t.env_id]}</td>
                <td className="px-4 py-3 align-top">
                  <Pill className={pillColorForDifficulty(t.difficulty)}>{t.difficulty}</Pill>
                </td>
                <td className="px-4 py-3 align-top">
                  {t.target_primitive ? (
                    <Pill className={pillColorForPrimitive(t.target_primitive)}>
                      {PRIMITIVE_LABELS[t.target_primitive]}
                    </Pill>
                  ) : (
                    <span className="text-muted text-xs">—</span>
                  )}
                </td>
                <td className="px-4 py-3 align-top text-ink/80">
                  {t.intervention_family || <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3 align-top text-xs">
                  <div className="flex flex-col gap-0.5">
                    {t.human140 && (
                      <span className="inline-flex items-center text-sage">● Human-140</span>
                    )}
                    {t.duplicate_audit && (
                      <span className="inline-flex items-center text-navy">● Duplicate</span>
                    )}
                    {!t.human140 && !t.duplicate_audit && (
                      <span className="text-muted">—</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length > 250 && (
        <p className="mt-4 text-xs text-muted">
          Showing first 250 results. Narrow your filters to see the rest.
        </p>
      )}
    </div>
  );
}

function FilterSelect<T extends string>({
  label,
  value,
  onChange,
  options,
  labelFor,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: T[];
  labelFor: (v: T) => string;
}) {
  return (
    <div>
      <label className="block text-xs uppercase tracking-wider text-muted mb-1">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="w-full border border-border rounded-md px-3 py-2 text-sm bg-white"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {labelFor(opt)}
          </option>
        ))}
      </select>
    </div>
  );
}
