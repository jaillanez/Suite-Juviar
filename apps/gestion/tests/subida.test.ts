import assert from "node:assert/strict";
import { test } from "node:test";
import { codigoDelLink, teclaPin } from "../src/lib/subida.ts";

const CODIGO = "a1b2c3d4.Zx9_-0123456789abcdefghijklmnopq";

test("el código del link sale del # y se descarta lo que no tiene su forma", () => {
  assert.equal(codigoDelLink(`#${CODIGO}`), CODIGO);
  assert.equal(codigoDelLink(`#${encodeURIComponent(CODIGO)}`), CODIGO);
  for (const malo of ["", "#", "#a1b2c3d4", "#A1B2C3D4.Zx9_-0123456789abcdefghij", "#a1b2c3d4.corto",
    `#a1b2c3d4.${"x".repeat(81)}`, "#a1b2c3d4.%E0%A4%A", "#a1b2c3d4.<script>alert(1)</script>xxxxxxx"]) {
    assert.equal(codigoDelLink(malo), "", malo);
  }
});

test("el teclado del PIN acepta sólo 3 números y borra el último", () => {
  let pin = "";
  for (const tecla of ["4", "x", "2", "", "7", "9"]) pin = teclaPin(pin, tecla);
  assert.equal(pin, "427");
  assert.equal(teclaPin(pin, "borrar"), "42");
  assert.equal(teclaPin("", "borrar"), "");
  assert.equal(teclaPin("1", "12"), "1");
});
