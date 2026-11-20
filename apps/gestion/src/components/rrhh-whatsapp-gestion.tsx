"use client";

import { useEffect, useState } from "react";
import { abrirArchivo, api } from "@/lib/api";
import { ErrorVisible, FormularioVentana as Formulario, Pestanas, Tabla, Vacio, Ventana } from "./compartidos";

type Lectura = { dias_detectados?: number; fecha_desde?: string; fecha_hasta?: string; fecha_reintegro?: string; profesional?: string; mensaje?: string; motor?: string };
type Confirmacion = "sin_pedir" | "esperando" | "corrigiendo" | "confirmado" | "no_coincide" | "sin_confirmar";
type Estado = "PENDIENTE" | "EN_LEGAJO" | "ATENDIDO" | "DESCARTADO";
type Mensaje = Record<string, unknown> & {
  id: string; legajo: string; nombre: string; empresa: string; tipo: "certificado" | "epp"; texto: string; recibido_en: string;
  con_archivo: boolean; archivo_tipo: string; lectura: Lectura; lectura_error: string; confirmacion: Confirmacion; correccion: string;
  respondido_en: string | null; estado: Estado; resuelto_por: string; resuelto_en: string | null; nota: string;
  datos_confirmados: { dias?: number | null; desde?: string | null; hasta?: string | null; nombre_adjunto?: string };
};
type Recorrido = Record<string, unknown> & { id: number; sede: string; sede_nombre: string; nombre: string; activo: boolean; personas: number; actualizado_por: string };
type Sede = { id: string; nombre: string };

const TIPOS: Record<Mensaje["tipo"], string> = { certificado: "Certificado médico", epp: "Pedido de EPP" };
const ESTADOS: Record<Estado, string> = { PENDIENTE: "Pendiente de revisión", EN_LEGAJO: "Pasado al legajo", ATENDIDO: "Atendido", DESCARTADO: "Descartado" };
const CONFIRMACIONES: Record<Confirmacion, string> = {
  sin_pedir: "No se le pidió (no se pudo leer)", esperando: "Esperando su respuesta", corrigiendo: "Dijo que no; falta que escriba la corrección",
  confirmado: "Confirmó que es correcto", no_coincide: "Dijo que no coincide", sin_confirmar: "Sin confirmar",
};
const fecha = (v: string | null | undefined) => v ? new Date(v).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : "—";
const dia = (v: string | null | undefined) => v ? new Date(`${v}T12:00:00`).toLocaleDateString("es-AR") : "—";
const mensaje = (x: unknown, defecto: string) => x instanceof Error ? x.message : defecto;
const confirmacion = (m: Mensaje) => m.tipo !== "certificado" ? "—" : `${CONFIRMACIONES[m.confirmacion]}${m.correccion ? `: «${m.correccion}»` : ""}`;

/** Certificado: RRHH confirma o corrige lo que se leyó y lo pasa al legajo. Pedido de EPP: lo atiende. */
function VentanaMensaje({ m, cerrar, cambio }: { m: Mensaje; cerrar: () => void; cambio: () => void }) {
  const [accion, setAccion] = useState<"legajo" | "atender" | "descartar" | null>(null);
  const pendiente = m.estado === "PENDIENTE"; const l = m.lectura;
  const listo = () => { setAccion(null); cambio(); };
  return <Ventana titulo={`${TIPOS[m.tipo]} · ${m.nombre}`} cerrar={cerrar}>
    <dl className="ficha">
      <div><dt>Empleado</dt><dd>{m.nombre}</dd></div>
      <div><dt>Legajo</dt><dd>{m.legajo} · {m.empresa}</dd></div>
      <div><dt>Llegó</dt><dd>{fecha(m.recibido_en)}</dd></div>
      <div><dt>Estado</dt><dd>{ESTADOS[m.estado]}{m.resuelto_por ? ` · ${m.resuelto_por} · ${fecha(m.resuelto_en)}` : ""}</dd></div>
      <div><dt>Texto</dt><dd>{m.texto || "—"}</dd></div>
      <div><dt>Archivo</dt><dd>{m.con_archivo ? <button onClick={() => void abrirArchivo(`rrhh-whatsapp/mensajes/${m.id}/archivo`)}>Ver archivo</button> : "—"}</dd></div>
      {m.tipo === "certificado" && <>
        <div><dt>Lo que se leyó</dt><dd>{m.lectura_error || (l.dias_detectados || l.fecha_desde || l.fecha_hasta
          ? `${l.dias_detectados ? `${l.dias_detectados} días` : ""}${l.fecha_desde ? ` · desde ${dia(l.fecha_desde)}` : ""}${l.fecha_hasta ? ` hasta ${dia(l.fecha_hasta)}` : ""}`
          : "No se pudieron leer los datos.")}</dd></div>
        <div><dt>Respuesta del empleado</dt><dd>{confirmacion(m)}</dd></div>
      </>}
      {m.nota && <div><dt>{m.estado === "DESCARTADO" ? "Motivo" : "Nota"}</dt><dd>{m.nota}</dd></div>}
      {m.estado === "EN_LEGAJO" && <div><dt>En el legajo</dt><dd>{m.datos_confirmados.nombre_adjunto}{m.datos_confirmados.dias ? ` · ${m.datos_confirmados.dias} días` : ""}</dd></div>}
    </dl>
    {pendiente && <div className="acciones">
      <button className="peligro" onClick={() => setAccion("descartar")}>Descartar</button>
      {m.tipo === "certificado" && m.con_archivo && <button className="primario" onClick={() => setAccion("legajo")}>Pasar al legajo</button>}
      {m.tipo === "epp" && <button className="primario" onClick={() => setAccion("atender")}>Marcar atendido</button>}
    </div>}
    {accion === "legajo" && <Formulario titulo="Pasar el certificado al legajo" boton="Pasar al legajo" tamano="ancha" cerrar={() => setAccion(null)} enviar={async f => {
      const numero = (k: string) => f.get(k) ? Number(f.get(k)) : null; const texto = (k: string) => String(f.get(k) ?? "");
      await api(`rrhh-whatsapp/mensajes/${m.id}/legajo`, { method: "POST", body: JSON.stringify({
        nombre: texto("nombre"), dias: numero("dias"), desde: texto("desde") || null, hasta: texto("hasta") || null,
        profesional: texto("profesional"), nota: texto("nota") }) });
      listo();
    }}>
      <p className="ayuda">Los datos vienen de la lectura automática del certificado: revisalos contra el archivo y corregí lo que haga falta. {m.confirmacion === "no_coincide" && m.correccion ? `El empleado avisó: «${m.correccion}».` : ""}</p>
      <label>Nombre del adjunto<input name="nombre" maxLength={120} defaultValue={`Certificado médico ${new Date(m.recibido_en).toLocaleDateString("es-AR").replaceAll("/", "-")}`} /></label>
      <label>Días<input name="dias" type="number" min={1} max={365} defaultValue={l.dias_detectados ?? ""} /></label>
      <label>Desde<input name="desde" type="date" defaultValue={l.fecha_desde ?? ""} /></label>
      <label>Hasta<input name="hasta" type="date" defaultValue={l.fecha_hasta ?? ""} /></label>
      <label>Profesional<input name="profesional" maxLength={120} defaultValue={l.profesional ?? ""} /></label>
      <label>Nota <span className="ayuda">(opcional)</span><input name="nota" maxLength={300} /></label>
    </Formulario>}
    {accion === "atender" && <Formulario titulo="Marcar el pedido como atendido" boton="Marcar atendido" cerrar={() => setAccion(null)} enviar={async f => {
      await api(`rrhh-whatsapp/mensajes/${m.id}/atender`, { method: "POST", body: JSON.stringify({ nota: String(f.get("nota") ?? "") }) }); listo();
    }}>
      <label>Nota <span className="ayuda">(qué se hizo, opcional)</span><input name="nota" maxLength={300} /></label>
    </Formulario>}
    {accion === "descartar" && <Formulario titulo="Descartar el mensaje" boton="Descartar" cerrar={() => setAccion(null)} enviar={async f => {
      await api(`rrhh-whatsapp/mensajes/${m.id}/descartar`, { method: "POST", body: JSON.stringify({ motivo: String(f.get("motivo") ?? "") }) }); listo();
    }}>
      <label>Motivo<input name="motivo" required maxLength={300} placeholder="Foto ilegible, se le pidió de nuevo" /></label>
    </Formulario>}
  </Ventana>;
}

function Bandeja() {
  const [mensajes, setMensajes] = useState<Mensaje[] | null>(null); const [error, setError] = useState("");
  const [filtro, setFiltro] = useState<Estado | "">("PENDIENTE"); const [abierto, setAbierto] = useState<Mensaje | null>(null);
  async function cargar() {
    try { const filas = await api<Mensaje[]>(`rrhh-whatsapp/mensajes${filtro ? `?estado=${filtro}` : ""}`); setMensajes(filas); setError(""); setAbierto(a => a && (filas.find(f => f.id === a.id) ?? null)); }
    catch (x) { setMensajes([]); setError(mensaje(x, "No se pudieron leer los mensajes.")); }
  }
  useEffect(() => { void cargar(); }, [filtro]);
  return <section className="tarjeta">
    <h2>Mensajes del personal</h2>
    <p className="ayuda">Certificados médicos y pedidos de EPP que el personal cargado en «Personal en el bot» mandó por WhatsApp. Nada pasa solo al legajo: cada uno queda pendiente hasta que RRHH lo revisa. Del certificado, el bot le pregunta al empleado si los días leídos son correctos.</p>
    <div className="barra-filtros"><label>Estado<select value={filtro} onChange={e => setFiltro(e.target.value as Estado | "")}><option value="">Todos</option>{Object.entries(ESTADOS).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label></div>
    {error && <ErrorVisible mensaje={error} />}
    {!mensajes ? <p className="ayuda">Cargando…</p> : !mensajes.length ? <Vacio>No hay mensajes.</Vacio> :
      <Tabla etiqueta="Mensajes del personal" filas={mensajes} porPagina={15} alElegir={setAbierto} columnas={[
        { clave: "recibido_en", titulo: "Llegó", valor: m => fecha(m.recibido_en) },
        { clave: "nombre", titulo: "Empleado", valor: m => `${m.nombre} (${m.legajo} · ${m.empresa})` },
        { clave: "tipo", titulo: "Tipo", valor: m => TIPOS[m.tipo] },
        { clave: "texto", titulo: "Texto", valor: m => m.texto || "—" },
        { clave: "con_archivo", titulo: "Archivo", valor: m => m.con_archivo ? "Sí" : "—" },
        { clave: "confirmacion", titulo: "Respuesta del empleado", valor: m => confirmacion(m) },
        { clave: "estado", titulo: "Estado", valor: m => ESTADOS[m.estado] },
      ]} />}
    {abierto && <VentanaMensaje m={abierto} cerrar={() => setAbierto(null)} cambio={() => void cargar()} />}
  </section>;
}

function Recorridos() {
  const [lista, setLista] = useState<Recorrido[] | null>(null); const [sedes, setSedes] = useState<Sede[]>([]); const [error, setError] = useState("");
  const [editando, setEditando] = useState<Recorrido | "nuevo" | null>(null);
  async function cargar() {
    try { setLista(await api<Recorrido[]>("rrhh-whatsapp/recorridos")); setError(""); }
    catch (x) { setLista([]); setError(mensaje(x, "No se pudieron leer los recorridos.")); }
  }
  useEffect(() => { void cargar(); api<Sede[]>("rrhh-whatsapp/sedes").then(setSedes).catch(() => setSedes([])); }, []);
  const actual = editando === "nuevo" ? null : editando;
  return <section className="tarjeta">
    <div className="titulo-fila"><div><h2>Recorridos del micro</h2><p className="ayuda">Cuando llega el micro, la guardia de la bodega toca «Llegó el micro» y elige el recorrido: el bot avisa por WhatsApp al personal de ese recorrido. A cada persona se le asigna su recorrido en «Personal en el bot».</p></div>
      <button className="primario" onClick={() => setEditando("nuevo")}>Nuevo recorrido</button></div>
    {error && <ErrorVisible mensaje={error} />}
    {!lista ? <p className="ayuda">Cargando…</p> : !lista.length ? <Vacio>Todavía no hay recorridos.</Vacio> :
      <Tabla etiqueta="Recorridos del micro" filas={lista} alElegir={setEditando} columnas={[
        { clave: "sede_nombre", titulo: "Bodega" },
        { clave: "nombre", titulo: "Recorrido" },
        { clave: "personas", titulo: "Personas" },
        { clave: "activo", titulo: "Estado", valor: r => r.activo ? "Activo" : "Inactivo" },
      ]} />}
    {editando && <Formulario titulo={actual ? `Recorrido ${actual.nombre}` : "Nuevo recorrido"} boton="Guardar" cerrar={() => setEditando(null)} enviar={async f => {
      const cuerpo = { sede: f.get("sede"), nombre: f.get("nombre"), activo: f.get("activo") === "on" };
      await api(actual ? `rrhh-whatsapp/recorridos/${actual.id}` : "rrhh-whatsapp/recorridos", { method: actual ? "PUT" : "POST", body: JSON.stringify(cuerpo) });
      setEditando(null); await cargar();
    }}>
      <label>Bodega<select name="sede" required defaultValue={actual?.sede ?? ""}><option value="" disabled>Elegí la bodega</option>{sedes.map(s => <option key={s.id} value={s.id}>{s.nombre}</option>)}</select></label>
      <label>Nombre del recorrido<input name="nombre" required minLength={2} maxLength={80} defaultValue={actual?.nombre ?? ""} placeholder="Rawson - Pocito" /></label>
      <label className="casilla"><input type="checkbox" name="activo" defaultChecked={actual?.activo ?? true} />Activo</label>
    </Formulario>}
  </section>;
}

/** Lo que llega por WhatsApp para RRHH y los recorridos del micro del personal. */
export function RrhhWhatsappGestion() {
  const [vista, setVista] = useState<"bandeja" | "recorridos">("bandeja");
  return <>
    <Pestanas opciones={[["bandeja", "Bandeja"], ["recorridos", "Recorridos del micro"]] as const} activa={vista} cambiar={setVista} />
    {vista === "bandeja" ? <Bandeja /> : <Recorridos />}
  </>;
}
