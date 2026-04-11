import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@webagentbench/shared";

import { useLmsLayout } from "../context";
import type { Course, Grade } from "../types";

interface CourseWithGrades {
  course: Course;
  weightedScore: string | null;
}

export function CoursesPage() {
  const { api } = useLmsLayout();
  const location = useLocation();
  const [coursesData, setCoursesData] = useState<CourseWithGrades[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const courses = await api.listCourses();
        const results: CourseWithGrades[] = [];
        for (const course of courses) {
          try {
            const gradesData = await api.getCourseGrades(course.id);
            results.push({
              course,
              weightedScore: gradesData.weighted_score,
            });
          } catch {
            results.push({ course, weightedScore: null });
          }
        }
        if (!cancelled) setCoursesData(results);
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api]);

  if (loading) return <div className="lms-loading">Loading...</div>;

  return (
    <div aria-label="Courses">
      <h1 className="lms-section-header">Courses</h1>
      {coursesData.length === 0 ? (
        <p className="lms-empty">No enrolled courses</p>
      ) : (
        <div className="lms-grid">
          {coursesData.map(({ course, weightedScore }) => (
            <Link
              key={course.id}
              to={preserveQueryParams(`/courses/${course.id}`, location.search)}
              className="lms-card"
              style={{ textDecoration: "none", color: "inherit" }}
              aria-label={`Course ${course.course_code} ${course.title}`}
            >
              <div className="lms-card__title">{course.course_code}</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 500, margin: "0.25rem 0" }}>
                {course.title}
              </div>
              <div style={{ fontSize: "0.85rem", color: "#666" }}>
                {course.instructor_name}
              </div>
              <div style={{ fontSize: "0.85rem", color: "#666" }}>
                {course.semester} -- {course.credits} credits
              </div>
              {weightedScore !== null && (
                <div
                  style={{ marginTop: "0.5rem", fontWeight: 600 }}
                  aria-label={`Current grade ${weightedScore}%`}
                >
                  Grade: {weightedScore}%
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
