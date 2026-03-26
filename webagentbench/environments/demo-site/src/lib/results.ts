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

export interface TrajectoryData {
  task_id: string;
  title: string;
  instruction: string;
  difficulty: string;
  model: string;
  total_steps: number;
  elapsed_seconds: number;
  completed: boolean;
  evaluation: {
    score: number;
    success: boolean;
    reasoning: string;
    criteria_results?: Array<{ desc: string; passed: boolean; penalty?: number }>;
  };
  steps: TrajectoryStep[];
}

type RawTrajectoryPayload = TrajectoryData | TrajectoryStep[];

export function normalizeTrajectoryData(
  taskId: string,
  payload: RawTrajectoryPayload | null,
): TrajectoryData | null {
  if (!payload) {
    return null;
  }

  if (Array.isArray(payload)) {
    const steps = payload as TrajectoryStep[];
    const elapsedSeconds = steps.length > 0 ? (steps[steps.length - 1]?.elapsed_seconds ?? 0) : 0;
    return {
      task_id: taskId,
      title: taskId,
      instruction: "",
      difficulty: "",
      model: "",
      total_steps: steps.length,
      elapsed_seconds: elapsedSeconds,
      completed: false,
      evaluation: {
        score: 0,
        success: false,
        reasoning: "",
        criteria_results: [],
      },
      steps,
    };
  }

  return {
    ...payload,
    total_steps: payload.total_steps ?? payload.steps?.length ?? 0,
    elapsed_seconds: payload.elapsed_seconds ?? 0,
    evaluation: {
      score: payload.evaluation?.score ?? 0,
      success: payload.evaluation?.success ?? false,
      reasoning: payload.evaluation?.reasoning ?? "",
      criteria_results: payload.evaluation?.criteria_results ?? [],
    },
    steps: payload.steps ?? [],
  };
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
): Promise<TrajectoryData | null> {
  try {
    const res = await fetch(`/results/trajectories/${taskId}.json`);
    if (!res.ok) return null;
    return normalizeTrajectoryData(taskId, (await res.json()) as RawTrajectoryPayload);
  } catch {
    return null;
  }
}
