// «¿Olvidaste tu contraseña?»: el correo trae `/restablecer/#<código>`. El código va después
// de «#» para que no viaje al servidor en la dirección ni quede en registros: la pantalla lo
// lee y lo manda sólo junto con la contraseña nueva.

export const CLAVE_MINIMA = 10;

/** Código del enlace, o "" si la dirección no trae uno con la forma esperada. */
export function tokenDelEnlace(hash: string): string {
  let token = "";
  try { token = decodeURIComponent(hash.replace(/^#/, "").trim()); } catch { return ""; }
  return /^[A-Za-z0-9_-]{40,100}$/.test(token) ? token : "";
}

/** Mismas reglas que el servidor (validar_clave); "" si la contraseña sirve. */
export function problemaDeClave(clave: string): string {
  if (clave.length < CLAVE_MINIMA) return `La contraseña debe tener al menos ${CLAVE_MINIMA} caracteres.`;
  if (clave.trim() !== clave || !clave.trim()) return "La contraseña no puede empezar ni terminar con espacios.";
  return "";
}
