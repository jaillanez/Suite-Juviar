// Pantalla /subir: link personal (`/subir/#<id>.<secreto>`) + PIN de 3 números.
// El código va después de «#» para que no viaje al servidor en la dirección ni quede en
// registros: la pantalla lo lee y lo manda sólo junto con el PIN.

export const LARGO_PIN = 3;

/** Código del link personal, o "" si la dirección no trae uno con la forma esperada. */
export function codigoDelLink(hash: string): string {
  let codigo = "";
  try { codigo = decodeURIComponent(hash.replace(/^#/, "").trim()); } catch { return ""; }
  return /^[0-9a-f]{8}\.[A-Za-z0-9_-]{20,80}$/.test(codigo) ? codigo : "";
}

/** Teclado del PIN: un número más, «borrar» quita el último; nunca pasa de 3. */
export function teclaPin(actual: string, tecla: string): string {
  if (tecla === "borrar") return actual.slice(0, -1);
  if (!/^[0-9]$/.test(tecla) || actual.length >= LARGO_PIN) return actual;
  return actual + tecla;
}
