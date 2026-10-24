import { getHomePath, navigate } from "../app/router";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/Icon";
import { Logo } from "../components/Logo";

export function ForbiddenPage() {
  const { user } = useAuth();
  return <main className="system-page"><Logo /><div className="system-card frosted"><span className="soft-icon soft-icon--large"><Icon name="lock" /></span><span className="eyebrow">403 · KHÔNG ĐỦ QUYỀN</span><h1>Bạn không có quyền mở trang này.</h1><p>Hãy quay về trang chính của bạn hoặc đăng nhập bằng tài khoản có quyền truy cập.</p><button className="button button--primary" type="button" onClick={() => navigate(user ? getHomePath(user.role) : "/login", true)}>Về trang chính <Icon name="arrow-right" /></button></div></main>;
}
