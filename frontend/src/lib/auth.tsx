"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiGet, getToken, setToken, clearToken } from "./api";
import type { Me } from "./types";

interface AuthContextValue {
  isAuthenticated: boolean;
  me: Me | null;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Initialize synchronously from the stored token so a page load with a
  // valid session starts authenticated — no false-false race that would
  // redirect a protected route to /login before the effect runs.
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => Boolean(getToken()),
  );
  const [me, setMe] = useState<Me | null>(null);

  // Fetch the caller's identity once (name + role) for the navbar and any
  // role-aware UI. /auth/me is behind the global gate, so it only succeeds
  // with a valid token.
  useEffect(() => {
    if (!isAuthenticated) return;
    apiGet<Me>("/auth/me")
      .then(setMe)
      .catch(() => setMe(null));
  }, [isAuthenticated]);

  const login = useCallback((token: string) => {
    setToken(token);
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setIsAuthenticated(false);
    setMe(null);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, me, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
