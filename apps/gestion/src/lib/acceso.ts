export type Empresa = "ENAV" | "JUBIAR";
export type Perfil = "RRHH" | "MEDICO" | "HYS" | "COMPRAS" | "SUPERVISOR";
export type Seccion = "inicio" | "epp" | "analitica" | "seleccion" | "capacitaciones" | "legajo" | "salud" | "turnos";

export const perfiles: Record<Perfil, { nombre: string; secciones: Seccion[] }> = {
  RRHH: { nombre: "RRHH general", secciones: ["inicio", "epp", "seleccion", "capacitaciones", "legajo", "turnos"] },
  MEDICO: { nombre: "Servicio médico", secciones: ["inicio", "salud"] },
  HYS: { nombre: "Higiene y Seguridad", secciones: ["inicio", "epp", "analitica", "capacitaciones"] },
  COMPRAS: { nombre: "Compras", secciones: ["inicio", "epp", "analitica"] },
  SUPERVISOR: { nombre: "Supervisión", secciones: ["inicio", "capacitaciones", "turnos"] },
};

export const nombres: Record<Seccion, string> = {
  inicio: "Resumen", epp: "EPP", analitica: "Analítica", seleccion: "Selección",
  capacitaciones: "Capacitaciones", legajo: "Legajos", salud: "Salud", turnos: "Turnos",
};

export function puedeEntrar(perfil: Perfil, seccion: Seccion): boolean {
  return perfiles[perfil].secciones.includes(seccion);
}
