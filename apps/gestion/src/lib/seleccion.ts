// Textos de Selección que dependen de cómo se leyó cada currículum. Nunca se le dice a RRHH que el
// currículum no trae un dato si en realidad el sistema no lo pudo leer.

export type LecturaIA = "LEIDO" | "EN_COLA" | "LEYENDO" | "ERROR" | "SIN_LEER" | "NO_DISPONIBLE";
export type MotivoFaltantes = "NO_LO_ENCONTRO" | "NO_SE_PUDO_LEER" | "LEYENDO";
export type EstadoLectura = { datos_faltantes?: string[]; motivo_faltantes?: MotivoFaltantes; lectura_ia?: LecturaIA; texto_leido?: boolean };

export const CAMPOS: Record<string, string> = { edad_o_fecha_nacimiento: "Edad o fecha de nacimiento", nivel_estudios: "Nivel de estudios", experiencia: "Experiencia", oficio: "Oficio o perfil", localidad: "Localidad", contacto: "Contacto" };
export const campo = (c: string) => CAMPOS[c] ?? c.replaceAll("_", " ");
const lista = (campos: string[]) => campos.map(campo).join(", ");

export const leyendo = (c: EstadoLectura) => c.lectura_ia === "EN_COLA" || c.lectura_ia === "LEYENDO";

/** Lo que dice la columna «Datos faltantes» de la lista. */
export function resumenFaltantes(c: EstadoLectura): { texto: string; clase: string } {
  if (!c.datos_faltantes?.length) return leyendo(c) ? { texto: "Completo (la IA lo está revisando)", clase: "estado" } : { texto: "Completo", clase: "estado" };
  if (leyendo(c)) return { texto: "Leyendo con IA…", clase: "estado estado-neutro" };
  if (c.motivo_faltantes === "NO_LO_ENCONTRO") return { texto: `Falta: ${lista(c.datos_faltantes)}`, clase: "estado estado-revisar" };
  return { texto: `Sin leer: ${lista(c.datos_faltantes)}`, clase: "estado estado-revisar" };
}

/** El aviso del detalle sobre los datos obligatorios que no aparecen. */
export function avisoFaltantes(c: EstadoLectura, errorIA?: string | null): string | null {
  const faltan = c.datos_faltantes ?? [];
  if (leyendo(c)) return faltan.length ? `La IA está leyendo este currículum. En unos segundos se completan los datos (por ahora no se leyó: ${lista(faltan)}).` : null;
  if (!faltan.length) return null;
  if (c.motivo_faltantes === "NO_LO_ENCONTRO") return `Datos faltantes: ${lista(faltan)}. La IA leyó todo el currículum y no los encontró. Miralo en el original y, si de verdad no están, pedíselos al postulante.`;
  const base = c.texto_leido === false
    ? `El sistema no pudo leer el texto de este archivo, así que no sabe si trae: ${lista(faltan)}. Miralo en el original.`
    : `El sistema no pudo leer: ${lista(faltan)}. Puede que estén en el currículum con otro formato: miralo en el original.`;
  if (c.lectura_ia === "ERROR") return `${base} La lectura con IA falló${errorIA ? ` (${errorIA})` : ""}; tocá «Volver a leer este currículum».`;
  return base;
}

export const ORIGEN: Record<string, string> = { IA: "Leído por la IA", LECTURA_AUTOMATICA: "Leído automáticamente", RRHH: "Confirmado por RRHH" };

/** Avance del reproceso: «Leyendo 3 de 10…». */
export function progresoLectura(p: { en_cola?: number; hechos?: number; lote?: number } | null | undefined): string {
  if (!p?.en_cola) return "";
  const lote = Math.max(p.lote ?? 0, (p.hechos ?? 0) + p.en_cola);
  return `Leyendo currículums: ${Math.min((p.hechos ?? 0) + 1, lote)} de ${lote}…`;
}

// Zoom de la vista previa: null es «ajustar a la pantalla».
export const ZOOM_MINIMO = 0.1;
export const ZOOM_MAXIMO = 8;
export function zoom(actual: number | null, ajustada: number, direccion: 1 | -1): number {
  const base = actual ?? ajustada;
  const siguiente = direccion > 0 ? base * 1.25 : base / 1.25;
  return Math.min(ZOOM_MAXIMO, Math.max(ZOOM_MINIMO, Math.round(siguiente * 100) / 100));
}
export function escalaAjustada(natural: { ancho: number; alto: number }, caja: { ancho: number; alto: number }): number {
  if (!natural.ancho || !natural.alto || !caja.ancho || !caja.alto) return 1;
  return Math.min(1, caja.ancho / natural.ancho, caja.alto / natural.alto);
}
