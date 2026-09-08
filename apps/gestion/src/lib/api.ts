export class ErrorApi extends Error {
  constructor(message: string, public estado: number) { super(message); }
}

export async function api<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "/backend";
  const guardada = typeof window === "undefined" ? null : sessionStorage.getItem("gestion-sesion");
  const sesion = guardada ? JSON.parse(guardada) as { perfil: string; empresa: string } : null;
  const respuesta = await fetch(`${base}/${ruta.replace(/^\//, "")}`, {
    cache: "no-store",
    ...opciones,
    headers: {
      "Content-Type": "application/json",
      ...(sesion ? {
        "X-Perfil-Simulado": sesion.perfil,
        "X-Empresa-Simulada": sesion.empresa,
        "X-Actor-Simulado": `${sesion.perfil.toLowerCase()}-prueba`,
      } : {}),
      ...opciones?.headers,
    },
  });
  const cuerpo = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    const mensaje = cuerpo?.detail ?? cuerpo?.error ?? "No pudimos completar la operación.";
    throw new ErrorApi(typeof mensaje === "string" ? mensaje : "Revisá los datos e intentá nuevamente.", respuesta.status);
  }
  return cuerpo as T;
}
