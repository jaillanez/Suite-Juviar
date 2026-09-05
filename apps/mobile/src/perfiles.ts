export const PERFILES = ["campo", "deposito", "bascula"] as const;
export type Perfil = (typeof PERFILES)[number];

/** El backend devuelve el perfil según puesto y sector del legajo de Nexus. */
export interface ContextoMovil {
  legajo: string;
  nombre_completo: string;
  empresa: "ENAV" | "JUBIAR";
  perfil: Perfil;
}

export const DATOS_PERFIL: Record<Perfil, { titulo: string; detalle: string }> = {
  campo: { titulo: "Campo", detalle: "Fichaje y tareaje en el cuartel" },
  deposito: { titulo: "Depósito", detalle: "Entrega y firma de EPP" },
  bascula: { titulo: "Báscula", detalle: "Pesadas y romaneos" },
};
