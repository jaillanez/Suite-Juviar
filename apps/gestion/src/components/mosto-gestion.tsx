"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Perfil } from "@/lib/acceso";
import { ErrorVisible, FormularioVentana as Formulario, Pestanas, Tabla, Vacio, Ventana } from "./compartidos";

type Analisis = { azucar_gl: number; absorbancia_520: number | null; alcohol: number | null; observaciones: string; actor: string; fecha: string };
type Decision = { etapa: "calidad" | "produccion" | "comercial"; aprueba: boolean; motivo: string; actor: string; fecha: string };
type Pileta = { id: string; pileta: string; litros: number; analisis: Analisis };
type Paso = { lugar: string; actor: string; fecha: string; nota: string };
type Liquidacion = { litros: number; azucar_promedio: number; margen_gl: number; azucar_liquidada: number; azucar_referencia: number; precio_base: number; precio_litro: number; total: number };
type Estado = "EN_ANALISIS" | "RECHAZADA_CALIDAD" | "APROBADA" | "RECHAZADA" | "CERRADA";
type Viaje = Record<string, unknown> & {
  id: string; compra_id: string; compra_numero: number; proveedor: string; tipo: string; tipo_nombre: string;
  bodega: string; bodega_nombre: string; patente: string; litros: number; ingreso_por: string; ingreso_en: string;
  analisis: Analisis | null; descarga: Paso | null; recorrido: Paso[]; demorado: boolean; horas_en_planta: number; compra_cerrada: boolean;
};
type Compra = Record<string, unknown> & {
  id: string; numero: number; proveedor: string; cuit: string; tipo: string; tipo_nombre: string; litros: number; precio_base: number;
  creada_por: string; creada_en: string; analisis: Analisis | null; decisiones: Decision[]; piletas: Pileta[];
  sin_margen: boolean; sin_margen_motivo: string; sin_margen_por: string; sin_margen_en: string | null; cerrada_en: string | null; cerrada_por: string;
  estado: Estado; estado_nombre: string; litros_recibidos: number; viajes: number; liquidacion: Liquidacion | null; liquidacion_final: boolean;
};
type Ficha = Compra & { detalle_viajes: Viaje[] };
type Catalogo = { tipos: Record<string, string>; bodegas: Record<string, string>; azucar_referencia: number; margen_gl: number; horas_virgen: number | null };
type Aviso = { id: string; viaje_id: string; texto: string; creado_en: string; en_planta: boolean; envios: { canal: string; nombre: string; resultado: string; detalle: string }[] };

const ETAPAS = { calidad: "Calidad", produccion: "Jefe de Producción", comercial: "Comercial" };
const RESULTADOS: Record<string, string> = { enviado: "enviado", encolado: "en cola del bot", sin_configurar: "canal sin configurar", error: "no salió" };
const fecha = (v: string | null) => v ? new Date(v).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }) : "—";
const numero = (v: number, d = 0) => v.toLocaleString("es-AR", { maximumFractionDigits: d });
const pesos = (v: number) => v.toLocaleString("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 4 });
const mensaje = (x: unknown, defecto: string) => x instanceof Error ? x.message : defecto;
const opcional = (v: FormDataEntryValue | null) => v === null || v === "" ? null : Number(v);
const datosAnalisis = (f: FormData) => ({ azucar_gl: Number(f.get("azucar_gl")), absorbancia_520: opcional(f.get("absorbancia_520")), alcohol: opcional(f.get("alcohol")), observaciones: f.get("observaciones") ?? "" });
const resumenAnalisis = (a: Analisis | null) => a ? [`${numero(a.azucar_gl, 1)} g/L`, a.absorbancia_520 !== null && `abs. 520 ${numero(a.absorbancia_520, 3)}`, a.alcohol !== null && `${numero(a.alcohol, 2)} % alc.`].filter(Boolean).join(" · ") : "Sin análisis";

function CamposAnalisis() {
  return <>
    <label>Azúcar (g/L)<input name="azucar_gl" type="number" step="0.1" min="0.1" max="999" required autoFocus /></label>
    <label>Absorbancia a 520 nm (opcional)<input name="absorbancia_520" type="number" step="0.001" min="0" max="99" /></label>
    <label>Alcohol % (opcional)<input name="alcohol" type="number" step="0.01" min="0" max="99" /></label>
    <label>Observaciones (opcional)<input name="observaciones" maxLength={300} /></label>
  </>;
}

type Permisos = { laboratorio: boolean; produccion: boolean; comercial: boolean; comprar: boolean; bascula: boolean };
function permisos(perfil: Perfil): Permisos {
  const todo = perfil === "SUPERADMIN";
  return {
    laboratorio: todo || perfil === "LABORATORIO", produccion: todo || perfil === "PRODUCCION", comercial: todo || perfil === "COMERCIAL",
    comprar: todo || perfil === "COMERCIAL" || perfil === "COMPRAS", bascula: todo || perfil === "BASCULA",
  };
}

function Demorados({ avisos }: { avisos: Aviso[] }) {
  const activos = avisos.filter(a => a.en_planta);
  if (!activos.length) return null;
  return <section className="aviso-error" role="alert">
    <strong>Mosto virgen sin descargar</strong>
    {activos.map(a => <span key={a.id}>{a.texto} <span className="ayuda">Aviso {fecha(a.creado_en)}: {a.envios.length ? a.envios.map(e => `${e.nombre} por ${e.canal === "correo" ? "mail" : "WhatsApp"} ${RESULTADOS[e.resultado] ?? e.resultado}`).join(" · ") : "no hay a quién avisar cargado en Parámetros"}.</span></span>)}
  </section>;
}

function VentanaViaje({ viaje, p, cerrar, cambio }: { viaje: Viaje; p: Permisos; cerrar: () => void; cambio: () => void }) {
  const [accion, setAccion] = useState<"analisis" | "descarga" | "recorrido" | null>(null);
  const ruta = `mosto/viajes/${viaje.id}`;
  const enviar = async (sufijo: string, cuerpo: unknown) => { await api(`${ruta}${sufijo}`, { method: "POST", body: JSON.stringify(cuerpo) }); setAccion(null); cambio(); };
  return <Ventana titulo={`${viaje.patente} · ${viaje.tipo_nombre}`} cerrar={cerrar}>
    {viaje.demorado && <p className="aviso-error"><strong>Lleva {numero(viaje.horas_en_planta, 1)} h sin descargarse.</strong></p>}
    <dl className="ficha">
      <div><dt>Compra</dt><dd>N.º {viaje.compra_numero} · {viaje.proveedor}</dd></div>
      <div><dt>Bodega</dt><dd>{viaje.bodega_nombre}</dd></div>
      <div><dt>Litros</dt><dd>{numero(viaje.litros)}</dd></div>
      <div><dt>Ingresó</dt><dd>{fecha(viaje.ingreso_en)} · {viaje.ingreso_por}</dd></div>
      <div><dt>Análisis</dt><dd>{resumenAnalisis(viaje.analisis)}{viaje.analisis && ` · ${viaje.analisis.actor}`}</dd></div>
      <div><dt>Descarga</dt><dd>{viaje.descarga ? `${viaje.descarga.lugar} · ${fecha(viaje.descarga.fecha)} · ${viaje.descarga.actor}` : "Todavía en el camión"}</dd></div>
    </dl>
    {viaje.recorrido.length > 0 && <><h3>Recorrido en planta</h3><ul className="lista-simple">{viaje.recorrido.map((r, i) => <li key={i}>{fecha(r.fecha)} → {r.lugar}{r.nota && ` (${r.nota})`} · {r.actor}</li>)}</ul></>}
    {!viaje.compra_cerrada && <div className="acciones">
      {p.laboratorio && <button onClick={() => setAccion("analisis")}>{viaje.analisis ? "Corregir análisis" : "Cargar análisis"}</button>}
      {p.produccion && !viaje.descarga && <button className="primario" onClick={() => setAccion("descarga")}>Registrar descarga</button>}
      {p.produccion && viaje.descarga && <button onClick={() => setAccion("recorrido")}>Registrar pase</button>}
    </div>}
    {accion === "analisis" && <Formulario titulo="Análisis del viaje" boton="Guardar" cerrar={() => setAccion(null)} enviar={f => enviar("/analisis", datosAnalisis(f))}><CamposAnalisis /></Formulario>}
    {accion === "descarga" && <Formulario titulo="Descarga" boton="Registrar" cerrar={() => setAccion(null)} enviar={f => enviar("/descarga", { lugar: f.get("lugar"), nota: f.get("nota") })}>
      <label>Dónde se descargó<input name="lugar" required maxLength={80} autoFocus placeholder="Pileta 4, tanque 2, concentrador…" /></label>
      <label>Nota (opcional)<input name="nota" maxLength={200} /></label>
    </Formulario>}
    {accion === "recorrido" && <Formulario titulo="Pase en planta" boton="Registrar" cerrar={() => setAccion(null)} enviar={f => enviar("/recorrido", { lugar: f.get("lugar"), nota: f.get("nota") })}>
      <label>A dónde pasa el mosto<input name="lugar" required maxLength={80} autoFocus placeholder="Concentrador" /></label>
      <label>Nota (opcional)<input name="nota" maxLength={200} /></label>
    </Formulario>}
  </Ventana>;
}

function Viajes({ p, compras, catalogo, avisos, cambio }: { p: Permisos; compras: Compra[]; catalogo: Catalogo; avisos: Aviso[]; cambio: () => void }) {
  const [viajes, setViajes] = useState<Viaje[] | null>(null); const [error, setError] = useState("");
  const [enPlanta, setEnPlanta] = useState(true); const [elegido, setElegido] = useState<string | null>(null); const [alta, setAlta] = useState(false);
  const leer = useCallback(() => api<Viaje[]>(`mosto/viajes?en_planta=${enPlanta}`).then(v => { setViajes(v); setError(""); }).catch(x => setError(mensaje(x, "No se pudieron leer los viajes."))), [enPlanta]);
  useEffect(() => { void leer(); }, [leer]);
  const recargar = () => { void leer(); cambio(); };
  const abiertas = compras.filter(c => c.estado === "APROBADA");
  const viaje = viajes?.find(v => v.id === elegido);
  return <section className="tarjeta">
    <Demorados avisos={avisos} />
    <div className="acciones">
      <label className="casilla"><input type="checkbox" checked={enPlanta} onChange={e => setEnPlanta(e.target.checked)} /> Sólo los que están en planta sin descargar</label>
      {p.bascula && <button className="primario" disabled={!abiertas.length} title={abiertas.length ? "" : "No hay compras aprobadas abiertas"} onClick={() => setAlta(true)}>Ingresar camión</button>}
    </div>
    {catalogo.horas_virgen === null && <p className="ayuda">Falta cargar en Parámetros las horas límite del mosto virgen: sin eso no hay alarma.</p>}
    {error && <ErrorVisible mensaje={error} />}
    {viajes && (viajes.length ? <Tabla etiqueta="Viajes de mosto" filas={viajes} alElegir={v => setElegido(v.id)} columnas={[
      { clave: "patente", titulo: "Patente", valor: v => v.demorado ? `⚠ ${v.patente}` : v.patente },
      { clave: "tipo_nombre", titulo: "Tipo" },
      { clave: "proveedor", titulo: "Proveedor", valor: v => `${v.proveedor} (N.º ${v.compra_numero})` },
      { clave: "bodega_nombre", titulo: "Bodega" },
      { clave: "litros", titulo: "Litros", valor: v => numero(v.litros) },
      { clave: "ingreso_en", titulo: "Ingresó", valor: v => fecha(v.ingreso_en) },
      { clave: "horas_en_planta", titulo: "Horas", valor: v => v.descarga ? "—" : numero(v.horas_en_planta, 1) },
      { clave: "analisis", titulo: "Azúcar", valor: v => v.analisis ? `${numero(v.analisis.azucar_gl, 1)} g/L` : "Sin análisis" },
      { clave: "descarga", titulo: "Descarga", valor: v => v.descarga ? v.descarga.lugar : "Sin descargar" },
    ]} /> : <Vacio>{enPlanta ? "No hay camiones de mosto en planta." : "Todavía no entró ningún camión de mosto."}</Vacio>)}
    {viaje && <VentanaViaje viaje={viaje} p={p} cerrar={() => setElegido(null)} cambio={recargar} />}
    {alta && <Formulario titulo="Ingresar camión de mosto" boton="Ingresar" cerrar={() => setAlta(false)} enviar={async f => {
      await api("mosto/viajes", { method: "POST", body: JSON.stringify({ compra_id: f.get("compra_id"), bodega: f.get("bodega"), patente: f.get("patente"), litros: Number(f.get("litros")) }) });
      setAlta(false); recargar();
    }}>
      <label>Compra<select name="compra_id" required defaultValue=""><option value="" disabled>Elegí la compra</option>{abiertas.map(c => <option key={c.id} value={c.id}>N.º {c.numero} · {c.proveedor} · {c.tipo_nombre}</option>)}</select></label>
      <label>Bodega<select name="bodega" required defaultValue=""><option value="" disabled>Elegí la bodega</option>{Object.entries(catalogo.bodegas).map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
      <label>Patente<input name="patente" required maxLength={12} autoCapitalize="characters" /></label>
      <label>Litros<input name="litros" type="number" min="1" step="1" required /></label>
    </Formulario>}
  </section>;
}

function VentanaCompra({ id, p, cerrar, cambio }: { id: string; p: Permisos; cerrar: () => void; cambio: () => void }) {
  const [ficha, setFicha] = useState<Ficha | null>(null); const [error, setError] = useState("");
  const [accion, setAccion] = useState<"analisis" | "calidad" | "produccion" | "comercial" | "pileta" | "margen" | "cerrar" | null>(null);
  const ruta = `mosto/compras/${id}`;
  const leer = useCallback(() => api<Ficha>(ruta).then(f => { setFicha(f); setError(""); }).catch(x => setError(mensaje(x, "No se pudo leer la compra."))), [ruta]);
  useEffect(() => { void leer(); }, [leer]);
  const enviar = async (sufijo: string, cuerpo: unknown = {}) => { setFicha(await api<Ficha>(`${ruta}${sufijo}`, { method: "POST", body: JSON.stringify(cuerpo) })); setAccion(null); cambio(); };
  const decision = (etapa: "calidad" | "produccion" | "comercial", motivoObligatorio: boolean) => <Formulario titulo={`Decisión de ${ETAPAS[etapa]}`} boton="Guardar" cerrar={() => setAccion(null)} enviar={f => enviar(`/${etapa}`, { aprueba: f.get("aprueba") === "si", motivo: f.get("motivo") })}>
    <label>Decisión<select name="aprueba" required defaultValue=""><option value="" disabled>Elegí</option><option value="si">Aprobar</option><option value="no">Rechazar</option></select></label>
    <label>Motivo{motivoObligatorio ? "" : " (obligatorio si rechaza)"}<input name="motivo" maxLength={300} required={motivoObligatorio} /></label>
  </Formulario>;
  const l = ficha?.liquidacion;
  return <Ventana titulo={ficha ? `Compra N.º ${ficha.numero} · ${ficha.proveedor}` : "Compra"} tamano="amplia" cerrar={cerrar}>
    {error && <ErrorVisible mensaje={error} />}
    {ficha && <>
      <div className="cabecera-ficha"><span className="estado">{ficha.estado_nombre}</span><span className="ayuda">{ficha.tipo_nombre} · CUIT {ficha.cuit}</span></div>
      <dl className="ficha">
        <div><dt>Litros contratados</dt><dd>{numero(ficha.litros)} · recibidos {numero(ficha.litros_recibidos)} en {ficha.viajes} viajes</dd></div>
        <div><dt>Precio base por litro</dt><dd>{pesos(ficha.precio_base)}</dd></div>
        <div><dt>Muestra de la oferta</dt><dd>{resumenAnalisis(ficha.analisis)}{ficha.analisis?.observaciones && ` · ${ficha.analisis.observaciones}`}</dd></div>
        <div><dt>Margen de azúcar</dt><dd>{ficha.sin_margen ? `Sin margen (excepción comercial: ${ficha.sin_margen_motivo})` : "Se descuenta el margen de Parámetros"}{ficha.sin_margen_por && ` · ${ficha.sin_margen_por}, ${fecha(ficha.sin_margen_en)}`}</dd></div>
        <div><dt>Cargada</dt><dd>{ficha.creada_por} · {fecha(ficha.creada_en)}</dd></div>
      </dl>
      {ficha.decisiones.length > 0 && <><h3>Decisiones</h3><ul className="lista-simple">{ficha.decisiones.map((d, i) => <li key={i}>{fecha(d.fecha)} · {ETAPAS[d.etapa]}: {d.aprueba ? "aprobó" : "rechazó"}{d.motivo && ` (${d.motivo})`} · {d.actor}</li>)}</ul></>}
      {ficha.piletas.length > 0 && <><h3>Muestras por pileta</h3><ul className="lista-simple">{ficha.piletas.map(m => <li key={m.id}>{m.pileta} · {numero(m.litros)} L · {resumenAnalisis(m.analisis)}</li>)}</ul></>}
      {l && <><h3>{ficha.liquidacion_final ? "Liquidación al cierre" : "Liquidación estimada"}</h3><dl className="ficha">
        <div><dt>Azúcar promedio de los viajes</dt><dd>{numero(l.azucar_promedio, 2)} g/L (ponderado por litros)</dd></div>
        <div><dt>Azúcar que se liquida</dt><dd>{numero(l.azucar_liquidada, 2)} g/L{l.margen_gl ? ` (menos ${numero(l.margen_gl, 2)} g/L de margen)` : ""}</dd></div>
        <div><dt>Precio por litro sugerido</dt><dd>{pesos(l.precio_litro)} = {pesos(l.precio_base)} × {numero(l.azucar_liquidada, 2)} / {numero(l.azucar_referencia)}</dd></div>
        <div><dt>Total sugerido</dt><dd>{pesos(l.total)} por {numero(l.litros)} L</dd></div>
      </dl>{!ficha.liquidacion_final && <p className="ayuda">Se calcula con los viajes que ya tienen análisis. El precio final queda fijo al cerrar la compra.</p>}</>}
      {ficha.detalle_viajes.length > 0 && <><h3>Viajes</h3><ul className="lista-simple">{ficha.detalle_viajes.map(v => <li key={v.id}>{fecha(v.ingreso_en)} · {v.patente} · {numero(v.litros)} L · {v.analisis ? `${numero(v.analisis.azucar_gl, 1)} g/L` : "sin análisis"} · {v.descarga ? `descargado en ${v.descarga.lugar}` : "sin descargar"}</li>)}</ul></>}
      <div className="acciones">
        {p.laboratorio && ficha.estado === "EN_ANALISIS" && <button onClick={() => setAccion("analisis")}>{ficha.analisis ? "Corregir análisis" : "Cargar análisis"}</button>}
        {p.laboratorio && ficha.estado === "EN_ANALISIS" && ficha.analisis && <button className="primario" onClick={() => setAccion("calidad")}>Decisión de Calidad</button>}
        {p.produccion && ficha.estado === "RECHAZADA_CALIDAD" && <button className="primario" onClick={() => setAccion("produccion")}>Decisión del Jefe de Producción</button>}
        {p.comercial && (ficha.estado === "RECHAZADA_CALIDAD" || ficha.estado === "RECHAZADA") && <button onClick={() => setAccion("comercial")}>Decisión comercial por escasez</button>}
        {p.laboratorio && ficha.estado === "APROBADA" && <button onClick={() => setAccion("pileta")}>Agregar muestra de pileta</button>}
        {p.comercial && ficha.estado === "APROBADA" && <button onClick={() => setAccion("margen")}>{ficha.sin_margen ? "Volver a aplicar el margen" : "Excepción: sin margen"}</button>}
        {p.comercial && ficha.estado === "APROBADA" && <button className="primario" onClick={() => setAccion("cerrar")}>Cerrar compra y liquidar</button>}
      </div>
      {accion === "analisis" && <Formulario titulo="Análisis de la muestra de la oferta" boton="Guardar" cerrar={() => setAccion(null)} enviar={f => enviar("/analisis", datosAnalisis(f))}><CamposAnalisis /></Formulario>}
      {accion === "calidad" && decision("calidad", false)}
      {accion === "produccion" && decision("produccion", true)}
      {accion === "comercial" && decision("comercial", true)}
      {accion === "pileta" && <Formulario titulo="Muestra de pileta" boton="Guardar" cerrar={() => setAccion(null)} enviar={f => enviar("/piletas", { pileta: f.get("pileta"), litros: Number(f.get("litros")), ...datosAnalisis(f) })}>
        <label>Pileta<input name="pileta" required maxLength={40} /></label>
        <label>Litros de la pileta<input name="litros" type="number" min="1" step="1" required /></label>
        <CamposAnalisis />
      </Formulario>}
      {accion === "margen" && <Formulario titulo={ficha.sin_margen ? "Volver a aplicar el margen" : "Liquidar sin margen"} boton="Guardar" cerrar={() => setAccion(null)} enviar={f => enviar("/margen", { sin_margen: !ficha.sin_margen, motivo: f.get("motivo") ?? "" })}>
        {ficha.sin_margen ? <p className="ayuda">Se vuelve a descontar el margen de azúcar de Parámetros.</p> : <label>Motivo de la excepción<input name="motivo" required maxLength={300} autoFocus /></label>}
      </Formulario>}
      {accion === "cerrar" && <Formulario titulo="Cerrar compra" boton="Cerrar y liquidar" cerrar={() => setAccion(null)} enviar={() => enviar("/cerrar")}>
        <p className="ayuda">Se promedia el azúcar de todos los viajes y queda fijo el precio sugerido. Después no entran más viajes ni se cambian análisis.</p>
      </Formulario>}
    </>}
  </Ventana>;
}

function Compras({ p, compras, cambio }: { p: Permisos; compras: Compra[]; cambio: () => void }) {
  const [elegida, setElegida] = useState<string | null>(null); const [alta, setAlta] = useState(false);
  return <section className="tarjeta">
    {p.comprar && <div className="acciones"><button className="primario" onClick={() => setAlta(true)}>Cargar compra</button></div>}
    {compras.length ? <Tabla etiqueta="Compras de mosto" filas={compras} alElegir={c => setElegida(c.id)} columnas={[
      { clave: "numero", titulo: "N.º" },
      { clave: "proveedor", titulo: "Proveedor" },
      { clave: "tipo_nombre", titulo: "Tipo" },
      { clave: "estado_nombre", titulo: "Estado" },
      { clave: "litros", titulo: "Litros", valor: c => `${numero(c.litros_recibidos)} de ${numero(c.litros)}` },
      { clave: "precio_base", titulo: "Precio base", valor: c => pesos(c.precio_base) },
      { clave: "liquidacion", titulo: "Precio sugerido", valor: c => c.liquidacion ? pesos(c.liquidacion.precio_litro) : "—" },
    ]} /> : <Vacio>Todavía no hay compras de mosto cargadas.</Vacio>}
    {elegida && <VentanaCompra id={elegida} p={p} cerrar={() => setElegida(null)} cambio={cambio} />}
    {alta && <Formulario titulo="Cargar compra de mosto" boton="Cargar" cerrar={() => setAlta(false)} enviar={async f => {
      await api("mosto/compras", { method: "POST", body: JSON.stringify({ proveedor: f.get("proveedor"), cuit: String(f.get("cuit")).replace(/\D/g, ""), tipo: f.get("tipo"), litros: Number(f.get("litros")), precio_base: Number(f.get("precio_base")) }) });
      setAlta(false); cambio();
    }}>
      <label>Proveedor<input name="proveedor" required maxLength={120} autoFocus /></label>
      <label>CUIT<input name="cuit" required inputMode="numeric" maxLength={13} /></label>
      <label>Tipo<select name="tipo" required defaultValue=""><option value="" disabled>Elegí</option><option value="sulfitado">Mosto sulfitado</option><option value="virgen">Mosto virgen</option></select></label>
      <label>Litros<input name="litros" type="number" min="1" step="1" required /></label>
      <label>Precio base por litro ($)<input name="precio_base" type="number" min="0.0001" step="0.0001" required /></label>
      <p className="ayuda">El laboratorio carga después el análisis de la muestra y Calidad decide.</p>
    </Formulario>}
  </section>;
}

export function MostoGestion({ perfil }: { perfil: Perfil }) {
  const p = permisos(perfil);
  const [pestana, setPestana] = useState<"viajes" | "compras">("viajes");
  const [compras, setCompras] = useState<Compra[]>([]); const [catalogo, setCatalogo] = useState<Catalogo | null>(null);
  const [avisos, setAvisos] = useState<Aviso[]>([]); const [error, setError] = useState("");
  const leer = useCallback(() => Promise.all([api<Compra[]>("mosto/compras"), api<Catalogo>("mosto/catalogo"), api<Aviso[]>("mosto/avisos")])
    .then(([c, k, a]) => { setCompras(c); setCatalogo(k); setAvisos(a); setError(""); })
    .catch(x => setError(mensaje(x, "No se pudieron leer los datos del mosto."))), []);
  useEffect(() => { void leer(); const t = setInterval(() => void leer(), 60000); return () => clearInterval(t); }, [leer]);
  return <>
    <Pestanas opciones={[["viajes", "Viajes"], ["compras", "Compras"]] as const} activa={pestana} cambiar={setPestana} />
    {error && <ErrorVisible mensaje={error} />}
    {catalogo && pestana === "viajes" && <Viajes p={p} compras={compras} catalogo={catalogo} avisos={avisos} cambio={leer} />}
    {pestana === "compras" && <Compras p={p} compras={compras} cambio={leer} />}
  </>;
}

type Destinatario = { nombre: string; correo: string; telefono: string };
type ParametrosMosto = { azucar_referencia: number; margen_gl: number; horas_virgen: number | null; destinatarios: Destinatario[]; actualizado_por: string; actualizado_en: string | null };

/** Tarjeta de Parámetros: referencia de azúcar, margen, horas límite y a quién avisar. */
export function ParametrosMosto() {
  const [datos, setDatos] = useState<ParametrosMosto | null>(null); const [destinatarios, setDestinatarios] = useState<Destinatario[]>([]);
  const [error, setError] = useState(""); const [aviso, setAviso] = useState(""); const [ocupado, setOcupado] = useState(false);
  useEffect(() => { api<ParametrosMosto>("mosto/parametros").then(d => { setDatos(d); setDestinatarios(d.destinatarios); }).catch(x => setError(mensaje(x, "No se pudieron leer los parámetros del mosto."))); }, []);
  async function guardar(f: FormData) {
    setOcupado(true); setError(""); setAviso("");
    try {
      const d = await api<ParametrosMosto>("mosto/parametros", { method: "PUT", body: JSON.stringify({
        azucar_referencia: Number(f.get("azucar_referencia")), margen_gl: Number(f.get("margen_gl")), horas_virgen: opcional(f.get("horas_virgen")),
        destinatarios: destinatarios.filter(x => x.nombre || x.correo || x.telefono),
      }) });
      setDatos(d); setDestinatarios(d.destinatarios); setAviso("Guardado.");
    } catch (x) { setError(mensaje(x, "No se pudo guardar.")); }
    setOcupado(false);
  }
  const cambiar = (i: number, cambio: Partial<Destinatario>) => setDestinatarios(ds => ds.map((d, j) => j === i ? { ...d, ...cambio } : d));
  return <section className="tarjeta">
    <h2>Mosto</h2>
    {error && <ErrorVisible mensaje={error} />}
    {datos && <form onSubmit={e => { e.preventDefault(); void guardar(new FormData(e.currentTarget)); }}>
      <div className="campos-organica">
        <label>Azúcar de referencia del precio base (g/L)<input name="azucar_referencia" type="number" step="0.1" min="1" max="999" required defaultValue={datos.azucar_referencia} /></label>
        <label>Margen de resguardo (g/L)<input name="margen_gl" type="number" step="0.1" min="0" max="49" required defaultValue={datos.margen_gl} /></label>
        <label>Horas límite del mosto virgen sin descargar<input name="horas_virgen" type="number" step="0.5" min="0.5" max="240" defaultValue={datos.horas_virgen ?? ""} placeholder="Sin cargar: no hay alarma" /></label>
      </div>
      <fieldset className="franjas"><legend>A quién avisar si un camión de mosto virgen se demora</legend>
        {destinatarios.length === 0 && <p className="ayuda">Nadie cargado: el aviso se ve sólo en Gestión.</p>}
        <p className="ayuda">El WhatsApp sólo sale a celulares activos en «Personal en el bot».</p>
        {destinatarios.map((d, i) => <div key={i} className="destinatario-mosto">
          <input aria-label="Nombre" placeholder="Nombre" maxLength={80} value={d.nombre} onChange={e => cambiar(i, { nombre: e.target.value })} />
          <input aria-label="Mail" type="email" placeholder="Mail" maxLength={120} value={d.correo} onChange={e => cambiar(i, { correo: e.target.value })} />
          <input aria-label="Celular" inputMode="numeric" placeholder="Celular, ej. 5492645550000" maxLength={20} value={d.telefono} onChange={e => cambiar(i, { telefono: e.target.value.replace(/\D/g, "") })} />
          <button type="button" aria-label="Quitar" title="Quitar" onClick={() => setDestinatarios(ds => ds.filter((_, j) => j !== i))}>✕</button>
        </div>)}
        <button type="button" onClick={() => setDestinatarios(ds => [...ds, { nombre: "", correo: "", telefono: "" }])}>Agregar persona</button>
      </fieldset>
      <div className="acciones"><button className="primario" disabled={ocupado}>Guardar</button>{aviso && <span className="ayuda">{aviso}</span>}</div>
      {datos.actualizado_por && <p className="ayuda">Último cambio: {datos.actualizado_por}, {fecha(datos.actualizado_en)}.</p>}
    </form>}
  </section>;
}
