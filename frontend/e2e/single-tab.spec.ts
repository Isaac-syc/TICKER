import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("el observador solo puede trabajar en una pestaña", async ({ context }) => {
  const first = await context.newPage();
  await login(first, "observer");
  await expect(first.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Segunda pestaña del mismo navegador: queda bloqueada.
  const second = await context.newPage();
  await second.goto("/dashboard");
  await expect(second.getByRole("heading", { name: "Ya tienes una pestaña abierta" })).toBeVisible();

  // "Usar aquí" mueve la sesión y congela la primera.
  await second.getByRole("button", { name: "Usar aquí" }).click();
  await expect(second.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(
    first.getByRole("heading", { name: "Tu sesión se movió a otra pestaña" }),
  ).toBeVisible();
});

test("otros roles pueden usar varias pestañas", async ({ context }) => {
  const first = await context.newPage();
  await login(first, "admin");
  const second = await context.newPage();
  await second.goto("/tickets");
  await expect(second.getByRole("heading", { name: "Tickets" })).toBeVisible();
  await expect(first.getByTestId("role-badge")).toBeVisible();
});
