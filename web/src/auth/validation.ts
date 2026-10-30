export interface FieldErrors {
  name?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Password rules, shown live while registering; mirror backend/app/auth/schemas.py. */
export const PASSWORD_RULES: { label: string; test: (password: string) => boolean }[] = [
  { label: "Ít nhất 8 ký tự", test: (password) => password.length >= 8 },
  { label: "Có chữ hoa (A–Z)", test: (password) => /[A-Z]/.test(password) },
  { label: "Có chữ thường (a–z)", test: (password) => /[a-z]/.test(password) },
  { label: "Có chữ số (0–9)", test: (password) => /\d/.test(password) },
];

export function validateLogin(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!EMAIL_PATTERN.test(email.trim())) {
    errors.email = "Nhập email đúng định dạng.";
  }
  if (!password) {
    errors.password = "Nhập mật khẩu.";
  }
  return errors;
}

export function validateRegistration(
  name: string,
  email: string,
  password: string,
  confirmPassword: string,
): FieldErrors {
  const errors = validateLogin(email, password);
  if (name.trim().length < 2) {
    errors.name = "Tên cần có ít nhất 2 ký tự.";
  }
  if (!PASSWORD_RULES.every((rule) => rule.test(password))) {
    errors.password = "Dùng ít nhất 8 ký tự, gồm chữ hoa, chữ thường và số.";
  }
  if (confirmPassword !== password) {
    errors.confirmPassword = "Mật khẩu xác nhận chưa khớp.";
  }
  return errors;
}
