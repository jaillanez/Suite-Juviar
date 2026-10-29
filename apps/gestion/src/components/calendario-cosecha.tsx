"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Vacio, Ventana } from "./compartidos";

type Turno = { id: number; cuit: string; productor: string; codigo: string | null; camiones: number; camiones_usados: number; kg_por_camion: number; organica: boolean; estado: string; pedido_por: string; canal: string };
type Dia = { fecha: string; capacidad_kg: number | null; capacidad_propia: boolean; reservado_kg: number; turnos: Turno[] };
type Mes = { sede: string; mes: string; capacidad_por_defecto_kg: number | null; dias: Dia[] };
type Productor = { cuit: string; razon_social: string; codigos: string[]; ultima_entrega: string | null };

const SEDES = [["chimbas", "Chimbas"], ["lavalle", "Lavalle"], ["media-agua", "Media Agua"]] as const;
const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const CANALES: Record<string, string> = { bodega: "Cargado por la bodega", whatsapp: "Pedido por WhatsApp", web: "Pedido por la web" };
const kg = (n: number) => `${n.toLocaleString("es-AR")} kg`;
const toneladas = (n: number) => `${(n / 1000).toLocaleString("es-AR", { maximumFractionDigits: 1 })} t`;
const hoyLocal = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const mensaje = (x: unknown) => x instanceof Error ? x.message : "No se pudo completar.";

function moverMes(mes: string, delta: number) {
  const [a, m] = mes.split("-").map(Number); const d = new Date(a, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function nombreMes(mes: string) { const [a, m] = mes.split("-").map(Number); const t = new Date(a, m - 1, 1).toLocaleDateString("es-AR", { month: "long", year: "numeric" }); return t[0].toUpperCase() + t.slice(1); }
function nombreDia(fecha: string) { const t = new Date(`${fecha}T12:00:00`).toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" }); return t[0].toUpperCase() + t.slice(1); }

export function CalendarioCosecha() {
  const [sede, setSede] = useState("chimbas"); const [mes, setMes] = useState(hoyLocal().slice(0, 7));
  const [datos, setDatos] = useState<Mes | null>(null); const [error, setError] = useState(""); const [aviso, setAviso] = useState("");
  const [diaAbierto, setDiaAbierto] = useState<string | null>(null); const [errorVentana, setErrorVentana] = useState("");
  const [editandoDefecto, setEditandoDefecto] = useState(false);
  const [busqueda, setBusqueda] = useState(""); const [resultados, setResultados] = useState<Productor[]>([]); const [productor, setProductor] = useState<Productor | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function cargar() { try { setDatos(await api<Mes>(`turnos-bodega/mes?sede=${sede}&mes=${mes}`)); setError(""); } catch (x) { setError(mensaje(x)); } }
  useEffect(() => { cargar(); }, [sede, mes]);
  useEffect(() => { const q = busqueda.trim(); if (q.length < 2 || productor) { setResultados([]); return; } const r = setTimeout(() => api<Productor[]>(`turnos-bodega/productores?q=${encodeURIComponent(q)}`).then(setResultados).catch(() => setResultados([])), 250); return () => clearTimeout(r); }, [busqueda, productor]);

  const dia = datos?.dias.find((d) => d.fecha === diaAbierto) ?? null;
  const hoy = hoyLocal();
  const primero = datos ? (new Date(`${datos.dias[0].fecha}T12:00:00`).getDay() + 6) % 7 : 0;

  function abrirDia(fecha: string) { setDiaAbierto(fecha); setErrorVentana(""); setProductor(null); setBusqueda(""); }
  async function guardarDefecto(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setErrorVentana("");
    try { await api("turnos-bodega/capacidad", { method: "PUT", body: JSON.stringify({ sede, fecha: null, kg_dia: Number(f.get("kg")) }) }); setEditandoDefecto(false); setAviso("Capacidad diaria guardada."); await cargar(); } catch (x) { setErrorVentana(mensaje(x)); }
  }
  async function guardarCapacidadDia(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!dia) return; const f = new FormData(e.currentTarget); setErrorVentana("");
    try { await api("turnos-bodega/capacidad", { method: "PUT", body: JSON.stringify({ sede, fecha: dia.fecha, kg_dia: Number(f.get("kg")) }) }); await cargar(); } catch (x) { setErrorVentana(mensaje(x)); }
  }
  async function anotar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!dia) return; setErrorVentana("");
    if (!productor) { setErrorVentana("Elegí el productor de la lista."); return; }
    const form = e.currentTarget; const f = new FormData(form); setGuardando(true);
    try {
      await api("turnos-bodega", { method: "POST", body: JSON.stringify({ sede, fecha: dia.fecha, cuit: productor.cuit, codigo: productor.codigos[0] ?? null, camiones: Number(f.get("camiones")), kg_por_camion: Number(f.get("kg_por_camion")), organica: f.get("organica") === "si" }) });
      form.reset(); setProductor(null); setBusqueda(""); await cargar();
    } catch (x) { setErrorVentana(mensaje(x)); } finally { setGuardando(false); }
  }
  async function cancelar(t: Turno) { setErrorVentana(""); try { await api(`turnos-bodega/${t.id}/cancelar`, { method: "POST" }); await cargar(); } catch (x) { setErrorVentana(mensaje(x)); } }

  return <>
    {error && <ErrorVisible mensaje={error} />}
    {aviso && <div className="aviso-exito" role="status">{aviso}</div>}
    <section className="tarjeta">
      <div className="titulo-fila calendario-cabecera">
        <label>Bodega<select value={sede} onChange={(e) => setSede(e.target.value)}>{SEDES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>
        <div className="navegacion-mes"><button onClick={() => setMes(moverMes(mes, -1))} aria-label="Mes anterior">‹</button><strong>{nombreMes(mes)}</strong><button onClick={() => setMes(moverMes(mes, 1))} aria-label="Mes siguiente">›</button></div>
        <div className="capacidad-defecto"><span>Capacidad diaria: <strong>{datos?.capacidad_por_defecto_kg != null ? toneladas(datos.capacidad_por_defecto_kg) : "sin definir"}</strong></span><button onClick={() => { setErrorVentana(""); setEditandoDefecto(true); }}>Cambiar</button></div>
      </div>
      {datos && datos.capacidad_por_defecto_kg == null && <p className="ayuda-contextual">Primero definí cuántos kilos por día puede recibir esta bodega (botón «Cambiar»). Después tocá un día para anotar productores.</p>}
      {datos && <div className="calendario" role="grid" aria-label={`Turnos de ${nombreMes(mes)}`}>
        {DIAS.map((d) => <div key={d} className="calendario-dia-semana" role="columnheader">{d}</div>)}
        {Array.from({ length: primero }, (_, i) => <div key={`v${i}`} className="calendario-vacio" />)}
        {datos.dias.map((d) => {
          const activos = d.turnos.filter((t) => t.estado === "activo");
          const uso = d.capacidad_kg ? Math.min(1, d.reservado_kg / d.capacidad_kg) : 0;
          const pasado = d.fecha < hoy;
          return <button key={d.fecha} role="gridcell" className={`calendario-celda${pasado ? " pasado" : ""}${d.fecha === hoy ? " hoy" : ""}${uso >= 1 ? " lleno" : ""}`} onClick={() => abrirDia(d.fecha)}>
            <span className="calendario-numero">{Number(d.fecha.slice(8))}</span>
            {activos.length > 0 && <span className="calendario-turnos">{activos.length} {activos.length === 1 ? "productor" : "productores"}</span>}
            {d.capacidad_kg != null && <><span className="barra-cupo" aria-hidden="true"><span style={{ width: `${uso * 100}%` }} /></span><small>{uso >= 1 ? "Completo" : `Libres ${toneladas(Math.max(d.capacidad_kg - d.reservado_kg, 0))}`}</small></>}
          </button>;
        })}
      </div>}
    </section>

    {editandoDefecto && <Ventana tamano="chica" titulo="Capacidad diaria de la bodega" cerrar={() => setEditandoDefecto(false)}>
      <p className="ayuda">Kilos que la bodega puede recibir por día. Se usa en todos los días que no tengan una capacidad propia.</p>
      {errorVentana && <ErrorVisible mensaje={errorVentana} />}
      <form className="form-grid" onSubmit={guardarDefecto}><label>Kilos por día<input name="kg" type="number" min="0" step="1000" required defaultValue={datos?.capacidad_por_defecto_kg ?? ""} autoFocus /></label><div className="acciones"><button type="button" onClick={() => setEditandoDefecto(false)}>Cancelar</button><button className="primario">Guardar</button></div></form>
    </Ventana>}

    {dia && <Ventana tamano="amplia" titulo={nombreDia(dia.fecha)} cerrar={() => setDiaAbierto(null)}>
      {errorVentana && <ErrorVisible mensaje={errorVentana} />}
      <div className="metricas"><article><span>Capacidad</span><strong>{dia.capacidad_kg != null ? toneladas(dia.capacidad_kg) : "Sin definir"}</strong><small>{dia.capacidad_propia ? "Propia de este día" : "La de todos los días"}</small></article><article><span>Reservado</span><strong>{toneladas(dia.reservado_kg)}</strong><small>{dia.turnos.filter((t) => t.estado === "activo").reduce((s, t) => s + t.camiones, 0)} camiones</small></article><article><span>Libre</span><strong>{dia.capacidad_kg != null ? toneladas(Math.max(dia.capacidad_kg - dia.reservado_kg, 0)) : "—"}</strong><small>&nbsp;</small></article></div>
      <form className="form-linea" onSubmit={guardarCapacidadDia}><label>Capacidad sólo para este día (kg)<input name="kg" type="number" min="0" step="1000" required defaultValue={dia.capacidad_kg ?? ""} key={dia.fecha} /></label><button>Guardar capacidad del día</button></form>
      <h3>Productores anotados</h3>
      {dia.turnos.length ? <div className="tabla-scroll"><table><thead><tr><th>Productor</th><th>Camiones</th><th>Kilos estimados</th><th>Orgánica</th><th>Cómo se anotó</th><th></th></tr></thead><tbody>{dia.turnos.map((t) => <tr key={t.id} className={t.estado === "cancelado" ? "turno-cancelado" : ""}><td><strong>{t.productor}</strong>{t.codigo && <small> · {t.codigo}</small>}</td><td>{t.camiones_usados}/{t.camiones}</td><td>{kg(t.camiones * t.kg_por_camion)}</td><td>{t.organica ? "Sí" : "No"}</td><td>{CANALES[t.canal] ?? t.canal}<br /><small>{t.pedido_por}</small></td><td>{t.estado === "activo" ? (t.camiones_usados === 0 && dia.fecha >= hoy ? <button onClick={() => cancelar(t)}>Cancelar</button> : null) : <span className="estado">Cancelado</span>}</td></tr>)}</tbody></table></div> : <Vacio>Todavía no hay productores anotados para este día.</Vacio>}
      {dia.fecha >= hoy && <><h3>Anotar un productor</h3>
        <form className="form-grid" onSubmit={anotar}>
          <label className="campo-ancho campo-buscable">Productor (nombre, CUIT o código)<input value={busqueda} onChange={(e) => { setBusqueda(e.target.value); setProductor(null); }} placeholder="Escribí al menos 2 letras" autoComplete="off" />
            {resultados.length > 0 && <div className="resultados-busqueda">{resultados.map((p) => <button type="button" key={p.cuit} onClick={() => { setProductor(p); setBusqueda(p.razon_social); setResultados([]); }}><strong>{p.razon_social}</strong><span>CUIT {p.cuit}{p.codigos.length ? ` · ${p.codigos.join(", ")}` : ""}</span></button>)}</div>}
            {productor && <small>Elegido: {productor.razon_social}</small>}</label>
          <label>Camiones<input name="camiones" type="number" min="1" max="50" defaultValue="1" required /></label>
          <label>Kilos por camión (estimado)<input name="kg_por_camion" type="number" min="1000" max="40000" step="500" defaultValue="11000" required /></label>
          <label>Uva orgánica<select name="organica" defaultValue="no"><option value="no">No</option><option value="si">Sí (requiere certificado vigente)</option></select></label>
          <div className="acciones"><button className="primario" disabled={guardando}>{guardando ? "Anotando…" : "Anotar turno"}</button></div>
        </form></>}
    </Ventana>}
  </>;
}
