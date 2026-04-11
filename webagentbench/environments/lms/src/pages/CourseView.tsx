import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { preserveQueryParams, Tabs } from "@webagentbench/shared";

import { useLmsLayout } from "../context";
import type {
  Assignment,
  Course,
  Discussion,
  Grade,
  Module,
} from "../types";

const TABS = [
  { label: "Modules", value: "modules" },
  { label: "Assignments", value: "assignments" },
  { label: "Discussions", value: "discussions" },
  { label: "Grades", value: "grades" },
  { label: "Syllabus", value: "syllabus" },
];

export function CourseViewPage() {
  const { id } = useParams<{ id: string }>();
  const courseId = id!;
  const { api } = useLmsLayout();
  const location = useLocation();

  const [course, setCourse] = useState<Course | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [discussions, setDiscussions] = useState<Discussion[]>([]);
  const [gradesData, setGradesData] = useState<{
    weighted_score: string | null;
    category_scores: Record<string, string | null>;
    grades: Grade[];
  } | null>(null);
  const [activeTab, setActiveTab] = useState("modules");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, mods, assigns, discs, gd] = await Promise.all([
          api.getCourse(courseId),
          api.listModules(courseId),
          api.listAssignments(courseId),
          api.listDiscussions(courseId),
          api.getCourseGrades(courseId),
        ]);
        if (!cancelled) {
          setCourse(c);
          setModules(mods);
          setAssignments(assigns);
          setDiscussions(discs);
          setGradesData(gd);
        }
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api, courseId]);

  if (loading) return <div className="lms-loading">Loading...</div>;
  if (!course) return <div className="lms-empty">Course not found</div>;

  return (
    <div aria-label={`Course ${course.course_code} ${course.title}`}>
      <h1 className="lms-section-header">
        {course.course_code}: {course.title}
      </h1>
      <p style={{ color: "#666", marginBottom: "1rem" }}>
        {course.instructor_name} -- {course.semester} -- {course.credits} credits
      </p>

      <Tabs label="Course sections" items={TABS} value={activeTab} onChange={setActiveTab} />

      <div style={{ marginTop: "1rem" }}>
        {activeTab === "modules" && (
          <ModulesTab modules={modules} courseId={courseId} />
        )}
        {activeTab === "assignments" && (
          <AssignmentsTab assignments={assignments} courseId={courseId} />
        )}
        {activeTab === "discussions" && (
          <DiscussionsTab discussions={discussions} courseId={courseId} />
        )}
        {activeTab === "grades" && gradesData && (
          <GradesTab course={course} gradesData={gradesData} assignments={assignments} />
        )}
        {activeTab === "syllabus" && (
          <SyllabusTab course={course} />
        )}
      </div>
    </div>
  );
}

/* --- Modules Tab --- */

function ModulesTab({ modules, courseId }: { modules: Module[]; courseId: string }) {
  return (
    <section aria-label="Modules">
      {modules.length === 0 ? (
        <p className="lms-empty">No modules</p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0 }}>
          {modules.map((mod) => {
            const isLocked = mod.status === "locked";
            return (
              <li key={mod.id} className="lms-card" aria-label={`Module ${mod.title}`}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  {isLocked && (
                    <span className="lms-lock-icon" aria-label="Locked module" role="img">
                      &#x1f512;
                    </span>
                  )}
                  <strong>{mod.title}</strong>
                  <span className={`lms-badge lms-badge--${mod.status}`} aria-label={`Status: ${mod.status}`}>
                    {mod.status}
                  </span>
                </div>
                {isLocked && mod.unlock_condition !== "none" && (
                  <p style={{ fontSize: "0.85rem", color: "#888", margin: "0.25rem 0 0" }}>
                    {mod.unlock_condition === "prerequisite" && (
                      <>Requires: {mod.unlock_value.join(", ")} (completed)</>
                    )}
                    {mod.unlock_condition === "min_score" && (
                      <>
                        Requires:{" "}
                        {mod.unlock_value.map((v) => {
                          const parts = v.split(":");
                          return `${parts[0]} (score >= ${parts[1] ?? "0"})`;
                        }).join(", ")}
                      </>
                    )}
                    {mod.unlock_condition === "date" && (
                      <>Available after: {mod.unlock_value[0] ? new Date(mod.unlock_value[0]).toLocaleDateString() : "TBD"}</>
                    )}
                  </p>
                )}
                {mod.content_items.length > 0 && (
                  <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem" }}>
                    {mod.content_items.map((item, idx) => (
                      <li
                        key={idx}
                        style={{ fontSize: "0.9rem", marginBottom: "0.25rem" }}
                        aria-label={`Content item: ${item.title}${item.completed ? " (completed)" : ""}`}
                      >
                        <span style={{ marginRight: "0.5rem" }}>
                          {item.completed ? "\u2705" : "\u2B1C"}
                        </span>
                        {item.title}
                        <span style={{ color: "#999", marginLeft: "0.5rem", fontSize: "0.8rem" }}>
                          ({item.type})
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/* --- Assignments Tab --- */

function AssignmentsTab({ assignments, courseId }: { assignments: Assignment[]; courseId: string }) {
  const location = useLocation();

  return (
    <section aria-label="Assignments">
      {assignments.length === 0 ? (
        <p className="lms-empty">No assignments</p>
      ) : (
        <table className="lms-table" aria-label="Assignments Table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Type</th>
              <th>Due Date</th>
              <th>Status</th>
              <th>Score</th>
              <th>Points</th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((a) => (
              <tr key={a.id}>
                <td>
                  <Link
                    to={preserveQueryParams(`/courses/${courseId}/assignments/${a.id}`, location.search)}
                    className="lms-link"
                    aria-label={`Assignment ${a.title}`}
                  >
                    {a.title}
                  </Link>
                </td>
                <td>{a.type}</td>
                <td>{new Date(a.due_at).toLocaleDateString()}</td>
                <td>
                  <span
                    className={`lms-badge lms-badge--${a.submission_status}`}
                    aria-label={`Status: ${a.submission_status.replace(/_/g, " ")}`}
                  >
                    {a.submission_status.replace(/_/g, " ")}
                  </span>
                </td>
                <td>{a.score ?? "-"}</td>
                <td>{a.points_possible}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/* --- Discussions Tab --- */

function DiscussionsTab({ discussions, courseId }: { discussions: Discussion[]; courseId: string }) {
  const location = useLocation();

  return (
    <section aria-label="Discussions">
      {discussions.length === 0 ? (
        <p className="lms-empty">No discussions</p>
      ) : (
        <div>
          {discussions.map((d) => (
            <Link
              key={d.id}
              to={preserveQueryParams(`/courses/${courseId}/discussions/${d.id}`, location.search)}
              className="lms-card"
              style={{ display: "block", textDecoration: "none", color: "inherit" }}
              aria-label={`Discussion ${d.title}`}
            >
              <div className="lms-card__title">{d.title}</div>
              <div style={{ fontSize: "0.85rem", color: "#666" }}>
                Due: {new Date(d.due_at).toLocaleDateString()} --
                Min posts: {d.min_posts}, Min replies: {d.min_replies} --
                {d.points_possible} points
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

/* --- Grades Tab --- */

function GradesTab({
  course,
  gradesData,
  assignments,
}: {
  course: Course;
  gradesData: {
    weighted_score: string | null;
    category_scores: Record<string, string | null>;
    grades: Grade[];
  };
  assignments: Assignment[];
}) {
  const policy = course.syllabus.grading_policy;

  return (
    <section aria-label="Grade Breakdown">
      <div style={{ marginBottom: "1rem" }}>
        <strong>Overall Weighted Score: </strong>
        <span aria-label={`Overall weighted score ${gradesData.weighted_score ?? "N/A"}%`}>
          {gradesData.weighted_score ? `${gradesData.weighted_score}%` : "N/A"}
        </span>
      </div>

      <table className="lms-table" aria-label="Grade Breakdown Table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Weight</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(policy).map(([catName, catPolicy]) => (
            <tr key={catName}>
              <td>{catName}</td>
              <td>{(parseFloat(catPolicy.weight) * 100).toFixed(0)}%</td>
              <td>
                {gradesData.category_scores[catName]
                  ? `${gradesData.category_scores[catName]}%`
                  : "N/A"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: "1.5rem" }}>Assignment Details</h3>
      <table className="lms-table" aria-label="Assignment Grades">
        <thead>
          <tr>
            <th>Assignment</th>
            <th>Category</th>
            <th>Score</th>
            <th>Points</th>
            <th>%</th>
            <th>Late Penalty</th>
            <th>Dropped</th>
          </tr>
        </thead>
        <tbody>
          {gradesData.grades.map((g) => {
            const assignment = assignments.find((a) => a.id === g.assignment_id);
            const pct = g.score !== null
              ? ((parseFloat(g.score) / parseFloat(g.points_possible)) * 100).toFixed(1)
              : "-";
            return (
              <tr
                key={g.id}
                className={g.is_dropped ? "lms-dropped" : ""}
              >
                <td>{assignment?.title ?? g.assignment_id}</td>
                <td>{g.weight_category}</td>
                <td>{g.score ?? "-"}</td>
                <td>{g.points_possible}</td>
                <td>{pct}</td>
                <td>
                  {parseFloat(g.late_penalty_applied) > 0
                    ? `${(parseFloat(g.late_penalty_applied) * 100).toFixed(0)}%`
                    : "-"}
                </td>
                <td>
                  {g.is_dropped && (
                    <span className="lms-badge lms-badge--dropped" aria-label="Dropped">
                      Dropped
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

/* --- Syllabus Tab --- */

function SyllabusTab({ course }: { course: Course }) {
  const policy = course.syllabus.grading_policy;
  const latePolicy = course.syllabus.late_policy;

  return (
    <section aria-label="Syllabus">
      <h3>Grading Policy</h3>
      <table className="lms-table" aria-label="Grading Policy">
        <thead>
          <tr>
            <th>Category</th>
            <th>Weight</th>
            <th>Drop Lowest</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(policy).map(([name, p]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{(parseFloat(p.weight) * 100).toFixed(0)}%</td>
              <td>{p.drop_lowest > 0 ? p.drop_lowest : "None"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: "1.5rem" }}>Late Policy</h3>
      <div className="lms-card" aria-label="Late Policy Details">
        <p><strong>Penalty per day:</strong> {(parseFloat(latePolicy.penalty_per_day) * 100).toFixed(0)}% per day</p>
        <p><strong>Max late days:</strong> {latePolicy.max_late_days}</p>
        <p><strong>Grace period:</strong> {latePolicy.grace_period_hours} hours</p>
      </div>

      <h3 style={{ marginTop: "1.5rem" }}>Important Dates</h3>
      <div className="lms-card" aria-label="Important Dates">
        <p><strong>Drop deadline:</strong> {new Date(course.drop_deadline).toLocaleDateString()}</p>
        <p><strong>Final exam:</strong> {new Date(course.final_exam_date).toLocaleDateString()}</p>
      </div>
    </section>
  );
}
