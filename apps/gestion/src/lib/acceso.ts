export type Empresa = "ENAV" | "JUBIAR";
export type Perfil = "SUPERADMIN" | "RRHH" | "MEDICO" | "HYS" | "COMPRAS" | "SUPERVISOR" | "BODEGA" | "CAMPO" | "BASCULA";
export type Seccion = "inicio" | "produccion" | "fila" | "bot" | "epp" | "analitica" | "seleccion" | "capacitaciones" | "legajo" | "salud" | "turnos" | "contactos" | "configuracion";

export const todasLasSecciones: Seccion[] = [
  "inicio", "epp", "analitica", "seleccion", "capacitaciones", "legajo",
  "salud", "turnos", "produccion", "fila", "bot", "contactos", "configuracion",
];

export const perfiles: Record<Perfil, { nombre: string; secciones: Seccion[] }> = {
  SUPERADMIN: { nombre: "Superadministrador", secciones: todasLasSecciones },
  RRHH: { nombre: "RRHH general", secciones: ["inicio", "epp", "seleccion", "capacitaciones", "legajo", "turnos", "configuracion"] },
  MEDICO: { nombre: "Servicio médico", secciones: ["inicio", "salud", "configuracion"] },
  HYS: { nombre: "Higiene y Seguridad", secciones: ["inicio", "epp", "analitica", "capacitaciones", "configuracion"] },
  COMPRAS: { nombre: "Compras", secciones: ["inicio", "epp", "analitica", "configuracion"] },
  SUPERVISOR: { nombre: "Supervisión", secciones: ["inicio", "capacitaciones", "turnos", "configuracion"] },
  BODEGA: { nombre: "Administración de bodega", secciones: ["inicio", "produccion", "fila", "bot", "contactos", "configuracion"] },
  CAMPO: { nombre: "Recepción de campo", secciones: ["inicio", "produccion", "configuracion"] },
  BASCULA: { nombre: "Operación de báscula", secciones: ["inicio", "produccion", "configuracion"] },
};

export const nombres: Record<Seccion, string> = {
  inicio: "Resumen", epp: "EPP", analitica: "Analítica", seleccion: "Selección",
  capacitaciones: "Capacitaciones", legajo: "Legajos", salud: "Salud", turnos: "Turnos",
  produccion: "Recepción", fila: "Fila de camiones", bot: "Consultas de productores",
  contactos: "Contactos", configuracion: "Empresa y perfil",
};

export const gruposMenu: { nombre: string; secciones: Seccion[] }[] = [
  { nombre: "General", secciones: ["inicio"] },
  { nombre: "RRHH", secciones: ["epp", "analitica", "seleccion", "capacitaciones", "legajo", "salud", "turnos"] },
  { nombre: "Producción", secciones: ["produccion", "fila"] },
  { nombre: "Bot", secciones: ["bot", "contactos"] },
  { nombre: "Configuración", secciones: ["configuracion"] },
];

export function puedeEntrar(perfil: Perfil, seccion: Seccion): boolean {
  return perfiles[perfil].secciones.includes(seccion);
}
