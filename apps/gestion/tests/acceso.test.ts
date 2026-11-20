import assert from "node:assert/strict";
import { test } from "node:test";
import { gruposMenu, puedeEntrar, perfiles, todasLasSecciones } from "../src/lib/acceso.ts";

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
  assert.deepEqual(perfiles.COMPRAS.secciones, ["inicio", "epp", "analitica", "mosto", "controles", "configuracion"]);
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

test("el menú separa RRHH, Producción, Bot y Configuración", () => {
  const porNombre = Object.fromEntries(gruposMenu.map((grupo) => [grupo.nombre, grupo.secciones]));
  assert.deepEqual(porNombre.Mantenimiento, ["activos"]);
  assert.deepEqual(porNombre.Producción, ["produccion", "fila", "cosecha", "mosto"]);
  assert.deepEqual(porNombre.Administración, ["controles"]);
  assert.deepEqual(porNombre.Bot, ["bot", "contactos", "personal"]);
  assert.deepEqual(porNombre.Configuración, ["configuracion", "usuarios", "parametros"]);
  assert.equal(porNombre.RRHH.includes("epp"), true);
  assert.equal(porNombre.RRHH.includes("salud"), true);
});

test("Mantenimiento sólo ve equipos y activos", () => {
  assert.deepEqual(perfiles.MANTENIMIENTO.secciones, ["inicio", "activos", "configuracion"]);
  assert.equal(puedeEntrar("RRHH", "activos"), false);
});

test("la bandeja de WhatsApp del personal es de RRHH, no del servicio médico ni de otros", () => {
  assert.equal(puedeEntrar("RRHH", "whatsapp-rrhh"), true);
  for (const perfil of ["MEDICO", "HYS", "BODEGA", "MANTENIMIENTO", "DEPOSITO"] as const) {
    assert.equal(puedeEntrar(perfil, "whatsapp-rrhh"), false);
  }
  const rrhh = gruposMenu.find((grupo) => grupo.nombre === "RRHH");
  assert.equal(rrhh?.secciones.includes("whatsapp-rrhh"), true);
});

test("Administración sólo ve los controles de ARCA", () => {
  assert.deepEqual(perfiles.ADMINISTRACION.secciones, ["inicio", "controles", "configuracion"]);
  assert.equal(puedeEntrar("COMPRAS", "controles"), true);
  assert.equal(puedeEntrar("RRHH", "controles"), false);
});
