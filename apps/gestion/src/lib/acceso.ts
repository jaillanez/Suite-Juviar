export type Empresa = "ENAV" | "JUBIAR";
export type Perfil = "SUPERADMIN" | "RRHH" | "MEDICO" | "HYS" | "COMPRAS" | "SUPERVISOR" | "MANTENIMIENTO" | "ENCARGADO_MANTENIMIENTO" | "BODEGA" | "CAMPO" | "BASCULA" | "DEPOSITO" | "LABORATORIO" | "PRODUCCION" | "COMERCIAL";
export type Seccion = "inicio" | "produccion" | "fila" | "bot" | "epp" | "analitica" | "seleccion" | "capacitaciones" | "legajo" | "salud" | "turnos" | "contactos" | "configuracion" | "usuarios" | "parametros" | "cosecha" | "personal" | "activos" | "mosto";

export const todasLasSecciones: Seccion[] = [
  "inicio", "epp", "analitica", "seleccion", "capacitaciones", "legajo",
  "salud", "turnos", "activos", "produccion", "fila", "cosecha", "mosto", "bot", "contactos", "personal", "configuracion", "usuarios", "parametros",
];

export const perfiles: Record<Perfil, { nombre: string; secciones: Seccion[] }> = {
  SUPERADMIN: { nombre: "Superadministrador", secciones: todasLasSecciones },
  RRHH: { nombre: "RRHH general", secciones: ["inicio", "epp", "seleccion", "capacitaciones", "legajo", "turnos", "configuracion"] },
  MEDICO: { nombre: "Servicio médico", secciones: ["inicio", "salud", "configuracion"] },
  HYS: { nombre: "Higiene y Seguridad", secciones: ["inicio", "epp", "analitica", "capacitaciones", "configuracion"] },
  COMPRAS: { nombre: "Compras", secciones: ["inicio", "epp", "analitica", "mosto", "configuracion"] },
  SUPERVISOR: { nombre: "Supervisión", secciones: ["inicio", "capacitaciones", "turnos", "configuracion"] },
  MANTENIMIENTO: { nombre: "Mantenimiento", secciones: ["inicio", "activos", "configuracion"] },
  // Además firma (autoriza) los remitos de salida de equipos y herramientas.
  ENCARGADO_MANTENIMIENTO: { nombre: "Encargado de Mantenimiento", secciones: ["inicio", "activos", "configuracion"] },
  BODEGA: { nombre: "Administración de bodega", secciones: ["inicio", "produccion", "fila", "cosecha", "bot", "contactos", "configuracion"] },
  CAMPO: { nombre: "Recepción de campo", secciones: ["inicio", "produccion", "configuracion"] },
  BASCULA: { nombre: "Operación de báscula", secciones: ["inicio", "produccion", "fila", "mosto", "configuracion"] },
  // Entrega EPP desde el celular (/celular); en la computadora sólo ve su cuenta.
  DEPOSITO: { nombre: "Depósito (entrega de EPP)", secciones: ["inicio", "configuracion"] },
  LABORATORIO: { nombre: "Laboratorio", secciones: ["inicio", "mosto", "configuracion"] },
  PRODUCCION: { nombre: "Jefatura de Producción", secciones: ["inicio", "mosto", "configuracion"] },
  COMERCIAL: { nombre: "Jefatura Comercial", secciones: ["inicio", "mosto", "configuracion"] },
};

export const nombres: Record<Seccion, string> = {
  inicio: "Resumen", epp: "EPP", analitica: "Analítica", seleccion: "Selección",
  capacitaciones: "Capacitaciones", legajo: "Legajos", salud: "Salud", turnos: "Turnos",
  produccion: "Recepción", fila: "Fila de camiones", bot: "Conversaciones del bot",
  contactos: "Contactos", configuracion: "Empresa y perfil", usuarios: "Usuarios", parametros: "Parámetros", cosecha: "Turnos de cosecha", personal: "Personal en el bot", activos: "Equipos y activos", mosto: "Mosto",
};

export const gruposMenu: { nombre: string; secciones: Seccion[] }[] = [
  { nombre: "General", secciones: ["inicio"] },
  { nombre: "RRHH", secciones: ["epp", "analitica", "seleccion", "capacitaciones", "legajo", "salud", "turnos"] },
  { nombre: "Mantenimiento", secciones: ["activos"] },
  { nombre: "Producción", secciones: ["produccion", "fila", "cosecha", "mosto"] },
  { nombre: "Bot", secciones: ["bot", "contactos", "personal"] },
  { nombre: "Configuración", secciones: ["configuracion", "usuarios", "parametros"] },
];

export function puedeEntrar(perfil: Perfil, seccion: Seccion): boolean {
  return perfiles[perfil].secciones.includes(seccion);
}
