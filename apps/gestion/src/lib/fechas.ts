// Fechas por defecto de la suite: ningún campo de fecha arranca vacío.
// Rango desde/hasta → primer día del mes actual y hoy; fecha sola → hoy.
// Siempre en hora local del navegador (no UTC): a las 23:30 de Argentina
// (UTC−3) en UTC ya es el día siguiente y «hoy» saltaría de día.

/** Fecha local en formato AAAA-MM-DD, el que usa `<input type="date">`. */
export function fechaLocal(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Hoy en hora local. */
export function hoyLocal(ahora: Date = new Date()): string {
  return fechaLocal(ahora);
}

/** Primer día del mes actual en hora local. */
export function inicioMesLocal(ahora: Date = new Date()): string {
  return `${fechaLocal(ahora).slice(0, 8)}01`;
}

/** Rango por defecto de los filtros: del primer día del mes a hoy. */
export function rangoMesActual(ahora: Date = new Date()): { desde: string; hasta: string } {
  return { desde: inicioMesLocal(ahora), hasta: hoyLocal(ahora) };
}
