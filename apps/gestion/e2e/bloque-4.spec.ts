import { expect, Page, test } from "@playwright/test";

const base = "http://127.0.0.1:8012/api/v1";
const rrhh = { "X-Perfil-Simulado": "RRHH", "X-Actor-Simulado": "rrhh-e2e" };
const medico = { "X-Perfil-Simulado": "MEDICO", "X-Actor-Simulado": "medico-e2e" };

async function ingresar(page: Page, perfil: string, ruta: string) {
  await page.goto(ruta);
  await page.getByLabel("Perfil").selectOption(perfil);
  await page.getByRole("button", { name: "Continuar" }).click();
}

test("Legajo: busca, abre ficha y conserva adjunto tras la baja lógica", async ({ page }) => {
  await ingresar(page, "RRHH", "/legajo");
  await page.getByLabel("Legajo", { exact: true }).first().fill("1042");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(page.getByRole("region", { name: "Personas" })).toContainText("1042");
  await page.getByRole("button", { name: "Abrir" }).click();
  await expect(page.getByText("Nexus · sólo lectura")).toBeVisible();
  await page.getByLabel("Archivo original").setInputFiles({
    name: "contrato-e2e.pdf", mimeType: "application/pdf", buffer: Buffer.from("PDF original E2E"),
  });
  await page.getByRole("button", { name: "Adjuntar" }).click();
  await expect(page.getByRole("cell", { name: "contrato-e2e.pdf" })).toBeVisible();
  page.once("dialog", dialog => dialog.accept("Reemplazado por versión vigente"));
  await page.getByRole("button", { name: "Dar de baja" }).click();
  await expect(page.getByText(/Baja: Reemplazado por versión vigente/)).toBeVisible();
  await page.getByRole("button", { name: "Ver original" }).click();
  await expect(page.getByTitle("Original contrato-e2e.pdf")).toBeVisible();
  await expect(page.locator("main")).not.toContainText(/diagnóstico|enfermedad|licencia médica/i);
});

test("Salud: certificado completo, artículo 208 preliminar y bitácora", async ({ page }) => {
  await ingresar(page, "MEDICO", "/salud");
  await expect(page.getByText("Dueño del dato: Servicio Médico.")).toBeVisible();
  await page.getByLabel("Legajo").first().fill("1042");
  await page.getByLabel("Diagnóstico del catálogo").selectOption("MUESTRA-RESP");
  await page.getByLabel("Desde").first().fill("2026-09-01");
  await page.getByLabel("Hasta").first().fill("2026-09-03");
  await page.getByLabel("Días corridos").fill("3");
  await page.getByLabel("Profesional").fill("Dra. E2E");
  await page.getByLabel("Escaneo original").setInputFiles({ name: "certificado.pdf", mimeType: "application/pdf", buffer: Buffer.from("certificado medico") });
  await page.getByRole("button", { name: "Registrar certificado" }).click();
  await expect(page.getByRole("status")).toContainText("registrado y auditado");
  await expect(page.getByRole("region", { name: "Certificados médicos" })).toContainText("Dra. E2E");
  await page.getByRole("button", { name: "Evaluar" }).click();
  await expect(page.getByText(/Preliminar: antigüedad y cargas de familia simuladas/)).toBeVisible();
  await expect(page.getByText("No se puede imprimir ni exportar mientras use datos simulados.")).toBeVisible();
  await page.getByRole("button", { name: "Actualizar reporte" }).click();
  await expect(page.getByText(/Mínimo de agregado: 2/)).toBeVisible();
  await page.getByRole("button", { name: "Consultar bitácora" }).click();
  await expect(page.getByRole("region", { name: "Bitácora de accesos médicos" })).toContainText("CARGA_CERTIFICADO");
  await expect(page.getByRole("region", { name: "Bitácora de accesos médicos" })).not.toContainText("MUESTRA-RESP");
});

test("Negativos críticos de Salud se rechazan en la API", async ({ request }) => {
  expect((await request.get(`${base}/salud/catalogo`, { headers: rrhh })).status()).toBe(403);
  const carga = await request.post(`${base}/salud/certificados`, { headers: medico, data: {
    legajo: "1042", diagnostico_codigo: "MUESTRA-TRAU", desde: "2026-09-08", hasta: "2026-09-08", dias: 1,
    profesional: "Dr. E2E", adjunto_nombre: "scan.pdf", adjunto_base64: Buffer.from("scan").toString("base64"),
  } });
  expect(carga.ok(), await carga.text()).toBeTruthy();
  const bitacora = await (await request.get(`${base}/salud/bitacora`, { headers: medico })).json();
  expect(JSON.stringify(bitacora).toLowerCase()).not.toContain("diagnostico");
  expect((await request.patch(`${base}/salud/bitacora/${bitacora[0].id}`, { headers: medico, data: { accion: "ALTERADA" } })).status()).toBe(405);
  expect((await request.delete(`${base}/salud/bitacora/${bitacora[0].id}`, { headers: medico })).status()).toBe(405);
  expect((await request.get(`${base}/salud/articulo-208/1042/exportar`, { headers: medico })).status()).toBe(409);
  expect((await request.get(`${base}/salud/reportes?nominado=true`, { headers: medico })).status()).toBe(400);
});
