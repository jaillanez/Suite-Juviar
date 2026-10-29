"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ocultarMarcasPrueba } from "@/lib/api";
import { ErrorVisible } from "./compartidos";

type Romaneo = { id: string; numero: number; estado: string };
type Productor = { cuit: string; razon_social: string; codigos: string[]; ultima_entrega: string | null };
type CamionFila = { id: number; numero_dia: number | null; patente: string; patente_acoplado: string | null; clientecuit: string | null; chofer_dni: string | null; chofer_nombre: string | null; productor: string | null; variedad_declarada: string | null; estado: string };
const SEDES = [["chimbas", "Chimbas"], ["lavalle", "Lavalle"], ["media-agua", "Media Agua"]] as const;
const VACIO = { productor_cuit: "", transportista_cuit: "", chofer_dni: "", patente_chasis: "", patente_acoplado: "", variedad: "", finca: "" };
const cuitLegible = (c: string) => c.length === 11 ? `${c.slice(0, 2)}-${c.slice(2, 10)}-${c.slice(10)}` : c;
export type AreaProduccion = "recepcion" | "fila" | "bot";

const FILA_URL = process.env.NEXT_PUBLIC_FILA_URL ?? "https://juviar-bot.duckdns.org";
const BOT_URL = process.env.NEXT_PUBLIC_BOT_SIMULADOR_URL ?? "http://127.0.0.1:8099";

export function ProduccionGestion({ area = "recepcion" }: { area?: AreaProduccion }) {
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [creado, setCreado] = useState<Romaneo | null>(null);
  const [campos, setCampos] = useState(VACIO); const [productor, setProductor] = useState<Productor | null>(null);
  const [busqueda, setBusqueda] = useState(""); const [resultados, setResultados] = useState<Productor[]>([]);
  const [variedades, setVariedades] = useState<string[]>([]); const [sede, setSede] = useState("chimbas"); const [camiones, setCamiones] = useState<CamionFila[]>([]); const [avisoDatos, setAvisoDatos] = useState("");
  const poner = (clave: keyof typeof VACIO, valor: string) => setCampos(c => ({ ...c, [clave]: valor }));
  useEffect(() => { if (area !== "recepcion") return; api<string[]>("recepcion-datos/variedades").then(setVariedades).catch(() => setAvisoDatos("No se pudo leer la lista de productores y variedades: cargá los datos a mano.")); }, [area]);
  useEffect(() => { if (area !== "recepcion") return; api<CamionFila[]>(`recepcion-datos/camiones?sede=${sede}`).then(setCamiones).catch(() => setCamiones([])); }, [area, sede, creado]);
  useEffect(() => { const q = busqueda.trim(); if (q.length < 2 || productor) { setResultados([]); return; } const r = setTimeout(() => api<Productor[]>(`recepcion-datos/productores?q=${encodeURIComponent(q)}`).then(setResultados).catch(() => setResultados([])), 250); return () => clearTimeout(r); }, [busqueda, productor]);
  function elegirProductor(p: Productor) { setProductor(p); poner("productor_cuit", p.cuit); setBusqueda(p.razon_social); setResultados([]); }
  function tomarCamion(c: CamionFila) {
    setCampos(v => ({ ...v, productor_cuit: c.clientecuit ?? "", chofer_dni: c.chofer_dni ?? "", patente_chasis: c.patente, patente_acoplado: c.patente_acoplado ?? "", variedad: c.variedad_declarada ?? v.variedad }));
    setProductor(c.clientecuit ? { cuit: c.clientecuit, razon_social: c.productor ?? c.clientecuit, codigos: [], ultima_entrega: null } : null); setBusqueda(c.productor ?? "");
  }

  async function abrirRomaneo(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    setGuardando(true);
    setError("");
    setCreado(null);
    const datos = new FormData(evento.currentTarget);
    try {
      const respuesta = await api<Romaneo>("recepcion/romaneos", {
        method: "POST",
        body: JSON.stringify({
          productor_cuit: datos.get("productor_cuit"),
          transportista_cuit: datos.get("transportista_cuit"),
          chofer_dni: datos.get("chofer_dni"),
          patente_chasis: datos.get("patente_chasis"),
          patente_acoplado: datos.get("patente_acoplado") || null,
          variedad: datos.get("variedad"),
          finca: datos.get("finca") || null,
          bruto_kg: Number(datos.get("bruto_kg")),
          origen_peso: datos.get("origen_peso"),
          operador_legajo: datos.get("operador_legajo"),
        }),
      });
      setCreado(respuesta);
      formulario.reset(); setCampos(VACIO); setProductor(null); setBusqueda("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo abrir el romaneo.");
    } finally {
      setGuardando(false);
    }
  }

  return <div className="produccion">
    {area === "recepcion" && <section className="tarjeta produccion-operacion">
      <div className="titulo-fila"><div><h2>Abrir romaneo</h2><p className="ayuda">Registra el ingreso real del camión. El peso queda trazado con su origen y operador.</p></div></div>
      {error && <ErrorVisible mensaje={error} />}
      {creado && <div className="resultado-operacion" role="status"><strong>Romaneo {creado.numero} abierto</strong><span>Estado: {creado.estado}</span><small>ID {creado.id}</small></div>}
      {avisoDatos && <p className="ayuda">{avisoDatos}</p>}
      <div className="camiones-recepcion"><div className="titulo-fila"><h3>Camiones en la fila</h3><label>Bodega<select value={sede} onChange={e => setSede(e.target.value)}>{SEDES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label></div>
        {camiones.length ? <><p className="ayuda">Tocá un camión para completar sus datos.</p><ul className="lista-camiones-recepcion">{camiones.map(c => <li key={c.id}><button type="button" onClick={() => tomarCamion(c)}><strong>{c.numero_dia ? `${c.numero_dia} · ` : ""}{c.patente}</strong><span>{c.productor ?? "Productor sin confirmar"}</span><small>{c.estado === "llamado" ? "Llamado" : c.estado === "en_bascula" ? "En báscula" : "En espera"}{c.variedad_declarada ? ` · ${c.variedad_declarada}` : ""}</small></button></li>)}</ul></> : <p className="ayuda">No hay camiones esperando en esta bodega. Podés cargar el ingreso a mano.</p>}
      </div>
      <form className="form-grid produccion-form" onSubmit={abrirRomaneo}>
        <label className="campo-ancho campo-buscable">Productor (nombre, CUIT o código)<input value={busqueda} onChange={e => { setBusqueda(e.target.value); setProductor(null); poner("productor_cuit", ""); }} placeholder="Escribí al menos 2 letras" autoComplete="off" />
          {resultados.length > 0 && <div className="resultados-busqueda">{resultados.map(p => <button type="button" key={p.cuit} onClick={() => elegirProductor(p)}><strong>{p.razon_social}</strong><span>CUIT {cuitLegible(p.cuit)}{p.codigos.length ? ` · ${p.codigos.join(", ")}` : ""}{p.ultima_entrega ? ` · última entrega ${new Date(`${p.ultima_entrega}T12:00:00`).toLocaleDateString("es-AR")}` : ""}</span></button>)}</div>}
          {productor && <small>Elegido: {productor.razon_social} · CUIT {cuitLegible(productor.cuit)}</small>}</label>
        <label>CUIT del productor<input name="productor_cuit" inputMode="numeric" required value={campos.productor_cuit} onChange={e => poner("productor_cuit", e.target.value)} /></label>
        <label>CUIT del transportista<input name="transportista_cuit" inputMode="numeric" required value={campos.transportista_cuit} onChange={e => poner("transportista_cuit", e.target.value)} /></label>
        <label>DNI del chofer<input name="chofer_dni" inputMode="numeric" required value={campos.chofer_dni} onChange={e => poner("chofer_dni", e.target.value)} /></label>
        <label>Patente del camión<input name="patente_chasis" autoCapitalize="characters" required value={campos.patente_chasis} onChange={e => poner("patente_chasis", e.target.value.toUpperCase())} /></label>
        <label>Patente del acoplado<input name="patente_acoplado" autoCapitalize="characters" value={campos.patente_acoplado} onChange={e => poner("patente_acoplado", e.target.value.toUpperCase())} /></label>
        <label>Variedad<input name="variedad" list="variedades-recepcion" required value={campos.variedad} onChange={e => poner("variedad", e.target.value)} placeholder="Elegí o escribí la variedad" /></label><datalist id="variedades-recepcion">{variedades.map(v => <option key={v} value={v} />)}</datalist>
        <label>Finca<input name="finca" value={campos.finca} onChange={e => poner("finca", e.target.value)} /></label>
        <label>Peso bruto (kg)<input name="bruto_kg" type="number" min="1" step="0.01" required /></label>
        <label>Origen del peso<select name="origen_peso"><option value="BASCULA_DIGITAL">Báscula digital</option><option value="CARGA_MANUAL">Carga manual</option></select></label>
        <label>Legajo del operador<input name="operador_legajo" required /></label>
        <button className="primario" disabled={guardando}>{guardando ? "Registrando…" : "Abrir romaneo"}</button>
      </form>
    </section>}

    {area === "fila" && <section className="tarjeta produccion-acceso">
      <div><h2>Fila de camiones</h2><p>Operá llamados, confirmaciones, ingresos directos y búsqueda de productores desde la consola del portón.</p></div>
      <div className="acciones-produccion">
        <a className="boton primario" href={`${FILA_URL}/guardia/chimbas`} target="_blank" rel="noreferrer">Abrir consola de guardia</a>
        <a className="boton" href={`${FILA_URL}/pantalla/chimbas`} target="_blank" rel="noreferrer">Abrir pantalla de espera</a>
      </div>
      <p className="ayuda">La consola se abre en el servicio DMZ y mantiene sus propias credenciales. Gestión nunca recibe el token del guardia.</p>
    </section>}

    {area === "bot" && <section className="tarjeta produccion-acceso">
      <div><h2>Bot de productores</h2><p>Probá consultas por cuenta, estadísticas de cosecha, reportes PDF y administración de contactos.</p></div>
      <div className="acciones-produccion">
        {!ocultarMarcasPrueba && <a className="boton primario" href={BOT_URL} target="_blank" rel="noreferrer">Abrir simulador del bot</a>}
        <a className="boton" href="/contactos">Administrar contactos</a>
      </div>
      <p className="ayuda">Los reportes públicos se generan en la DMZ con datos mínimos publicados desde la red interna.</p>
    </section>}
  </div>;
}
