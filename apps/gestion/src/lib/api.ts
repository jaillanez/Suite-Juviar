export class ErrorApi extends Error {
  constructor(message: string, public estado: number) { super(message); }
}

export async function api<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  const respuesta = await fetch(`/backend/${ruta.replace(/^\//, "")}`, {
    cache: "no-store",
    ...opciones,
    headers: { "Content-Type": "application/json", ...opciones?.headers },
  });
  const cuerpo = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    const mensaje = cuerpo?.detail ?? cuerpo?.error ?? "No pudimos completar la operación.";
    throw new ErrorApi(typeof mensaje === "string" ? mensaje : "Revisá los datos e intentá nuevamente.", respuesta.status);
  }
  return cuerpo as T;
}
