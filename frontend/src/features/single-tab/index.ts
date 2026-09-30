import { api, call, TAB_ID, tokenStore } from "@/lib/api/client";

import { createSingleTabManager } from "./manager";

export const singleTab = createSingleTabManager({
  tabId: TAB_ID,
  claim: () => call(api.POST("/api/v1/auth/tab-lease")),
  takeover: () => call(api.POST("/api/v1/auth/tab-lease/takeover")),
  // keepalive permite que la petición salga aunque la pestaña se esté cerrando.
  release: () => {
    const token = tokenStore.get();
    if (!token) return;
    void fetch("/api/v1/auth/tab-lease/release", {
      method: "POST",
      keepalive: true,
      headers: { Authorization: `Bearer ${token}`, "X-Tab-Id": TAB_ID },
    }).catch(() => undefined);
  },
  locks: typeof navigator !== "undefined" ? navigator.locks : undefined,
  createChannel:
    typeof BroadcastChannel !== "undefined" ? (name) => new BroadcastChannel(name) : undefined,
});

export type { SingleTabState } from "./manager";
