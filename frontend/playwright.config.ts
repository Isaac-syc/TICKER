import { defineConfig, devices } from "@playwright/test";

/** E2E contra el stack completo de Docker (nginx + web + api + db + redis). */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "es-MX",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
