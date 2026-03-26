/* helpers to load result data from public/results/ */

export interface TaskResult {
  task_id: string;
  title: string;
  env_id: string;
  difficulty: string;
  primitives: string[];
  instruction: string;
  score: number;
  success: boolean;
  steps: number;
  elapsed_seconds: number;
  completed: boolean;
  reasoning: string;
}

export interface ResultSummary {
  source_file: string;
  agent: { model: string; provider: string };
  benchmark: string;
  version: string;
  timestamp: string;
  aggregate: {
    total_tasks: number;
    success_count: number;
    success_rate: number;
    avg_score: number;
  };
  by_difficulty: Record<string, { count: number; avg_score: number }>;
  tasks: TaskResult[];
}

export interface TrajectoryStep {
  step: number;
  thought: string;
  action: Record<string, unknown>;
  targets: { role: string; name: string };
  status: string;
  elapsed_seconds: number;
}

export async function fetchSummary(): Promise<ResultSummary | null> {
  try {
    const res = await fetch("/results/summary.json");
    if (!res.ok) return null;
    return (await res.json()) as ResultSummary;
  } catch {
    return null;
  }
}

export async function fetchTrajectory(
  taskId: string,
): Promise<TrajectoryStep[] | null> {
  try {
    const res = await fetch(`/results/trajectories/${taskId}.json`);
    if (!res.ok) return null;
    return (await res.json()) as TrajectoryStep[];
  } catch {
    return null;
  }
}
