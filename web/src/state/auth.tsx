import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export interface SessionUser {
  analyst_id: string;
  name: string;
  role: "analyst" | "detection_engineer";
}

interface AuthState {
  user: SessionUser | null;
  status: "loading" | "authenticated" | "anonymous";
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

async function fetchMe(): Promise<SessionUser | null> {
  const res = await fetch("/api/v1/auth/me", { credentials: "include" });
  if (!res.ok) return null;
  return res.json();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  useEffect(() => {
    fetchMe().then((u) => {
      setUser(u);
      setStatus(u ? "authenticated" : "anonymous");
    });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const problem = await res.json().catch(() => null);
      throw new Error(problem?.detail ?? "Login failed.");
    }
    const body = await res.json();
    setUser(body.user);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
    setUser(null);
    setStatus("anonymous");
  }, []);

  return <AuthContext.Provider value={{ user, status, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
