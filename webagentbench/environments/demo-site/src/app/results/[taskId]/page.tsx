import fs from "fs";
import path from "path";
import TrajectoryPage from "./TrajectoryPage";

export function generateStaticParams() {
  try {
    const summaryPath = path.join(process.cwd(), "public", "results", "summary.json");
    const summary = JSON.parse(fs.readFileSync(summaryPath, "utf-8"));
    return (summary.tasks || []).map((t: { task_id: string }) => ({
      taskId: t.task_id,
    }));
  } catch {
    return [];
  }
}

export default function Page({ params }: { params: { taskId: string } }) {
  return <TrajectoryPage taskId={params.taskId} />;
}
