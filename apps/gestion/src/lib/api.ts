// Servidor de demostración: sin avisos de «datos de prueba» en pantalla.
export const ocultarMarcasPrueba = process.env.NEXT_PUBLIC_OCULTAR_MARCAS_PRUEBA === "1";

export class ErrorApi extends Error {
  constructor(message: string, public estado: number) { super(message); }
}

// Con ingreso real la sesión viaja en una cookie que el navegador no deja leer.
export function ingresoReal(): boolean {
  return typeof window !== "undefined" && sessionStorage.getItem("gestion-modo") === "real";
}

function cabecerasSesion(): Record<string, string> {
  if (ingresoReal()) return {};
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
  if (respuesta.status === 401 && ingresoReal() && !ruta.replace(/^\//, "").startsWith("ingreso")) {
    sessionStorage.removeItem("gestion-sesion");
    window.location.assign("/");
  }
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
