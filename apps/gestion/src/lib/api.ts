export class ErrorApi extends Error {
  constructor(message: string, public estado: number) { super(message); }
}

function cabecerasSesion(): Record<string, string> {
  const guardada = typeof window === "undefined" ? null : sessionStorage.getItem("gestion-sesion");
  const sesion = guardada ? JSON.parse(guardada) as { perfil: string; empresa: string } : null;
  return sesion ? {
    "X-Perfil-Simulado": sesion.perfil,
    "X-Empresa-Simulada": sesion.empresa,
    "X-Actor-Simulado": `${sesion.perfil.toLowerCase()}-prueba`,
  } : {};
}

export async function api<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "/backend";
  const respuesta = await fetch(`${base}/${ruta.replace(/^\//, "")}`, {
    cache: "no-store",
    ...opciones,
    headers: {
      "Content-Type": "application/json",
      ...cabecerasSesion(),
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

export async function abrirArchivo(ruta: string): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "/backend";
  const pestaña = window.open("about:blank", "_blank");
  try {
    const respuesta = await fetch(`${base}/${ruta.replace(/^\//, "")}`, {
      cache: "no-store",
      headers: cabecerasSesion(),
    });
    if (!respuesta.ok) {
      const cuerpo = await respuesta.json().catch(() => null);
      throw new ErrorApi(cuerpo?.detail ?? cuerpo?.error ?? "No pudimos abrir el archivo.", respuesta.status);
    }
    const url = URL.createObjectURL(await respuesta.blob());
    if (pestaña) pestaña.location.href = url;
    else window.location.href = url;
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    pestaña?.close();
    throw error;
  }
}
