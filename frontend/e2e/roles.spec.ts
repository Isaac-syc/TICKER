import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("admin ve la sección de administración", async ({ page }) => {
  await login(page, "admin");
  await expect(page.getByTestId("role-badge")).toHaveText("admin");
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Usuarios" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Roles y permisos" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Bitácora" })).toBeVisible();
});

test("usuario crea un ticket y no ve administración", async ({ page }) => {
  await login(page, "user");
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Usuarios" })).toHaveCount(0);

  await nav.getByRole("link", { name: "Nuevo ticket" }).click();
  const title = `Monitor sin señal ${Date.now()}`;
  await page.getByLabel("Título").fill(title);
  await page.getByLabel("Categoría").selectOption({ label: "Hardware" });
  await page.getByLabel("Prioridad").selectOption("HIGH");
  await page.getByLabel("Descripción").fill("El monitor externo no detecta la laptop desde hoy.");
  await page.getByRole("button", { name: "Crear ticket" }).click();

  await expect(page.getByTestId("ticket-title")).toHaveText(title);
  await expect(page.getByTestId("timeline")).toContainText("creó el ticket");
  await expect(page.getByTestId("transitions").getByRole("button", { name: "Cancelar" })).toBeVisible();
});

test("observador es de solo lectura", async ({ page }) => {
  await login(page, "observer");
  await expect(page.getByText("Modo solo lectura.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Nuevo ticket" })).toHaveCount(0);
  await page.goto("/tickets/new");
  await expect(page.getByText("No tienes acceso a esta sección")).toBeVisible();
});
