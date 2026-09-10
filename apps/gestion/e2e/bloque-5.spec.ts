import { expect, Page, test } from "@playwright/test";

const base = "http://127.0.0.1:8012/api/v1/turnos";
const supervisor = { "X-Perfil-Simulado": "SUPERVISOR", "X-Sector-Simulado": "Bodega", "X-Actor-Simulado": "sup-e2e" };
const rrhh = { "X-Perfil-Simulado": "RRHH", "X-Actor-Simulado": "rrhh-e2e" };

async function ingresar(page: Page, perfil: string) {
  await page.goto("/turnos");
  await page.getByLabel("Perfil").selectOption(perfil);
  await page.getByRole("button", { name: "Continuar" }).click();
}

test("Turnos: semana, cambio tardío, conciliación, lote, bandeja y reporte", async ({ page }) => {
  await ingresar(page, "SUPERVISOR");
  await expect(page.getByRole("heading", { name: "Cronograma semanal · Bodega" })).toBeVisible();
  const cambio = page.getByRole("button", { name: "Registrar cambio tardío" }).first();
  let numeroPrompt = 0;
  const responderHorario = (d: import("@playwright/test").Dialog) => d.accept(numeroPrompt++ === 0 ? "07:00" : "15:00");
  page.on("dialog", responderHorario);
  await cambio.click();
  page.off("dialog", responderHorario);
  await expect(page.getByText(/Cambio tardío registrado/)).toBeVisible();
  await page.getByRole("button", { name: "Registrar semana" }).click();
  await expect(page.getByText(/Semana registrada/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Cronograma semanal" })).toContainText("2026-09-15");

  await page.getByLabel("Perfil").selectOption("RRHH");
  await expect(page.getByRole("heading", { name: "Conciliación día por día" })).toBeVisible();
  await page.getByRole("button", { name: "Comparar plan y fichadas" }).click();
  await expect(page.getByRole("region", { name: "Conciliación diaria" })).toContainText("sin informar");
  const casillas = page.getByRole("checkbox");
  await casillas.first().check();
  await casillas.nth(1).check();
  page.once("dialog", d => d.accept());
  await page.getByRole("button", { name: "Resolver 2 seleccionadas" }).click();
  await expect(page.getByText(/2 propuestas resueltas en lote/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Bandeja de salida" })).toContainText("SIMULADA · SIN VALIDEZ");
  await page.getByRole("button", { name: "Actualizar" }).click();
  await expect(page.getByRole("region", { name: "Reporte de regularizaciones tardías" })).toContainText("Bodega");
});

test("Negativos: permisos, sector ajeno y edición directa de un día cerrado", async ({ request }) => {
  expect((await request.get(`${base}/cronogramas`, { headers: { "X-Perfil-Simulado": "DEPOSITO" } })).status()).toBe(403);
  const ajeno = await request.post(`${base}/cronogramas`, { headers: supervisor, data: {
    legajo: "1042", sector: "Finca", fecha: "2026-09-15", desde: "08:00", hasta: "16:00",
  } });
  expect(ajeno.status()).toBe(403);
  const cerrado = await request.post(`${base}/cronogramas`, { headers: supervisor, data: {
    legajo: "1042", sector: "Bodega", fecha: "2026-09-01", desde: "08:00", hasta: "16:00",
  } });
  expect(cerrado.status()).toBe(409);
  expect(await cerrado.text()).toContain("día está cerrado");
});

test("Pendientes persisten y la salida local no escribe en el sistema externo", async ({ request }) => {
  const conciliada = await request.get(`${base}/conciliacion?desde=2026-09-01&hasta=2026-09-30&sector=Bodega`, { headers: rrhh });
  expect(conciliada.ok(), await conciliada.text()).toBeTruthy();
  const antes = await (await request.get(`${base}/propuestas?estado=PROPUESTA`, { headers: rrhh })).json();
  await request.get(`${base}/conciliacion?desde=2026-09-01&hasta=2026-09-30&sector=Bodega`, { headers: rrhh });
  const despues = await (await request.get(`${base}/propuestas?estado=PROPUESTA`, { headers: rrhh })).json();
  expect(despues.map((x: { id: string }) => x.id)).toEqual(antes.map((x: { id: string }) => x.id));
  const bandeja = await (await request.get(`${base}/bandeja`, { headers: rrhh })).json();
  for (const salida of bandeja) {
    expect(salida.simulada).toBe(true);
    expect(salida.formato).toContain("contrato pendiente");
  }
});

test("Turnos conserva controles y tablas dentro del viewport angosto", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await ingresar(page, "SUPERVISOR");
  await expect(page.getByRole("button", { name: "Registrar semana" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 812, height: 375 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
