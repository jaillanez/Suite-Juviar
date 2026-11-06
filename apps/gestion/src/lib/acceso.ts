export type Empresa = "ENAV" | "JUBIAR";
export type Perfil = "SUPERADMIN" | "RRHH" | "MEDICO" | "HYS" | "COMPRAS" | "SUPERVISOR" | "MANTENIMIENTO" | "BODEGA" | "CAMPO" | "BASCULA" | "DEPOSITO";
export type Seccion = "inicio" | "produccion" | "fila" | "bot" | "epp" | "analitica" | "seleccion" | "capacitaciones" | "legajo" | "salud" | "turnos" | "contactos" | "configuracion" | "usuarios" | "parametros" | "cosecha" | "personal" | "activos";

export const todasLasSecciones: Seccion[] = [
  "inicio", "epp", "analitica", "seleccion", "capacitaciones", "legajo",
  "salud", "turnos", "activos", "produccion", "fila", "cosecha", "bot", "contactos", "personal", "configuracion", "usuarios", "parametros",
];

export const perfiles: Record<Perfil, { nombre: string; secciones: Seccion[] }> = {
  SUPERADMIN: { nombre: "Superadministrador", secciones: todasLasSecciones },
  RRHH: { nombre: "RRHH general", secciones: ["inicio", "epp", "seleccion", "capacitaciones", "legajo", "turnos", "configuracion"] },
  MEDICO: { nombre: "Servicio médico", secciones: ["inicio", "salud", "configuracion"] },
  HYS: { nombre: "Higiene y Seguridad", secciones: ["inicio", "epp", "analitica", "capacitaciones", "configuracion"] },
  COMPRAS: { nombre: "Compras", secciones: ["inicio", "epp", "analitica", "configuracion"] },
  SUPERVISOR: { nombre: "Supervisión", secciones: ["inicio", "capacitaciones", "turnos", "configuracion"] },
  MANTENIMIENTO: { nombre: "Mantenimiento", secciones: ["inicio", "activos", "configuracion"] },
  BODEGA: { nombre: "Administración de bodega", secciones: ["inicio", "produccion", "fila", "cosecha", "bot", "contactos", "configuracion"] },
  CAMPO: { nombre: "Recepción de campo", secciones: ["inicio", "produccion", "configuracion"] },
  BASCULA: { nombre: "Operación de báscula", secciones: ["inicio", "produccion", "configuracion"] },
  // Entrega EPP desde el celular (/celular); en la computadora sólo ve su cuenta.
  DEPOSITO: { nombre: "Depósito (entrega de EPP)", secciones: ["inicio", "configuracion"] },
};

export const nombres: Record<Seccion, string> = {
  inicio: "Resumen", epp: "EPP", analitica: "Analítica", seleccion: "Selección",
  capacitaciones: "Capacitaciones", legajo: "Legajos", salud: "Salud", turnos: "Turnos",
  produccion: "Recepción", fila: "Fila de camiones", bot: "Conversaciones del bot",
  contactos: "Contactos", configuracion: "Empresa y perfil", usuarios: "Usuarios", parametros: "Parámetros", cosecha: "Turnos de cosecha", personal: "Personal en el bot", activos: "Equipos y activos",
};

export const gruposMenu: { nombre: string; secciones: Seccion[] }[] = [
  { nombre: "General", secciones: ["inicio"] },
  { nombre: "RRHH", secciones: ["epp", "analitica", "seleccion", "capacitaciones", "legajo", "salud", "turnos"] },
  { nombre: "Mantenimiento", secciones: ["activos"] },
  { nombre: "Producción", secciones: ["produccion", "fila", "cosecha"] },
  { nombre: "Bot", secciones: ["bot", "contactos", "personal"] },
  { nombre: "Configuración", secciones: ["configuracion", "usuarios", "parametros"] },
];

export function puedeEntrar(perfil: Perfil, seccion: Seccion): boolean {
  return perfiles[perfil].secciones.includes(seccion);
}
