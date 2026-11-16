"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Confirmacion, ErrorVisible } from "./compartidos";

export type EstadoOrganica = {
  recibe: boolean; abierta: boolean; origen: "manual" | "franja" | null; desde: string | null; hasta: string | null;
  abierta_por: string | null; abierta_desde: "guardia" | "bascula" | null; prioridad: boolean;
  quien_abre: QuienAbre; modo_franjas: Modo;
};
type QuienAbre = "guardia" | "bascula" | "ambos";
type Modo = "manual" | "fijas";
type Franja = { dia: number; desde: string; hasta: string };
type Parametros = { recibe_organica: boolean; quien_abre: QuienAbre; modo_franjas: Modo; inicio_cosecha: string | null; dias_prioridad: number; actualizado_por: string | null; actualizado_en: string | null };
type Sesion = { abierta_en: string; abierta_por: string; abierta_desde: string; cerrada_en: string | null; cerrada_por: string | null; cerrada_desde: string | null };
type Sede = { sede: string; nombre: string; parametros: Parametros; franjas: Franja[]; estado: EstadoOrganica | null; sesiones: Sesion[] };

const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const QUIEN: Record<QuienAbre, string> = { guardia: "La guardia", bascula: "Báscula", ambos: "La guardia o Báscula" };
const DESDE: Record<string, string> = { guardia: "guardia", bascula: "Báscula", parametro: "cambio de parámetros" };

const hora = (v: string | null) => v ? new Date(v).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }) : "";
const fechaHora = (v: string | null) => v ? new Date(v).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }) : "";

/** Aviso de la sesión de una bodega en el tablero de la fila; Báscula la abre y la cierra desde acá. */
export function ControlOrganica({ sede, estado, puedeOperar, cambio }: { sede: string; estado: EstadoOrganica | null | undefined; puedeOperar: boolean; cambio: () => void }) {
  const [error, setError] = useState(""); const [ocupado, setOcupado] = useState(false); const [preguntando, setPreguntando] = useState(false);
  if (!estado?.recibe) return null;
  const opera = puedeOperar && estado.modo_franjas === "manual" && estado.quien_abre !== "guardia";
  async function cambiar() {
    const abrir = !estado!.abierta;
    setPreguntando(false); setOcupado(true); setError("");
    try { await api(`fila-organica/${sede}/${abrir ? "abrir" : "cerrar"}`, { method: "POST" }); cambio(); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo cambiar la sesión."); }
    setOcupado(false);
  }
  return <div className={`sesion-organica${estado.abierta ? " abierta" : ""}`} role="status">
    <strong>{estado.abierta ? "Sesión orgánica abierta" : "Sesión convencional"}</strong>
    <span>{estado.abierta
      ? `Desde las ${hora(estado.desde)}${estado.hasta ? ` hasta las ${hora(estado.hasta)}` : ""}${estado.abierta_desde ? ` · la abrió ${DESDE[estado.abierta_desde]}` : ""}. Sólo entra uva orgánica certificada.`
      : "La uva orgánica que entre ahora se recibe como convencional."}</span>
    {estado.prioridad && <span>Primeros días de cosecha: la orgánica va primero en la fila.</span>}
    {estado.modo_franjas === "fijas" && <span className="ayuda">Sigue las franjas horarias fijas.</span>}
    {opera && <button className={estado.abierta ? "peligro" : "primario"} disabled={ocupado} onClick={() => setPreguntando(true)}>{estado.abierta ? "Cerrar sesión orgánica" : "Abrir sesión orgánica"}</button>}
    {!opera && estado.modo_franjas === "manual" && <span className="ayuda">La abre y la cierra {QUIEN[estado.quien_abre].toLowerCase()}.</span>}
    {error && <ErrorVisible mensaje={error} />}
    <Confirmacion abierto={preguntando} cancelar={() => setPreguntando(false)} confirmar={cambiar}
      titulo={estado.abierta ? "¿Cerrar la sesión orgánica?" : "¿Abrir la sesión orgánica?"}
      detalle={estado.abierta ? "Vuelve a entrar uva convencional." : "Mientras esté abierta no se llama ni pasa a báscula uva convencional."} />
  </div>;
}

/** Parámetros de la sesión orgánica de cada bodega (pestaña de Turnos de cosecha). */
export function ConfigOrganica() {
  const [sedes, setSedes] = useState<Sede[] | null>(null); const [error, setError] = useState("");
  const leer = useCallback(() => api<{ sedes: Sede[] }>("fila-organica").then((d) => { setSedes(d.sedes); setError(""); })
    .catch((x) => setError(x instanceof Error ? x.message : "No se pudo leer la configuración.")), []);
  useEffect(() => { leer(); }, [leer]);
  if (error && !sedes) return <ErrorVisible mensaje={error} />;
  if (!sedes) return <section className="tarjeta"><p className="ayuda">Leyendo la configuración…</p></section>;
  return <div className="config-organica">{sedes.map((s) => <ConfigSede key={s.sede} sede={s} guardado={leer} />)}</div>;
}

function ConfigSede({ sede, guardado }: { sede: Sede; guardado: () => void }) {
  const p = sede.parametros;
  const [recibe, setRecibe] = useState(p.recibe_organica); const [quien, setQuien] = useState<QuienAbre>(p.quien_abre);
  const [modo, setModo] = useState<Modo>(p.modo_franjas); const [inicio, setInicio] = useState(p.inicio_cosecha ?? "");
  const [dias, setDias] = useState(String(p.dias_prioridad));
  const [franjas, setFranjas] = useState<Franja[]>(sede.franjas.map((f) => ({ ...f, desde: f.desde.slice(0, 5), hasta: f.hasta.slice(0, 5) })));
  const [mensaje, setMensaje] = useState(""); const [error, setError] = useState(""); const [ocupado, setOcupado] = useState(false);

  function cambiarFranja(i: number, cambio: Partial<Franja>) { setFranjas((fs) => fs.map((f, j) => j === i ? { ...f, ...cambio } : f)); }
  async function guardar() {
    setOcupado(true); setError(""); setMensaje("");
    try {
      await api(`fila-organica/${sede.sede}`, { method: "PUT", body: JSON.stringify({
        recibe_organica: recibe, quien_abre: quien, modo_franjas: modo, inicio_cosecha: inicio || null,
        dias_prioridad: Number(dias), franjas: modo === "fijas" ? franjas : [],
      }) });
      setMensaje("Guardado."); guardado();
    } catch (x) { setError(x instanceof Error ? x.message : "No se pudo guardar."); }
    setOcupado(false);
  }
  return <article className="tarjeta">
    <header className="titulo-fila"><h2>{sede.nombre}</h2>{sede.estado?.recibe && <span className={`estado-camion ${sede.estado.abierta ? "estado-llamado" : ""}`}>{sede.estado.abierta ? "Sesión orgánica abierta" : "Sesión convencional"}</span>}</header>
    <label className="casilla"><input type="checkbox" checked={recibe} onChange={(e) => setRecibe(e.target.checked)} /> Esta bodega recibe uva orgánica</label>
    {recibe && <div className="campos-organica">
      <label>Quién abre y cierra la sesión orgánica<select value={quien} onChange={(e) => setQuien(e.target.value as QuienAbre)}>
        <option value="ambos">La guardia o Báscula</option><option value="guardia">Sólo la guardia</option><option value="bascula">Sólo Báscula</option></select></label>
      <label>Franjas horarias<select value={modo} onChange={(e) => setModo(e.target.value as Modo)}>
        <option value="manual">Se abren y cierran en el momento</option><option value="fijas">Fijas por día de la semana</option></select></label>
      {modo === "fijas" && <fieldset className="franjas"><legend>Horarios de sesión orgánica</legend>
        {franjas.length === 0 && <p className="ayuda">Sin franjas: la sesión orgánica no se abre nunca.</p>}
        {franjas.map((f, i) => <div key={i} className="franja-organica">
          <select aria-label="Día" value={f.dia} onChange={(e) => cambiarFranja(i, { dia: Number(e.target.value) })}>{DIAS.map((d, j) => <option key={d} value={j + 1}>{d}</option>)}</select>
          <input aria-label="Desde" type="time" value={f.desde} onChange={(e) => cambiarFranja(i, { desde: e.target.value })} />
          <input aria-label="Hasta" type="time" value={f.hasta} onChange={(e) => cambiarFranja(i, { hasta: e.target.value })} />
          <button type="button" aria-label="Quitar franja" title="Quitar franja" onClick={() => setFranjas((fs) => fs.filter((_, j) => j !== i))}>✕</button>
        </div>)}
        <button type="button" onClick={() => setFranjas((fs) => [...fs, { dia: Math.min((fs.at(-1)?.dia ?? 0) + 1, 7), desde: fs.at(-1)?.desde ?? "08:00", hasta: fs.at(-1)?.hasta ?? "13:00" }])}>Agregar franja</button>
      </fieldset>}
      <label>Primer día de cosecha<input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} /></label>
      <label>Días en que la orgánica va primero en la fila<input type="number" min="0" max="120" value={dias} onChange={(e) => setDias(e.target.value)} /></label>
    </div>}
    {error && <ErrorVisible mensaje={error} />}
    <div className="acciones"><button className="primario" disabled={ocupado} onClick={guardar}>Guardar</button>{mensaje && <span className="ayuda">{mensaje}</span>}</div>
    {p.actualizado_por && <p className="ayuda">Último cambio: {p.actualizado_por}, {fechaHora(p.actualizado_en)}.</p>}
    {sede.sesiones.length > 0 && <details><summary>Últimas sesiones</summary><ul className="lista-simple">{sede.sesiones.map((x) =>
      <li key={x.abierta_en}>{fechaHora(x.abierta_en)} abrió {DESDE[x.abierta_desde] ?? x.abierta_desde} ({x.abierta_por}){x.cerrada_en ? ` · cerró ${DESDE[x.cerrada_desde ?? ""] ?? x.cerrada_desde} a las ${hora(x.cerrada_en)}` : " · sigue abierta"}</li>)}</ul></details>}
  </article>;
}
