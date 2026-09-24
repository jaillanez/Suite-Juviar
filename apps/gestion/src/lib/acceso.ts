export type Empresa = "ENAV" | "JUBIAR";
export type Perfil = "SUPERADMIN" | "RRHH" | "MEDICO" | "HYS" | "COMPRAS" | "SUPERVISOR" | "BODEGA" | "CAMPO" | "BASCULA";
export type Seccion = "inicio" | "produccion" | "epp" | "analitica" | "seleccion" | "capacitaciones" | "legajo" | "salud" | "turnos" | "contactos";

export const todasLasSecciones: Seccion[] = [
  "inicio", "produccion", "epp", "analitica", "seleccion",
  "capacitaciones", "legajo", "salud", "turnos", "contactos",
];

export const perfiles: Record<Perfil, { nombre: string; secciones: Seccion[] }> = {
  SUPERADMIN: { nombre: "Superadministrador", secciones: todasLasSecciones },
  RRHH: { nombre: "RRHH general", secciones: ["inicio", "epp", "seleccion", "capacitaciones", "legajo", "turnos"] },
  MEDICO: { nombre: "Servicio médico", secciones: ["inicio", "salud"] },
  HYS: { nombre: "Higiene y Seguridad", secciones: ["inicio", "epp", "analitica", "capacitaciones"] },
  COMPRAS: { nombre: "Compras", secciones: ["inicio", "epp", "analitica"] },
  SUPERVISOR: { nombre: "Supervisión", secciones: ["inicio", "capacitaciones", "turnos"] },
  BODEGA: { nombre: "Administración de bodega", secciones: ["inicio", "produccion", "contactos"] },
  CAMPO: { nombre: "Recepción de campo", secciones: ["inicio", "produccion"] },
  BASCULA: { nombre: "Operación de báscula", secciones: ["inicio", "produccion"] },
};

export const nombres: Record<Seccion, string> = {
  inicio: "Resumen", epp: "EPP", analitica: "Analítica", seleccion: "Selección",
  capacitaciones: "Capacitaciones", legajo: "Legajos", salud: "Salud", turnos: "Turnos",
  contactos: "Contactos de productores", produccion: "Producción",
};

export function puedeEntrar(perfil: Perfil, seccion: Seccion): boolean {
  return perfiles[perfil].secciones.includes(seccion);
}
