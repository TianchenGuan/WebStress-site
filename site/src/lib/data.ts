import type {
  TaskEntry,
  PrimitiveCard,
  EnvironmentCard,
  ResultsSummary,
} from "../data/types";

const DATA = "/data";

export async function loadTasks(): Promise<TaskEntry[]> {
  const r = await fetch(`${DATA}/tasks_index.json`);
  if (!r.ok) throw new Error("failed to load tasks_index.json");
  return r.json();
}

export async function loadPrimitives(): Promise<PrimitiveCard[]> {
  const r = await fetch(`${DATA}/primitives.json`);
  if (!r.ok) throw new Error("failed to load primitives.json");
  return r.json();
}

export async function loadEnvironments(): Promise<EnvironmentCard[]> {
  const r = await fetch(`${DATA}/environments.json`);
  if (!r.ok) throw new Error("failed to load environments.json");
  return r.json();
}

export async function loadResults(): Promise<ResultsSummary> {
  const r = await fetch(`${DATA}/results_summary.json`);
  if (!r.ok) throw new Error("failed to load results_summary.json");
  return r.json();
}
