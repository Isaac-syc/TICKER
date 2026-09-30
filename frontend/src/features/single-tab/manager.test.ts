import { describe, expect, it, vi } from "vitest";

import { createSingleTabManager, type LeaseResult } from "./manager";

/** Implementación mínima de Web Locks (mismo origen) para simular varias pestañas. */
class FakeLocks {
  private holder: { abort: (e: Error) => void } | null = null;

  async request(
    _name: string,
    options: LockOptions,
    callback: (lock: Lock | null) => Promise<unknown>,
  ): Promise<unknown> {
    if (this.holder && !options.steal) {
      if (options.ifAvailable) return callback(null);
      throw new Error("queue no soportada en el fake");
    }
    if (this.holder && options.steal) {
      const abort = new Error("stolen");
      abort.name = "AbortError";
      this.holder.abort(abort);
    }
    return new Promise((resolve, reject) => {
      const entry = { abort: reject };
      this.holder = entry;
      void callback({ name: "x", mode: "exclusive" } as Lock).then((v) => {
        if (this.holder === entry) this.holder = null;
        resolve(v);
      });
    });
  }
}

const granted: LeaseResult = { required: true, granted: true, other_device: false };
const flush = () => new Promise((r) => setTimeout(r, 0));

function makeTab(locks: FakeLocks, claim: () => Promise<LeaseResult> = async () => granted) {
  return createSingleTabManager({
    tabId: Math.random().toString(36),
    claim,
    takeover: async () => granted,
    release: vi.fn(),
    locks: locks as unknown as LockManager,
    heartbeatMs: 60_000,
  });
}

describe("single-tab manager", () => {
  it("activa la primera pestaña y bloquea la segunda", async () => {
    const locks = new FakeLocks();
    const a = makeTab(locks);
    const b = makeTab(locks);
    a.start();
    await flush();
    b.start();
    await flush();
    expect(a.getState().status).toBe("active");
    expect(b.getState().status).toBe("blocked");
    a.stop();
    b.stop();
  });

  it('"Usar aquí" mueve la sesión y congela la pestaña anterior', async () => {
    const locks = new FakeLocks();
    const a = makeTab(locks);
    const b = makeTab(locks);
    a.start();
    await flush();
    b.start();
    await flush();
    b.takeover();
    await flush();
    await flush();
    expect(b.getState().status).toBe("active");
    expect(a.getState().status).toBe("displaced");
    a.stop();
    b.stop();
  });

  it("queda bloqueada si el servidor reporta otra sesión (otro dispositivo)", async () => {
    const locks = new FakeLocks();
    const tab = makeTab(locks, async () => ({ required: true, granted: false, other_device: true }));
    tab.start();
    await flush();
    await flush();
    expect(tab.getState()).toEqual({ status: "blocked", otherDevice: true });
    tab.stop();
  });

  it("un TAB_CONFLICT del servidor congela la pestaña activa", async () => {
    const tab = makeTab(new FakeLocks());
    tab.start();
    await flush();
    tab.conflict();
    expect(tab.getState().status).toBe("displaced");
    tab.stop();
    expect(tab.getState().status).toBe("idle");
  });
});
