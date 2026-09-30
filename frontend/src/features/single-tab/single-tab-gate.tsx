"use client";

import { AppWindow, Loader2, MonitorSmartphone } from "lucide-react";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";

import { singleTab, type SingleTabState } from ".";

const SERVER_STATE: SingleTabState = { status: "idle", otherDevice: false };

export function useSingleTab(): SingleTabState {
  return useSyncExternalStore(singleTab.subscribe, singleTab.getState, () => SERVER_STATE);
}

/** Envuelve la app: si el rol exige pestaña única, bloquea hasta confirmar que esta es la activa. */
export function SingleTabGate({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const required = Boolean(user?.role.single_tab_session);
  const state = useSingleTab();

  useEffect(() => {
    if (required) singleTab.start();
    else singleTab.stop();
  }, [required]);

  if (!required || state.status === "active") return <>{children}</>;

  if (state.status === "idle" || state.status === "checking") {
    return (
      <div className="grid min-h-dvh place-items-center">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Verificando pestaña activa…
        </div>
      </div>
    );
  }

  const displaced = state.status === "displaced";
  const Icon = state.otherDevice ? MonitorSmartphone : AppWindow;
  return (
    <div className="grid min-h-dvh place-items-center bg-muted/40 p-6">
      <div
        role="alertdialog"
        aria-labelledby="single-tab-title"
        className="w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-lg"
      >
        <div className="mx-auto mb-4 grid size-12 place-items-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
          <Icon className="size-6" />
        </div>
        <h1 id="single-tab-title" className="text-lg font-semibold">
          {displaced ? "Tu sesión se movió a otra pestaña" : "Ya tienes una pestaña abierta"}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {displaced
            ? "Tu rol solo permite trabajar en una pestaña a la vez. Esta pestaña quedó en pausa."
            : state.otherDevice
              ? "Tu sesión está activa en otro navegador o dispositivo. Si continúas aquí, esa sesión se cerrará."
              : "Tu rol solo permite trabajar en una pestaña a la vez. Puedes continuar aquí y la otra pestaña quedará en pausa."}
        </p>
        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
          <Button onClick={() => singleTab.takeover()}>Usar aquí</Button>
          <Button variant="outline" onClick={() => void logout()}>
            Cerrar sesión
          </Button>
        </div>
      </div>
    </div>
  );
}
