/**
 * Cliente HTTP tipado (openapi-fetch) con:
 * - access token solo en memoria (nunca en localStorage) → reduce el impacto de un XSS;
 * - refresh "single-flight" y serializado entre pestañas con Web Locks (evita que dos pestañas
 *   roten el mismo refresh token a la vez);
 * - header X-Tab-Id en cada petición para la regla de pestaña única;
 * - eventos globales para sesión expirada y conflicto de pestaña.
 */
import createClient from "openapi-fetch";

import type { paths } from "./schema";
import type { ErrorOut, TokenOut } from "./types";

function newTabId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Identificador de esta pestaña. Vive en memoria: "duplicar pestaña" genera uno nuevo. */
export const TAB_ID = newTabId();

let accessToken: string | null = null;
export const tokenStore = {
  get: () => accessToken,
  set: (token: string | null) => {
    accessToken = token;
  },
};

type AuthEventName = "session-expired" | "session-refreshed" | "tab-conflict";
const bus = typeof window !== "undefined" ? new EventTarget() : null;

export const authEvents = {
  emit(name: AuthEventName, detail?: unknown) {
    bus?.dispatchEvent(new CustomEvent(name, { detail }));
  },
  on(name: AuthEventName, handler: (detail: unknown) => void): () => void {
    const listener = (e: Event) => handler((e as CustomEvent).detail);
    bus?.addEventListener(name, listener);
    return () => bus?.removeEventListener(name, listener);
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const CSRF_HEADER = { "X-Requested-With": "helpdesk" };

function withCrossTabLock<T>(name: string, fn: () => Promise<T>): Promise<T> {
  if (typeof navigator !== "undefined" && navigator.locks?.request) {
    return navigator.locks.request(name, fn) as Promise<T>;
  }
  return fn();
}

let refreshing: Promise<TokenOut | null> | null = null;

/** Rota el refresh token (cookie httpOnly) y guarda el nuevo access token. */
export function refreshSession(): Promise<TokenOut | null> {
  refreshing ??= withCrossTabLock("hd-refresh", async () => {
    try {
      const res = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: CSRF_HEADER,
      });
      if (!res.ok) {
        tokenStore.set(null);
        return null;
      }
      const body = (await res.json()) as TokenOut;
      tokenStore.set(body.access_token);
      authEvents.emit("session-refreshed", body);
      return body;
    } catch {
      return null;
    }
  }).finally(() => {
    refreshing = null;
  });
  return refreshing;
}

function decorate(request: Request): Request {
  const token = tokenStore.get();
  if (token) request.headers.set("Authorization", `Bearer ${token}`);
  request.headers.set("X-Tab-Id", TAB_ID);
  return request;
}

async function errorCode(res: Response): Promise<string | undefined> {
  try {
    const body = (await res.clone().json()) as ErrorOut;
    return body.error?.code;
  } catch {
    return undefined;
  }
}

/** fetch con auth: reintenta una vez tras refrescar si el access token expiró. */
export async function authFetch(request: Request): Promise<Response> {
  const retry = request.clone();
  let res = await fetch(decorate(request));
  if (res.status === 401 && !request.url.includes("/api/v1/auth/login")) {
    const refreshed = await refreshSession();
    if (refreshed) {
      res = await fetch(decorate(retry));
    } else {
      authEvents.emit("session-expired");
    }
  }
  if (res.status === 409 && (await errorCode(res)) === "tab_conflict") {
    authEvents.emit("tab-conflict");
  }
  return res;
}

export const api = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
  fetch: authFetch,
});

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Convierte la respuesta de openapi-fetch en datos o lanza ApiError con el mensaje del back. */
export async function call<T>(promise: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (!response.ok) {
    const body = error as ErrorOut | undefined;
    throw new ApiError(
      response.status,
      body?.error?.code ?? "http_error",
      body?.error?.message ?? `Error ${response.status}`,
      body?.error?.details,
    );
  }
  return data as T;
}

export async function login(email: string, password: string): Promise<TokenOut> {
  const body = await call(api.POST("/api/v1/auth/login", { body: { email, password } }));
  tokenStore.set(body.access_token);
  return body;
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { ...CSRF_HEADER, "X-Tab-Id": TAB_ID },
    });
  } finally {
    tokenStore.set(null);
  }
}

type QueryValue = string | number | boolean | string[] | null | undefined;

/** Descarga un CSV autenticado (no se puede con un <a href> simple porque lleva Bearer). */
export async function downloadCsv(path: string, params: Record<string, QueryValue> = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    for (const v of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(v));
  }
  const res = await authFetch(new Request(url, { credentials: "same-origin" }));
  if (!res.ok) {
    const code = (await errorCode(res)) ?? "download_failed";
    throw new ApiError(res.status, code, "No se pudo descargar el archivo.");
  }
  const blob = await res.blob();
  const match = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = match?.[1] ?? "export.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
