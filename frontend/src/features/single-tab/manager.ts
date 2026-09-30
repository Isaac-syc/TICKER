/**
 * Regla "una sola pestaña" para roles con single_tab_session (p. ej. observador).
 *
 * Dos capas:
 * 1. Navegador: Web Locks API. Solo una pestaña del mismo origen puede tener el lock; si se
 *    cierra, el navegador lo libera solo. "Usar aquí" lo roba (`steal`), y la pestaña anterior
 *    recibe un AbortError → se congela.
 * 2. Servidor (fuente de verdad): lease en Redis por usuario con heartbeat. Cubre otros
 *    navegadores/dispositivos y que alguien desactive JS o manipule el front.
 *
 * Es un singleton de módulo (no depende del ciclo de vida de React), así el doble montaje de
 * StrictMode no provoca bloqueos falsos.
 */

export type SingleTabStatus = "idle" | "checking" | "active" | "blocked" | "displaced";

export interface SingleTabState {
  status: SingleTabStatus;
  otherDevice: boolean;
}

export interface LeaseResult {
  required: boolean;
  granted: boolean;
  other_device: boolean;
}

export interface SingleTabDeps {
  tabId: string;
  claim: () => Promise<LeaseResult>;
  takeover: () => Promise<LeaseResult>;
  release: () => void;
  locks?: LockManager;
  createChannel?: (name: string) => BroadcastChannel;
  heartbeatMs?: number;
}

const LOCK_NAME = "hd-single-tab";
const CHANNEL_NAME = "hd-single-tab";

export function createSingleTabManager(deps: SingleTabDeps) {
  let state: SingleTabState = { status: "idle", otherDevice: false };
  const listeners = new Set<() => void>();
  let started = false;
  let releaseHold: (() => void) | null = null;
  let heartbeat: ReturnType<typeof setInterval> | null = null;
  let channel: BroadcastChannel | null = null;
  // Cada intento de adquisición tiene un id; los callbacks de intentos viejos se ignoran.
  let attempt = 0;

  const set = (next: Partial<SingleTabState>) => {
    state = { ...state, ...next };
    listeners.forEach((l) => l());
  };

  const stopHeartbeat = () => {
    if (heartbeat) clearInterval(heartbeat);
    heartbeat = null;
  };

  const dropLock = () => {
    releaseHold?.();
    releaseHold = null;
  };

  const displace = () => {
    if (state.status === "idle") return;
    attempt++;
    stopHeartbeat();
    dropLock();
    set({ status: "displaced", otherDevice: false });
  };

  const beat = async () => {
    try {
      const res = await deps.claim();
      if (!res.granted) displace();
    } catch {
      /* errores de red: se reintenta en el siguiente latido */
    }
  };

  const startHeartbeat = () => {
    stopHeartbeat();
    heartbeat = setInterval(beat, deps.heartbeatMs ?? 20_000);
  };

  /** Pide el lease al servidor. Devuelve true si esta pestaña quedó activa. */
  const serverClaim = async (steal: boolean, id: number): Promise<boolean> => {
    try {
      const res = steal ? await deps.takeover() : await deps.claim();
      if (id !== attempt) return false;
      if (res.granted || !res.required) {
        set({ status: "active", otherDevice: false });
        startHeartbeat();
        if (steal) channel?.postMessage({ type: "takeover", tabId: deps.tabId });
        return true;
      }
      set({ status: "blocked", otherDevice: res.other_device });
      return false;
    } catch {
      if (id === attempt) set({ status: "blocked", otherDevice: false });
      return false;
    }
  };

  const acquire = (steal: boolean) => {
    const id = ++attempt;
    set({ status: "checking" });
    if (!deps.locks) {
      void serverClaim(steal, id);
      return;
    }
    const options: LockOptions = steal ? { steal: true } : { ifAvailable: true };
    deps.locks
      .request(LOCK_NAME, options, async (lock) => {
        if (id !== attempt) return;
        if (!lock) {
          set({ status: "blocked", otherDevice: false });
          return;
        }
        const ok = await serverClaim(steal, id);
        if (!ok) return; // al salir del callback se libera el lock
        await new Promise<void>((resolve) => {
          releaseHold = resolve;
        });
      })
      .catch((err: unknown) => {
        // Otra pestaña hizo "Usar aquí" y nos robó el lock.
        if (id === attempt && (err as Error)?.name === "AbortError") displace();
      });
  };

  const onPageHide = () => {
    if (state.status === "active") deps.release();
  };

  const onVisible = () => {
    if (document.visibilityState === "visible" && state.status === "active") void beat();
  };

  return {
    getState: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    start() {
      if (started) return;
      started = true;
      channel = deps.createChannel?.(CHANNEL_NAME) ?? null;
      channel?.addEventListener("message", (e: MessageEvent<{ type: string; tabId: string }>) => {
        if (e.data?.type === "takeover" && e.data.tabId !== deps.tabId) displace();
      });
      if (typeof window !== "undefined") {
        window.addEventListener("pagehide", onPageHide);
        document.addEventListener("visibilitychange", onVisible);
      }
      acquire(false);
    },
    /** "Usar aquí". */
    takeover() {
      dropLock();
      acquire(true);
    },
    /** El servidor rechazó una petición por TAB_CONFLICT. */
    conflict() {
      if (state.status === "active" || state.status === "checking") displace();
    },
    stop() {
      if (!started) return;
      if (state.status === "active") deps.release();
      started = false;
      attempt++;
      stopHeartbeat();
      dropLock();
      channel?.close();
      channel = null;
      if (typeof window !== "undefined") {
        window.removeEventListener("pagehide", onPageHide);
        document.removeEventListener("visibilitychange", onVisible);
      }
      set({ status: "idle", otherDevice: false });
    },
  };
}

export type SingleTabManager = ReturnType<typeof createSingleTabManager>;
