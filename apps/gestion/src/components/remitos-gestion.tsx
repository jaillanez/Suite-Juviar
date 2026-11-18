"use client";

import { useEffect, useState } from "react";
import { abrirArchivo, api } from "@/lib/api";
import { ErrorVisible, FormularioVentana as Formulario, PanelFirma, Pestanas, Tabla, Vacio, Ventana } from "./compartidos";

type Item = { descripcion: string; codigo: string | null; cantidad: number; volvio_en: string | null; volvio_por: string };
type Remito = Record<string, unknown> & {
  id: string; numero: number; bodega: string; bodega_nombre: string; destino: string; motivo: string; items: Item[];
  estado: "BORRADOR" | "AUTORIZADO" | "AFUERA" | "CERRADO" | "ANULADO"; creado_por: string; creado_en: string; origen: string;
  con_foto: boolean; firma: { modo: "celular" | "papel"; por: string; en: string } | null; salio_en: string | null; salio_por: string;
  anulado_motivo: string; afuera: number; dias_afuera: number | null; demorado: boolean;
};
type Mensaje = Record<string, unknown> & { id: string; nombre: string; texto: string; recibido_en: string; con_foto: boolean; remito_id: string | null; remito_numero: number | null; descartado: boolean; pendiente: boolean };
type Sector = { id: string; nombre: string; bodega_nombre: string };
type Parametros = { dias_maximos_fuera: number | null; modo_whatsapp: "revision" | "directo"; actualizado_por: string; actualizado_en: string | null };

const BODEGAS: Record<string, string> = { chimbas: "Chimbas", "media-agua": "Media Agua", lavalle: "Lavalle" };
const EMPRESAS: Record<string, string> = { ENAV: "ENAV", JUBIAR: "Juviar" };
const ESTADOS: Record<Remito["estado"], string> = { BORRADOR: "Falta firmar", AUTORIZADO: "Autorizado, falta salir", AFUERA: "Afuera", CERRADO: "Volvió todo", ANULADO: "Anulado" };
const fecha = (v: string | null) => v ? new Date(v).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : "—";
const mensaje = (x: unknown, defecto: string) => x instanceof Error ? x.message : defecto;
const nuevoItem = (): Item => ({ descripcion: "", codigo: "", cantidad: 1, volvio_en: null, volvio_por: "" });

/** Equipos con código y herramientas cargadas a mano; de todo se controla que vuelva. */
function EditorItems({ items, cambiar }: { items: Item[]; cambiar: (items: Item[]) => void }) {
  const poner = (i: number, cambio: Partial<Item>) => cambiar(items.map((x, j) => j === i ? { ...x, ...cambio } : x));
  return <fieldset className="franjas"><legend>Qué sale</legend>
    <p className="ayuda">Equipo con etiqueta: poné el código y la descripción se completa sola. Herramienta sin etiqueta: dejá el código vacío y describila.</p>
    {items.map((x, i) => <div key={i} className="item-remito">
      <input aria-label="Código" placeholder="Código, ej. BOM-0001" maxLength={20} value={x.codigo ?? ""} onChange={e => poner(i, { codigo: e.target.value.toUpperCase() })} />
      <input aria-label="Descripción" placeholder="Descripción, ej. Amoladora Bosch" maxLength={200} value={x.descripcion} onChange={e => poner(i, { descripcion: e.target.value })} />
      <input aria-label="Cantidad" type="number" min={1} max={999} value={x.cantidad} onChange={e => poner(i, { cantidad: Number(e.target.value) || 1 })} />
      <button type="button" aria-label="Quitar" title="Quitar" disabled={items.length === 1} onClick={() => cambiar(items.filter((_, j) => j !== i))}>✕</button>
    </div>)}
    <button type="button" disabled={items.length >= 50} onClick={() => cambiar([...items, nuevoItem()])}>Agregar ítem</button>
  </fieldset>;
}

function FormularioRemito({ remito, cerrar, guardado }: { remito?: Remito; cerrar: () => void; guardado: (r: Remito) => void }) {
  const [items, setItems] = useState<Item[]>(remito?.items.length ? remito.items : [nuevoItem()]);
  return <Formulario titulo={remito ? `Remito N.º ${remito.numero}` : "Nuevo remito de salida"} boton="Guardar" tamano="ancha" cerrar={cerrar} enviar={async f => {
    const cuerpo = { bodega: f.get("bodega"), destino: f.get("destino"), motivo: f.get("motivo"),
      items: items.filter(x => x.codigo || x.descripcion).map(x => ({ codigo: x.codigo || null, descripcion: x.descripcion, cantidad: x.cantidad })) };
    guardado(await api<Remito>(remito ? `activos/remitos/${remito.id}` : "activos/remitos", { method: remito ? "PUT" : "POST", body: JSON.stringify(cuerpo) }));
  }}>
    <label>Bodega de la que sale<select name="bodega" required defaultValue={remito?.bodega ?? ""}><option value="" disabled>Elegí la bodega</option>{Object.entries(BODEGAS).map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
    <label>Taller o lugar al que va<input name="destino" required maxLength={120} defaultValue={remito?.destino ?? ""} /></label>
    <label>Motivo<input name="motivo" required maxLength={300} defaultValue={remito?.motivo ?? ""} placeholder="Bobinado del motor" /></label>
    <EditorItems items={items} cambiar={setItems} />
  </Formulario>;
}

function VentanaRemito({ id, sectores, puedeFirmar, cerrar, cambio }: { id: string; sectores: Sector[]; puedeFirmar: boolean; cerrar: () => void; cambio: () => void }) {
  const [remito, setRemito] = useState<Remito | null>(null); const [error, setError] = useState(""); const [aviso, setAviso] = useState("");
  const [accion, setAccion] = useState<"editar" | "firmar" | "anular" | null>(null); const [regreso, setRegreso] = useState<string | null>(null);
  const [modo, setModo] = useState<"celular" | "papel">("celular"); const [firma, setFirma] = useState("");
  const ruta = `activos/remitos/${id}`;
  async function cargar() { try { setRemito(await api<Remito>(ruta)); setError(""); } catch (x) { setError(mensaje(x, "No se pudo leer el remito.")); } }
  useEffect(() => { void cargar(); }, [id]);
  function hecho(r: Remito, texto: string) { setRemito(r); setAccion(null); setRegreso(null); setAviso(texto); cambio(); }
  async function hacer(sufijo: string, cuerpo: unknown, texto: string) {
    setError(""); setAviso("");
    try { hecho(await api<Remito>(`${ruta}${sufijo}`, { method: "POST", body: JSON.stringify(cuerpo) }), texto); } catch (x) { setError(mensaje(x, "No se pudo completar.")); }
  }
  async function archivo(sufijo: string) { try { await abrirArchivo(`${ruta}${sufijo}`); } catch (x) { setError(mensaje(x, "No se pudo abrir.")); } }

  return <Ventana titulo={remito ? `Remito N.º ${remito.numero}` : "Remito"} tamano="amplia" cerrar={cerrar}>
    {error && <ErrorVisible mensaje={error} />}
    {aviso && <p className="aviso-exito">{aviso}</p>}
    {!remito ? !error && <p className="ayuda">Cargando…</p> : <>
      <div className="cabecera-ficha">
        <span className={`estado estado-remito-${remito.estado.toLowerCase()}`}>{ESTADOS[remito.estado]}</span>
        {remito.demorado && <span className="estado estado-remito-demorado">Demorado: {remito.dias_afuera} días afuera</span>}
        <span className="ayuda">{remito.bodega_nombre || "Falta la bodega"} → {remito.destino || "falta el destino"}</span>
      </div>
      <div className="acciones acciones-ficha">
        <button onClick={() => void archivo("/pdf")}>{remito.estado === "BORRADOR" ? "Ver PDF" : "Imprimir remito"}</button>
        {remito.con_foto && <button onClick={() => void archivo("/foto")}>Ver foto</button>}
        {remito.estado === "BORRADOR" && <button onClick={() => setAccion("editar")}>Editar</button>}
        {puedeFirmar && (remito.estado === "BORRADOR" || remito.estado === "AUTORIZADO") && <button className="peligro" onClick={() => setAccion("anular")}>Anular</button>}
        {puedeFirmar && remito.estado === "BORRADOR" && <button className="primario" onClick={() => { setFirma(""); setAccion("firmar"); }}>Firmar y autorizar</button>}
      </div>
      {remito.estado === "BORRADOR" && !puedeFirmar && <p className="ayuda">Lo tiene que firmar el Encargado de Mantenimiento; sin su firma la guardia no lo deja salir.</p>}
      <dl className="ficha">
        <div><dt>Motivo</dt><dd>{remito.motivo || "—"}</dd></div>
        <div><dt>Cargado</dt><dd>{remito.creado_por} · {fecha(remito.creado_en)}{remito.origen === "whatsapp" ? " · por WhatsApp" : ""}</dd></div>
        <div><dt>Firma</dt><dd>{remito.firma ? `${remito.firma.modo === "celular" ? "En el celular" : "En papel"} · ${remito.firma.por} · ${fecha(remito.firma.en)}` : "Sin firmar"}</dd></div>
        <div><dt>Salida</dt><dd>{remito.salio_en ? `${remito.salio_por} · ${fecha(remito.salio_en)}` : "Todavía no salió"}</dd></div>
        {remito.estado === "ANULADO" && <div><dt>Anulado</dt><dd>{remito.anulado_motivo}</dd></div>}
      </dl>
      <Tabla etiqueta="Ítems del remito" porPagina={50} filas={remito.items.map((x, i) => ({ ...x, indice: i }))} columnas={[
        { clave: "codigo", titulo: "Código", valor: x => x.codigo || "Sin código" },
        { clave: "descripcion", titulo: "Descripción" },
        { clave: "cantidad", titulo: "Cant." },
        { clave: "volvio_en", titulo: "Volvió", valor: x => x.volvio_en ? `${fecha(x.volvio_en)} · ${x.volvio_por}`
          : remito.estado !== "AFUERA" ? "—"
          : x.codigo ? <button onClick={() => setRegreso(x.codigo)}>Registrar regreso</button>
          : <button onClick={() => void hacer(`/items/${x.indice}/regreso`, {}, "Regreso registrado.")}>Volvió</button> },
      ]} />

      {accion === "editar" && <FormularioRemito remito={remito} cerrar={() => setAccion(null)} guardado={r => hecho(r, "Remito guardado.")} />}
      {accion === "firmar" && <Formulario titulo="Firmar y autorizar la salida" boton="Autorizar" tamano="ancha" cerrar={() => setAccion(null)} enviar={async () => {
        if (modo === "celular" && !firma) throw new Error("Firmá en el recuadro.");
        hecho(await api<Remito>(`${ruta}/firma`, { method: "POST", body: JSON.stringify({ modo, imagen: modo === "celular" ? firma : null }) }), "Autorizado: la guardia de la bodega ya lo ve en su consola.");
      }}>
        <div className="opciones-firma" role="radiogroup" aria-label="Cómo firmás">
          <label><input type="radio" name="modo" checked={modo === "celular"} onChange={() => setModo("celular")} /> Firmo acá, en la pantalla</label>
          <label><input type="radio" name="modo" checked={modo === "papel"} onChange={() => setModo("papel")} /> Firmo en papel el remito impreso</label>
        </div>
        {modo === "celular" ? <PanelFirma etiqueta="Firma del Encargado de Mantenimiento" alCambiar={setFirma} />
          : <p className="ayuda">Autorizás ahora y después firmás a mano el remito impreso. La guardia va a pedir ver esa firma.</p>}
      </Formulario>}
      {accion === "anular" && <Formulario titulo="Anular remito" boton="Anular" cerrar={() => setAccion(null)} enviar={async f => {
        hecho(await api<Remito>(`${ruta}/anular`, { method: "POST", body: JSON.stringify({ motivo: f.get("motivo") }) }), "Remito anulado: la guardia ya no lo deja salir.");
      }}>
        <label>Motivo<input name="motivo" required maxLength={300} autoFocus /></label>
      </Formulario>}
      {regreso && <Formulario titulo={`Regreso de ${regreso}`} boton="Registrar regreso" cerrar={() => setRegreso(null)} enviar={async f => {
        hecho(await api<Remito>(`${ruta}/equipos/${encodeURIComponent(regreso)}/regreso`, { method: "POST", body: JSON.stringify({
          costo: Number(f.get("costo")), empresa: f.get("empresa"), trabajo_realizado: f.get("trabajo"), sector_id: f.get("sector_id") }) }), "Regreso registrado.");
      }}>
        <label>Costo de la reparación ($)<input name="costo" type="number" min={0} step="0.01" required autoFocus /></label>
        <label>Empresa a la que va la factura<select name="empresa" required defaultValue=""><option value="" disabled>Elegí la empresa</option>{Object.entries(EMPRESAS).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
        <label>Trabajo realizado<input name="trabajo" maxLength={500} /></label>
        <label>Vuelve al sector<select name="sector_id" required defaultValue=""><option value="" disabled>Elegí el sector</option>{sectores.map(s => <option key={s.id} value={s.id}>{s.nombre} · {s.bodega_nombre}</option>)}</select></label>
      </Formulario>}
    </>}
  </Ventana>;
}

function BandejaWhatsapp({ abrirRemito }: { abrirRemito: (id: string) => void }) {
  const [mensajes, setMensajes] = useState<Mensaje[] | null>(null); const [error, setError] = useState("");
  async function cargar() { try { setMensajes(await api<Mensaje[]>("activos/mensajes-whatsapp")); setError(""); } catch (x) { setMensajes([]); setError(mensaje(x, "No se pudieron leer los mensajes.")); } }
  useEffect(() => { void cargar(); }, []);
  async function usar(m: Mensaje) {
    try { const r = await api<Remito>(`activos/mensajes-whatsapp/${m.id}/remito`, { method: "POST" }); await cargar(); abrirRemito(r.id); }
    catch (x) { setError(mensaje(x, "No se pudo armar el remito.")); }
  }
  async function descartar(m: Mensaje) {
    try { await api(`activos/mensajes-whatsapp/${m.id}/descartar`, { method: "POST" }); await cargar(); } catch (x) { setError(mensaje(x, "No se pudo descartar.")); }
  }
  return <section className="tarjeta">
    <h2>Mensajes de WhatsApp</h2>
    <p className="ayuda">Fotos y textos que mandó el personal de mantenimiento desde el celular. Cómo entran (para revisar o directo como remito) se elige en Parámetros.</p>
    {error && <ErrorVisible mensaje={error} />}
    {!mensajes ? <p className="ayuda">Cargando…</p> : !mensajes.length ? <Vacio>Todavía no llegó ningún mensaje.</Vacio> :
      <Tabla etiqueta="Mensajes de WhatsApp" filas={mensajes} columnas={[
        { clave: "recibido_en", titulo: "Llegó", valor: m => fecha(m.recibido_en) },
        { clave: "nombre", titulo: "De" },
        { clave: "texto", titulo: "Texto", valor: m => m.texto || "—" },
        { clave: "con_foto", titulo: "Foto", valor: m => m.con_foto ? <button onClick={() => void abrirArchivo(`activos/mensajes-whatsapp/${m.id}/foto`)}>Ver foto</button> : "—" },
        { clave: "pendiente", titulo: "Qué se hizo", valor: m => m.remito_id ? <button onClick={() => abrirRemito(m.remito_id!)}>Remito N.º {m.remito_numero}</button>
          : m.descartado ? "Descartado"
          : <span className="acciones"><button className="primario" onClick={() => void usar(m)}>Armar remito</button><button onClick={() => void descartar(m)}>Descartar</button></span> },
      ]} />}
  </section>;
}

export function RemitosGestion({ perfil, sectores }: { perfil: string; sectores: Sector[] }) {
  const puedeFirmar = perfil === "SUPERADMIN" || perfil === "ENCARGADO_MANTENIMIENTO";
  const [vista, setVista] = useState<"remitos" | "whatsapp">("remitos");
  const [remitos, setRemitos] = useState<Remito[] | null>(null); const [error, setError] = useState("");
  const [filtro, setFiltro] = useState(""); const [abierto, setAbierto] = useState<string | null>(null); const [nuevo, setNuevo] = useState(false);
  async function cargar() {
    try { setRemitos(await api<Remito[]>(`activos/remitos${filtro ? `?estado=${filtro}` : ""}`)); setError(""); }
    catch (x) { setRemitos([]); setError(mensaje(x, "No se pudieron leer los remitos.")); }
  }
  useEffect(() => { void cargar(); }, [filtro]);
  const demorados = (remitos ?? []).filter(r => r.demorado);
  return <>
    <Pestanas opciones={[["remitos", "Remitos"], ["whatsapp", "Mensajes de WhatsApp"]] as const} activa={vista} cambiar={setVista} />
    {vista === "whatsapp" && <BandejaWhatsapp abrirRemito={id => { setAbierto(id); void cargar(); }} />}
    {vista === "remitos" && <section className="tarjeta">
      <div className="titulo-fila"><div><h2>Remitos de salida</h2><p className="ayuda">Nada sale de la planta sin un remito firmado por el Encargado de Mantenimiento. La guardia de la bodega lo ve en su consola y marca la salida.</p></div>
        <button className="primario" onClick={() => setNuevo(true)}>Nuevo remito</button></div>
      {demorados.length > 0 && <p className="aviso-error"><strong>{demorados.length === 1 ? "Hay un remito demorado" : `Hay ${demorados.length} remitos demorados`}:</strong> {demorados.map(r => `N.º ${r.numero} (${r.dias_afuera} días)`).join(", ")}.</p>}
      <div className="barra-filtros"><label>Estado<select value={filtro} onChange={e => setFiltro(e.target.value)}><option value="">Todos</option>{Object.entries(ESTADOS).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label></div>
      {error && <ErrorVisible mensaje={error} />}
      {!remitos ? <p className="ayuda">Cargando…</p> : !remitos.length ? <Vacio>No hay remitos.</Vacio> :
        <Tabla etiqueta="Remitos de salida" filas={remitos} alElegir={r => setAbierto(r.id)} columnas={[
          { clave: "numero", titulo: "N.º" },
          { clave: "estado", titulo: "Estado", valor: r => <span className={`estado estado-remito-${r.demorado ? "demorado" : r.estado.toLowerCase()}`}>{r.demorado ? `Demorado (${r.dias_afuera} días)` : ESTADOS[r.estado]}</span> },
          { clave: "bodega_nombre", titulo: "Bodega", valor: r => r.bodega_nombre || "—" },
          { clave: "destino", titulo: "Destino", valor: r => r.destino || "—" },
          { clave: "items", titulo: "Lleva", valor: r => r.items.map(x => x.codigo || x.descripcion).join(", ") },
          { clave: "afuera", titulo: "Afuera", valor: r => r.salio_en ? `${r.afuera} de ${r.items.length}` : "—" },
          { clave: "creado_en", titulo: "Cargado", valor: r => fecha(r.creado_en) },
        ]} />}
    </section>}
    {nuevo && <FormularioRemito cerrar={() => setNuevo(false)} guardado={r => { setNuevo(false); setAbierto(r.id); void cargar(); }} />}
    {abierto && <VentanaRemito id={abierto} sectores={sectores} puedeFirmar={puedeFirmar} cerrar={() => setAbierto(null)} cambio={() => void cargar()} />}
  </>;
}

/** Tarjeta de Parámetros: días máximos afuera y cómo entra lo que llega por WhatsApp. */
export function ParametrosRemitos() {
  const [datos, setDatos] = useState<Parametros | null>(null); const [error, setError] = useState(""); const [aviso, setAviso] = useState(""); const [ocupado, setOcupado] = useState(false);
  useEffect(() => { api<Parametros>("activos/parametros-remitos").then(setDatos).catch(x => setError(mensaje(x, "No se pudieron leer los parámetros de remitos."))); }, []);
  async function guardar(f: FormData) {
    setOcupado(true); setError(""); setAviso("");
    try {
      const dias = String(f.get("dias") || "").trim();
      setDatos(await api<Parametros>("activos/parametros-remitos", { method: "PUT", body: JSON.stringify({ dias_maximos_fuera: dias ? Number(dias) : null, modo_whatsapp: f.get("modo") }) }));
      setAviso("Guardado.");
    } catch (x) { setError(mensaje(x, "No se pudo guardar.")); }
    setOcupado(false);
  }
  return <section className="tarjeta">
    <h2>Remitos de salida de Mantenimiento</h2>
    {error && <ErrorVisible mensaje={error} />}
    {datos && <form onSubmit={e => { e.preventDefault(); void guardar(new FormData(e.currentTarget)); }}>
      <label>Días que algo puede estar afuera antes de marcarlo demorado<input name="dias" type="number" min={1} max={365} defaultValue={datos.dias_maximos_fuera ?? ""} placeholder="Sin cargar: no se marca" /></label>
      <fieldset className="franjas"><legend>Lo que manda el personal por WhatsApp (foto y texto)</legend>
        <label><input type="radio" name="modo" value="revision" defaultChecked={datos.modo_whatsapp === "revision"} /> Queda para revisar: el Encargado arma el remito desde el mensaje</label>
        <label><input type="radio" name="modo" value="directo" defaultChecked={datos.modo_whatsapp === "directo"} /> Entra directo: se arma solo el remito, listo para que el Encargado lo complete y firme</label>
        <p className="ayuda">En los dos casos nada sale sin la firma del Encargado. El WhatsApp sólo se acepta de celulares activos en «Personal en el bot».</p>
      </fieldset>
      <div className="acciones"><button className="primario" disabled={ocupado}>Guardar</button>{aviso && <span className="ayuda">{aviso}</span>}</div>
      {datos.actualizado_por && <p className="ayuda">Último cambio: {datos.actualizado_por}, {fecha(datos.actualizado_en)}.</p>}
    </form>}
  </section>;
}
