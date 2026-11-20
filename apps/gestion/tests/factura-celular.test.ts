import assert from "node:assert/strict";
import { test } from "node:test";
import { esQrDeArca, importeEscrito } from "../src/lib/foto-factura.ts";

test("sólo se toma como factura el QR de ARCA (o AFIP) con datos", () => {
  assert.equal(esQrDeArca("https://www.afip.gob.ar/fe/qr/?p=eyJ2ZXIiOjF9"), true);
  assert.equal(esQrDeArca("https://arca.gob.ar/fe/qr?p=eyJ2ZXIiOjF9"), true);
  for (const otro of ["http://www.afip.gob.ar/fe/qr/?p=x", "https://www.afip.gob.ar.falso.com/fe/qr/?p=x",
    "https://www.afip.gob.ar/fe/qr/", "https://www.afip.gob.ar/otra/?p=x", "BOM-0001", ""]) {
    assert.equal(esQrDeArca(otro), false, otro);
  }
});

test("el importe escrito a mano acepta coma o punto decimal", () => {
  assert.equal(importeEscrito("12.100,50"), 12100.5);
  assert.equal(importeEscrito("$ 999,9"), 999.9);
  assert.equal(importeEscrito("12100.50"), 12100.5);
  assert.equal(importeEscrito("12.100"), 12100);
});
