"use client";

import { useEffect, useState, useCallback } from "react";
import { loadTaskManifest, loadTaskDetail, type TaskMeta, type TaskDetail } from "@/lib/tasks";
import { GmailWrapper } from "@/components/gmail-wrapper";
import type { GmailFixture } from "@webagentbench/gmail/mutator";

export default function EnvironmentPage() {
  const [tasks, setTasks] = useState<TaskMeta[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load manifest on mount
  useEffect(() => {
    loadTaskManifest().then((items) => {
      setTasks(items);
      if (items.length > 0) {
        setSelectedTaskId(items[0].task_id);
      }
    });
  }, []);

  // Load fixture when task changes
  const loadFixture = useCallback(async (taskId: string) => {
    setIsLoading(true);
    setError(null);
    setTaskDetail(null);
    try {
      const detail = await loadTaskDetail(taskId);
      if (!detail) {
        setError(`Could not load fixture for task "${taskId}".`);
      } else {
        setTaskDetail(detail);
      }
    } catch {
      setError("Failed to load task fixture.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTaskId) {
      loadFixture(selectedTaskId);
    }
  }, [selectedTaskId, loadFixture]);

  const selectedMeta = tasks.find((t) => t.task_id === selectedTaskId);

  return (
    <div className="max-w-[1200px] mx-auto px-12">
      {/* Header */}
      <section className="pt-[120px] pb-6">
        <p className="font-mono text-xs tracking-[3px] uppercase text-[var(--text-tertiary)] mb-8">
          Environment
        </p>
        <h1 className="text-[clamp(2rem,4vw,3.2rem)] font-medium tracking-tight leading-[1.15] mb-3">
          Interactive explorer
        </h1>
        <p className="text-[15px] text-[var(--text-secondary)] leading-[1.7] max-w-[540px]">
          Select a task to load its pre-generated Gmail environment.
          All actions run locally in your browser — no backend required.
        </p>
      </section>

      {/* Task selector */}
      <div className="flex flex-col gap-4 pb-6">
        <label
          htmlFor="task-select"
          className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)]"
        >
          Task
        </label>
        <select
          id="task-select"
          value={selectedTaskId ?? ""}
          onChange={(e) => setSelectedTaskId(e.target.value)}
          className="w-full max-w-[540px] px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text-primary)] text-sm focus:outline-none focus:border-[var(--text-tertiary)] transition-colors"
        >
          {tasks.map((t) => (
            <option key={t.task_id} value={t.task_id}>
              {t.title} ({t.difficulty})
            </option>
          ))}
        </select>
      </div>

      {/* Task instruction */}
      {taskDetail && (
        <div className="border border-[var(--border)] rounded-md p-5 mb-6 max-w-[720px]">
          <div className="flex items-baseline gap-3 mb-2">
            <span className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)]">
              Instruction
            </span>
            {selectedMeta && (
              <span className="text-xs text-[var(--text-tertiary)] font-mono">
                {selectedMeta.difficulty} &middot; ~{selectedMeta.expected_steps} steps
              </span>
            )}
          </div>
          <p className="text-[15px] text-[var(--text-primary)] leading-[1.7]">
            {taskDetail.instruction}
          </p>
        </div>
      )}

      {/* Loading / error states */}
      {isLoading && (
        <div className="flex items-center justify-center py-20 text-sm text-[var(--text-tertiary)]">
          Loading environment...
        </div>
      )}

      {error && (
        <div className="border border-[var(--red)] rounded-md p-5 mb-6 text-sm text-[var(--red)]">
          {error}
        </div>
      )}

      {/* Gmail environment */}
      {taskDetail && !isLoading && !error && (
        <div className="border border-[var(--border)] rounded-md overflow-hidden mb-16" style={{ height: "calc(100vh - 120px)", minHeight: 500 }}>
          <GmailWrapper
            key={taskDetail.task_id}
            fixture={taskDetail.state as unknown as GmailFixture}
            initialRoute={taskDetail.start_path ?? "/inbox?label=inbox"}
          />
        </div>
      )}
    </div>
  );
}
