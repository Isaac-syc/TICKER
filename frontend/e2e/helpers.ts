import { expect, type Page } from "@playwright/test";

/** Credenciales demo del seed (mismos valores por defecto que .env.example). */
export const USERS = {
  admin: {
    email: process.env.E2E_ADMIN_EMAIL ?? "admin@helpdesk.test",
    password: process.env.E2E_ADMIN_PASSWORD ?? "Admin#2026!",
  },
  user: {
    email: process.env.E2E_USER_EMAIL ?? "usuario@helpdesk.test",
    password: process.env.E2E_USER_PASSWORD ?? "Usuario#2026!",
  },
  observer: {
    email: process.env.E2E_OBSERVER_EMAIL ?? "observador@helpdesk.test",
    password: process.env.E2E_OBSERVER_PASSWORD ?? "Observador#2026!",
  },
};

export async function login(page: Page, who: keyof typeof USERS) {
  await page.goto("/login");
  await page.getByLabel("Correo").fill(USERS[who].email);
  await page.getByLabel("Contraseña").fill(USERS[who].password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();

  // Con roles de pestaña única, una sesión de una prueba anterior (otro contexto = otro
  // "dispositivo") puede seguir dueña del lease: se toma aquí, como lo haría el usuario.
  const takeover = page.getByRole("button", { name: "Usar aquí" });
  const badge = page.getByTestId("role-badge");
  await expect(badge.or(takeover)).toBeVisible();
  if (await takeover.isVisible()) await takeover.click();
  await expect(badge).toBeVisible();
}
