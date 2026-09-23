"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Vacio } from "./compartidos";

type Contacto = { telefono: string; tareas: string[]; activo: boolean; origen: string; alta_por: string; alta_en: string };
type Evento = { telefono: string; tipo: string; actor: string; momento: string; detalle?: { motivo?: string } };
type Resultado = { contactos: Contacto[]; eventos: Evento[]; tareas_disponibles: string[] };
type Pendiente = { id: number; telefono_crudo: string; telefono?: string; nombre_excel: string; sucursal?: string; motivo: string; entregas: number };
type Productor = { clientecuit: string; razonsocial: string; codigos: string[] };
type Guardia = { usuario: string; nombre: string; sede: string; activo: boolean; ultimo_ingreso?: string };

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
  const [pendientes, setPendientes] = useState<Pendiente[]>([]);
  const [resolviendo, setResolviendo] = useState<Pendiente | null>(null);
  const [consulta, setConsulta] = useState("");
  const [productores, setProductores] = useState<Productor[]>([]);
  const [guardias, setGuardias] = useState<Guardia[]>([]);
  const [claveTemporal, setClaveTemporal] = useState<{ usuario: string; clave_temporal: string } | null>(null);

  async function cargarPendientes() {
    try { setPendientes(await api<Pendiente[]>("contactos/pendientes/lista")); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudieron cargar los pendientes."); }
  }

  async function cargarGuardias() {
    try { setGuardias(await api<Guardia[]>("guardias")); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudieron cargar los guardias."); }
  }

  useEffect(() => { void cargarPendientes(); void cargarGuardias(); }, []);

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

  async function alta(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setError("");
    const tareas = f.getAll("tareas");
    try {
      await api(`contactos/${encodeURIComponent(cuit)}`, { method: "POST", body: JSON.stringify({ telefono: f.get("telefono"), tareas, motivo: f.get("motivo") }) });
      e.currentTarget.reset(); await buscar();
    } catch (x) { setError(x instanceof Error ? x.message : "No se pudo dar de alta."); }
  }

  async function buscarProductores(valor: string) {
    setConsulta(valor);
    if (valor.trim().length < 2) { setProductores([]); return; }
    try { setProductores(await api<Productor[]>(`contactos/productores/buscar?q=${encodeURIComponent(valor)}`)); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo buscar productores."); }
  }

  async function resolver(productor: Productor) {
    if (!resolviendo) return;
    try {
      await api(`contactos/pendientes/${resolviendo.id}/resolver?clientecuit=${encodeURIComponent(productor.clientecuit)}`, { method: "POST", body: JSON.stringify({ telefono: resolviendo.telefono ?? resolviendo.telefono_crudo, tareas: ["ver_informes", "pedir_turnos", "administrar_contactos"], motivo: "vinculado por la bodega" }) });
      setResolviendo(null); setConsulta(""); setProductores([]); await cargarPendientes();
    } catch (x) { setError(x instanceof Error ? x.message : "No se pudo resolver el pendiente."); }
  }

  async function descartar(p: Pendiente) {
    const nota = window.prompt("Motivo para descartarlo"); if (!nota) return;
    try { await api(`contactos/pendientes/${p.id}/descartar`, { method: "POST", body: JSON.stringify({ nota }) }); await cargarPendientes(); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo descartar."); }
  }

  async function crearGuardia(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const formulario = e.currentTarget; const f = new FormData(formulario);
    try {
      setClaveTemporal(await api("guardias", { method: "POST", body: JSON.stringify({ usuario: f.get("usuario"), nombre: f.get("nombre"), sede: f.get("sede") }) }));
      formulario.reset(); await cargarGuardias();
    } catch (x) { setError(x instanceof Error ? x.message : "No se pudo crear el guardia."); }
  }

  async function bajaGuardia(usuario: string) {
    if (!window.confirm(`¿Deshabilitar a ${usuario}? Sus sesiones se cerrarán.`)) return;
    try { await api(`guardias/${usuario}`, { method: "DELETE" }); await cargarGuardias(); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo deshabilitar."); }
  }

  return <>
    <section className="tarjeta contacto-busqueda"><div className="titulo-fila"><div><h2>Contactos de un productor</h2><p className="ayuda">Buscá por CUIT para revisar accesos o agregar un teléfono.</p></div>{pendientes.length > 0 && <span className="estado">{pendientes.length} pendientes</span>}</div><form className="form-linea" onSubmit={buscar}><label>CUIT<input value={cuit} onChange={e => setCuit(e.target.value)} placeholder="20-12345678-9" required /></label><button className="primario">Ver contactos</button></form></section>
    {error && <ErrorVisible mensaje={error} />}
    {datos && <section className="contactos-operacion"><form className="tarjeta alta-contacto" onSubmit={alta}><div><h2>Agregar contacto</h2><p className="ayuda">El teléfono se normaliza al formato de WhatsApp y el alta se publica inmediatamente.</p></div><label>Teléfono<input name="telefono" inputMode="tel" placeholder="0264 15 456-7890" required /></label><fieldset><legend>Tareas iniciales</legend>{datos.tareas_disponibles.map(t => <label key={t}><input name="tareas" type="checkbox" value={t} defaultChecked />{etiquetas[t]}</label>)}</fieldset><label>Motivo<input name="motivo" required minLength={3} placeholder="Pedido por el productor" /></label><button className="primario">Dar de alta</button></form><div className="titulo-fila"><div><h2>Accesos habilitados</h2><p className="ayuda">Los cambios se aplican sobre este CUIT y quedan en el historial.</p></div><span className="estado">{datos.contactos.filter(c => c.activo).length} activos</span></div>
      <div className="contactos-lista">{datos.contactos.length ? datos.contactos.map(c => <article className={`contacto-fila ${c.activo ? "" : "contacto-inactivo"}`} key={c.telefono}><div><strong>{c.telefono}</strong><small>{c.activo ? `Alta: ${c.origen}` : "Dado de baja"}</small></div><fieldset disabled={!c.activo}><legend>Tareas permitidas</legend>{datos.tareas_disponibles.map(t => <label key={t}><input type="checkbox" checked={c.tareas.includes(t)} onChange={e => cambiar(c, t, e.target.checked)} />{etiquetas[t]}</label>)}</fieldset>{c.activo && c.tareas.includes("administrar_contactos") && <button onClick={() => setReemplazo(c.telefono)}>Reemplazar administrador</button>}</article>) : <Vacio />}</div>
      {reemplazo && <form className="tarjeta reemplazo" onSubmit={reemplazar}><div><h2>Reemplazar administrador</h2><p>El teléfono anterior perderá acceso en la misma operación.</p></div><label>Administrador anterior<input value={reemplazo} readOnly /></label><label>Teléfono nuevo<input name="nuevo" inputMode="tel" required pattern="[0-9]{8,20}" /></label><label>Motivo<input name="motivo" required minLength={3} /></label><div className="acciones"><button type="button" onClick={() => setReemplazo(null)}>Cancelar</button><button className="primario">Confirmar reemplazo</button></div></form>}
      <section className="tarjeta"><h2>Historial reciente</h2>{datos.eventos.length ? <ol className="historial-contactos">{datos.eventos.map((e, i) => <li key={`${e.momento}-${i}`}><strong>{e.tipo.replaceAll("_", " ")}</strong><span>{e.telefono} · {e.actor}</span><time>{new Date(e.momento).toLocaleString("es-AR")}</time></li>)}</ol> : <Vacio>Sin movimientos.</Vacio>}</section>
    </section>}
    <section className="tarjeta pendientes-contactos"><div className="titulo-fila"><div><h2>Teléfonos por vincular</h2><p className="ayuda">Ordenados por cantidad estimada de entregas. Elegí el productor correcto o descartá el registro.</p></div><span className="estado">{pendientes.length}</span></div>{pendientes.length ? <div className="contactos-lista">{pendientes.map(p => <article className="contacto-fila" key={p.id}><div><strong>{p.nombre_excel}</strong><small>{p.telefono_crudo} · {p.sucursal || "Sin sucursal"} · {p.entregas} entregas</small></div><div className="acciones"><button onClick={() => { setResolviendo(p); setConsulta(p.nombre_excel); void buscarProductores(p.nombre_excel); }}>Vincular</button><button className="peligro" onClick={() => void descartar(p)}>Descartar</button></div></article>)}</div> : <Vacio>No quedan teléfonos pendientes.</Vacio>}{resolviendo && <section className="resolver-pendiente"><div className="titulo-fila"><div><h2>Vincular a {resolviendo.nombre_excel}</h2><p className="ayuda">Sólo se crea el acceso cuando elegís un resultado.</p></div><button onClick={() => setResolviendo(null)}>Cancelar</button></div><label>Buscar productor<input value={consulta} onChange={e => void buscarProductores(e.target.value)} autoFocus /></label><div className="contactos-lista">{productores.map(p => <button className="resultado-productor" key={p.clientecuit} onClick={() => void resolver(p)}><strong>{p.razonsocial}</strong><small>{p.codigos.join(", ")} · CUIT {p.clientecuit}</small></button>)}</div></section>}</section>
    <section className="tarjeta pendientes-contactos"><div><h2>Guardias y tablets</h2><p className="ayuda">Cada usuario opera una sola sede. La clave temporal se muestra una vez y debe cambiarse al ingresar.</p></div><form className="form-linea" onSubmit={crearGuardia}><label>Usuario<input name="usuario" pattern="[a-z0-9._-]{3,30}" required /></label><label>Nombre<input name="nombre" minLength={3} required /></label><label>Sede<select name="sede"><option value="chimbas">Chimbas</option><option value="lavalle">Lavalle</option><option value="media-agua">Media Agua</option></select></label><button className="primario">Crear guardia</button></form>{claveTemporal && <div className="tarjeta clave-temporal"><strong>Clave temporal de {claveTemporal.usuario}</strong><code>{claveTemporal.clave_temporal}</code><p className="ayuda">Copiala ahora: no vuelve a mostrarse.</p></div>}<div className="contactos-lista">{guardias.map(g => <article className={`contacto-fila ${g.activo ? "" : "contacto-inactivo"}`} key={g.usuario}><div><strong>{g.nombre}</strong><small>{g.usuario} · {g.sede} · {g.activo ? "Activo" : "Inactivo"}</small></div>{g.activo && <button className="peligro" onClick={() => void bajaGuardia(g.usuario)}>Deshabilitar</button>}</article>)}</div></section>
  </>;
}
