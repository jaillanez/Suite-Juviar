"use client";

import { useCallback, useEffect, useState } from "react";
import { abrirArchivo, api, descargarArchivo } from "@/lib/api";
import { hoyLocal } from "@/lib/fechas";
import { ErrorVisible, FormularioVentana as Formulario, Tabla, Vacio, Ventana } from "./compartidos";

type EstadoControl = "ok" | "alerta" | "pendiente" | "no_aplica" | "sin_configurar" | "error" | "sin_correr";
type ControlVista = { numero: number; nombre: string; estado: EstadoControl; estado_nombre: string; detalle: string; fuente: string; fecha: string | null; actor: string; nota: string; archivo: string; puede_subir: boolean };
type Factura = Record<string, unknown> & {
  id: string; empresa: string; cuit_emisor: string; razon_social: string; tipo_nombre: string; comprobante: string; fecha: string;
  importe_total: number; moneda: string; cotizacion: number; importe_pesos: number; importe_texto: string; autorizacion: string; autorizacion_nombre: string; codigo_autorizacion: string; cargada_por: string; cargada_en: string;
  alerta: boolean; controlada: boolean; tiene_foto: boolean; controles: ControlVista[];
};
type Padron = { nombre: string; titulo: string; descargado_en: string | null; generado: string; cuits: number };
type Catalogo = {
  empresas: string[]; tipos_comprobante: Record<string, string>; autorizaciones: Record<string, string>; monedas: Record<string, string>;
  controles: { numero: number; nombre: string; descripcion: string; activo: boolean }[];
  enlaces_impositivo: string[]; ambiente_nombre: string; faltantes: string[]; padrones: Padron[];
};

const fecha = (v: string | null) => v ? new Date(v).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }) : "—";
const dia = (v: string) => v.split("-").reverse().join("/");
const pesos = (v: number) => v.toLocaleString("es-AR", { style: "currency", currency: "ARS" });
// En moneda extranjera el servidor arma «USD 297,36 (≈ $ 453.325,32 a 1.524,50)»; en pesos, como siempre.
const importe = (f: Factura) => f.moneda && f.moneda !== "PES" && f.importe_texto ? f.importe_texto : pesos(f.importe_total);
const mensaje = (x: unknown, defecto: string) => x instanceof Error ? x.message : defecto;
const SIMBOLO: Record<EstadoControl, string> = { ok: "✓", alerta: "!", pendiente: "…", no_aplica: "–", sin_configurar: "?", error: "×", sin_correr: "·" };

async function aBase64(archivo: File): Promise<string> {
  const bytes = new Uint8Array(await archivo.arrayBuffer());
  let texto = "";
  for (let i = 0; i < bytes.length; i += 0x8000) texto += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(texto);
}

function Chip({ c }: { c: ControlVista }) {
  return <span className={`estado estado-arca estado-arca-${c.estado}`} title={`${c.numero}. ${c.nombre}: ${c.estado_nombre}`}>{c.numero} {SIMBOLO[c.estado]}</span>;
}

function SubirConstancia({ factura, control, enlaces, cerrar, listo }: { factura: Factura; control: ControlVista; enlaces: string[]; cerrar: () => void; listo: (f: Factura) => void }) {
  return <Formulario titulo={`Subir PDF · ${control.nombre}`} boton="Subir" cerrar={cerrar} enviar={async f => {
    const archivo = f.get("archivo");
    if (!(archivo instanceof File) || !archivo.size) throw new Error("Elegí el PDF que bajaste de ARCA.");
    if (archivo.size > 10 * 1024 * 1024) throw new Error("El PDF es muy grande: el máximo es 10 MB.");
    listo(await api<Factura>(`controles-arca/facturas/${factura.id}/controles/${control.numero}/constancia`, { method: "POST", body: JSON.stringify({
      contenido_base64: await aBase64(archivo), resultado: f.get("resultado"), nota: f.get("nota") ?? "",
    }) }));
  }}>
    {control.numero === 1 && <div className="ayuda">Entrá con la clave fiscal y bajá en PDF Reproweb, agente de retención y la consulta puntual del CUIT {factura.cuit_emisor}:
      <ul className="lista-simple">{enlaces.map(e => <li key={e}><a href={e} target="_blank" rel="noreferrer noopener">{e}</a></li>)}</ul></div>}
    <label>PDF de ARCA<input name="archivo" type="file" accept="application/pdf,.pdf" required autoFocus /></label>
    <label>¿Cómo dio?<select name="resultado" defaultValue="ok"><option value="ok">Bien</option><option value="alerta">Con alerta</option></select></label>
    <label>Qué encontraste (obligatorio si dio con alerta)<input name="nota" maxLength={300} /></label>
    <p className="ayuda">El sistema le pone el nombre solo: CUIT_{control.numero}_{control.numero === 4 ? "NºFACTURA_" : ""}fecha.</p>
  </Formulario>;
}

function VentanaFactura({ inicial, catalogo, cerrar, cambio }: { inicial: Factura; catalogo: Catalogo; cerrar: () => void; cambio: () => void }) {
  const [factura, setFactura] = useState(inicial); const [error, setError] = useState(""); const [ocupado, setOcupado] = useState(false);
  const [subiendo, setSubiendo] = useState<ControlVista | null>(null);
  const actualizar = (f: Factura) => { setFactura(f); cambio(); };
  async function correr() {
    setOcupado(true); setError("");
    try { actualizar(await api<Factura>(`controles-arca/facturas/${factura.id}/controles`, { method: "POST" })); }
    catch (x) { setError(mensaje(x, "No se pudieron correr los controles.")); }
    setOcupado(false);
  }
  async function bajar(c: ControlVista) {
    try { await descargarArchivo(`controles-arca/facturas/${factura.id}/controles/${c.numero}/pdf`, c.archivo); }
    catch (x) { setError(mensaje(x, "No se pudo bajar el PDF.")); }
  }
  return <Ventana titulo={`${factura.comprobante} · ${factura.razon_social || factura.cuit_emisor}`} tamano="amplia" cerrar={cerrar}>
    {factura.alerta && <p className="aviso-error" role="alert"><strong>Alerta: algún control dio mal. Revisalo antes de pagar.</strong></p>}
    {error && <ErrorVisible mensaje={error} />}
    <dl className="ficha">
      <div><dt>Se le facturó a</dt><dd>{factura.empresa}</dd></div>
      <div><dt>Proveedor</dt><dd>{factura.razon_social || "Sin razón social"} · CUIT {factura.cuit_emisor}</dd></div>
      <div><dt>Fecha</dt><dd>{dia(factura.fecha)}</dd></div>
      <div><dt>Importe total</dt><dd>{importe(factura)}</dd></div>
      <div><dt>Autorización</dt><dd>{factura.autorizacion_nombre}{factura.codigo_autorizacion && ` ${factura.codigo_autorizacion}`}</dd></div>
      <div><dt>Cargada</dt><dd>{factura.cargada_por} · {fecha(factura.cargada_en)}</dd></div>
    </dl>
    <div className="acciones">{factura.tiene_foto && <button onClick={() => abrirArchivo(`controles-arca/facturas/${factura.id}/foto`).catch(x => setError(mensaje(x, "No se pudo abrir la foto.")))}>Ver foto de la factura</button>}<button className="primario" disabled={ocupado} onClick={correr}>{ocupado ? "Consultando ARCA…" : factura.controlada ? "Volver a correr los controles" : "Correr controles"}</button></div>
    <ul className="controles-arca">{factura.controles.map(c => <li key={c.numero} className={`control-arca control-arca-${c.estado}`}>
      <div className="titulo-fila"><h3>{c.numero}. {c.nombre}</h3><span className={`estado estado-arca estado-arca-${c.estado}`}>{c.estado_nombre}</span></div>
      {c.detalle && <p>{c.detalle}</p>}
      {c.estado === "pendiente" && c.numero === 1 && <p className="ayuda">Se hace en ARCA con clave fiscal: {catalogo.enlaces_impositivo.map((e, i) => <span key={e}>{i > 0 && " · "}<a href={e} target="_blank" rel="noreferrer noopener">{new URL(e).hostname}</a></span>)}</p>}
      {c.fecha && <p className="ayuda">{fecha(c.fecha)} · {c.actor}{c.fuente && ` · ${c.fuente}`}</p>}
      {(c.archivo || c.puede_subir) && <div className="acciones">
        {c.archivo && <button onClick={() => bajar(c)}>Bajar {c.archivo}</button>}
        {c.puede_subir && <button onClick={() => setSubiendo(c)}>{c.archivo ? "Reemplazar PDF" : "Subir PDF de ARCA"}</button>}
      </div>}
    </li>)}</ul>
    {subiendo && <SubirConstancia factura={factura} control={subiendo} enlaces={catalogo.enlaces_impositivo} cerrar={() => setSubiendo(null)} listo={f => { setSubiendo(null); actualizar(f); }} />}
  </Ventana>;
}

function Padrones({ padrones, cambio }: { padrones: Padron[]; cambio: () => void }) {
  const [ocupado, setOcupado] = useState(""); const [error, setError] = useState("");
  async function actualizar(nombre: string) {
    setOcupado(nombre); setError("");
    try { await api(`controles-arca/padrones/${nombre}/actualizar`, { method: "POST" }); cambio(); }
    catch (x) { setError(mensaje(x, "No se pudo bajar el listado.")); }
    setOcupado("");
  }
  return <div className="padrones-arca">
    {error && <ErrorVisible mensaje={error} />}
    {padrones.map(p => <div key={p.nombre}><span><strong>{p.titulo}</strong>: {p.descargado_en ? `bajado ${fecha(p.descargado_en)} (${p.cuits.toLocaleString("es-AR")} CUIT${p.generado ? `, ARCA lo generó el ${p.generado}` : ""})` : "todavía no se bajó"}</span>
      <button disabled={Boolean(ocupado)} onClick={() => actualizar(p.nombre)}>{ocupado === p.nombre ? "Bajando…" : "Actualizar ahora"}</button></div>)}
    <p className="ayuda">Se bajan solos una vez por día.</p>
  </div>;
}

export function ControlesArcaGestion() {
  const [catalogo, setCatalogo] = useState<Catalogo | null>(null); const [facturas, setFacturas] = useState<Factura[] | null>(null);
  const [error, setError] = useState(""); const [soloAlertas, setSoloAlertas] = useState(false);
  const [elegida, setElegida] = useState<Factura | null>(null); const [alta, setAlta] = useState(false);
  const [autorizacion, setAutorizacion] = useState("CAE"); const [moneda, setMoneda] = useState("PES");
  const leer = useCallback(() => Promise.all([api<Catalogo>("controles-arca/catalogo"), api<Factura[]>(`controles-arca/facturas?solo_alertas=${soloAlertas}`)])
    .then(([c, f]) => { setCatalogo(c); setFacturas(f); setError(""); })
    .catch(x => setError(mensaje(x, "No se pudieron leer las facturas."))), [soloAlertas]);
  useEffect(() => { void leer(); }, [leer]);
  return <>
    {error && <ErrorVisible mensaje={error} />}
    {catalogo && <section className="tarjeta">
      {catalogo.faltantes.length > 0 && <div className="aviso-pendiente"><strong>Para los controles automáticos falta:</strong><ul className="lista-simple">{catalogo.faltantes.map(f => <li key={f}>{f}</li>)}</ul></div>}
      <p className="ayuda">Ambiente de ARCA: {catalogo.ambiente_nombre}. Controles activos: {catalogo.controles.filter(c => c.activo).map(c => c.numero).join(", ") || "ninguno"}.</p>
      <Padrones padrones={catalogo.padrones} cambio={leer} />
    </section>}
    <section className="tarjeta">
      <div className="acciones">
        <label className="casilla"><input type="checkbox" checked={soloAlertas} onChange={e => setSoloAlertas(e.target.checked)} /> Sólo las que tienen alerta</label>
        <button className="primario" disabled={!catalogo} onClick={() => { setAutorizacion("CAE"); setMoneda("PES"); setAlta(true); }}>Cargar factura</button>
      </div>
      {facturas && (facturas.length ? <Tabla etiqueta="Facturas de proveedores" filas={facturas} alElegir={setElegida} claseFila={f => f.alerta ? "fila-alerta" : ""} columnas={[
        { clave: "alerta", titulo: "Estado", valor: f => f.alerta ? <span className="estado estado-arca estado-arca-alerta">Alerta</span> : f.controlada ? (f.controles.some(c => ["pendiente", "error", "sin_configurar"].includes(c.estado)) ? "Faltan controles" : "Controlada") : "Sin controlar" },
        { clave: "empresa", titulo: "Empresa" },
        { clave: "razon_social", titulo: "Proveedor", valor: f => <>{f.razon_social || "—"}<br /><small>{f.cuit_emisor}</small></> },
        { clave: "comprobante", titulo: "Comprobante" },
        { clave: "fecha", titulo: "Fecha", valor: f => dia(f.fecha) },
        { clave: "importe_total", titulo: "Importe", valor: f => importe(f) },
        { clave: "controles", titulo: "Controles", valor: f => <span className="chips-arca">{f.controles.map(c => <Chip key={c.numero} c={c} />)}</span> },
      ]} /> : <Vacio>{soloAlertas ? "No hay facturas con alerta." : "Todavía no se cargó ninguna factura."}</Vacio>)}
      <p className="ayuda">1 control impositivo · 2 inscripción · 3 apócrifas · 4 CAE/CAI/CAEA · 5 agentes de retención. ✓ bien · ! alerta · … pendiente · – no corresponde · ? falta configurar · × no se pudo consultar.</p>
    </section>
    {elegida && catalogo && <VentanaFactura key={elegida.id} inicial={elegida} catalogo={catalogo} cerrar={() => setElegida(null)} cambio={() => void leer()} />}
    {alta && catalogo && <Formulario titulo="Cargar factura de proveedor" boton="Cargar" tamano="ancha" cerrar={() => setAlta(false)} enviar={async f => {
      const nueva = await api<Factura>("controles-arca/facturas", { method: "POST", body: JSON.stringify({
        empresa: f.get("empresa"), cuit_emisor: String(f.get("cuit_emisor") ?? "").replace(/\D/g, ""), razon_social: f.get("razon_social") ?? "",
        tipo_comprobante: Number(f.get("tipo_comprobante")), punto_venta: Number(f.get("punto_venta")), numero: Number(f.get("numero")),
        fecha: f.get("fecha"), importe_total: Number(f.get("importe_total")), autorizacion: f.get("autorizacion"),
        moneda, cotizacion: moneda === "PES" ? 1 : Number(f.get("cotizacion")),
        codigo_autorizacion: autorizacion === "CF" ? "" : String(f.get("codigo_autorizacion") ?? "").replace(/\D/g, ""),
      }) });
      setAlta(false); void leer(); setElegida(nueva);
    }}>
      <div className="form-grid">
        <label>Se le facturó a<select name="empresa" required defaultValue=""><option value="" disabled>Elegí la empresa</option>{catalogo.empresas.map(e => <option key={e}>{e}</option>)}</select></label>
        <label>CUIT del proveedor<input name="cuit_emisor" required inputMode="numeric" maxLength={13} placeholder="30693135679" autoFocus /></label>
        <label>Razón social (opcional)<input name="razon_social" maxLength={120} /></label>
        <label>Tipo de comprobante<select name="tipo_comprobante" required defaultValue="1">{Object.entries(catalogo.tipos_comprobante).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Punto de venta<input name="punto_venta" type="number" min="1" max="99999" step="1" required /></label>
        <label>Número<input name="numero" type="number" min="1" max="99999999" step="1" required /></label>
        <label>Fecha<input name="fecha" type="date" required defaultValue={hoyLocal()} max={hoyLocal()} /></label>
        <label>Moneda<select name="moneda" value={moneda} onChange={e => setMoneda(e.target.value)}>{Object.entries(catalogo.monedas ?? { PES: "Pesos argentinos" }).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Importe total {moneda === "PES" ? "($)" : "(en esa moneda)"}<input name="importe_total" type="number" min="0.01" step="0.01" required /></label>
        {moneda !== "PES" && <label>Cotización (pesos por unidad)<input name="cotizacion" type="number" min="0.000001" step="any" required /></label>}
        <label>Autorización<select name="autorizacion" value={autorizacion} onChange={e => setAutorizacion(e.target.value)}>{Object.entries(catalogo.autorizaciones).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        {autorizacion !== "CF" && <label>Código {autorizacion} (14 números)<input name="codigo_autorizacion" required inputMode="numeric" pattern="\d{14}" maxLength={14} /></label>}
      </div>
    </Formulario>}
  </>;
}

type Parametros = {
  controles_activos: number[]; excluir_controlador_fiscal: boolean; ambiente: "homologacion" | "produccion"; cuit_representante: string;
  cuit_empresas: Record<string, string>; url_apocrifas: string; url_rg18: string; enlaces_impositivo: string[]; actualizado_por: string; actualizado_en: string | null;
};
type EstadoCertificado = {
  ambiente: string; ambiente_nombre: string; cuit: string; servidor_listo: boolean;
  activo: { cuit: string; alias: string; sujeto: string; vence: string | null; vencido: boolean; cargado_por: string; cargado_en: string | null } | null;
  pedido: { cuit: string; alias: string; pedido_por: string; pedido_en: string } | null;
};
const CONTROLES = ["Control impositivo (a mano, con clave fiscal)", "Constancia de inscripción", "Facturas apócrifas", "Autorización de la factura (CAE/CAI/CAEA)", "Agentes de retención (RG 18)"];

function bajarTexto(texto: string, nombre: string) {
  const url = URL.createObjectURL(new Blob([texto], { type: "application/pkcs10" }));
  const enlace = document.createElement("a"); enlace.href = url; enlace.download = nombre; enlace.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function Certificado({ estado, cambio }: { estado: EstadoCertificado; cambio: (e: EstadoCertificado) => void }) {
  const [error, setError] = useState(""); const [aviso, setAviso] = useState(""); const [ocupado, setOcupado] = useState(false);
  async function hacer(accion: () => Promise<string>) {
    setOcupado(true); setError(""); setAviso("");
    try { setAviso(await accion()); } catch (x) { setError(mensaje(x, "No se pudo completar.")); }
    setOcupado(false);
  }
  const generar = () => hacer(async () => {
    if ((estado.activo || estado.pedido) && !window.confirm("Ya hay un certificado o un pedido. ¿Generar un pedido nuevo? El certificado cargado sigue andando hasta que subas el nuevo.")) return "";
    const r = await api<{ nombre: string; csr_pem: string; estado: EstadoCertificado }>("controles-arca/certificado/pedido", { method: "POST" });
    bajarTexto(r.csr_pem, r.nombre); cambio(r.estado);
    return `Se bajó ${r.nombre}. Subilo en ARCA y después cargá acá el certificado que te da ARCA.`;
  });
  const subir = (archivo: File | undefined) => archivo && hacer(async () => {
    if (archivo.size > 20000) throw new Error("Ese archivo no parece un certificado: subí el .crt que te dio ARCA.");
    cambio(await api<EstadoCertificado>("controles-arca/certificado", { method: "PUT", body: JSON.stringify({ certificado_pem: await archivo.text() }) }));
    return "Certificado cargado.";
  });
  return <fieldset className="franjas"><legend>Certificado de ARCA · {estado.ambiente_nombre}</legend>
    {error && <ErrorVisible mensaje={error} />}
    {aviso && <p className="aviso-exito">{aviso}</p>}
    {!estado.servidor_listo && <p className="aviso-error">Falta configurar SJ_CLAVE_PARAMETROS en el servidor: sin eso no se puede guardar el certificado.</p>}
    <p>{estado.activo ? <>Cargado: CUIT {estado.activo.cuit}, vence el {fecha(estado.activo.vence)}{estado.activo.vencido && <strong> (vencido)</strong>}. Lo cargó {estado.activo.cargado_por}, {fecha(estado.activo.cargado_en)}.</> : "Todavía no hay certificado cargado: los controles 2 y 4 quedan sin configurar."}</p>
    {estado.pedido && <p className="ayuda">Pedido generado por {estado.pedido.pedido_por} el {fecha(estado.pedido.pedido_en)}, esperando el certificado de ARCA.</p>}
    <ol className="lista-simple">
      <li>Tocá «Generar pedido de certificado». Se baja un archivo .csr; la clave privada queda guardada en el servidor y no sale nunca.</li>
      <li>En ARCA, con la clave fiscal de {estado.cuit}, entrá a «Administración de Certificados Digitales»{estado.ambiente === "homologacion" ? " (en homologación: «WSASS»)" : ""}, creá el alias y subí el .csr.</li>
      <li>Bajá el certificado (.crt) que te da ARCA y subilo acá.</li>
      <li>En el «Administrador de Relaciones» asociá ese certificado a ws_sr_constancia_inscripcion y a wscdc. Las consultas salen con el CUIT {estado.cuit}: no hace falta que las empresas deleguen nada.</li>
    </ol>
    <div className="acciones">
      <button className="primario" disabled={ocupado || !estado.servidor_listo} onClick={generar}>Generar pedido de certificado</button>
      {estado.pedido && <button disabled={ocupado} onClick={() => hacer(async () => { await descargarArchivo("controles-arca/certificado/pedido", `pedido_${estado.pedido!.alias}_${estado.pedido!.cuit}.csr`); return ""; })}>Bajar el pedido de nuevo</button>}
      <label className="carga" aria-disabled={ocupado || !estado.servidor_listo}>Subir certificado de ARCA (.crt)<input type="file" accept=".crt,.pem,.cer" hidden disabled={ocupado || !estado.servidor_listo} onChange={e => { void subir(e.target.files?.[0]); e.target.value = ""; }} /></label>
    </div>
  </fieldset>;
}

/** Tarjeta de Parámetros: qué controles corren, ambiente, CUIT, listados y certificado. */
export function ParametrosControlesArca() {
  const [datos, setDatos] = useState<Parametros | null>(null); const [certificado, setCertificado] = useState<EstadoCertificado | null>(null);
  const [error, setError] = useState(""); const [aviso, setAviso] = useState(""); const [ocupado, setOcupado] = useState(false);
  const leer = useCallback(() => Promise.all([api<Parametros>("controles-arca/parametros"), api<EstadoCertificado>("controles-arca/certificado")])
    .then(([p, c]) => { setDatos(p); setCertificado(c); }).catch(x => setError(mensaje(x, "No se pudieron leer los parámetros de ARCA."))), []);
  useEffect(() => { void leer(); }, [leer]);
  async function guardar(f: FormData) {
    setOcupado(true); setError(""); setAviso("");
    try {
      setDatos(await api<Parametros>("controles-arca/parametros", { method: "PUT", body: JSON.stringify({
        controles_activos: CONTROLES.map((_, i) => i + 1).filter(n => f.get(`control_${n}`)), excluir_controlador_fiscal: Boolean(f.get("excluir_cf")),
        ambiente: f.get("ambiente"), cuit_representante: String(f.get("cuit_representante") ?? "").replace(/\D/g, ""),
        cuit_empresas: { ENAV: String(f.get("cuit_ENAV") ?? "").replace(/\D/g, ""), JUBIAR: String(f.get("cuit_JUBIAR") ?? "").replace(/\D/g, "") },
        url_apocrifas: f.get("url_apocrifas"), url_rg18: f.get("url_rg18"),
        enlaces_impositivo: String(f.get("enlaces") ?? "").split("\n").map(e => e.trim()).filter(Boolean),
      }) }));
      setCertificado(await api<EstadoCertificado>("controles-arca/certificado"));
      setAviso("Guardado.");
    } catch (x) { setError(mensaje(x, "No se pudo guardar.")); }
    setOcupado(false);
  }
  return <section className="tarjeta">
    <h2>Controles de ARCA</h2>
    <p className="ayuda">Todo lo que puede cambiar con la normativa: qué controles se hacen, las excepciones y de dónde se bajan los listados.</p>
    {error && <ErrorVisible mensaje={error} />}
    {datos && <form key={datos.actualizado_en ?? "inicial"} onSubmit={e => { e.preventDefault(); void guardar(new FormData(e.currentTarget)); }}>
      <fieldset className="franjas"><legend>Controles activos</legend>
        {CONTROLES.map((nombre, i) => <label key={nombre} className="casilla"><input type="checkbox" name={`control_${i + 1}`} defaultChecked={datos.controles_activos.includes(i + 1)} /> {i + 1}. {nombre}</label>)}
        <label className="casilla"><input type="checkbox" name="excluir_cf" defaultChecked={datos.excluir_controlador_fiscal} /> Las facturas de controlador fiscal no se controlan (control 4)</label>
      </fieldset>
      <div className="campos-organica">
        <label>Ambiente de ARCA<select name="ambiente" defaultValue={datos.ambiente}><option value="homologacion">Homologación (pruebas)</option><option value="produccion">Producción</option></select></label>
        <label>CUIT del representante (dueño del certificado)<input name="cuit_representante" required inputMode="numeric" maxLength={13} defaultValue={datos.cuit_representante} /></label>
        <label>CUIT de ENAV<input name="cuit_ENAV" inputMode="numeric" maxLength={13} defaultValue={datos.cuit_empresas.ENAV} placeholder="Sin cargar" /></label>
        <label>CUIT de JUBIAR<input name="cuit_JUBIAR" inputMode="numeric" maxLength={13} defaultValue={datos.cuit_empresas.JUBIAR} placeholder="Sin cargar" /></label>
        <label>Listado de facturas apócrifas<input name="url_apocrifas" type="url" required maxLength={300} defaultValue={datos.url_apocrifas} /></label>
        <label>Listado de agentes de retención (RG 18)<input name="url_rg18" type="url" required maxLength={300} defaultValue={datos.url_rg18} /></label>
        <label>Enlaces del control impositivo (uno por renglón)<textarea name="enlaces" rows={3} defaultValue={datos.enlaces_impositivo.join("\n")} /></label>
      </div>
      <div className="acciones"><button className="primario" disabled={ocupado}>Guardar</button>{aviso && <span className="ayuda">{aviso}</span>}</div>
      {datos.actualizado_por && <p className="ayuda">Último cambio: {datos.actualizado_por}, {fecha(datos.actualizado_en)}.</p>}
    </form>}
    {certificado && <Certificado estado={certificado} cambio={setCertificado} />}
    <PersonasSubidaPin />
  </section>;
}

/* ---------- Personas que suben facturas con link + PIN ---------- */

type PersonaSubida = {
  id: string; nombre: string; actor: string; empresas: string[]; activo: boolean;
  estado: "activo" | "bloqueado" | "link_desactivado" | "inactivo"; bloqueado_hasta: string | null;
  fallos_acumulados: number; ultimo_ingreso: string | null; creado_por: string; creado_en: string; facturas: number;
};
// El PIN y el link se muestran una sola vez: en el servidor sólo queda su resumen.
type Entrega = { nombre: string; pin?: string; codigo?: string };
const ESTADO_SUBIDA: Record<PersonaSubida["estado"], string> = {
  activo: "Activo", bloqueado: "Bloqueado", link_desactivado: "Link desactivado", inactivo: "Desactivado",
};
const linkSubida = (codigo: string) => `${window.location.origin}/subir/#${codigo}`;

function EntregaUnaVez({ entrega, cerrar }: { entrega: Entrega; cerrar: () => void }) {
  const [aviso, setAviso] = useState("");
  const link = entrega.codigo ? linkSubida(entrega.codigo) : "";
  async function copiar() {
    try { await navigator.clipboard.writeText(link); setAviso("Link copiado."); }
    catch { setAviso("No se pudo copiar: seleccioná el link y copialo a mano."); }
  }
  async function compartir() {
    try { await navigator.share({ title: "Subir facturas", text: `Link para subir facturas de ${entrega.nombre}`, url: link }); }
    catch { /* la persona canceló */ }
  }
  return <Ventana titulo={`Datos de ingreso · ${entrega.nombre}`} tamano="chica" cerrar={cerrar}>
    <p className="aviso-error"><strong>Anotalo ahora: no se vuelve a mostrar.</strong> Mandá el link y el PIN por separado (por ejemplo el link por WhatsApp y el PIN de palabra).</p>
    {entrega.pin && <p>PIN: <strong className="pin-una-vez">{entrega.pin}</strong></p>}
    {link && <>
      <label>Link personal<input readOnly value={link} onFocus={e => e.currentTarget.select()} /></label>
      <div className="acciones">
        <button className="primario" onClick={() => void copiar()}>Copiar link</button>
        {typeof navigator !== "undefined" && "share" in navigator && <button onClick={() => void compartir()}>Compartir</button>}
        {aviso && <span className="ayuda">{aviso}</span>}
      </div>
    </>}
    <div className="acciones"><button onClick={cerrar}>Listo, ya lo anoté</button></div>
  </Ventana>;
}

export function PersonasSubidaPin() {
  const [personas, setPersonas] = useState<PersonaSubida[] | null>(null);
  const [error, setError] = useState(""); const [ocupado, setOcupado] = useState(false);
  const [entrega, setEntrega] = useState<Entrega | null>(null);
  const leer = useCallback(() => api<PersonaSubida[]>("controles-arca/subida-pin/personas").then(setPersonas)
    .catch(x => setError(mensaje(x, "No se pudo leer la lista de personas."))), []);
  useEffect(() => { void leer(); }, [leer]);
  async function hacer(accion: () => Promise<Entrega | null>) {
    setOcupado(true); setError("");
    try { const r = await accion(); if (r) setEntrega(r); await leer(); }
    catch (x) { setError(mensaje(x, "No se pudo completar.")); }
    setOcupado(false);
  }
  function alta(f: FormData, formulario: HTMLFormElement) {
    void hacer(async () => {
      const empresas = ["ENAV", "JUBIAR"].filter(e => f.get(`empresa_${e}`));
      if (!empresas.length) throw new Error("Elegí al menos una empresa.");
      const pin = String(f.get("pin") ?? "").trim();
      const r = await api<{ persona: PersonaSubida; pin: string; codigo: string }>("controles-arca/subida-pin/personas", {
        method: "POST", body: JSON.stringify({ nombre: String(f.get("nombre") ?? "").trim(), empresas, ...(pin ? { pin } : {}) }) });
      formulario.reset();
      return { nombre: r.persona.nombre, pin: r.pin, codigo: r.codigo };
    });
  }
  const nuevoPin = (p: PersonaSubida) => hacer(async () => {
    if (!window.confirm(`¿Darle un PIN nuevo a ${p.nombre}? El anterior deja de servir y su celular tiene que volver a entrar.`)) return null;
    const r = await api<{ persona: PersonaSubida; pin: string }>(`controles-arca/subida-pin/personas/${p.id}/pin`, { method: "POST", body: "{}" });
    return { nombre: p.nombre, pin: r.pin };
  });
  const nuevoLink = (p: PersonaSubida) => hacer(async () => {
    if (!window.confirm(`¿Darle un link nuevo a ${p.nombre}? El anterior deja de servir y su celular tiene que volver a entrar con el PIN.`)) return null;
    const r = await api<{ persona: PersonaSubida; codigo: string }>(`controles-arca/subida-pin/personas/${p.id}/link`, { method: "POST" });
    return { nombre: p.nombre, codigo: r.codigo };
  });
  const desactivar = (p: PersonaSubida) => hacer(async () => {
    if (!window.confirm(`¿Desactivar a ${p.nombre}? Su celular deja de entrar en el momento.`)) return null;
    await api(`controles-arca/subida-pin/personas/${p.id}/desactivar`, { method: "POST" });
    return null;
  });
  return <fieldset className="franjas"><legend>Personas que suben facturas con PIN</legend>
    <p className="ayuda">Para quien sólo saca fotos de facturas desde el celular: entra con su link personal y un PIN de 3 números, sin correo ni contraseña, y sólo puede cargar facturas y ver las que cargó. El celular queda recordado 30 días. Con 5 PIN incorrectos seguidos se bloquea 15 minutos; con 20 sin un ingreso bueno, el link se desactiva hasta darle uno nuevo.</p>
    {error && <ErrorVisible mensaje={error} />}
    <form className="campos-organica" onSubmit={e => { e.preventDefault(); alta(new FormData(e.currentTarget), e.currentTarget); }}>
      <label>Nombre y apellido<input name="nombre" required maxLength={80} /></label>
      <span className="casillas-en-linea">Empresas que puede elegir
        <label className="casilla"><input type="checkbox" name="empresa_ENAV" defaultChecked /> ENAV</label>
        <label className="casilla"><input type="checkbox" name="empresa_JUBIAR" /> JUBIAR</label>
      </span>
      <label>PIN (opcional: vacío lo elige el sistema)<input name="pin" inputMode="numeric" pattern="[0-9]{3}" maxLength={3} autoComplete="off" /></label>
      <div className="acciones"><button className="primario" disabled={ocupado}>Dar de alta</button></div>
    </form>
    {personas && (personas.length ? <div className="tabla-scroll"><table>
      <thead><tr><th>Persona</th><th>Empresas</th><th>Estado</th><th>Último ingreso</th><th>Facturas</th><th>Alta</th><th /></tr></thead>
      <tbody>{personas.map(p => <tr key={p.id}>
        <td><strong>{p.nombre}</strong><br /><small>PIN {p.id}</small></td>
        <td>{p.empresas.join(", ")}</td>
        <td>{ESTADO_SUBIDA[p.estado]}{p.estado === "bloqueado" && p.bloqueado_hasta && <><br /><small>hasta {fecha(p.bloqueado_hasta)}</small></>}</td>
        <td>{fecha(p.ultimo_ingreso)}</td>
        <td>{p.facturas}</td>
        <td><small>{p.creado_por}<br />{fecha(p.creado_en)}</small></td>
        <td>{p.activo && <div className="acciones">
          <button disabled={ocupado} onClick={() => void nuevoPin(p)}>Nuevo PIN</button>
          <button disabled={ocupado} onClick={() => void nuevoLink(p)}>Nuevo link</button>
          <button className="peligro" disabled={ocupado} onClick={() => void desactivar(p)}>Desactivar</button>
        </div>}</td>
      </tr>)}</tbody>
    </table></div> : <Vacio>Todavía no hay nadie que suba facturas con PIN.</Vacio>)}
    {entrega && <EntregaUnaVez entrega={entrega} cerrar={() => setEntrega(null)} />}
  </fieldset>;
}
