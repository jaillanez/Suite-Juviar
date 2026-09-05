export const PERFILES = ["campo", "deposito", "bascula"] as const;
export type Perfil = (typeof PERFILES)[number];

/** El backend devuelve el perfil según puesto y sector del legajo de Nexus. */
export interface SesionMovil {
  legajo: string;
  nombreCompleto: string;
  empresa: "ENAV" | "JUBIAR";
  perfil: Perfil;
}
