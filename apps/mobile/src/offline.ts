export type ItemEntregaOffline = {
  codigo: string;
  cantidad: number;
};

export type EntregaOffline = {
  id_cliente: string;
  legajo: string;
  items: ItemEntregaOffline[];
  metodo_firma: "TRAZO_TABLET" | "PIN";
  evidencia_firma: string;
  entregada_en: string;
  actor_declarado: string;
  observaciones: string;
};

export type EntregaEnCola = {
  entrega: EntregaOffline;
  creada_en: string;
  intentos: number;
  proximo_intento_en: string;
};

export type ConfirmacionEntrega = {
  id: string;
  items: number;
  constancia: string;
};

export type ResultadoRegistro =
  | { estado: "CONFIRMADA"; confirmacion: ConfirmacionEntrega }
  | { estado: "PENDIENTE" };

export interface AlmacenCola {
  listar(): Promise<EntregaEnCola[]>;
  guardar(registro: EntregaEnCola): Promise<void>;
  eliminar(id: string): Promise<void>;
}

export type EnviarEntrega = (entrega: EntregaOffline) => Promise<ConfirmacionEntrega>;

// Requiere confirmación de Operaciones/HyS antes de salir del entorno de prueba.
export const POLITICA_COLA = Object.freeze({
  estado: "PROPUESTA_SIN_VALIDAR",
  maximoPendientes: 20,
  maximaAntiguedadMs: 24 * 60 * 60 * 1000,
  esperaInicialMs: 5_000,
  esperaMaximaMs: 15 * 60 * 1000,
});

export class ColaBloqueada extends Error {}

export function motivoBloqueo(
  pendientes: EntregaEnCola[],
  ahora = new Date(),
): string | null {
  if (pendientes.length >= POLITICA_COLA.maximoPendientes) {
    return `Hay ${pendientes.length} entregas pendientes (límite provisional: ${POLITICA_COLA.maximoPendientes}).`;
  }
  const masAntigua = pendientes.reduce<number | null>((minimo, pendiente) => {
    const creada = Date.parse(pendiente.creada_en);
    return minimo === null || creada < minimo ? creada : minimo;
  }, null);
  if (
    masAntigua !== null
    && ahora.getTime() - masAntigua >= POLITICA_COLA.maximaAntiguedadMs
  ) {
    return "La entrega pendiente más antigua lleva 24 horas sin sincronizar.";
  }
  return null;
}

export function esperaReintentoMs(intentos: number): number {
  return Math.min(
    POLITICA_COLA.esperaInicialMs * 2 ** Math.max(0, intentos - 1),
    POLITICA_COLA.esperaMaximaMs,
  );
}

function registroInicial(entrega: EntregaOffline, ahora: Date): EntregaEnCola {
  return {
    entrega,
    creada_en: ahora.toISOString(),
    intentos: 0,
    proximo_intento_en: ahora.toISOString(),
  };
}

function conFallo(registro: EntregaEnCola, ahora: Date): EntregaEnCola {
  const intentos = registro.intentos + 1;
  return {
    ...registro,
    intentos,
    proximo_intento_en: new Date(ahora.getTime() + esperaReintentoMs(intentos)).toISOString(),
  };
}

export async function registrarConCola(
  almacen: AlmacenCola,
  entrega: EntregaOffline,
  enviar: EnviarEntrega,
  ahora = new Date(),
): Promise<ResultadoRegistro> {
  const pendientes = await almacen.listar();
  const bloqueo = motivoBloqueo(pendientes, ahora);
  if (bloqueo) throw new ColaBloqueada(bloqueo);

  // El commit local ocurre antes de tocar la red. Una caída durante el POST no
  // puede borrar la firma ni hacerle creer al operador que hubo confirmación.
  const registro = registroInicial(entrega, ahora);
  await almacen.guardar(registro);
  try {
    const confirmacion = await enviar(entrega);
    await almacen.eliminar(entrega.id_cliente);
    return { estado: "CONFIRMADA", confirmacion };
  } catch {
    await almacen.guardar(conFallo(registro, ahora));
    return { estado: "PENDIENTE" };
  }
}

export async function sincronizarCola(
  almacen: AlmacenCola,
  enviar: EnviarEntrega,
  ahora = new Date(),
): Promise<ConfirmacionEntrega[]> {
  const confirmadas: ConfirmacionEntrega[] = [];
  const pendientes = (await almacen.listar()).sort(
    (a, b) => Date.parse(a.creada_en) - Date.parse(b.creada_en),
  );
  for (const registro of pendientes) {
    if (Date.parse(registro.proximo_intento_en) > ahora.getTime()) continue;
    try {
      const confirmacion = await enviar(registro.entrega);
      await almacen.eliminar(registro.entrega.id_cliente);
      confirmadas.push(confirmacion);
    } catch {
      await almacen.guardar(conFallo(registro, ahora));
    }
  }
  return confirmadas;
}

const NOMBRE_BASE = "suite-juviar-rrhh-epp";
const NOMBRE_ALMACEN = "entregas_pendientes";

function esperarSolicitud<T>(solicitud: IDBRequest<T>): Promise<T> {
  return new Promise((resolver, rechazar) => {
    solicitud.onsuccess = () => resolver(solicitud.result);
    solicitud.onerror = () => rechazar(solicitud.error ?? new Error("Falló IndexedDB"));
  });
}

function esperarTransaccion(transaccion: IDBTransaction): Promise<void> {
  return new Promise((resolver, rechazar) => {
    transaccion.oncomplete = () => resolver();
    transaccion.onerror = () => rechazar(transaccion.error ?? new Error("Falló IndexedDB"));
    transaccion.onabort = () => rechazar(transaccion.error ?? new Error("IndexedDB abortó"));
  });
}

export class AlmacenIndexedDB implements AlmacenCola {
  private base: Promise<IDBDatabase> | null = null;

  private abrir(): Promise<IDBDatabase> {
    if (this.base) return this.base;
    this.base = new Promise((resolver, rechazar) => {
      const solicitud = indexedDB.open(NOMBRE_BASE, 1);
      solicitud.onupgradeneeded = () => {
        const base = solicitud.result;
        if (!base.objectStoreNames.contains(NOMBRE_ALMACEN)) {
          base.createObjectStore(NOMBRE_ALMACEN, { keyPath: "entrega.id_cliente" });
        }
      };
      solicitud.onsuccess = () => resolver(solicitud.result);
      solicitud.onerror = () => rechazar(solicitud.error ?? new Error("No se pudo abrir IndexedDB"));
    });
    return this.base;
  }

  async listar(): Promise<EntregaEnCola[]> {
    const base = await this.abrir();
    const transaccion = base.transaction(NOMBRE_ALMACEN, "readonly");
    return esperarSolicitud(
      transaccion.objectStore(NOMBRE_ALMACEN).getAll() as IDBRequest<EntregaEnCola[]>,
    );
  }

  async guardar(registro: EntregaEnCola): Promise<void> {
    const base = await this.abrir();
    const transaccion = base.transaction(NOMBRE_ALMACEN, "readwrite");
    transaccion.objectStore(NOMBRE_ALMACEN).put(registro);
    await esperarTransaccion(transaccion);
  }

  async eliminar(id: string): Promise<void> {
    const base = await this.abrir();
    const transaccion = base.transaction(NOMBRE_ALMACEN, "readwrite");
    transaccion.objectStore(NOMBRE_ALMACEN).delete(id);
    await esperarTransaccion(transaccion);
  }
}
