import { expect, Page, test } from "@playwright/test";

async function ingresar(page: Page, perfil: string, ruta: string) {
  await page.goto(ruta);
  await page.getByLabel("Perfil").selectOption(perfil);
  await page.getByRole("button", { name: "Continuar" }).click();
}

test("Capacitaciones: convocatoria, tandas, deduplicación y anulación visible", async ({ page, request }) => {
  await ingresar(page, "RRHH", "/capacitaciones");
  const api = "http://127.0.0.1:8012/api/v1/capacitaciones";
  const headers = { "X-Perfil-Simulado": "RRHH", "X-Actor-Simulado": "rrhh-e2e" };
  const tema = await request.post(`${api}/temas`, { headers, data: { nombre: "Ergonomía E2E", horas: 2 } });
  const temaId = (await tema.json()).id;
  const dictados: string[] = [];
  for (const fecha of ["2026-08-01", "2026-08-02"]) {
    const respuesta = await request.post(`${api}/dictados`, { headers, data: { tema_id: temaId, fecha, instructor: "HyS", duracion_horas: 2, convocatoria_tipo: "LISTA", convocatoria_detalle: "Administración", convocados: ["1042", "1043"] } });
    dictados.push((await respuesta.json()).id);
  }
  for (const dictadoId of dictados) await request.post(`${api}/dictados/${dictadoId}/asistencias`, { headers, data: { legajo: "1042", nombre_completo: "Persona Uno", presente: true } });
  await request.post(`${api}/dictados/${dictados[0]}/asistencias`, { headers, data: { legajo: "1043", nombre_completo: "Persona Dos", presente: true } });
  await page.reload();
  await page.getByLabel("Tema").last().selectOption(temaId);
  await expect(page.getByText("100%", { exact: true })).toBeVisible();
  await expect(page.getByText("2 convocados")).toBeVisible();
  await page.getByLabel("Dictado para asistencia").selectOption(dictados[0]);
  page.once("dialog", dialog => dialog.accept("Carga duplicada E2E"));
  await page.getByRole("button", { name: "Anular con motivo" }).last().click();
  await expect(page.getByText(/Anulada: Carga duplicada E2E/)).toBeVisible();
  await expect(page.getByText("50%", { exact: true })).toBeVisible();

  const rechazo = await request.get(`${api}/temas`, { headers: { "X-Perfil-Simulado": "DEPOSITO" } });
  expect(rechazo.status()).toBe(403);
});

test("Capacitaciones sin convocatoria muestra cantidad y nunca porcentaje", async ({ page, request }) => {
  await ingresar(page, "RRHH", "/capacitaciones");
  const api = "http://127.0.0.1:8012/api/v1/capacitaciones";
  const headers = { "X-Perfil-Simulado": "RRHH" };
  const tema = await request.post(`${api}/temas`, { headers, data: { nombre: "Inducción sin convocatoria E2E", horas: 1 } });
  const temaId = (await tema.json()).id;
  const dictado = await request.post(`${api}/dictados`, { headers, data: { tema_id: temaId, fecha: "2026-08-03", instructor: "RRHH", duracion_horas: 1 } });
  await request.post(`${api}/dictados/${(await dictado.json()).id}/asistencias`, { headers, data: { legajo: "1050", nombre_completo: "Persona sin convocatoria", presente: true } });
  await page.reload();
  await page.getByLabel("Tema").last().selectOption(temaId);
  await expect(page.getByText("Cantidad, sin %")).toBeVisible();
  await expect(page.getByText("Sin convocatoria declarada")).toBeVisible();
});

test("Analítica: filtro, muestra, fecha de corte y bloqueo SIM explicado", async ({ page, request }) => {
  const base = "http://127.0.0.1:8012/api/v1";
  const hys = { "X-Perfil-Simulado": "HYS" }; const deposito = { "X-Perfil-Simulado": "DEPOSITO", "X-Legajo-Usuario": "1210" };
  const catalogo = await (await request.get(`${base}/rrhh-epp/catalogo`, { headers: hys })).json();
  const elemento = catalogo.find((e: { items: unknown[] }) => e.items.length >= 2);
  const items = elemento.items.slice(0, 2).map((i: { codigo_interno: string }) => i.codigo_interno);
  for (const item of items) {
    await request.put(`${base}/rrhh-epp/stock/${item}`, { headers: deposito, data: { disponible: 30, minimo: 2 } });
    for (let i = 0; i < 7; i++) await request.post(`${base}/rrhh-epp/entregas`, { headers: deposito, data: { legajo: "1210", items: [{ codigo: elemento.codigo, item_codigo: item, cantidad: 1, reclamo_calidad: i === 1 ? "ROTURA" : null }], metodo_firma: "PIN", evidencia_firma: "1234", id_cliente: `ANA-${items.indexOf(item)}-${i}-E2E`, entregada_en: `2026-${String(i + 1).padStart(2, "0")}-01T12:00:00Z`, motivo: "DESGASTE" } });
  }
  const tableroApi = await request.get(`${base}/epp-analitica/tablero?desde=2026-01-01&hasta=2026-12-31`, { headers: hys });
  expect(tableroApi.ok(), await tableroApi.text()).toBeTruthy();
  await ingresar(page, "HYS", "/analitica");
  await page.getByLabel("Hasta").fill("2026-12-31");
  await page.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(page.getByRole("region", { name: "Tablero analítico" })).toContainText(items[0]);
  await expect(page.getByText("Bloqueada", { exact: true })).toBeVisible();
  await expect(page.getByText("Hay entregas contra ítems SIM-*")).toBeVisible();
  await expect(page.getByText("2026-12-31", { exact: true })).toBeVisible();
  await page.getByLabel("Ítem A").fill(items[0]); await page.getByLabel("Ítem B").fill(items[1]);
  await page.getByRole("button", { name: "Comparar" }).click();
  await expect(page.getByText(/"habilitado": true/)).toBeVisible();

  const rechazo = await request.get(`${base}/epp-analitica/tablero?desde=2026-01-01&hasta=2026-12-31`, { headers: { "X-Perfil-Simulado": "RRHH" } });
  expect(rechazo.status()).toBe(403);
});

test("Analítica: una reposición sólo estacional no se presenta como rotura", async ({ page, request }) => {
  const base = "http://127.0.0.1:8012/api/v1";
  const hys = { "X-Perfil-Simulado": "HYS" }; const deposito = { "X-Perfil-Simulado": "DEPOSITO", "X-Legajo-Usuario": "1210" };
  const catalogo = await (await request.get(`${base}/rrhh-epp/catalogo`, { headers: hys })).json();
  const elemento = catalogo.at(-1); const item = elemento.items[0].codigo_interno;
  expect((await request.put(`${base}/rrhh-epp/stock/${item}`, { headers: deposito, data: { disponible: 10, minimo: 1 } })).ok()).toBeTruthy();
  const comun = { legajo: "1210", items: [{ codigo: elemento.codigo, item_codigo: item, cantidad: 1 }], metodo_firma: "PIN", evidencia_firma: "1234" };
  expect((await request.post(`${base}/rrhh-epp/entregas`, { headers: deposito, data: { ...comun, id_cliente: "ANA-EST-INICIAL-E2E", entregada_en: "2026-01-01T12:00:00Z", circuito: "ESPONTANEA", motivo: "DESGASTE" } })).ok()).toBeTruthy();
  expect((await request.post(`${base}/rrhh-epp/entregas`, { headers: deposito, data: { ...comun, id_cliente: "ANA-EST-CONVENIO-E2E", entregada_en: "2026-07-01T12:00:00Z", circuito: "PROGRAMADA", motivo: "ENTREGA_ESTACIONAL" } })).ok()).toBeTruthy();
  await ingresar(page, "HYS", "/analitica");
  await page.getByLabel("Hasta").fill("2026-12-31"); await page.getByRole("button", { name: "Aplicar filtros" }).click();
  const fila = page.getByRole("row").filter({ hasText: item });
  await expect(fila).toContainText("Sin datos suficientes (N=0)");
  await expect(fila).not.toContainText("días");
});
