"use client";

import { FormEvent, PointerEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  AlmacenIndexedDB,
  type ConfirmacionEntrega,
  type EntregaOffline,
  motivoBloqueo,
  POLITICA_COLA,
  registrarConCola,
  sincronizarCola,
} from "../offline";
import { ContextoMovil, DATOS_PERFIL } from "../perfiles";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/backend/rrhh-epp";

type Resultado = {
  legajo: string;
  nombre_completo: string;
  dni: string;
  puesto: string;
  sector: string;
  empresa: string;
};

type Elemento = {
  codigo: string;
  producto: string;
  tipo_modelo: string;
  marca: string;
  posee_certificacion: boolean;
  certificacion: string | null;
  unidad: string;
  cantidad_sugerida: number;
  frecuencia: string;
  temporada: string;
  obligatorio: boolean;
  fundamento: string;
  origen: "BASE" | "SECTOR" | "PUESTO";
  ultima_entrega: string | null;
};

type Ficha = {
  cabecera: Resultado & { tipo_vinculo: string; fuente: string };
  epp_requerido: Elemento[];
  historial: Array<{ id: string; fecha: string; items: number }>;
};

async function pedir<T>(ruta: string, legajo: string, opciones?: RequestInit): Promise<T> {
  const respuesta = await fetch(`${API}${ruta}`, {
    ...opciones,
    headers: {
      "Content-Type": "application/json",
      "X-Legajo-Usuario": legajo,
      ...opciones?.headers,
    },
  });
  const cuerpo = await respuesta.json().catch(() => ({ detail: "Respuesta ilegible" }));
  if (!respuesta.ok) throw new Error(cuerpo.error ?? cuerpo.detail ?? "Error inesperado");
  return cuerpo as T;
}

function Acceso({ alIngresar }: { alIngresar: (contexto: ContextoMovil) => void }) {
  const [legajo, setLegajo] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  async function ingresar(evento?: FormEvent) {
    evento?.preventDefault();
    setCargando(true);
    setError("");
    try {
      alIngresar(await pedir<ContextoMovil>("/sesion", legajo.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No fue posible iniciar la sesión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="acceso">
      <p className="kicker">SUITE JUVIAR · IDENTIDAD DECLARADA · SOLO LOCAL</p>
      <h1>Una aplicación. Tu perfil.</h1>
      <p className="description">
        Prueba sin autenticación: cualquiera con acceso local puede declarar otro legajo. El
        backend asigna el perfil desde Parametría.
      </p>
      <form className="panel acceso-form" onSubmit={ingresar}>
        <label htmlFor="legajo">Legajo del usuario</label>
        <input
          id="legajo"
          value={legajo}
          onChange={(e) => setLegajo(e.target.value)}
          placeholder="1210"
          inputMode="numeric"
          autoFocus
        />
        <button className="principal" disabled={!legajo.trim() || cargando}>
          {cargando ? "Verificando…" : "Ingresar"}
        </button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
      <div className="demo">
        <span>Usuarios de demostración</span>
        <button type="button" onClick={() => setLegajo("1210")}>1210 · depósito</button>
        <button type="button" onClick={() => setLegajo("1501")}>1501 · campo</button>
        <button type="button" onClick={() => setLegajo("1601")}>1601 · báscula</button>
      </div>
    </main>
  );
}

function Firma({ alCambiar }: { alCambiar: (valor: string) => void }) {
  const lienzo = useRef<HTMLCanvasElement>(null);
  const dibujando = useRef(false);

  function punto(evento: PointerEvent<HTMLCanvasElement>) {
    const canvas = lienzo.current;
    if (!canvas) return;
    const caja = canvas.getBoundingClientRect();
    return {
      x: (evento.clientX - caja.left) * (canvas.width / caja.width),
      y: (evento.clientY - caja.top) * (canvas.height / caja.height),
    };
  }

  function iniciar(evento: PointerEvent<HTMLCanvasElement>) {
    const canvas = lienzo.current;
    const p = punto(evento);
    if (!canvas || !p) return;
    canvas.setPointerCapture(evento.pointerId);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    dibujando.current = true;
  }

  function mover(evento: PointerEvent<HTMLCanvasElement>) {
    if (!dibujando.current) return;
    const canvas = lienzo.current;
    const p = punto(evento);
    if (!canvas || !p) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#141a1f";
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    alCambiar(canvas.toDataURL("image/png"));
  }

  function terminar() {
    dibujando.current = false;
  }

  function borrar() {
    const canvas = lienzo.current;
    canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    alCambiar("");
  }

  return (
    <div className="firma">
      <canvas
        ref={lienzo}
        width={900}
        height={220}
        aria-label="Firma del trabajador"
        onPointerDown={iniciar}
        onPointerMove={mover}
        onPointerUp={terminar}
        onPointerCancel={terminar}
      />
      <button type="button" onClick={borrar}>Borrar firma</button>
    </div>
  );
}

function Deposito({ sesion }: { sesion: ContextoMovil }) {
  const almacen = useRef<AlmacenIndexedDB | null>(null);
  const sincronizacionActiva = useRef(false);
  const [consulta, setConsulta] = useState("");
  const [resultados, setResultados] = useState<Resultado[]>([]);
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [seleccion, setSeleccion] = useState<Record<string, boolean>>({});
  const [cantidades, setCantidades] = useState<Record<string, number>>({});
  const [firma, setFirma] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const [buscado, setBuscado] = useState(false);
  const [pendientes, setPendientes] = useState(0);
  const [bloqueoCola, setBloqueoCola] = useState<string | null>(null);
  const [colaPreparada, setColaPreparada] = useState(false);
  const [sincronizando, setSincronizando] = useState(false);
  const [constancia, setConstancia] = useState<string | null>(null);

  const obtenerAlmacen = useCallback(() => {
    if (!almacen.current) almacen.current = new AlmacenIndexedDB();
    return almacen.current;
  }, []);

  const refrescarCola = useCallback(async () => {
    const lista = await obtenerAlmacen().listar();
    setPendientes(lista.length);
    setBloqueoCola(motivoBloqueo(lista));
    setColaPreparada(true);
  }, [obtenerAlmacen]);

  const enviar = useCallback((entrega: EntregaOffline) => pedir<ConfirmacionEntrega>(
    "/entregas",
    sesion.legajo,
    { method: "POST", body: JSON.stringify(entrega) },
  ), [sesion.legajo]);

  const sincronizar = useCallback(async () => {
    if (sincronizacionActiva.current) return;
    sincronizacionActiva.current = true;
    setSincronizando(true);
    try {
      const confirmadas = await sincronizarCola(obtenerAlmacen(), enviar);
      await refrescarCola();
      if (confirmadas.length > 0) {
        const ultima = confirmadas.at(-1)!;
        setMensaje(`Se sincronizaron ${confirmadas.length} entrega(s).`);
        setConstancia(`${API}/constancias/${ultima.id}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "No fue posible leer la cola local");
    } finally {
      sincronizacionActiva.current = false;
      setSincronizando(false);
    }
  }, [enviar, obtenerAlmacen, refrescarCola]);

  useEffect(() => {
    void sincronizar();
    const alRecuperarConexion = () => void sincronizar();
    window.addEventListener("online", alRecuperarConexion);
    const temporizador = window.setInterval(() => void sincronizar(), 30_000);
    return () => {
      window.removeEventListener("online", alRecuperarConexion);
      window.clearInterval(temporizador);
    };
  }, [sincronizar]);

  async function buscar(evento: FormEvent) {
    evento.preventDefault();
    if (bloqueoCola) {
      setError(`${bloqueoCola} Recupere la conexión antes de iniciar otra entrega.`);
      return;
    }
    setError("");
    setCargando(true);
    setBuscado(false);
    try {
      setResultados(await pedir<Resultado[]>(`/legajos?q=${encodeURIComponent(consulta)}`, sesion.legajo));
      setBuscado(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No fue posible buscar");
    } finally {
      setCargando(false);
    }
  }

  async function elegir(numero: string) {
    setError("");
    setMensaje("");
    setCargando(true);
    try {
      const nueva = await pedir<Ficha>(`/legajos/${numero}`, sesion.legajo);
      setFicha(nueva);
      setResultados([]);
      setBuscado(false);
      setSeleccion({});
      setCantidades(Object.fromEntries(nueva.epp_requerido.map((e) => [e.codigo, e.cantidad_sugerida])));
      setFirma("");
      setConstancia(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No fue posible abrir el legajo");
    } finally {
      setCargando(false);
    }
  }

  async function registrar() {
    if (!ficha) return;
    if (bloqueoCola) {
      setError(`${bloqueoCola} Recupere la conexión antes de registrar otra entrega.`);
      return;
    }
    const items = ficha.epp_requerido
      .filter((elemento) => seleccion[elemento.codigo])
      .map((elemento) => ({ codigo: elemento.codigo, cantidad: cantidades[elemento.codigo] ?? 1 }));
    setError("");
    setMensaje("");
    setConstancia(null);
    setCargando(true);
    try {
      const entrega: EntregaOffline = {
        id_cliente: `tablet-${globalThis.crypto.randomUUID()}`,
        legajo: ficha.cabecera.legajo,
        items,
        metodo_firma: "TRAZO_TABLET",
        evidencia_firma: firma,
        entregada_en: new Date().toISOString(),
        actor_declarado: sesion.legajo,
        observaciones: "",
      };
      const resultado = await registrarConCola(obtenerAlmacen(), entrega, enviar);
      await refrescarCola();
      if (resultado.estado === "CONFIRMADA") {
        setMensaje(
          `Entrega ${resultado.confirmacion.id} registrada: ${resultado.confirmacion.items} elemento(s).`,
        );
        setConstancia(`${API}/constancias/${resultado.confirmacion.id}`);
      } else {
        setMensaje(
          `Entrega ${entrega.id_cliente} pendiente de sincronizar. No se emitió constancia.`,
        );
      }
      setFicha(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No fue posible registrar la entrega");
    } finally {
      setCargando(false);
    }
  }

  const elegidos = Object.values(seleccion).filter(Boolean).length;

  return (
    <section className="flujo">
      <div className="aviso">Entorno de prueba · constancias sin validez legal</div>
      <div
        className={`cola-estado ${bloqueoCola ? "cola-bloqueada" : ""}`}
        role="status"
        aria-live="polite"
      >
        <strong>
          {colaPreparada ? pendientes : "—"} entrega(s) pendiente(s) de sincronizar
        </strong>
        <span>
          {sincronizando
            ? "Intentando sincronizar…"
            : `Política ${POLITICA_COLA.estado}: límite ${POLITICA_COLA.maximoPendientes} o 24 horas.`}
        </span>
        {bloqueoCola && <span>{bloqueoCola} Nuevas entregas bloqueadas.</span>}
      </div>
      <form className="panel buscador" onSubmit={buscar}>
        <label htmlFor="buscar">Trabajador: legajo, apellido o DNI</label>
        <div className="fila">
          <input id="buscar" value={consulta} onChange={(e) => setConsulta(e.target.value)} placeholder="1042 o Quiroga" />
          <button
            className="principal"
            disabled={!consulta.trim() || cargando || !colaPreparada || Boolean(bloqueoCola)}
          >
            {cargando ? "Procesando…" : "Buscar"}
          </button>
        </div>
        {buscado && resultados.length === 0 && (
          <p className="vacio" role="status">No encontramos trabajadores activos con ese dato.</p>
        )}
        {resultados.map((persona) => (
          <button
            className="resultado"
            type="button"
            key={persona.legajo}
            onClick={() => elegir(persona.legajo)}
            disabled={Boolean(bloqueoCola)}
          >
            <strong>{persona.nombre_completo}</strong>
            <span>{persona.legajo} · {persona.puesto} · {persona.empresa}</span>
          </button>
        ))}
      </form>

      {error && <p className="error" role="alert">{error}</p>}
      {mensaje && <p className="exito" role="status">{mensaje}</p>}
      {constancia && (
        <a className="constancia" href={constancia} target="_blank" rel="noreferrer">
          Abrir constancia confirmada
        </a>
      )}

      {ficha && (
        <div className="panel entrega">
          <div className="persona">
            <h2>{ficha.cabecera.nombre_completo}</h2>
            <p>Legajo {ficha.cabecera.legajo} · DNI {ficha.cabecera.dni}</p>
            <p>{ficha.cabecera.puesto} · {ficha.cabecera.sector}</p>
          </div>
          <div className="elementos">
            {ficha.epp_requerido.map((elemento) => (
              <div className={`elemento ${seleccion[elemento.codigo] ? "activo" : ""}`} key={elemento.codigo}>
                <input
                  aria-label={`Entregar ${elemento.producto}`}
                  type="checkbox"
                  checked={Boolean(seleccion[elemento.codigo])}
                  onChange={(e) => setSeleccion({ ...seleccion, [elemento.codigo]: e.target.checked })}
                />
                <div>
                  <strong>{elemento.producto}</strong>
                  <span>{elemento.codigo} · {elemento.marca} · {elemento.unidad}</span>
                  <small>{elemento.origen} · {elemento.fundamento}</small>
                  <small>Última entrega: {elemento.ultima_entrega ?? "sin registro"}</small>
                </div>
                <input
                  aria-label={`Cantidad de ${elemento.producto}`}
                  type="number"
                  min={1}
                  value={cantidades[elemento.codigo] ?? 1}
                  onChange={(e) => setCantidades({ ...cantidades, [elemento.codigo]: Number(e.target.value) })}
                />
              </div>
            ))}
          </div>
          <h3>Conformidad del trabajador</h3>
          <Firma alCambiar={setFirma} />
          <button
            className="principal confirmar"
            onClick={registrar}
            disabled={!elegidos || !firma || cargando || Boolean(bloqueoCola)}
          >
            {cargando ? "Registrando…" : "Registrar entrega"}
          </button>
        </div>
      )}
    </section>
  );
}

export default function MobileHome() {
  const [sesion, setSesion] = useState<ContextoMovil | null>(null);

  if (!sesion) return <Acceso alIngresar={setSesion} />;
  const perfil = DATOS_PERFIL[sesion.perfil];

  return (
    <main>
      <header className="cabecera-app">
        <div>
          <p className="kicker">SUITE JUVIAR · {sesion.empresa}</p>
          <h1>{perfil.titulo}</h1>
          <p>{sesion.nombre_completo} · legajo {sesion.legajo}</p>
        </div>
        <button type="button" onClick={() => setSesion(null)}>Salir</button>
      </header>
      {sesion.perfil === "deposito" ? (
        <Deposito sesion={sesion} />
      ) : (
        <section className="panel perfil-unico">
          <span>Perfil habilitado</span>
          <h2>{perfil.titulo}</h2>
          <p>{perfil.detalle}</p>
          <small>Las herramientas de otros perfiles no están disponibles para este usuario.</small>
        </section>
      )}
    </main>
  );
}
