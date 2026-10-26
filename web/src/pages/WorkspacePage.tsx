import type { ReactNode } from "react";

import { type MatchedRoute, matchRoute } from "../app/routes";
import { AppShell } from "../components/AppShell";
import { BuilderPage } from "../features/agents/BuilderPage";
import { HubPage } from "../features/agents/HubPage";
import { MyAgentsPage } from "../features/agents/MyAgentsPage";
import { ToolsPage } from "../features/agents/ToolsPage";
import { AdminAuditPage, TeacherAuditPage } from "../features/audit/AuditPages";
import { AdminCertificationPage } from "../features/certify/AdminCertificationPage";
import { ClassDetailPage } from "../features/classes/ClassDetailPage";
import { StudentHomePage } from "../features/classes/StudentHomePage";
import { StudentClassesPage } from "../features/classes/StudentClassesPage";
import { TeacherClassesPage } from "../features/classes/TeacherClassesPage";
import { ParentConsentPage, ParentHomePage } from "../features/family/ParentPages";
import { ParentReportsPage } from "../features/reports/ReportPages";
import { NotFoundPage } from "./NotFoundPage";
import { PlaceholderPage } from "./PlaceholderPage";

/** Screens that exist so far; every other route shows its placeholder with the plan week it lands in. */
const screens: Record<string, (route: MatchedRoute) => ReactNode> = {
  "/teacher/classes": () => <TeacherClassesPage />,
  "/teacher/classes/:classId": ({ params }) => <ClassDetailPage key={params.classId} classId={params.classId} />,
  "/teacher/hub": () => <HubPage />,
  "/teacher/builder": () => <BuilderPage />,
  "/teacher/audit": () => <TeacherAuditPage />,
  "/student/home": () => <StudentHomePage />,
  "/student/classes": () => <StudentClassesPage />,
  "/student/hub": () => <HubPage />,
  "/student/agents": () => <MyAgentsPage />,
  "/parent/hub": () => <HubPage />,
  "/admin/agents": () => <HubPage />,
  "/admin/tools": () => <ToolsPage />,
  "/admin/certification": () => <AdminCertificationPage />,
  "/admin/audit": () => <AdminAuditPage />,
  "/parent/home": () => <ParentHomePage />,
  "/parent/consent": () => <ParentConsentPage />,
  "/parent/reports": () => <ParentReportsPage />,
};

export function WorkspacePage({ pathname }: { pathname: string }) {
  const matched = matchRoute(pathname);
  if (!matched) return <NotFoundPage />;
  const { meta } = matched;
  const screen = screens[meta.pattern];

  return (
    <AppShell pathname={pathname} pattern={meta.pattern} title={meta.title} eyebrow={meta.eyebrow} description={meta.description} classId={matched.params.classId}>
      {screen ? screen(matched) : <PlaceholderPage title={meta.title} week={meta.week} />}
    </AppShell>
  );
}
