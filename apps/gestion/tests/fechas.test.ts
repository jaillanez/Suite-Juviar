import assert from "node:assert/strict";
import { test } from "node:test";

process.env.TZ = "America/Argentina/San_Juan";
const { fechaLocal, hoyLocal, inicioMesLocal, rangoMesActual } = await import("../src/lib/fechas.ts");

test("el rango por defecto va del primer día del mes a hoy", () => {
  const ahora = new Date(2026, 10, 26, 10, 0);
  assert.deepEqual(rangoMesActual(ahora), { desde: "2026-11-01", hasta: "2026-11-26" });
  assert.equal(inicioMesLocal(new Date(2026, 0, 1, 0, 5)), "2026-01-01");
  assert.equal(fechaLocal(new Date(2026, 1, 9)), "2026-02-09");
});

test("a las 23:30 de Argentina sigue siendo hoy aunque en UTC ya sea mañana", () => {
  const noche = new Date("2026-11-30T23:30:00-03:00");
  assert.equal(noche.toISOString().slice(0, 10), "2026-12-01");
  assert.equal(hoyLocal(noche), "2026-11-30");
  assert.deepEqual(rangoMesActual(noche), { desde: "2026-11-01", hasta: "2026-11-30" });
});
