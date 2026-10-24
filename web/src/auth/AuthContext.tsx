import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

import * as authApi from "./api";
import { endWelcome, startWelcome } from "../welcome/welcomeStore";
import type { LoginPayload, RegisterPayload, User } from "./api";

type AuthStatus = "loading" | "guest" | "authenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  login: (payload: LoginPayload) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    let active = true;
    authApi
      .getSession()
      .then((sessionUser) => {
        if (!active) return;
        setUser(sessionUser);
        setStatus(sessionUser ? "authenticated" : "guest");
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
        setStatus("guest");
      });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login: async (payload) => {
        const nextUser = await authApi.login(payload);
        // Before the user state that lets the destination render: the cover must exist in that first frame.
        startWelcome(nextUser);
        setUser(nextUser);
        setStatus("authenticated");
        return nextUser;
      },
      register: async (payload) => {
        const nextUser = await authApi.register(payload);
        startWelcome(nextUser);
        setUser(nextUser);
        setStatus("authenticated");
        return nextUser;
      },
      logout: async () => {
        await authApi.logout();
        endWelcome();
        setUser(null);
        setStatus("guest");
      },
    }),
    [status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
