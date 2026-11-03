"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Confirmacion, ErrorVisible, FormularioVentana as Formulario, Tabla, Vacio, Ventana } from "./compartidos";

type Tipo = { id: string; nombre: string; prefijo: string };
type Sector = { id: string; nombre: string; bodega: string; bodega_nombre: string };
type Equipo = Record<string, unknown> & {
  codigo: string; tipo_id: string; tipo: string; descripcion: string; sector_id: string; sector: string;
  bodega: string; bodega_nombre: string;
  marca: string; modelo: string; numero_serie: string; estado: "EN_PLANTA" | "EN_TALLER" | "DE_BAJA";
  reparaciones: number; costo_reparaciones: number; costo_por_empresa: Record<string, number>; alta_en: string; alta_por: string;
  baja_motivo: string; baja_en: string | null; baja_por: string;
};
type Movimiento = { tipo: string; fecha: string; actor: string; desde_sector: string; hacia_sector: string; detalle: string };
type Reparacion = { id: string; taller: string; motivo: string; salida_en: string; regreso_en: string | null; costo: number | null; trabajo_realizado: string; empresa: string | null };
type Ficha = Equipo & { historial: Movimiento[]; detalle_reparaciones: Reparacion[] };

const ESTADOS = { EN_PLANTA: "En planta", EN_TALLER: "En taller externo", DE_BAJA: "De baja" };
const MOVIMIENTOS: Record<string, string> = { ALTA: "Alta", TRASLADO: "Traslado", SALIDA_TALLER: "Salida a taller", REGRESO_TALLER: "Regreso de taller", BAJA: "Baja" };
const BODEGAS: Record<string, string> = { chimbas: "Chimbas", "media-agua": "Media Agua", lavalle: "Lavalle" };
const EMPRESAS: Record<string, string> = { ENAV: "ENAV", JUBIAR: "Juviar" };
const ubicacion = (e: Equipo) => e.estado === "EN_TALLER" ? "En taller externo" : `${e.sector} · ${e.bodega_nombre}`;
const fecha = (v: string | null) => v ? new Date(v).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : "—";
const pesos = (v: number) => v.toLocaleString("es-AR", { style: "currency", currency: "ARS" });
const mensaje = (x: unknown, defecto: string) => x instanceof Error ? x.message : defecto;

function lugar(m: Movimiento) {
  if (m.tipo === "TRASLADO") return `${m.desde_sector} → ${m.hacia_sector}`;
  if (m.tipo === "SALIDA_TALLER") return `Sale de ${m.desde_sector}`;
  if (m.tipo === "BAJA") return `Estaba en ${m.desde_sector}`;
  return `A ${m.hacia_sector}`;
}

function SelectorSector({ sectores, nombre = "sector_id", excluir, etiqueta = "Sector" }: { sectores: Sector[]; nombre?: string; excluir?: string; etiqueta?: string }) {
  return <label>{etiqueta}<select name={nombre} required defaultValue="">
    <option value="" disabled>Elegí un sector</option>
    {Object.entries(BODEGAS).map(([id, bodega]) => {
      const propios = sectores.filter(s => s.bodega === id && s.id !== excluir);
      return propios.length ? <optgroup key={id} label={bodega}>{propios.map(s => <option key={s.id} value={s.id}>{s.nombre}</option>)}</optgroup> : null;
    })}
  </select></label>;
}

function VentanaEquipo({ codigo, sectores, cerrar, cambio }: { codigo: string; sectores: Sector[]; cerrar: () => void; cambio: () => void }) {
  const [ficha, setFicha] = useState<Ficha | null>(null); const [error, setError] = useState(""); const [aviso, setAviso] = useState("");
  const [accion, setAccion] = useState<"traslado" | "taller" | "regreso" | "editar" | "etiqueta" | "baja" | null>(null);
  const [vista, setVista] = useState<"datos" | "reparaciones" | "historial">("datos");
  const ruta = `activos/equipos/${encodeURIComponent(codigo)}`;

  async function cargar() {
    try { setFicha(await api<Ficha>(ruta)); setError(""); } catch (x) { setError(mensaje(x, "No se pudo leer el equipo.")); }
  }
  useEffect(() => { void cargar(); }, [codigo]);

  async function hecho(texto: string) { setAccion(null); setAviso(texto); await cargar(); cambio(); }
  const enviar = (sufijo: string, cuerpo: unknown, metodo = "POST") => api(`${ruta}${sufijo}`, { method: metodo, body: JSON.stringify(cuerpo) });

  return <Ventana titulo={ficha ? `${ficha.codigo} · ${ficha.descripcion}` : codigo} tamano="amplia" cerrar={cerrar}>
    {error && <ErrorVisible mensaje={error} />}
    {aviso && <p className="aviso-exito">{aviso}</p>}
    {!ficha ? !error && <p className="ayuda">Cargando…</p> : <>
      <div className="cabecera-ficha">
        <span className={`estado estado-equipo-${ficha.estado.toLowerCase()}`}>{ESTADOS[ficha.estado]}</span>
        <span className="ayuda">{ficha.tipo} · {ubicacion(ficha)}</span>
      </div>
      <div className="acciones acciones-ficha">
        {ficha.estado !== "DE_BAJA" && <>
          <button onClick={() => { setAviso(""); setAccion("etiqueta"); }}>Imprimir etiqueta</button>
          <button onClick={() => { setAviso(""); setAccion("editar"); }}>Editar datos</button>
        </>}
        {ficha.estado === "EN_PLANTA" && <>
          <button className="peligro" onClick={() => { setAviso(""); setAccion("baja"); }}>Dar de baja</button>
          <button onClick={() => { setAviso(""); setAccion("taller"); }}>Enviar a taller</button>
          <button className="primario" onClick={() => { setAviso(""); setAccion("traslado"); }}>Trasladar</button>
        </>}
        {ficha.estado === "EN_TALLER" && <button className="primario" onClick={() => { setAviso(""); setAccion("regreso"); }}>Registrar regreso</button>}
      </div>
      <div className="pestanas pestanas-chicas">
        {(["datos", "reparaciones", "historial"] as const).map(v => <button key={v} className={vista === v ? "activo" : ""} onClick={() => setVista(v)}>
          {v === "datos" ? "Datos" : v === "reparaciones" ? `Reparaciones (${ficha.detalle_reparaciones.length})` : `Historial (${ficha.historial.length})`}</button>)}
      </div>
      {vista === "datos" && <dl className="ficha">
        <div><dt>Tipo</dt><dd>{ficha.tipo}</dd></div>
        <div><dt>Ubicación</dt><dd>{ubicacion(ficha)}</dd></div>
        <div><dt>Marca y modelo</dt><dd>{[ficha.marca, ficha.modelo].filter(Boolean).join(" ") || "—"}</dd></div>
        <div><dt>Número de serie</dt><dd>{ficha.numero_serie || "—"}</dd></div>
        <div><dt>Reparaciones externas</dt><dd>{ficha.reparaciones} · {pesos(ficha.costo_reparaciones)}</dd></div>
        <div><dt>Gasto imputado</dt><dd>{Object.entries(EMPRESAS).map(([id, n]) => `${n} ${pesos(ficha.costo_por_empresa[id] ?? 0)}`).join(" · ")}</dd></div>
        <div><dt>Alta</dt><dd>{ficha.alta_por} · {fecha(ficha.alta_en)}</dd></div>
        {ficha.estado === "DE_BAJA" && <div><dt>Baja</dt><dd>{ficha.baja_motivo} · {ficha.baja_por} · {fecha(ficha.baja_en)}</dd></div>}
      </dl>}
      {vista === "reparaciones" && (ficha.detalle_reparaciones.length ? <Tabla etiqueta="Reparaciones externas" filas={ficha.detalle_reparaciones as Array<Reparacion & Record<string, unknown>>} columnas={[
        { clave: "taller", titulo: "Taller" },
        { clave: "motivo", titulo: "Motivo" },
        { clave: "salida_en", titulo: "Salió", valor: r => fecha(r.salida_en) },
        { clave: "regreso_en", titulo: "Volvió", valor: r => r.regreso_en ? fecha(r.regreso_en) : "En el taller" },
        { clave: "costo", titulo: "Costo", valor: r => r.costo === null ? "—" : pesos(r.costo) },
        { clave: "empresa", titulo: "Factura a", valor: r => r.empresa ? EMPRESAS[r.empresa] ?? r.empresa : "—" },
        { clave: "trabajo_realizado", titulo: "Trabajo", valor: r => r.trabajo_realizado || "—" },
      ]} /> : <Vacio>Nunca salió a un taller externo.</Vacio>)}
      {vista === "historial" && <Tabla etiqueta="Historial de movimientos" filas={ficha.historial as Array<Movimiento & Record<string, unknown>>} columnas={[
        { clave: "fecha", titulo: "Fecha", valor: m => fecha(m.fecha) },
        { clave: "tipo", titulo: "Movimiento", valor: m => MOVIMIENTOS[m.tipo] ?? m.tipo },
        { clave: "hacia_sector", titulo: "Lugar", valor: lugar },
        { clave: "detalle", titulo: "Nota", valor: m => m.detalle || "—" },
        { clave: "actor", titulo: "Usuario" },
      ]} />}

      {accion === "traslado" && <Formulario titulo="Trasladar equipo" boton="Trasladar" cerrar={() => setAccion(null)} enviar={async f => { await enviar("/traslado", { sector_id: f.get("sector_id"), detalle: f.get("detalle") }); await hecho("Traslado registrado."); }}>
        <p className="ayuda">Está en {ubicacion(ficha)}.</p>
        <SelectorSector sectores={sectores} excluir={ficha.sector_id} etiqueta="Nuevo sector" />
        <label>Nota (opcional)<input name="detalle" maxLength={200} /></label>
      </Formulario>}
      {accion === "taller" && <Formulario titulo="Enviar a taller externo" boton="Registrar salida" cerrar={() => setAccion(null)} enviar={async f => { await enviar("/taller", { taller: f.get("taller"), motivo: f.get("motivo") }); await hecho("Salida a taller registrada."); }}>
        <label>Taller<input name="taller" required maxLength={120} autoFocus /></label>
        <label>Motivo<input name="motivo" required maxLength={300} /></label>
      </Formulario>}
      {accion === "regreso" && <Formulario titulo="Regreso del taller" boton="Registrar regreso" cerrar={() => setAccion(null)} enviar={async f => { await enviar("/regreso", { costo: Number(f.get("costo")), empresa: f.get("empresa"), trabajo_realizado: f.get("trabajo"), sector_id: f.get("sector_id") }); await hecho("Regreso registrado."); }}>
        <label>Costo de la reparación ($)<input name="costo" type="number" min={0} step="0.01" required autoFocus /></label>
        <label>Empresa a la que va la factura<select name="empresa" required defaultValue=""><option value="" disabled>Elegí la empresa</option>{Object.entries(EMPRESAS).map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
        <label>Trabajo realizado<input name="trabajo" maxLength={500} /></label>
        <SelectorSector sectores={sectores} etiqueta="Vuelve al sector" />
      </Formulario>}
      {accion === "editar" && <Formulario titulo="Editar datos" boton="Guardar" cerrar={() => setAccion(null)} enviar={async f => { await enviar("", { descripcion: f.get("descripcion"), marca: f.get("marca"), modelo: f.get("modelo"), numero_serie: f.get("numero_serie") }, "PUT"); await hecho("Datos guardados."); }}>
        <label>Descripción<input name="descripcion" required maxLength={120} defaultValue={ficha.descripcion} /></label>
        <label>Marca<input name="marca" maxLength={60} defaultValue={ficha.marca} /></label>
        <label>Modelo<input name="modelo" maxLength={60} defaultValue={ficha.modelo} /></label>
        <label>Número de serie<input name="numero_serie" maxLength={60} defaultValue={ficha.numero_serie} /></label>
      </Formulario>}
      {accion === "baja" && <Formulario titulo="Dar de baja" boton="Dar de baja" cerrar={() => setAccion(null)} enviar={async f => { await enviar("/baja", { motivo: f.get("motivo") }); await hecho("Equipo dado de baja."); }}>
        <p className="ayuda">El equipo sigue en la lista marcado «De baja», con todo su historial. Ya no se puede trasladar ni mandar a taller.</p>
        <label>Motivo<input name="motivo" required maxLength={300} autoFocus placeholder="Se reemplazó por una nueva" /></label>
      </Formulario>}
      {accion === "etiqueta" && <Formulario titulo="Imprimir etiqueta" boton="Imprimir" cerrar={() => setAccion(null)} enviar={async f => { await enviar("/etiqueta", { copias: Number(f.get("copias")) }); await hecho("Etiqueta enviada a la impresora."); }}>
        <p className="ayuda">Código de barras {ficha.codigo}.</p>
        <label>Copias<input name="copias" type="number" min={1} max={50} defaultValue={1} required /></label>
      </Formulario>}
    </>}
  </Ventana>;
}

function Catalogo<T extends Record<string, unknown> & { id: string; nombre: string }>({ titulo, ayuda, nuevo, items, ruta, columnas, campos, cambio, filtro }: {
  titulo: string; ayuda: string; nuevo: string; items: T[]; ruta: string;
  columnas: Array<{ clave: keyof T; titulo: string; valor?: (fila: T) => React.ReactNode }>;
  campos: (item?: T) => React.ReactNode; cambio: () => void; filtro?: React.ReactNode;
}) {
  const [editando, setEditando] = useState<T | "nuevo" | null>(null); const [borrando, setBorrando] = useState<T | null>(null); const [error, setError] = useState("");
  async function borrar(item: T) {
    setError("");
    try { await api(`${ruta}/${item.id}`, { method: "DELETE" }); cambio(); } catch (x) { setError(mensaje(x, "No se pudo eliminar.")); }
  }
  return <section className="tarjeta">
    <div className="titulo-fila"><div><h2>{titulo}</h2><p className="ayuda">{ayuda}</p></div><button className="primario" onClick={() => setEditando("nuevo")}>{nuevo}</button></div>
    {error && <ErrorVisible mensaje={error} />}
    {filtro}
    {items.length ? <Tabla etiqueta={titulo} filas={items} porPagina={15} alElegir={setEditando} columnas={[...columnas, {
      clave: "id", titulo: "", valor: item => <div className="acciones-fila">
        <button onClick={e => { e.stopPropagation(); setEditando(item); }}>Editar</button>
        <button className="peligro" onClick={e => { e.stopPropagation(); setBorrando(item); }}>Eliminar</button>
      </div>,
    }]} /> : <Vacio>Todavía no hay ninguno cargado.</Vacio>}
    {editando && <Formulario titulo={editando === "nuevo" ? nuevo : `Editar ${editando.nombre}`} boton="Guardar" cerrar={() => setEditando(null)} enviar={async f => {
      const cuerpo = JSON.stringify(Object.fromEntries(f.entries()));
      await (editando === "nuevo" ? api(ruta, { method: "POST", body: cuerpo }) : api(`${ruta}/${editando.id}`, { method: "PUT", body: cuerpo }));
      setEditando(null); cambio();
    }}>{campos(editando === "nuevo" ? undefined : editando)}</Formulario>}
    <Confirmacion abierto={borrando !== null} titulo="Eliminar" detalle={`Se elimina «${borrando?.nombre}». Sólo se puede si no tiene equipos cargados.`} cancelar={() => setBorrando(null)} confirmar={() => { const item = borrando!; setBorrando(null); void borrar(item); }} />
  </section>;
}

export function ActivosGestion() {
  const [pestana, setPestana] = useState<"equipos" | "tipos" | "sectores" | "reparados">("equipos");
  const [filtroBodegaSector, setFiltroBodegaSector] = useState("");
  const [tipos, setTipos] = useState<Tipo[]>([]); const [sectores, setSectores] = useState<Sector[]>([]);
  const [equipos, setEquipos] = useState<Equipo[] | null>(null); const [masReparados, setMasReparados] = useState<Equipo[]>([]);
  const [filtroTipo, setFiltroTipo] = useState(""); const [filtroSector, setFiltroSector] = useState(""); const [filtroBodega, setFiltroBodega] = useState("");
  const [error, setError] = useState(""); const [errorLectura, setErrorLectura] = useState("");
  const [abierto, setAbierto] = useState<string | null>(null); const [alta, setAlta] = useState(false);
  const lector = useRef<HTMLInputElement>(null);

  async function cargarCatalogos() {
    try {
      const [t, s] = await Promise.all([api<Tipo[]>("activos/tipos"), api<Sector[]>("activos/sectores")]);
      setTipos(t); setSectores(s);
    } catch (x) { setError(mensaje(x, "No se pudieron leer los tipos y sectores.")); }
  }
  async function cargarEquipos() {
    const filtros = new URLSearchParams();
    if (filtroTipo) filtros.set("tipo_id", filtroTipo);
    if (filtroSector) filtros.set("sector_id", filtroSector);
    if (filtroBodega) filtros.set("bodega", filtroBodega);
    try {
      const [lista, ranking] = await Promise.all([api<Equipo[]>(`activos/equipos?${filtros}`), api<Equipo[]>("activos/equipos?mas_reparados=true")]);
      setEquipos(lista); setMasReparados(ranking.filter(e => e.reparaciones > 0).slice(0, 10)); setError("");
    } catch (x) { setEquipos([]); setError(mensaje(x, "No se pudieron leer los equipos.")); }
  }
  useEffect(() => { void cargarCatalogos(); }, []);
  useEffect(() => { void cargarEquipos(); }, [filtroTipo, filtroSector, filtroBodega]);

  // Los lectores USB y los colectores Zebra escriben el código y mandan Enter, como un teclado.
  async function leer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setErrorLectura("");
    const codigo = String(new FormData(e.currentTarget).get("codigo") || "").trim().toUpperCase();
    if (!codigo) return;
    try { await api(`activos/equipos/${encodeURIComponent(codigo)}`); setAbierto(codigo); }
    catch (x) { setErrorLectura(mensaje(x, "No se encontró el equipo.")); }
    if (lector.current) lector.current.value = "";
  }

  const faltaCatalogo = !tipos.length || !sectores.length;
  const pestanas = [["equipos", "Equipos"], ["tipos", "Tipos"], ["sectores", "Sectores"], ["reparados", "Más reparados"]] as const;

  return <>
    <div className="pestanas">
      {pestanas.map(([id, nombre]) => <button key={id} className={pestana === id ? "activo" : ""} onClick={() => setPestana(id)}>{nombre}</button>)}
    </div>
    {error && <ErrorVisible mensaje={error} />}

    {pestana === "equipos" && <section className="tarjeta">
      <div className="titulo-fila"><div><h2>Equipos</h2><p className="ayuda">Tocá un equipo para ver su ficha, trasladarlo, mandarlo a taller o imprimir la etiqueta.</p></div>
        <button className="primario" disabled={faltaCatalogo} onClick={() => setAlta(true)}>Nuevo equipo</button></div>
      <div className="barra-filtros">
        <form className="lector-codigo" onSubmit={leer}><label>Leer código<input ref={lector} name="codigo" autoFocus autoComplete="off" placeholder="Escaneá o escribí, ej. BOM-0001" /></label><button>Abrir</button></form>
        <label>Tipo<select value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)}><option value="">Todos</option>{tipos.map(t => <option key={t.id} value={t.id}>{t.nombre}</option>)}</select></label>
        <label>Bodega<select value={filtroBodega} onChange={e => { setFiltroBodega(e.target.value); setFiltroSector(""); }}><option value="">Todas</option>{Object.entries(BODEGAS).map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
        <label>Sector<select value={filtroSector} onChange={e => setFiltroSector(e.target.value)}><option value="">Todos</option>{sectores.filter(s => !filtroBodega || s.bodega === filtroBodega).map(s => <option key={s.id} value={s.id}>{filtroBodega ? s.nombre : `${s.nombre} · ${s.bodega_nombre}`}</option>)}</select></label>
      </div>
      {errorLectura && <ErrorVisible mensaje={errorLectura} />}
      {faltaCatalogo ? <div className="vacio-accion"><p>Para dar de alta equipos primero cargá al menos un tipo y un sector.</p>
        <div className="acciones">{!tipos.length && <button onClick={() => setPestana("tipos")}>Cargar tipos</button>}{!sectores.length && <button onClick={() => setPestana("sectores")}>Cargar sectores</button>}</div></div>
        : equipos === null ? <p className="ayuda">Cargando…</p> : equipos.length ? <Tabla etiqueta="Equipos" filas={equipos} porPagina={15} alElegir={e => setAbierto(e.codigo)} columnas={[
          { clave: "codigo", titulo: "Código" },
          { clave: "descripcion", titulo: "Descripción" },
          { clave: "tipo", titulo: "Tipo" },
          { clave: "bodega_nombre", titulo: "Bodega" },
          { clave: "sector", titulo: "Sector", valor: e => e.estado === "EN_TALLER" ? "En taller" : e.sector },
          { clave: "estado", titulo: "Estado", valor: e => <span className={`estado estado-equipo-${e.estado.toLowerCase()}`}>{ESTADOS[e.estado]}</span> },
          { clave: "reparaciones", titulo: "Reparaciones", valor: e => String(e.reparaciones) },
        ]} /> : <Vacio>No hay equipos cargados con estos filtros.</Vacio>}
    </section>}

    {pestana === "tipos" && <Catalogo titulo="Tipos de activo" nuevo="Nuevo tipo" ayuda="Bombas, maquinarias, muebles… El prefijo es el comienzo del código de barras: por ejemplo BOM da BOM-0001." items={tipos} ruta="activos/tipos" cambio={() => void cargarCatalogos()}
      columnas={[{ clave: "nombre", titulo: "Nombre" }, { clave: "prefijo", titulo: "Prefijo del código" }]} campos={t => <>
        <label>Nombre<input name="nombre" required maxLength={60} defaultValue={t?.nombre} autoFocus /></label>
        <label>Prefijo del código (2 a 5 letras)<input name="prefijo" required pattern="[A-Za-z]{2,5}" maxLength={5} defaultValue={t?.prefijo} style={{ textTransform: "uppercase" }} /></label>
      </>} />}

    {pestana === "sectores" && <Catalogo titulo="Sectores" nuevo="Nuevo sector" ayuda="Lugares de cada bodega donde se ubican los equipos." items={sectores.filter(s => !filtroBodegaSector || s.bodega === filtroBodegaSector)} ruta="activos/sectores" cambio={() => void cargarCatalogos()}
      filtro={<div className="barra-filtros"><label>Bodega<select value={filtroBodegaSector} onChange={e => setFiltroBodegaSector(e.target.value)}><option value="">Todas</option>{Object.entries(BODEGAS).map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label></div>}
      columnas={[{ clave: "nombre", titulo: "Nombre" }, { clave: "bodega_nombre", titulo: "Bodega" }]} campos={s => <>
        <label>Nombre<input name="nombre" required maxLength={80} defaultValue={s?.nombre} autoFocus /></label>
        <label>Bodega<select name="bodega" required defaultValue={s?.bodega ?? filtroBodegaSector}><option value="" disabled>Elegí la bodega</option>{Object.entries(BODEGAS).map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
      </>} />}

    {pestana === "reparados" && <section className="tarjeta">
      <h2>Equipos con más reparaciones</h2>
      <p className="ayuda">Los que más veces fueron a un taller externo y cuánto se gastó en total. Sirve para decidir si conviene reparar o comprar uno nuevo.</p>
      {masReparados.length ? <Tabla etiqueta="Equipos con más reparaciones" filas={masReparados} alElegir={e => setAbierto(e.codigo)} columnas={[
        { clave: "codigo", titulo: "Código" },
        { clave: "descripcion", titulo: "Descripción" },
        { clave: "reparaciones", titulo: "Reparaciones", valor: e => String(e.reparaciones) },
        { clave: "costo_reparaciones", titulo: "Costo total", valor: e => pesos(e.costo_reparaciones) },
      ]} /> : <Vacio>Todavía ningún equipo pasó por un taller externo.</Vacio>}
    </section>}

    {alta && <Formulario titulo="Nuevo equipo" boton="Dar de alta" cerrar={() => setAlta(false)} enviar={async f => {
      const equipo = await api<Equipo>("activos/equipos", { method: "POST", body: JSON.stringify(Object.fromEntries(f.entries())) });
      setAlta(false); await cargarEquipos(); setAbierto(equipo.codigo);
    }}>
      <label>Tipo<select name="tipo_id" required defaultValue=""><option value="" disabled>Elegí un tipo</option>{tipos.map(t => <option key={t.id} value={t.id}>{t.nombre}</option>)}</select></label>
      <label>Descripción<input name="descripcion" required maxLength={120} placeholder="Bomba centrífuga de trasiego" /></label>
      <label>Marca<input name="marca" maxLength={60} /></label>
      <label>Modelo<input name="modelo" maxLength={60} /></label>
      <label>Número de serie<input name="numero_serie" maxLength={60} /></label>
      <SelectorSector sectores={sectores} />
      <p className="ayuda">El código se genera solo y no se repite.</p>
    </Formulario>}
    {abierto && <VentanaEquipo key={abierto} codigo={abierto} sectores={sectores} cerrar={() => { setAbierto(null); lector.current?.focus(); }} cambio={() => void cargarEquipos()} />}
  </>;
}
