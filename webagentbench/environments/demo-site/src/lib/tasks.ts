export interface TaskMeta {
  task_id: string;
  title: string;
  difficulty: string;
  primary_primitives: string[];
  secondary_primitives: string[];
  expected_steps: number;
  time_limit_seconds: number;
}

export interface TaskDetail extends TaskMeta {
  instruction: string;
  eval_check_descriptions: string[];
  start_path?: string;
  state: Record<string, unknown>;
}

export async function loadTaskManifest(): Promise<TaskMeta[]> {
  try {
    const res = await fetch("/fixtures/gmail/_manifest.json");
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function loadTaskDetail(taskId: string): Promise<TaskDetail | null> {
  try {
    const res = await fetch(`/fixtures/gmail/${taskId}.json`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
