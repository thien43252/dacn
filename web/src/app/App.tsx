import { lazy, Suspense, useEffect } from "react";

import { useAuth } from "../auth/AuthContext";
import { LoadingScreen } from "../components/LoadingScreen";
import { AuthPage } from "../pages/AuthPage";
import { ForbiddenPage } from "../pages/ForbiddenPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { WorkspacePage } from "../pages/WorkspacePage";
import { WelcomeGate } from "../welcome/WelcomeGate";
import { canAccessPath, getHomePath, isWorkspacePath, navigate, useLocation } from "./router";

const MakerLandingPage = lazy(() => import("../pages/MakerLandingPage").then((page) => ({ default: page.MakerLandingPage })));

export function App() {
  return <WelcomeGate><AppRoutes /></WelcomeGate>;
}

function AppRoutes() {
  const { pathname, search } = useLocation();
  const { status, user } = useAuth();
  const isWorkspace = isWorkspacePath(pathname);

  useEffect(() => {
    if (status === "guest" && isWorkspace) {
      navigate(`/login?next=${encodeURIComponent(pathname)}`, true);
    }
  }, [isWorkspace, pathname, status]);

  useEffect(() => {
    if (status === "authenticated" && user && (pathname === "/login" || pathname === "/register")) {
      const requested = new URLSearchParams(search).get("next");
      const target = requested && canAccessPath(user.role, requested) ? requested : getHomePath(user.role);
      navigate(target, true);
    }
  }, [pathname, search, status, user]);

  if (status === "loading") {
    return <LoadingScreen label="Đang mở không gian làm việc" />;
  }

  if (status === "guest" && isWorkspace) {
    return <LoadingScreen label="Đang chuyển đến trang đăng nhập" />;
  }

  if (pathname === "/") {
    return <Suspense fallback={<LoadingScreen label="Đang mở EduAgent Hub" />}><MakerLandingPage /></Suspense>;
  }

  if (pathname === "/login" || pathname === "/register") {
    return <AuthPage mode={pathname === "/register" ? "register" : "login"} />;
  }

  if (isWorkspace && user) {
    return canAccessPath(user.role, pathname) ? <WorkspacePage pathname={pathname} /> : <ForbiddenPage />;
  }

  if (pathname === "/forbidden") {
    return <ForbiddenPage />;
  }

  return <NotFoundPage />;
}
