import assert from "node:assert/strict";
import { test } from "node:test";
import { puedeEntrar, perfiles, todasLasSecciones } from "../src/lib/acceso.ts";

test("RRHH general no ve ni puede abrir Salud", () => {
  assert.equal(perfiles.RRHH.secciones.includes("salud"), false);
  assert.equal(puedeEntrar("RRHH", "salud"), false);
});

test("sólo el perfil médico recibe la sección Salud", () => {
  assert.equal(puedeEntrar("MEDICO", "salud"), true);
  for (const perfil of ["RRHH", "HYS", "COMPRAS", "SUPERVISOR"] as const) {
    assert.equal(puedeEntrar(perfil, "salud"), false);
  }
});

test("el menú se construye con secciones permitidas", () => {
  assert.deepEqual(perfiles.COMPRAS.secciones, ["inicio", "epp", "analitica"]);
  assert.equal(puedeEntrar("SUPERVISOR", "turnos"), true);
});

test("Producción queda integrada para campo, báscula y administración de bodega", () => {
  assert.equal(puedeEntrar("CAMPO", "produccion"), true);
  assert.equal(puedeEntrar("BASCULA", "produccion"), true);
  assert.equal(puedeEntrar("BODEGA", "produccion"), true);
  assert.equal(puedeEntrar("RRHH", "produccion"), false);
});

test("Superadministrador ve y puede abrir toda la aplicación", () => {
  assert.deepEqual(perfiles.SUPERADMIN.secciones, todasLasSecciones);
  for (const seccion of todasLasSecciones) {
    assert.equal(puedeEntrar("SUPERADMIN", seccion), true);
  }
});
