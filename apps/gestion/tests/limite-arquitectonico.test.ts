import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

function fuentes(ruta: string): string[] {
  return readdirSync(ruta).flatMap((nombre) => {
    const destino = join(ruta, nombre);
    if (statSync(destino).isDirectory()) return fuentes(destino);
    return /\.(ts|tsx)$/.test(nombre) ? [destino] : [];
  });
}

test("contrato 13: Gestión no importa módulos ni plataforma", () => {
  for (const archivo of fuentes(new URL("../src", import.meta.url).pathname)) {
    const contenido = readFileSync(archivo, "utf8");
    assert.doesNotMatch(contenido, /suite_juviar[/.](modulos|plataforma)/, archivo);
  }
});
