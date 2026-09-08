import { expect, Page, test } from "@playwright/test";

async function ingresar(page: Page, perfil: string, ruta: string) {
  await page.goto(ruta);
  await page.getByLabel("Perfil").selectOption(perfil);
  await page.getByRole("button", { name: "Continuar" }).click();
}

test("EPP: catálogo, matriz, stock y entregas quedan recorribles", async ({ page, request }) => {
  await ingresar(page, "HYS", "/epp");
  await expect(page.getByRole("heading", { name: "Elementos de protección personal" })).toBeVisible();
  await expect(page.getByText("Catálogo RD 062/11")).toBeVisible();
  await expect(page.getByRole("region", { name: "Catálogo EPP" })).toContainText("145 resultados");
  await page.getByRole("button", { name: "Matriz" }).click();
  await expect(page.getByText(/Matriz sin validar|Firmada por/)).toBeVisible();
  await page.getByRole("button", { name: "Stock" }).click();
  await expect(page.getByRole("heading", { name: "Existencias y mínimos" })).toBeVisible();
  await page.getByRole("button", { name: "Entregas" }).click();
  await expect(page.getByRole("heading", { name: "Entregas y constancias versionadas" })).toBeVisible();

  const rechazo = await request.post("http://127.0.0.1:8012/api/v1/rrhh-epp/catalogo/elementos/NO-AUTORIZADO", {
    headers: { "X-Perfil-Simulado": "RRHH" }, data: { producto: "No debe crearse" },
  });
  expect(rechazo.status()).toBe(403);
});

test("Selección: búsqueda, lote ilegible, revisión y original auditado", async ({ page }) => {
  await ingresar(page, "RRHH", "/seleccion");
  await page.getByLabel("Nombre").fill("Temporada E2E");
  await page.getByRole("button", { name: "Crear búsqueda" }).click();
  await expect(page.getByRole("cell", { name: "Temporada E2E" })).toBeVisible();
  await page.getByLabel("Carga manual").setInputFiles({ name: "ilegible.pdf", mimeType: "application/pdf", buffer: Buffer.from("sin texto PDF") });
  await expect(page.getByText("Apartado para revisión")).toBeVisible();
  await page.getByRole("button", { name: "Revisar" }).click();
  await expect(page.getByRole("heading", { name: /Ficha: ilegible.pdf/ })).toBeVisible();
  await expect(page.getByTitle("CV original")).toBeVisible();
});

test("URL directa de Salud con RRHH recibe 403 de la API", async ({ page }) => {
  await ingresar(page, "RRHH", "/salud");
  await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
  await expect(page.getByText(/API respondió 403/)).toBeVisible();
});
