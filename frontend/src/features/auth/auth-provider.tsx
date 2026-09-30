"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { singleTab } from "@/features/single-tab";
import * as client from "@/lib/api/client";
import type { Me, Permission, TokenOut } from "@/lib/api/types";
import { PERM } from "@/lib/labels";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: Status;
  user: Me | null;
  can: (permission: Permission) => boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  homePath: string;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function homePathFor(user: Me | null): string {
  if (!user) return "/login";
  return user.permissions.includes(PERM.dashboard) ? "/dashboard" : "/tickets";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<Me | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRefresh = useCallback((expiresIn: number) => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    // Renovamos un minuto antes de que expire el access token.
    const ms = Math.max(10, expiresIn - 60) * 1000;
    refreshTimer.current = setTimeout(() => void client.refreshSession(), ms);
  }, []);

  const applySession = useCallback(
    (token: TokenOut) => {
      setUser(token.user);
      setStatus("authenticated");
      scheduleRefresh(token.expires_in);
    },
    [scheduleRefresh],
  );

  const clearSession = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    singleTab.stop();
    client.tokenStore.set(null);
    queryClient.clear();
    setUser(null);
    setStatus("anonymous");
  }, [queryClient]);

  // Arranque: la cookie httpOnly de refresh (si existe) nos da un access token nuevo.
  useEffect(() => {
    let cancelled = false;
    void client.refreshSession().then((token) => {
      if (cancelled) return;
      if (token) applySession(token);
      else setStatus("anonymous");
    });
    return () => {
      cancelled = true;
    };
  }, [applySession]);

  useEffect(() => {
    const offRefreshed = client.authEvents.on("session-refreshed", (detail) =>
      applySession(detail as TokenOut),
    );
    const offExpired = client.authEvents.on("session-expired", () => {
      clearSession();
      toast.error("Tu sesión expiró. Inicia sesión de nuevo.");
    });
    const offConflict = client.authEvents.on("tab-conflict", () => singleTab.conflict());
    return () => {
      offRefreshed();
      offExpired();
      offConflict();
    };
  }, [applySession, clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const token = await client.login(email, password);
      queryClient.clear();
      applySession(token);
      return token.user;
    },
    [applySession, queryClient],
  );

  const logout = useCallback(async () => {
    singleTab.stop();
    await client.logout();
    clearSession();
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      can: (permission) => Boolean(user?.permissions.includes(permission)),
      login,
      logout,
      homePath: homePathFor(user),
    }),
    [status, user, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}

/** Renderiza hijos solo si el usuario tiene el permiso. */
export function Can({
  permission,
  children,
  fallback = null,
}: {
  permission: Permission;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { can } = useAuth();
  return <>{can(permission) ? children : fallback}</>;
}
