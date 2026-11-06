"use client";

import { FormEvent, PointerEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Empresa, Perfil, perfiles } from "@/lib/acceso";
import { api } from "@/lib/api";

// Pantallas para el celular: una tarea por pantalla, botones grandes y palabras simples.
// Las usa gente que no maneja tecnología, así que cada paso dice qué hacer y qué pasó.

type Yo = { nombre: string; email: string; perfil: Perfil; empresas: Empresa[]; empresa_sesion: Empresa; debe_cambiar_clave: boolean };
type Usuario = { nombre: string; perfil: Perfil; real: boolean };
type Tarea = "equipo" | "epp" | "capacitacion";

const TAREAS: Record<Tarea, { titulo: string; detalle: string; perfiles: Perfil[] }> = {
  equipo: { titulo: "Leer QR de un equipo", detalle: "Bombas, motores y máquinas", perfiles: ["SUPERADMIN", "MANTENIMIENTO"] },
  epp: { titulo: "Entregar ropa y EPP", detalle: "El trabajador firma lo que recibe", perfiles: ["SUPERADMIN", "DEPOSITO"] },
  capacitacion: { titulo: "Firmar asistencia", detalle: "A una capacitación", perfiles: ["SUPERADMIN", "RRHH", "HYS"] },
};

const mensaje = (x: unknown, defecto: string) => x instanceof Error && x.message ? x.message : defecto;

export default function Celular() {
  const [estado, setEstado] = useState<"cargando" | "ingreso" | "clave" | "listo">("cargando");
  const [real, setReal] = useState(true);
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [tarea, setTarea] = useState<Tarea | null>(null);

  function aplicar(yo: Yo) { setUsuario({ nombre: yo.nombre, perfil: yo.perfil, real: true }); setEstado(yo.debe_cambiar_clave ? "clave" : "listo"); }
  useEffect(() => {
    api<{ identidad_real: boolean }>("ingreso/estado").then(async ({ identidad_real }) => {
      if (!identidad_real) { setReal(false); sessionStorage.removeItem("gestion-modo"); const g = sessionStorage.getItem("gestion-sesion"); if (g) { setUsuario({ nombre: "", perfil: JSON.parse(g).perfil, real: false }); setEstado("listo"); } else setEstado("ingreso"); return; }
      sessionStorage.setItem("gestion-modo", "real");
      try { aplicar(await api<Yo>("ingreso/yo")); } catch { setEstado("ingreso"); }
    }).catch(() => setEstado("ingreso"));
  }, []);
  async function salir() {
    if (usuario?.real) await api("ingreso/salir", { method: "POST" }).catch(() => null);
    sessionStorage.removeItem("gestion-sesion"); setUsuario(null); setTarea(null); setEstado("ingreso");
  }

  if (estado === "cargando") return <main className="cel" aria-busy="true"><p className="cel-cargando">Cargando…</p></main>;
  if (estado === "ingreso") return real ? <Ingreso entrar={aplicar} /> : <IngresoPrueba entrar={p => { sessionStorage.setItem("gestion-sesion", JSON.stringify({ perfil: p, empresa: "ENAV" })); setUsuario({ nombre: "", perfil: p, real: false }); setEstado("listo"); }} />;
  if (estado === "clave") return <ClaveNueva listo={aplicar} />;
  if (!usuario) return null;
  const mias = (Object.keys(TAREAS) as Tarea[]).filter(t => TAREAS[t].perfiles.includes(usuario.perfil));
  const volver = () => setTarea(null);
  if (tarea === "equipo") return <LeerEquipo volver={volver} />;
  if (tarea === "epp") return <EntregarEpp volver={volver} />;
  if (tarea === "capacitacion") return <FirmarCapacitacion volver={volver} />;
  return <main className="cel">
    <header className="cel-barra"><span className="cel-marca">Suite Juviar</span><button className="cel-salir" onClick={() => void salir()}>Salir</button></header>
    <h1 className="cel-titulo">Hola{usuario.nombre ? `, ${usuario.nombre.split(" ")[0]}` : ""}</h1>
    {mias.length ? <><p className="cel-texto">¿Qué vas a hacer?</p>
      <div className="cel-tareas">{mias.map(t => <button key={t} className="cel-tarea" onClick={() => setTarea(t)}><Icono tarea={t} /><span><strong>{TAREAS[t].titulo}</strong><small>{TAREAS[t].detalle}</small></span></button>)}</div></>
      : <p className="cel-aviso">Tu usuario no tiene tareas para el celular. Si creés que es un error, avisale a Sistemas.</p>}
  </main>;
}

function Icono({ tarea }: { tarea: Tarea }) {
  const trazos: Record<Tarea, string> = {
    equipo: "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h2v2h-2z M18 14h2 M14 18h2v2 M18 18h2v2h-2",
    epp: "M7 21v-6a5 5 0 0110 0v6 M9 9V6a3 3 0 016 0v3 M6 10h12v4H6z",
    capacitacion: "M3 6l9-3 9 3-9 3z M7 8v5c3 2 7 2 10 0V8 M4 20c4-3 6 1 9-1s4-4 7-2",
  };
  return <svg className="cel-icono" viewBox="0 0 24 24" aria-hidden="true"><path d={trazos[tarea]} /></svg>;
}

/* ---------- Ingreso ---------- */

function Ingreso({ entrar }: { entrar: (yo: Yo) => void }) {
  const [error, setError] = useState(""); const [enviando, setEnviando] = useState(false); const [ver, setVer] = useState(false);
  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setEnviando(true);
    const f = new FormData(e.currentTarget);
    try { entrar(await api<Yo>("ingreso", { method: "POST", body: JSON.stringify({ email: String(f.get("email")).trim(), clave: f.get("clave") }) })); }
    catch (x) { setError(mensaje(x, "No pudimos entrar. Revisá la conexión.")); }
    finally { setEnviando(false); }
  }
  return <main className="cel cel-ingreso">
    <span className="cel-logo">SJ</span>
    <h1 className="cel-titulo">Suite Juviar</h1>
    <p className="cel-texto">Entrá con el correo y la contraseña que te dio Sistemas.</p>
    <form className="cel-form" onSubmit={enviar}>
      {error && <p className="cel-error" role="alert">{error}</p>}
      <label>Correo<input name="email" type="email" inputMode="email" autoComplete="username" autoCapitalize="none" required /></label>
      <label>Contraseña<span className="cel-clave"><input name="clave" type={ver ? "text" : "password"} autoComplete="current-password" required /><button type="button" onClick={() => setVer(v => !v)}>{ver ? "Ocultar" : "Ver"}</button></span></label>
      <button className="cel-boton" disabled={enviando}>{enviando ? "Entrando…" : "Entrar"}</button>
    </form>
    <p className="cel-pie">¿Te olvidaste la contraseña? Pedile una nueva a Sistemas.</p>
  </main>;
}

function IngresoPrueba({ entrar }: { entrar: (perfil: Perfil) => void }) {
  const opciones: Perfil[] = ["SUPERADMIN", "MANTENIMIENTO", "DEPOSITO", "RRHH", "HYS"];
  return <main className="cel cel-ingreso"><span className="cel-logo">SJ</span><h1 className="cel-titulo">Modo de prueba</h1><p className="cel-texto">Elegí con qué perfil entrar.</p>
    <div className="cel-lista">{opciones.map(p => <button key={p} className="cel-opcion" onClick={() => entrar(p)}><strong>{perfiles[p].nombre}</strong></button>)}</div></main>;
}

function ClaveNueva({ listo }: { listo: (yo: Yo) => void }) {
  const [error, setError] = useState("");
  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError("");
    const f = new FormData(e.currentTarget);
    if (f.get("nueva") !== f.get("repetir")) { setError("Las dos contraseñas nuevas no son iguales. Escribilas de nuevo."); return; }
    try { listo(await api<Yo>("ingreso/clave", { method: "POST", body: JSON.stringify({ actual: f.get("actual"), nueva: f.get("nueva") }) })); }
    catch (x) { setError(mensaje(x, "No pudimos cambiar la contraseña.")); }
  }
  return <main className="cel cel-ingreso"><h1 className="cel-titulo">Elegí tu contraseña</h1>
    <p className="cel-texto">Es la primera vez que entrás. Cambiá la contraseña que te dieron por una que sólo sepas vos. Tiene que tener al menos 10 letras o números.</p>
    <form className="cel-form" onSubmit={enviar}>
      {error && <p className="cel-error" role="alert">{error}</p>}
      <label>La contraseña que te dieron<input name="actual" type="password" autoComplete="current-password" required /></label>
      <label>Tu contraseña nueva<input name="nueva" type="password" minLength={10} autoComplete="new-password" required /></label>
      <label>Repetí la contraseña nueva<input name="repetir" type="password" minLength={10} autoComplete="new-password" required /></label>
      <button className="cel-boton">Guardar y entrar</button>
    </form></main>;
}

/* ---------- Piezas comunes ---------- */

function Pantalla({ titulo, paso, volver, children }: { titulo: string; paso?: string; volver: () => void; children: ReactNode }) {
  useEffect(() => { window.scrollTo(0, 0); }, [titulo, paso]);
  return <main className="cel">
    <header className="cel-barra"><button className="cel-volver" onClick={volver}>‹ Volver</button>{paso && <span className="cel-paso">{paso}</span>}</header>
    <h1 className="cel-titulo">{titulo}</h1>
    {children}
  </main>;
}

function Listo({ titulo, detalle, otra, textoOtra, inicio }: { titulo: string; detalle?: string; otra: () => void; textoOtra: string; inicio: () => void }) {
  return <main className="cel cel-listo">
    <div className="cel-tilde" aria-hidden="true">✓</div>
    <h1 className="cel-titulo">{titulo}</h1>
    {detalle && <p className="cel-texto">{detalle}</p>}
    <button className="cel-boton" onClick={otra}>{textoOtra}</button>
    <button className="cel-boton cel-secundario" onClick={inicio}>Volver al inicio</button>
  </main>;
}

function Firma({ quien, confirmar, enviando }: { quien: string; confirmar: (firma: string) => void; enviando: boolean }) {
  const lienzo = useRef<HTMLCanvasElement>(null); const dibujando = useRef(false); const [hay, setHay] = useState(false);
  useEffect(() => {
    const canvas = lienzo.current; if (!canvas) return;
    const escala = window.devicePixelRatio || 1; const caja = canvas.getBoundingClientRect();
    canvas.width = Math.round(caja.width * escala); canvas.height = Math.round(caja.height * escala);
    const ctx = canvas.getContext("2d"); if (!ctx) return;
    ctx.scale(escala, escala); ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#141a1f";
  }, []);
  function punto(e: PointerEvent<HTMLCanvasElement>) { const c = e.currentTarget.getBoundingClientRect(); return { x: e.clientX - c.left, y: e.clientY - c.top }; }
  function iniciar(e: PointerEvent<HTMLCanvasElement>) { const ctx = e.currentTarget.getContext("2d"); if (!ctx) return; e.currentTarget.setPointerCapture(e.pointerId); const p = punto(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); dibujando.current = true; }
  function mover(e: PointerEvent<HTMLCanvasElement>) { if (!dibujando.current) return; const ctx = e.currentTarget.getContext("2d"); if (!ctx) return; const p = punto(e); ctx.lineTo(p.x, p.y); ctx.stroke(); setHay(true); }
  function borrar() { const c = lienzo.current; c?.getContext("2d")?.clearRect(0, 0, c.width, c.height); setHay(false); }
  return <>
    <p className="cel-texto">Pasale el celular a <strong>{quien}</strong> para que firme con el dedo en el recuadro.</p>
    <div className="cel-firma"><canvas ref={lienzo} aria-label={`Firma de ${quien}`} onPointerDown={iniciar} onPointerMove={mover} onPointerUp={() => { dibujando.current = false; }} onPointerCancel={() => { dibujando.current = false; }} />{!hay && <span className="cel-firma-guia">Firmá acá</span>}</div>
    <button className="cel-boton cel-secundario" onClick={borrar} disabled={!hay}>Borrar y firmar de nuevo</button>
    <button className="cel-boton" disabled={!hay || enviando} onClick={() => lienzo.current && confirmar(lienzo.current.toDataURL("image/png"))}>{enviando ? "Guardando…" : "Confirmar firma"}</button>
  </>;
}

function Buscador({ etiqueta, ayuda, valor, cambiar }: { etiqueta: string; ayuda: string; valor: string; cambiar: (v: string) => void }) {
  return <label className="cel-buscador">{etiqueta}<input value={valor} onChange={e => cambiar(e.target.value)} placeholder={ayuda} autoComplete="off" enterKeyHint="search" /></label>;
}

/* ---------- Leer QR de un equipo ---------- */

type Equipo = { codigo: string; tipo: string; descripcion: string; sector: string; bodega_nombre: string; marca: string; modelo: string; numero_serie: string; estado: "EN_PLANTA" | "EN_TALLER" | "DE_BAJA"; reparaciones: number;
  detalle_reparaciones: Array<{ id: string; taller: string; motivo: string; salida_en: string; regreso_en: string | null; trabajo_realizado: string }>;
  historial: Array<{ tipo: string; fecha: string; desde_sector: string; hacia_sector: string; detalle: string }> };
const ESTADO_EQUIPO = { EN_PLANTA: "En planta", EN_TALLER: "En el taller", DE_BAJA: "Dado de baja" };
const MOVIMIENTO: Record<string, string> = { ALTA: "Alta", TRASLADO: "Traslado", SALIDA_TALLER: "Salió al taller", REGRESO_TALLER: "Volvió del taller", BAJA: "Baja" };
const dia = (v: string) => new Date(v).toLocaleDateString("es-AR", { day: "numeric", month: "short", year: "numeric" });

function Camara({ leido }: { leido: (codigo: string) => void }) {
  const video = useRef<HTMLVideoElement>(null); const alLeer = useRef(leido); const [error, setError] = useState("");
  useEffect(() => { alLeer.current = leido; }, [leido]);
  useEffect(() => {
    let controles: { stop: () => void } | undefined; let vigente = true;
    if (!navigator.mediaDevices?.getUserMedia) { setError("Este celular no deja usar la cámara desde acá."); return; }
    (async () => {
      try {
        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        if (!vigente || !video.current) return;
        controles = await new BrowserMultiFormatReader().decodeFromConstraints({ video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } } }, video.current,
          (r, _e, c) => { if (r && vigente) { vigente = false; c.stop(); navigator.vibrate?.(80); alLeer.current(r.getText().trim()); } });
        if (!vigente) controles.stop();
      } catch (x) {
        const n = x instanceof Error ? x.name : "";
        if (vigente) setError(n === "NotAllowedError" ? "Falta el permiso de la cámara. Andá a Ajustes del celular, entrá a la app y permití la cámara." : "No se pudo abrir la cámara. Cerrá otras apps que la estén usando y probá de nuevo.");
      }
    })();
    return () => { vigente = false; controles?.stop(); };
  }, []);
  if (error) return <p className="cel-error" role="alert">{error}</p>;
  return <div className="cel-camara"><video ref={video} muted playsInline /><span className="cel-mira" aria-hidden="true" /></div>;
}

function LeerEquipo({ volver }: { volver: () => void }) {
  const [equipo, setEquipo] = useState<Equipo | null>(null); const [error, setError] = useState(""); const [buscando, setBuscando] = useState(false);
  const [manual, setManual] = useState(false); const [intento, setIntento] = useState(0);
  const abrir = useCallback(async (codigo: string) => {
    setError(""); setBuscando(true);
    try { setEquipo(await api<Equipo>(`activos/equipos/${encodeURIComponent(codigo.toUpperCase())}`)); }
    catch (x) { setError(mensaje(x, "No encontramos ese equipo.")); setIntento(n => n + 1); }
    finally { setBuscando(false); }
  }, []);
  if (equipo) return <Pantalla titulo={equipo.descripcion} volver={() => { setEquipo(null); setIntento(n => n + 1); }}>
    <div className="cel-ficha">
      <p className="cel-codigo">{equipo.codigo}</p>
      <p className={`cel-estado cel-estado-${equipo.estado.toLowerCase()}`}>{ESTADO_EQUIPO[equipo.estado]}</p>
      <dl>
        <div><dt>Dónde está</dt><dd>{equipo.estado === "EN_TALLER" ? "En el taller externo" : `${equipo.sector} · ${equipo.bodega_nombre}`}</dd></div>
        <div><dt>Tipo</dt><dd>{equipo.tipo}</dd></div>
        {(equipo.marca || equipo.modelo) && <div><dt>Marca y modelo</dt><dd>{[equipo.marca, equipo.modelo].filter(Boolean).join(" ")}</dd></div>}
        {equipo.numero_serie && <div><dt>Número de serie</dt><dd>{equipo.numero_serie}</dd></div>}
      </dl>
    </div>
    <h2 className="cel-subtitulo">Reparaciones ({equipo.detalle_reparaciones.length})</h2>
    {equipo.detalle_reparaciones.length ? <ul className="cel-historia">{equipo.detalle_reparaciones.map(r => <li key={r.id}><strong>{r.motivo}</strong><span>{r.taller} · salió {dia(r.salida_en)}{r.regreso_en ? ` · volvió ${dia(r.regreso_en)}` : " · todavía en el taller"}</span>{r.trabajo_realizado && <span>{r.trabajo_realizado}</span>}</li>)}</ul> : <p className="cel-texto">Nunca se mandó a reparar.</p>}
    <h2 className="cel-subtitulo">Movimientos</h2>
    <ul className="cel-historia">{equipo.historial.slice(0, 8).map((m, i) => <li key={i}><strong>{MOVIMIENTO[m.tipo] ?? m.tipo}</strong><span>{dia(m.fecha)}{m.tipo === "TRASLADO" ? ` · ${m.desde_sector} → ${m.hacia_sector}` : ""}</span></li>)}</ul>
    <button className="cel-boton" onClick={() => { setEquipo(null); setIntento(n => n + 1); }}>Leer otro equipo</button>
  </Pantalla>;
  return <Pantalla titulo="Leer QR de un equipo" volver={volver}>
    <p className="cel-texto">Apuntá la cámara a la etiqueta del equipo. Se abre sola cuando la lee.</p>
    {error && <p className="cel-error" role="alert">{error}</p>}
    {buscando ? <p className="cel-cargando">Buscando el equipo…</p> : <Camara key={intento} leido={c => void abrir(c)} />}
    {manual ? <form className="cel-form" onSubmit={e => { e.preventDefault(); void abrir(String(new FormData(e.currentTarget).get("codigo") || "")); }}>
      <label>Código de la etiqueta<input name="codigo" autoCapitalize="characters" placeholder="Por ejemplo BOM-0001" required /></label>
      <button className="cel-boton">Buscar</button></form>
      : <button className="cel-boton cel-secundario" onClick={() => setManual(true)}>La etiqueta no se lee: escribir el código</button>}
  </Pantalla>;
}

/* ---------- Entregar ropa y EPP ---------- */

type Persona = { legajo: string; nombre_completo: string; puesto: string; sector: string };
type ItemStock = { codigo_interno: string; marca: string; modelo: string; talle: string; color: string };
type Elemento = { codigo: string; producto: string; cantidad_sugerida: number; obligatorio: boolean; ultima_entrega: string | null; items: ItemStock[] };
type FichaEpp = { cabecera: Persona; epp_requerido: Elemento[] };
const MOTIVOS_EPP = [
  { id: "temporada", titulo: "Entrega de temporada", detalle: "La que le corresponde por su puesto", circuito: "PROGRAMADA", motivo: "ENTREGA_ESTACIONAL" },
  { id: "rotura", titulo: "Se le rompió", detalle: "Reemplazo por rotura", circuito: "ESPONTANEA", motivo: "ROTURA" },
  { id: "desgaste", titulo: "Se le gastó", detalle: "Reemplazo por desgaste", circuito: "ESPONTANEA", motivo: "DESGASTE" },
] as const;
const descripcionItem = (i: ItemStock) => [i.talle && `Talle ${i.talle}`, i.color, i.marca, i.modelo].filter(Boolean).join(" · ") || i.codigo_interno;

function BuscarPersona({ ruta, elegir }: { ruta: (q: string) => string; elegir: (p: Persona) => void }) {
  const [q, setQ] = useState(""); const [personas, setPersonas] = useState<Persona[] | null>(null); const [error, setError] = useState("");
  useEffect(() => {
    const texto = q.trim(); if (texto.length < 2) { setPersonas(null); return; }
    const t = setTimeout(() => api<Persona[]>(ruta(texto)).then(p => { setPersonas(p); setError(""); }).catch(x => setError(mensaje(x, "No pudimos buscar."))), 300);
    return () => clearTimeout(t);
  }, [q, ruta]);
  return <>
    <Buscador etiqueta="Nombre, apellido o legajo" ayuda="Escribí al menos 2 letras" valor={q} cambiar={setQ} />
    {error && <p className="cel-error" role="alert">{error}</p>}
    {personas && (personas.length ? <div className="cel-lista">{personas.slice(0, 15).map(p => <button key={p.legajo} className="cel-opcion" onClick={() => elegir(p)}><strong>{p.nombre_completo}</strong><small>Legajo {p.legajo}{p.puesto ? ` · ${p.puesto}` : ""}</small></button>)}</div>
      : <p className="cel-texto">No encontramos a nadie con «{q.trim()}». Probá con el apellido o el número de legajo.</p>)}
  </>;
}

function EntregarEpp({ volver }: { volver: () => void }) {
  const [persona, setPersona] = useState<Persona | null>(null); const [ficha, setFicha] = useState<FichaEpp | null>(null);
  const [motivo, setMotivo] = useState<(typeof MOTIVOS_EPP)[number] | null>(null);
  const [elegidos, setElegidos] = useState<Record<string, { item: string; cantidad: number }>>({});
  const [firmando, setFirmando] = useState(false); const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(""); const [hecho, setHecho] = useState<number | null>(null);
  const reiniciar = () => { setPersona(null); setFicha(null); setMotivo(null); setElegidos({}); setFirmando(false); setHecho(null); setError(""); };
  const rutaPersonas = useCallback((q: string) => `rrhh-epp/legajos?q=${encodeURIComponent(q)}`, []);
  async function elegirPersona(p: Persona) {
    setPersona(p); setError("");
    try { setFicha(await api<FichaEpp>(`rrhh-epp/legajos/${encodeURIComponent(p.legajo)}`)); }
    catch (x) { setError(mensaje(x, "No pudimos leer qué le corresponde.")); }
  }
  function alternar(e: Elemento) {
    setElegidos(actual => {
      const nuevo = { ...actual };
      if (nuevo[e.codigo]) delete nuevo[e.codigo];
      else nuevo[e.codigo] = { item: e.items.length === 1 ? e.items[0].codigo_interno : "", cantidad: Math.max(1, e.cantidad_sugerida) };
      return nuevo;
    });
  }
  async function registrar(firma: string) {
    if (!ficha || !motivo) return;
    setEnviando(true); setError("");
    try {
      const r = await api<{ items: number }>("rrhh-epp/entregas", { method: "POST", body: JSON.stringify({
        id_cliente: `celular-${crypto.randomUUID()}`, legajo: ficha.cabecera.legajo, metodo_firma: "TRAZO_TABLET", evidencia_firma: firma,
        entregada_en: new Date().toISOString(), circuito: motivo.circuito, motivo: motivo.motivo,
        items: Object.entries(elegidos).map(([codigo, v]) => ({ codigo, item_codigo: v.item, cantidad: v.cantidad })),
      }) });
      setHecho(r.items);
    } catch (x) { setError(mensaje(x, "No se pudo guardar la entrega. Revisá la conexión y probá de nuevo.")); }
    finally { setEnviando(false); }
  }

  if (hecho !== null && persona) return <Listo titulo="Entrega guardada" detalle={`${persona.nombre_completo} firmó que recibió ${hecho} ${hecho === 1 ? "elemento" : "elementos"}.`} otra={reiniciar} textoOtra="Entregar a otra persona" inicio={volver} />;
  if (!persona) return <Pantalla titulo="¿A quién le entregás?" paso="Paso 1 de 4" volver={volver}><BuscarPersona ruta={rutaPersonas} elegir={p => void elegirPersona(p)} /></Pantalla>;
  const atras = () => { if (firmando) setFirmando(false); else if (motivo) setMotivo(null); else reiniciar(); };
  if (!ficha) return <Pantalla titulo={persona.nombre_completo} volver={atras}>{error ? <p className="cel-error" role="alert">{error}</p> : <p className="cel-cargando">Buscando lo que le corresponde…</p>}</Pantalla>;
  if (!motivo) return <Pantalla titulo="¿Por qué se entrega?" paso="Paso 2 de 4" volver={atras}>
    <p className="cel-texto">Entrega para <strong>{persona.nombre_completo}</strong>.</p>
    <div className="cel-lista">{MOTIVOS_EPP.map(m => <button key={m.id} className="cel-opcion" onClick={() => setMotivo(m)}><strong>{m.titulo}</strong><small>{m.detalle}</small></button>)}</div>
  </Pantalla>;
  const lista = Object.entries(elegidos); const faltaTalle = lista.some(([, v]) => !v.item);
  if (firmando) return <Pantalla titulo="Firma del trabajador" paso="Paso 4 de 4" volver={atras}>
    <ul className="cel-resumen">{lista.map(([codigo, v]) => { const e = ficha.epp_requerido.find(x => x.codigo === codigo); const i = e?.items.find(x => x.codigo_interno === v.item); return <li key={codigo}><strong>{v.cantidad} × {e?.producto}</strong>{i && <span>{descripcionItem(i)}</span>}</li>; })}</ul>
    {error && <p className="cel-error" role="alert">{error}</p>}
    <Firma quien={persona.nombre_completo} enviando={enviando} confirmar={f => void registrar(f)} />
  </Pantalla>;
  return <Pantalla titulo="¿Qué le entregás?" paso="Paso 3 de 4" volver={atras}>
    <p className="cel-texto">Tocá cada cosa que le das a <strong>{persona.nombre_completo}</strong>.</p>
    {ficha.epp_requerido.length ? <div className="cel-lista">{ficha.epp_requerido.map(e => { const sel = elegidos[e.codigo]; const sinStock = !e.items.length; return <div key={e.codigo} className={`cel-elemento${sel ? " elegido" : ""}`}>
      <button className="cel-opcion" disabled={sinStock} aria-pressed={Boolean(sel)} onClick={() => alternar(e)}><span className="cel-check" aria-hidden="true">{sel ? "✓" : ""}</span><span><strong>{e.producto}</strong><small>{sinStock ? "No hay en el depósito" : e.ultima_entrega ? `Última entrega: ${dia(e.ultima_entrega)}` : "Nunca se le entregó"}</small></span></button>
      {sel && <div className="cel-detalle-elemento">
        {e.items.length > 1 && <label>Talle o modelo<select value={sel.item} onChange={ev => setElegidos(a => ({ ...a, [e.codigo]: { ...sel, item: ev.target.value } }))}><option value="">Elegí uno</option>{e.items.map(i => <option key={i.codigo_interno} value={i.codigo_interno}>{descripcionItem(i)}</option>)}</select></label>}
        <div className="cel-cantidad"><span>Cantidad</span><button aria-label="Uno menos" disabled={sel.cantidad <= 1} onClick={() => setElegidos(a => ({ ...a, [e.codigo]: { ...sel, cantidad: sel.cantidad - 1 } }))}>−</button><strong>{sel.cantidad}</strong><button aria-label="Uno más" disabled={sel.cantidad >= 20} onClick={() => setElegidos(a => ({ ...a, [e.codigo]: { ...sel, cantidad: sel.cantidad + 1 } }))}>+</button></div>
      </div>}
    </div>; })}</div> : <p className="cel-aviso">Su puesto no tiene elementos asignados. Avisale a Higiene y Seguridad.</p>}
    <button className="cel-boton cel-fijo" disabled={!lista.length || faltaTalle} onClick={() => setFirmando(true)}>{!lista.length ? "Elegí al menos una cosa" : faltaTalle ? "Falta elegir el talle" : `Seguir a la firma (${lista.length})`}</button>
  </Pantalla>;
}

/* ---------- Firmar asistencia a una capacitación ---------- */

type Dictado = { id: string; fecha: string; instructor: string; tema: string };
type Convocado = { legajo: string; nombre_completo: string };
type Asistencia = { participante: { legajo: string }; presente: boolean; anulada: boolean; estado_firma: string };

function FirmarCapacitacion({ volver }: { volver: () => void }) {
  const [dictados, setDictados] = useState<Dictado[] | null>(null); const [dictado, setDictado] = useState<Dictado | null>(null);
  const [personas, setPersonas] = useState<Convocado[]>([]); const [firmaron, setFirmaron] = useState<Set<string>>(new Set());
  const [firmante, setFirmante] = useState<Convocado | null>(null); const [otra, setOtra] = useState(false);
  const [enviando, setEnviando] = useState(false); const [error, setError] = useState(""); const [aviso, setAviso] = useState("");
  useEffect(() => {
    api<Array<{ nombre: string; dictados: Array<Omit<Dictado, "tema">> }>>("capacitaciones/temas").then(temas => {
      const hoy = new Date(); hoy.setHours(0, 0, 0, 0); const desde = new Date(hoy); desde.setDate(desde.getDate() - 7);
      const todos = temas.flatMap(t => t.dictados.map(d => ({ ...d, tema: t.nombre })));
      setDictados(todos.filter(d => new Date(`${d.fecha}T12:00:00`) >= desde).sort((a, b) => a.fecha.localeCompare(b.fecha)));
    }).catch(x => setError(mensaje(x, "No pudimos leer las capacitaciones.")));
  }, []);
  async function cargar(d: Dictado) {
    const [c, a] = await Promise.all([api<Convocado[]>(`capacitaciones/dictados/${d.id}/convocados`), api<Asistencia[]>(`capacitaciones/dictados/${d.id}/asistencias`)]);
    setPersonas(c); setFirmaron(new Set(a.filter(x => !x.anulada && x.presente && x.estado_firma !== "PENDIENTE_FIRMA_PAPEL").map(x => x.participante.legajo)));
  }
  async function abrir(d: Dictado) { setDictado(d); setError(""); try { await cargar(d); } catch (x) { setError(mensaje(x, "No pudimos leer la lista de la capacitación.")); } }
  async function firmar(firma: string) {
    if (!dictado || !firmante) return;
    setEnviando(true); setError("");
    try {
      await api(`capacitaciones/dictados/${dictado.id}/asistencias`, { method: "POST", body: JSON.stringify({ legajo: firmante.legajo, nombre_completo: firmante.nombre_completo, presente: true, metodo_firma: "TRAZO_TABLET", evidencia_firma: firma }) });
      setAviso(`${firmante.nombre_completo} ya firmó.`); setFirmante(null); setOtra(false); await cargar(dictado);
    } catch (x) { setError(mensaje(x, "No se pudo guardar la firma. Probá de nuevo.")); }
    finally { setEnviando(false); }
  }

  if (!dictado) return <Pantalla titulo="¿Qué capacitación es?" paso="Paso 1 de 3" volver={volver}>
    {error && <p className="cel-error" role="alert">{error}</p>}
    {!dictados ? !error && <p className="cel-cargando">Buscando capacitaciones…</p>
      : dictados.length ? <div className="cel-lista">{dictados.map(d => <button key={d.id} className="cel-opcion" onClick={() => void abrir(d)}><strong>{d.tema}</strong><small>{dia(`${d.fecha}T12:00:00`)} · {d.instructor}</small></button>)}</div>
      : <p className="cel-aviso">No hay capacitaciones de esta semana ni próximas. Primero hay que cargarlas en Gestión desde la computadora.</p>}
  </Pantalla>;
  if (firmante) return <Pantalla titulo="Firma de asistencia" paso="Paso 3 de 3" volver={() => setFirmante(null)}>
    <p className="cel-texto">{dictado.tema} · {dia(`${dictado.fecha}T12:00:00`)}</p>
    {error && <p className="cel-error" role="alert">{error}</p>}
    <Firma quien={firmante.nombre_completo} enviando={enviando} confirmar={f => void firmar(f)} />
  </Pantalla>;
  const pendientes = personas.filter(p => !firmaron.has(p.legajo));
  return <Pantalla titulo={dictado.tema} paso="Paso 2 de 3" volver={() => { setDictado(null); setAviso(""); setOtra(false); }}>
    <p className="cel-texto">Tocá el nombre de quien va a firmar. {personas.length ? `Firmaron ${personas.length - pendientes.length} de ${personas.length}.` : ""}</p>
    {aviso && <p className="cel-exito" role="status">✓ {aviso}</p>}
    {error && <p className="cel-error" role="alert">{error}</p>}
    {personas.length ? <div className="cel-lista">{personas.map(p => { const ya = firmaron.has(p.legajo); return <button key={p.legajo} className={`cel-opcion${ya ? " firmo" : ""}`} disabled={ya} onClick={() => { setAviso(""); setFirmante(p); }}><span className="cel-check" aria-hidden="true">{ya ? "✓" : ""}</span><span><strong>{p.nombre_completo || `Legajo ${p.legajo}`}</strong><small>{ya ? "Ya firmó" : `Legajo ${p.legajo}`}</small></span></button>; })}</div>
      : <p className="cel-texto">Esta capacitación no tiene una lista de convocados.</p>}
    {otra ? <form className="cel-form" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); setAviso(""); setFirmante({ legajo: String(f.get("legajo")).trim(), nombre_completo: String(f.get("nombre")).trim() }); }}>
      <h2 className="cel-subtitulo">Otra persona</h2>
      <label>Legajo<input name="legajo" inputMode="numeric" required /></label>
      <label>Apellido y nombre<input name="nombre" autoCapitalize="words" required /></label>
      <button className="cel-boton">Ir a la firma</button></form>
      : <button className="cel-boton cel-secundario" onClick={() => setOtra(true)}>Firma alguien que no está en la lista</button>}
  </Pantalla>;
}
