import assert from "node:assert/strict";
import { test } from "node:test";
import { problemaDeClave, tokenDelEnlace } from "../src/lib/recuperacion.ts";

const TOKEN = "Zx9_-0123456789abcdefghijklmnopqrstuvwxyzAB";

test("el código del enlace sale del # y se descarta lo que no tiene su forma", () => {
  assert.equal(tokenDelEnlace(`#${TOKEN}`), TOKEN);
  assert.equal(tokenDelEnlace(`#${encodeURIComponent(TOKEN)}`), TOKEN);
  for (const malo of ["", "#", "#corto", `#${"x".repeat(101)}`, "#%E0%A4%A", `#${TOKEN}<script>`, `#${TOKEN}.x`]) {
    assert.equal(tokenDelEnlace(malo), "", malo);
  }
});

test("la contraseña nueva sigue las mismas reglas que el servidor", () => {
  assert.equal(problemaDeClave("clave-larga-1"), "");
  assert.match(problemaDeClave("corta"), /al menos 10/);
  assert.match(problemaDeClave(" con-espacio-1"), /espacios/);
  assert.match(problemaDeClave("con-espacio-1 "), /espacios/);
  assert.match(problemaDeClave("          "), /espacios/);
});
