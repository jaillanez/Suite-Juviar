import assert from "node:assert/strict";
import { test } from "node:test";
import { avisoFaltantes, escalaAjustada, estadoDetalle, pedirLectura, progresoLectura, resumenFaltantes, zoom } from "../src/lib/seleccion.ts";

const FALTAN = ["edad_o_fecha_nacimiento", "nivel_estudios"];

test("nunca dice que el currículum no trae un dato si no se pudo leer", () => {
  const sinLeer = avisoFaltantes({ datos_faltantes: FALTAN, motivo_faltantes: "NO_SE_PUDO_LEER", lectura_ia: "NO_DISPONIBLE", texto_leido: false });
  assert.match(sinLeer ?? "", /no pudo leer el texto de este archivo/);
  assert.doesNotMatch(sinLeer ?? "", /no los trae|pedíselos/);
  const falloIA = avisoFaltantes({ datos_faltantes: FALTAN, motivo_faltantes: "NO_SE_PUDO_LEER", lectura_ia: "ERROR", texto_leido: true }, "La IA no respondió");
  assert.match(falloIA ?? "", /El sistema no pudo leer: Edad o fecha de nacimiento, Nivel de estudios/);
  assert.match(falloIA ?? "", /La IA no respondió/);
  const leidoPorIA = avisoFaltantes({ datos_faltantes: FALTAN, motivo_faltantes: "NO_LO_ENCONTRO", lectura_ia: "LEIDO" });
  assert.match(leidoPorIA ?? "", /La IA leyó todo el currículum y no los encontró/);
});

test("sin faltantes no hay aviso y mientras la IA lee se avisa que está leyendo", () => {
  assert.equal(avisoFaltantes({ datos_faltantes: [], motivo_faltantes: "NO_LO_ENCONTRO", lectura_ia: "LEIDO" }), null);
  assert.match(avisoFaltantes({ datos_faltantes: FALTAN, motivo_faltantes: "LEYENDO", lectura_ia: "EN_COLA" }) ?? "", /está leyendo/);
  assert.deepEqual(resumenFaltantes({ datos_faltantes: FALTAN, lectura_ia: "LEYENDO" }), { texto: "Leyendo con IA…", clase: "estado estado-neutro" });
  assert.equal(resumenFaltantes({ datos_faltantes: ["experiencia"], motivo_faltantes: "NO_SE_PUDO_LEER" }).texto, "Sin leer: Experiencia");
  assert.equal(resumenFaltantes({ datos_faltantes: ["experiencia"], motivo_faltantes: "NO_LO_ENCONTRO" }).texto, "Falta: Experiencia");
  assert.equal(resumenFaltantes({ datos_faltantes: [] }).texto, "Completo");
});

test("avance del reproceso", () => {
  assert.equal(progresoLectura({ en_cola: 0, hechos: 3, lote: 3 }), "");
  assert.equal(progresoLectura({ en_cola: 7, hechos: 3, lote: 10 }), "Leyendo currículums: 4 de 10…");
  assert.equal(progresoLectura(null), "");
});

test("zoom de la vista previa: parte de la escala ajustada y tiene topes", () => {
  assert.equal(escalaAjustada({ ancho: 2000, alto: 1000 }, { ancho: 1000, alto: 1000 }), 0.5);
  assert.equal(escalaAjustada({ ancho: 300, alto: 200 }, { ancho: 1000, alto: 1000 }), 1); // nunca agranda sola
  assert.equal(zoom(null, 0.5, 1), 0.63);
  assert.equal(zoom(0.5, 0.2, -1), 0.4);
  assert.equal(zoom(8, 1, 1), 8);
  assert.equal(zoom(0.1, 1, -1), 0.1);
});

test("abrir el detalle pide la lectura con IA una sola vez y sólo si falta", () => {
  const sinLeer = { id: "a", lectura_pendiente: true, lectura_ia: "SIN_LEER" as const };
  assert.equal(pedirLectura(sinLeer, null), true);
  assert.equal(pedirLectura(sinLeer, "a"), false); // ya se pidió al abrirlo
  assert.equal(pedirLectura(sinLeer, "b"), true);
  assert.equal(pedirLectura({ id: "a", lectura_pendiente: false, lectura_ia: "LEIDO" }, null), false);
  assert.equal(pedirLectura({ id: "a", lectura_pendiente: true, lectura_ia: "EN_COLA" }, null), false);
});

test("con la IA en pausa el estado es claro y no se pierde ningún currículum", () => {
  assert.match(estadoDetalle({ lectura_ia: "REINTENTO" }), /no está disponible; se vuelve a intentar más tarde/);
  assert.match(avisoFaltantes({ datos_faltantes: FALTAN, motivo_faltantes: "NO_SE_PUDO_LEER", lectura_ia: "REINTENTO", texto_leido: true }) ?? "", /se vuelve a intentar más tarde/);
  assert.match(progresoLectura({ en_cola: 4, en_espera: 4, en_pausa: 120, hechos: 5, lote: 9 }), /Quedan 4 currículums esperando; no se pierde ninguno/);
  assert.equal(estadoDetalle({ lectura_ia: "LEYENDO" }), "La IA está leyendo este currículum…");
});
