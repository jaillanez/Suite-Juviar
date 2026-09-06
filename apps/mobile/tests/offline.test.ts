import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  type AlmacenCola,
  ColaBloqueada,
  type EntregaEnCola,
  type EntregaOffline,
  esperaReintentoMs,
  motivoBloqueo,
  POLITICA_COLA,
  registrarConCola,
  sincronizarCola,
} from "../src/offline.ts";

class Memoria implements AlmacenCola {
  registros = new Map<string, EntregaEnCola>();

  async listar() {
    return [...this.registros.values()];
  }

  async guardar(registro: EntregaEnCola) {
    this.registros.set(registro.entrega.id_cliente, structuredClone(registro));
  }

  async eliminar(id: string) {
    this.registros.delete(id);
  }
}

test("la pantalla conserva la franja roja de entorno sin validez legal", () => {
  const pagina = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  assert.match(pagina, /className="aviso"/);
  assert.match(pagina, /Entorno de prueba · constancias sin validez legal/);
});

function entrega(id = "tablet-00000001"): EntregaOffline {
  return {
    id_cliente: id,
    legajo: "1103",
    items: [{ codigo: "62", item_codigo: "SIM-62-01", cantidad: 1 }],
    metodo_firma: "TRAZO_TABLET",
    evidencia_firma: "data:image/png;base64,AAAA",
    entregada_en: "2026-09-06T13:45:12-03:00",
    actor_declarado: "1210",
    observaciones: "",
    circuito: "ESPONTANEA",
    motivo: "ROTURA",
  };
}

test("un corte durante el envío conserva la entrega completa", async () => {
  const almacen = new Memoria();
  const resultado = await registrarConCola(
    almacen,
    entrega(),
    async () => { throw new Error("red cortada"); },
    new Date("2026-09-06T16:45:12Z"),
  );

  assert.deepEqual(resultado, { estado: "PENDIENTE" });
  const [pendiente] = await almacen.listar();
  assert.deepEqual(pendiente.entrega, entrega());
  assert.equal(pendiente.intentos, 1);
});

test("una entrega pendiente no contiene enlace de constancia", async () => {
  const resultado = await registrarConCola(
    new Memoria(),
    entrega(),
    async () => { throw new Error("sin red"); },
  );

  assert.equal(resultado.estado, "PENDIENTE");
  assert.equal("confirmacion" in resultado, false);
});

test("el umbral bloquea una nueva entrega antes de guardarla", async () => {
  const almacen = new Memoria();
  const ahora = new Date("2026-09-06T16:45:12Z");
  for (let n = 0; n < POLITICA_COLA.maximoPendientes; n += 1) {
    await almacen.guardar({
      entrega: entrega(`tablet-${String(n).padStart(8, "0")}`),
      creada_en: ahora.toISOString(),
      intentos: 1,
      proximo_intento_en: ahora.toISOString(),
    });
  }

  await assert.rejects(
    registrarConCola(almacen, entrega("tablet-bloqueada"), async () => {
      throw new Error("no debería enviar");
    }, ahora),
    ColaBloqueada,
  );
  assert.equal((await almacen.listar()).length, POLITICA_COLA.maximoPendientes);
});

test("24 horas sin sincronizar también bloquean", () => {
  const pendiente: EntregaEnCola = {
    entrega: entrega(),
    creada_en: "2026-09-05T16:45:12Z",
    intentos: 1,
    proximo_intento_en: "2026-09-05T16:45:17Z",
  };
  assert.match(
    motivoBloqueo([pendiente], new Date("2026-09-06T16:45:12Z")) ?? "",
    /24 horas/,
  );
});

test("cada falla aumenta exponencialmente la espera", async () => {
  const almacen = new Memoria();
  const ahora = new Date("2026-09-06T16:45:12Z");
  await registrarConCola(almacen, entrega(), async () => {
    throw new Error("sin red");
  }, ahora);
  assert.equal(esperaReintentoMs(1), 5_000);

  await sincronizarCola(almacen, async () => {
    throw new Error("sigue sin red");
  }, new Date(ahora.getTime() + 5_000));
  const [pendiente] = await almacen.listar();
  assert.equal(pendiente.intentos, 2);
  assert.equal(
    Date.parse(pendiente.proximo_intento_en) - (ahora.getTime() + 5_000),
    10_000,
  );
});
