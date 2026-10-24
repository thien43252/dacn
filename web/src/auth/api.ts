import { ApiError, apiRequest } from "../api-client/http";

export { ApiError };

export type Role = "teacher" | "student" | "parent" | "admin";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload extends LoginPayload {
  name: string;
  /** Admin accounts are seeded, never self-registered. */
  role: Exclude<Role, "admin">;
}

interface AuthResponse {
  user: User;
}

export async function getSession(): Promise<User | null> {
  try {
    const response = await apiRequest<AuthResponse>("/api/auth/session");
    return response.user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

export async function login(payload: LoginPayload): Promise<User> {
  const response = await apiRequest<AuthResponse>("/api/auth/login", { method: "POST", body: payload });
  return response.user;
}

export async function register(payload: RegisterPayload): Promise<User> {
  const response = await apiRequest<AuthResponse>("/api/auth/register", { method: "POST", body: payload });
  return response.user;
}

export async function logout(): Promise<void> {
  await apiRequest<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}
