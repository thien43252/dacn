import { type FormEvent, useMemo, useState } from "react";

import { canAccessPath, getHomePath, navigate } from "../app/router";
import { useAuth } from "../auth/AuthContext";
import { ApiError, type RegisterPayload } from "../auth/api";
import { validateLogin, validateRegistration, type FieldErrors } from "../auth/validation";
import { Icon } from "../components/Icon";
import { Logo } from "../components/Logo";
import { HeroStudent } from "../components/HeroStudent";
import "../styles/auth-blue-maker.css";

type RegisterRole = RegisterPayload["role"];

/** Demo accounts created by `backend/scripts/seed_demo.py`. Local synthetic data only. */
const TEST_ACCOUNTS = [
  { label: "Giáo viên", name: "Cô Nguyễn Thu Hà", email: "teacher@demo.edu.vn", password: "Demo123!" },
  { label: "Học sinh", name: "Nguyễn Minh Anh", email: "student@demo.edu.vn", password: "Demo123!" },
  { label: "Phụ huynh", name: "Nguyễn Văn Bình", email: "parent@demo.edu.vn", password: "Demo123!" },
  { label: "Quản trị viên", name: "Quản trị viên", email: "admin@demo.edu.vn", password: "Demo123!" },
];

const REGISTER_ROLES: { value: RegisterRole; label: string }[] = [
  { value: "teacher", label: "Giáo viên" },
  { value: "student", label: "Học sinh" },
  { value: "parent", label: "Phụ huynh" },
];

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const [name, setName] = useState("");
  const [role, setRole] = useState<RegisterRole>("teacher");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const isRegister = mode === "register";
  const heading = useMemo(() => isRegister ? "Tạo tài khoản" : "Chào mừng bạn trở lại.", [isRegister]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors = isRegister
      ? validateRegistration(name, email, password, confirmPassword)
      : validateLogin(email, password);
    setErrors(nextErrors);
    setServerError("");
    if (Object.keys(nextErrors).length > 0) return;

    await signIn(() => isRegister
      ? register({ name: name.trim(), email: email.trim(), password, role })
      : login({ email: email.trim(), password }));
  }

  async function loginAs(account: { email: string; password: string }) {
    setEmail(account.email);
    setPassword(account.password);
    setErrors({});
    setServerError("");
    await signIn(() => login({ email: account.email, password: account.password }));
  }

  async function signIn(request: () => ReturnType<typeof login>) {
    setSubmitting(true);
    // Read before the request: once auth state flips, App's own redirect may already have consumed the query.
    const requested = new URLSearchParams(window.location.search).get("next");
    try {
      const user = await request();
      navigate(requested && canAccessPath(user.role, requested) ? requested : getHomePath(user.role), true);
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Kết nối gián đoạn. Vui lòng thử lại.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-story">
        <Logo inverse />
        <div className="auth-story__content">
          <span className="eyebrow eyebrow--light">EDUAGENT HUB</span>
          <h1>Mỗi lớp học<br />đều xứng đáng có<br /><em>trợ giảng tốt.</em></h1>
          <p>Tạo lớp, chọn agent đã kiểm định và đồng hành cùng học sinh, phụ huynh.</p>
        </div>
        <div className="auth-story__art"><HeroStudent scope="auth" props={["open"]} /></div>
        <div className="auth-story__quote"><Icon name="sparkles" /><span>“AI gợi ý.<br />Người học tự làm.”</span></div>
      </section>

      <section className={isRegister ? "auth-form-wrap" : "auth-form-wrap auth-form-wrap--login"}>
        <button className="back-link" type="button" onClick={() => navigate("/")}><Icon name="chevron-left" /> Trang giới thiệu</button>
        <div className="auth-form-card">
          <span className="eyebrow">{isRegister ? "TÀI KHOẢN MỚI" : "EDUAGENT HUB"}</span>
          <h2>{heading}</h2>
          <p>{isRegister ? "Chọn vai trò của bạn. Vai trò trong từng lớp do giáo viên quản lý." : "Đăng nhập để vào lớp học của bạn."}</p>

          <form onSubmit={submit} noValidate>
            {isRegister && <label className="field"><span>Họ và tên</span><input autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Nguyễn Minh Anh" aria-invalid={Boolean(errors.name)} />{errors.name && <small className="field__error">{errors.name}</small>}</label>}
            {isRegister && (
              <div className="field">
                <span>Bạn là</span>
                <div className="test-accounts__list" role="radiogroup" aria-label="Vai trò">
                  {REGISTER_ROLES.map((option) => (
                    <button key={option.value} type="button" role="radio" aria-checked={role === option.value}
                      className={`test-accounts__row${role === option.value ? " is-active" : ""}`} onClick={() => setRole(option.value)}>
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <label className="field"><span>Email</span><input autoComplete="email" inputMode="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="ban@email.com" aria-invalid={Boolean(errors.email)} />{errors.email && <small className="field__error">{errors.email}</small>}</label>
            <label className="field"><span>Mật khẩu</span><input autoComplete={isRegister ? "new-password" : "current-password"} type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Ít nhất 8 ký tự" aria-invalid={Boolean(errors.password)} />{errors.password && <small className="field__error">{errors.password}</small>}</label>
            {isRegister && <label className="field"><span>Xác nhận mật khẩu</span><input autoComplete="new-password" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Nhập lại mật khẩu" aria-invalid={Boolean(errors.confirmPassword)} />{errors.confirmPassword && <small className="field__error">{errors.confirmPassword}</small>}</label>}
            {serverError && <div className="form-error" role="alert">{serverError}</div>}
            <button className="button button--primary button--full" type="submit" disabled={submitting}>{submitting ? <><span className="button-spinner" /> Đang xử lý</> : <>{isRegister ? "Tạo tài khoản" : "Đăng nhập"} <Icon name="arrow-right" /></>}</button>
          </form>

          {!isRegister && (
            <div className="test-accounts">
              <strong>Tài khoản dùng thử</strong>
              <div className="test-accounts__list">
                {TEST_ACCOUNTS.map((account) => (
                  <button key={account.email} type="button" className="test-accounts__row" disabled={submitting} title={`${account.name} · ${account.email}`} onClick={() => void loginAs(account)}>
                    {account.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="auth-switch">{isRegister ? "Đã có tài khoản?" : "Chưa có tài khoản?"} <button type="button" onClick={() => navigate(isRegister ? "/login" : "/register")}>{isRegister ? "Đăng nhập" : "Tạo tài khoản"}</button></p>
        </div>
      </section>
    </main>
  );
}
