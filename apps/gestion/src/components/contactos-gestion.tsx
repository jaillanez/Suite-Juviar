"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Vacio } from "./compartidos";

type Contacto = { telefono: string; tareas: string[]; activo: boolean; origen: string; alta_por: string; alta_en: string };
type Evento = { telefono: string; tipo: string; actor: string; momento: string; detalle?: { motivo?: string } };
type Resultado = { contactos: Contacto[]; eventos: Evento[]; tareas_disponibles: string[] };

const etiquetas: Record<string, string> = {
  ver_informes: "Ver informes",
  pedir_turnos: "Pedir turnos",
  administrar_contactos: "Administrar contactos",
};

export function ContactosGestion() {
  const [cuit, setCuit] = useState("");
  const [datos, setDatos] = useState<Resultado | null>(null);
  const [error, setError] = useState("");
  const [reemplazo, setReemplazo] = useState<string | null>(null);

  async function buscar(e?: FormEvent) {
    e?.preventDefault(); setError("");
    try { setDatos(await api<Resultado>(`contactos/${encodeURIComponent(cuit)}`)); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo buscar."); }
  }

  async function cambiar(contacto: Contacto, tarea: string, activa: boolean) {
    const tareas = activa ? [...new Set([...contacto.tareas, tarea])] : contacto.tareas.filter(t => t !== tarea);
    try { await api(`contactos/${cuit}/${contacto.telefono}/tareas`, { method: "PUT", body: JSON.stringify({ tareas }) }); await buscar(); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo cambiar el permiso."); }
  }

  async function reemplazar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    try {
      await api(`contactos/${cuit}/reemplazar`, { method: "POST", body: JSON.stringify({ anterior: reemplazo, nuevo: f.get("nuevo"), motivo: f.get("motivo") }) });
      setReemplazo(null); await buscar();
    } catch (x) { setError(x instanceof Error ? x.message : "No se pudo reemplazar."); }
  }

  return <>
    <section className="tarjeta contacto-busqueda"><h2>Buscar productor</h2><form className="form-linea" onSubmit={buscar}><label>CUIT<input value={cuit} onChange={e => setCuit(e.target.value)} placeholder="20-12345678-9" required /></label><button className="primario">Ver contactos</button></form></section>
    {error && <ErrorVisible mensaje={error} />}
    {datos && <section className="contactos-operacion"><div className="titulo-fila"><div><h2>Accesos habilitados</h2><p className="ayuda">Los cambios se aplican sobre este CUIT y quedan en el historial.</p></div><span className="estado">{datos.contactos.filter(c => c.activo).length} activos</span></div>
      <div className="contactos-lista">{datos.contactos.length ? datos.contactos.map(c => <article className={`contacto-fila ${c.activo ? "" : "contacto-inactivo"}`} key={c.telefono}><div><strong>{c.telefono}</strong><small>{c.activo ? `Alta: ${c.origen}` : "Dado de baja"}</small></div><fieldset disabled={!c.activo}><legend>Tareas permitidas</legend>{datos.tareas_disponibles.map(t => <label key={t}><input type="checkbox" checked={c.tareas.includes(t)} onChange={e => cambiar(c, t, e.target.checked)} />{etiquetas[t]}</label>)}</fieldset>{c.activo && c.tareas.includes("administrar_contactos") && <button onClick={() => setReemplazo(c.telefono)}>Reemplazar administrador</button>}</article>) : <Vacio />}</div>
      {reemplazo && <form className="tarjeta reemplazo" onSubmit={reemplazar}><div><h2>Reemplazar administrador</h2><p>El teléfono anterior perderá acceso en la misma operación.</p></div><label>Administrador anterior<input value={reemplazo} readOnly /></label><label>Teléfono nuevo<input name="nuevo" inputMode="tel" required pattern="[0-9]{8,20}" /></label><label>Motivo<input name="motivo" required minLength={3} /></label><div className="acciones"><button type="button" onClick={() => setReemplazo(null)}>Cancelar</button><button className="primario">Confirmar reemplazo</button></div></form>}
      <section className="tarjeta"><h2>Historial reciente</h2>{datos.eventos.length ? <ol className="historial-contactos">{datos.eventos.map((e, i) => <li key={`${e.momento}-${i}`}><strong>{e.tipo.replaceAll("_", " ")}</strong><span>{e.telefono} · {e.actor}</span><time>{new Date(e.momento).toLocaleString("es-AR")}</time></li>)}</ol> : <Vacio>Sin movimientos.</Vacio>}</section>
    </section>}
  </>;
}
