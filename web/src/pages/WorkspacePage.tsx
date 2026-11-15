import type { ReactNode } from "react";

import { type MatchedRoute, matchRoute } from "../app/routes";
import { useLocation } from "../app/router";
import { AppShell } from "../components/AppShell";
import { BuilderPage } from "../features/agents/BuilderPage";
import { HubPage } from "../features/agents/HubPage";
import { MyAgentsPage } from "../features/agents/MyAgentsPage";
import { ToolsPage } from "../features/agents/ToolsPage";
import { AdminAuditPage, TeacherAuditPage } from "../features/audit/AuditPages";
import { AdminCertificationPage } from "../features/certify/AdminCertificationPage";
import { ClassDetailPage } from "../features/classes/ClassDetailPage";
import { LessonView } from "../features/lms/LessonView";
import { QuizEditor } from "../features/lms/QuizEditor";
import { QuizTake } from "../features/lms/QuizTake";
import { QuizResult } from "../features/lms/QuizResult";
import { AssignmentEditor } from "../features/lms/AssignmentEditor";
import { AssignmentView } from "../features/lms/AssignmentView";
import { TodoPage } from "../features/lms/TodoPage";
import { MyGradesPage } from "../features/lms/MyGradesPage";
import { StudentHomePage } from "../features/classes/StudentHomePage";
import { StudentClassesPage } from "../features/classes/StudentClassesPage";
import { TeacherClassesPage } from "../features/classes/TeacherClassesPage";
import { ParentConsentPage, ParentHomePage } from "../features/family/ParentPages";
import { ParentReportsPage } from "../features/reports/ReportPages";
import { ChatHomePage } from "../features/chat/ChatHomePage";
import { InboxPage } from "../features/inbox/InboxPage";
import { ApprovalSettingsPage } from "../features/settings/ApprovalSettings";
import { AdminApprovalsPage } from "../features/settings/AdminApprovalsPage";
import { AgentActivityPage, MyActivityPage } from "../features/agents/AgentActivityPage";
import { NotFoundPage } from "./NotFoundPage";
import { PlaceholderPage } from "./PlaceholderPage";

/** Screens that exist so far; every other route shows its placeholder with the plan week it lands in. */
const screens: Record<string, (route: MatchedRoute) => ReactNode> = {
  "/teacher/classes": () => <TeacherClassesPage />,
  "/teacher/classes/:classId": ({ params }) => <ClassDetailPage key={params.classId} classId={params.classId} />,
  "/teacher/classes/:classId/lessons/:lessonId": ({ params }) => (
    <LessonView key={params.lessonId} classId={params.classId} lessonId={params.lessonId} />
  ),
  "/teacher/classes/:classId/quizzes/:quizId": ({ params }) => (
    <QuizEditor key={params.quizId} classId={params.classId} quizId={params.quizId} />
  ),
  "/teacher/classes/:classId/assignments/:assignmentId": ({ params }) => (
    <AssignmentEditor key={params.assignmentId} classId={params.classId} assignmentId={params.assignmentId} />
  ),
  "/teacher/hub": () => <HubPage />,
  "/teacher/builder": () => <BuilderPage />,
  "/teacher/audit": () => <TeacherAuditPage />,
  "/student/home": () => <StudentHomePage />,
  "/student/todo": () => <TodoPage />,
  "/student/classes": () => <StudentClassesPage />,
  "/student/classes/:classId": ({ params }) => <ClassDetailPage key={params.classId} classId={params.classId} />,
  "/student/classes/:classId/grades": ({ params }) => (
    <MyGradesPage key={params.classId} classId={params.classId} />
  ),
  "/student/classes/:classId/lessons/:lessonId": ({ params }) => (
    <LessonView key={params.lessonId} classId={params.classId} lessonId={params.lessonId} />
  ),
  "/student/classes/:classId/quizzes/:quizId/take": ({ params }) => (
    <QuizTake key={params.quizId} classId={params.classId} quizId={params.quizId} />
  ),
  "/student/classes/:classId/quizzes/:quizId": ({ params }) => (
    <QuizResult key={params.quizId} classId={params.classId} quizId={params.quizId} role="student" overview />
  ),
  "/student/classes/:classId/quizzes/:quizId/result": ({ params }) => (
    <QuizResult key={params.quizId} classId={params.classId} quizId={params.quizId} role="student" />
  ),
  "/student/classes/:classId/assignments/:assignmentId": ({ params }) => (
    <AssignmentView key={params.assignmentId} classId={params.classId} assignmentId={params.assignmentId} role="student" />
  ),
  "/student/hub": () => <HubPage />,
  "/student/agents": () => <MyAgentsPage />,
  "/parent/classes/:classId": ({ params }) => <ClassDetailPage key={params.classId} classId={params.classId} />,
  "/parent/classes/:classId/lessons/:lessonId": ({ params }) => (
    <LessonView key={params.lessonId} classId={params.classId} lessonId={params.lessonId} />
  ),
  "/parent/classes/:classId/quizzes/:quizId": ({ params }) => (
    <QuizResult key={`${params.quizId}:${params.studentId}`} classId={params.classId} quizId={params.quizId} role="parent" studentId={params.studentId} overview />
  ),
  "/parent/classes/:classId/assignments/:assignmentId": ({ params }) => (
    <AssignmentView key={`${params.assignmentId}:${params.studentId}`} classId={params.classId} assignmentId={params.assignmentId} role="parent" studentId={params.studentId} />
  ),
  "/parent/hub": () => <HubPage />,
  "/admin/agents": () => <HubPage />,
  "/admin/tools": () => <ToolsPage />,
  "/admin/certification": () => <AdminCertificationPage />,
  "/admin/audit": () => <AdminAuditPage />,
  "/parent/home": () => <ParentHomePage />,
  "/parent/consent": () => <ParentConsentPage />,
  "/parent/reports": () => <ParentReportsPage />,
  // Feature 003: Messenger-style chat, inbox, approval settings, builder for every role.
  ...Object.fromEntries(
    ["teacher", "student", "parent"].flatMap((role) => [
      [`/${role}/chat`, () => <ChatHomePage />],
      [`/${role}/inbox`, () => <InboxPage />],
      [`/${role}/settings/approvals`, () => <ApprovalSettingsPage />],
      [
        `/${role}/builder/activity/:agentId`,
        ({ params }: MatchedRoute) => <AgentActivityPage key={params.agentId} agentId={params.agentId} backTo={`/${role}/builder?agent=${encodeURIComponent(params.agentId)}`} />,
      ],
    ]),
  ),
  "/student/builder": () => <BuilderPage />,
  "/parent/builder": () => <BuilderPage />,
  "/student/activity": () => <MyActivityPage />,
  "/parent/activity": () => <MyActivityPage />,
  "/admin/approvals": () => <AdminApprovalsPage />,
};

export function WorkspacePage({ pathname }: { pathname: string }) {
  const { search } = useLocation();
  const matched = matchRoute(pathname);
  if (!matched) return <NotFoundPage />;
  const studentId = new URLSearchParams(search).get("student_id");
  if (studentId) matched.params.studentId = studentId;
  const { meta } = matched;
  const screen = screens[meta.pattern];

  return (
    <AppShell pathname={pathname} pattern={meta.pattern} title={meta.title} eyebrow={meta.eyebrow} description={meta.description} classId={matched.params.classId}
      fillHeight={meta.pattern.endsWith("/chat")}>
      {screen ? screen(matched) : <PlaceholderPage title={meta.title} week={meta.week} />}
    </AppShell>
  );
}
