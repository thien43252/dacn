export interface FieldErrors {
  name?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
  if (password.length < 8 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password)) {
    errors.password = "Dùng ít nhất 8 ký tự, gồm chữ hoa, chữ thường và số.";
  }
  if (confirmPassword !== password) {
    errors.confirmPassword = "Mật khẩu xác nhận chưa khớp.";
  }
  return errors;
}
