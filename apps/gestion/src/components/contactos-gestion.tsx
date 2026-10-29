"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Confirmacion, ErrorVisible, Tabla, Vacio, Ventana } from "./compartidos";

type Contacto = { telefono: string; tareas: string[]; activo: boolean; origen: string; alta_por: string; alta_en: string };
type Evento = { telefono: string; tipo: string; actor: string; momento: string; detalle?: { motivo?: string } };
type Resultado = { contactos: Contacto[]; eventos: Evento[]; tareas_disponibles: string[] };
type Pendiente = { id: number; telefono_crudo: string; telefono?: string; nombre_excel: string; sucursal?: string; motivo: string; entregas: number };
type Productor = Record<string, unknown> & { clientecuit: string; razonsocial: string; codigos: string[]; ultima_entrega: string | null; contactos?: number };
type Guardia = Record<string, unknown> & { usuario: string; nombre: string; sede: string; activo: boolean; debe_cambiar_clave: boolean; creado_por: string; creado_en: string; ultimo_ingreso: string | null };
type EventoGuardia = { tipo: string; actor: string; momento: string; detalle: { antes?: { nombre: string; sede: string }; despues?: { nombre: string; sede: string } } | null };
type Clave = { usuario: string; clave_temporal: string };

const etiquetas: Record<string, string> = {
  ver_informes: "Ver informes",
  pedir_turnos: "Pedir turnos",
  administrar_contactos: "Administrar contactos",
};
const SEDES: Record<string, string> = { chimbas: "Chimbas", lavalle: "Lavalle", "media-agua": "Media Agua" };
const EVENTOS_GUARDIA: Record<string, string> = { alta: "Alta", cambio: "Cambio de datos", nueva_clave: "Clave nueva", baja: "Deshabilitada", reactivada: "Reactivada" };
const cuitLegible = (c: string) => c.length === 11 ? `${c.slice(0, 2)}-${c.slice(2, 10)}-${c.slice(10)}` : c;
const fecha = (v: string | null) => v ? new Date(v).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "Nunca";
const mensaje = (x: unknown, defecto: string) => x instanceof Error ? x.message : defecto;

function ClaveTemporal({ clave }: { clave: Clave }) {
  return <div className="tarjeta clave-temporal"><strong>Clave temporal de {clave.usuario}</strong><code>{clave.clave_temporal}</code><p className="ayuda">Copiala ahora: no vuelve a mostrarse. Al ingresar en la tablet se pide cambiarla.</p></div>;
}

/** Ventana de un productor: sus celulares, qué puede hacer cada uno, altas, bajas e historial. */
function VentanaProductor({ productor, cerrar, cambio }: { productor: Productor; cerrar: () => void; cambio: () => void }) {
  const cuit = productor.clientecuit;
  const [datos, setDatos] = useState<Resultado | null>(null); const [error, setError] = useState("");
  const [agregando, setAgregando] = useState(false); const [reemplazo, setReemplazo] = useState<string | null>(null);
  const [baja, setBaja] = useState<string | null>(null); const [errorVentana, setErrorVentana] = useState("");

  async function cargar() {
    try { setDatos(await api<Resultado>(`contactos/${encodeURIComponent(cuit)}`)); }
    catch (x) { setError(mensaje(x, "No se pudieron leer los contactos.")); }
  }
  useEffect(() => { void cargar(); }, [cuit]);

  async function hecho() { await cargar(); cambio(); }

  async function cambiarTarea(contacto: Contacto, tarea: string, activa: boolean) {
    setError("");
    const tareas = activa ? [...new Set([...contacto.tareas, tarea])] : contacto.tareas.filter(t => t !== tarea);
    try { await api(`contactos/${cuit}/${contacto.telefono}/tareas`, { method: "PUT", body: JSON.stringify({ tareas }) }); await hecho(); }
    catch (x) { setError(mensaje(x, "No se pudo cambiar el permiso.")); }
  }

  async function alta(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setErrorVentana("");
    try {
      await api(`contactos/${encodeURIComponent(cuit)}`, { method: "POST", body: JSON.stringify({ telefono: f.get("telefono"), tareas: f.getAll("tareas"), motivo: f.get("motivo") }) });
      setAgregando(false); await hecho();
    } catch (x) { setErrorVentana(mensaje(x, "No se pudo dar de alta.")); }
  }

  async function reemplazar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setErrorVentana("");
    try {
      await api(`contactos/${cuit}/reemplazar`, { method: "POST", body: JSON.stringify({ anterior: reemplazo, nuevo: f.get("nuevo"), motivo: f.get("motivo") }) });
      setReemplazo(null); await hecho();
    } catch (x) { setErrorVentana(mensaje(x, "No se pudo reemplazar.")); }
  }

  async function darDeBaja(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setErrorVentana("");
    try {
      await api(`contactos/${cuit}/${baja}/baja`, { method: "POST", body: JSON.stringify({ motivo: f.get("motivo") }) });
      setBaja(null); await hecho();
    } catch (x) { setErrorVentana(mensaje(x, "No se pudo dar de baja.")); }
  }

  const abrir = (accion: () => void) => { setErrorVentana(""); accion(); };
  const activos = datos?.contactos.filter(c => c.activo).length ?? 0;

  return <Ventana titulo={productor.razonsocial} tamano="amplia" cerrar={cerrar}>
    <div className="titulo-fila"><p className="ayuda">CUIT {cuitLegible(cuit)} · {productor.codigos.join(", ")} · {activos} {activos === 1 ? "celular activo" : "celulares activos"}. Los cambios llegan al bot en unos minutos.</p>
      <button className="primario" onClick={() => abrir(() => setAgregando(true))}>Agregar celular</button></div>
    {error && <ErrorVisible mensaje={error} />}
    {!datos ? <p className="ayuda">Cargando…</p> : <>
      <div className="contactos-lista">{datos.contactos.length ? datos.contactos.map(c => <article className={`contacto-fila ${c.activo ? "" : "contacto-inactivo"}`} key={c.telefono}>
        <div><strong>{c.telefono}</strong><small>{c.activo ? `Alta: ${c.origen.replaceAll("_", " ")} · ${c.alta_por}` : "Dado de baja"}</small></div>
        <fieldset disabled={!c.activo}><legend>Puede</legend>{datos.tareas_disponibles.map(t => <label key={t}><input type="checkbox" checked={c.tareas.includes(t)} onChange={e => void cambiarTarea(c, t, e.target.checked)} />{etiquetas[t]}</label>)}</fieldset>
        {c.activo && <div className="acciones">{c.tareas.includes("administrar_contactos") && <button onClick={() => abrir(() => setReemplazo(c.telefono))}>Reemplazar</button>}<button className="peligro" onClick={() => abrir(() => setBaja(c.telefono))}>Dar de baja</button></div>}
      </article>) : <Vacio>Este productor todavía no tiene celulares cargados.</Vacio>}</div>
      <h3>Historial</h3>
      {datos.eventos.length ? <ol className="historial-contactos">{datos.eventos.map((e, i) => <li key={`${e.momento}-${i}`}><strong>{e.tipo.replaceAll("_", " ")}</strong><span>{e.telefono} · {e.actor}{e.detalle?.motivo ? ` · ${e.detalle.motivo}` : ""}</span><time>{fecha(e.momento)}</time></li>)}</ol> : <Vacio>Sin movimientos.</Vacio>}
    </>}
    {agregando && datos && <Ventana titulo="Agregar celular" tamano="chica" cerrar={() => setAgregando(false)}><form className="formulario-ventana" onSubmit={alta}>
      {errorVentana && <ErrorVisible mensaje={errorVentana} />}
      <label>Celular<input name="telefono" inputMode="tel" placeholder="264 15 456-7890" required autoFocus /></label>
      <fieldset className="opciones-tipo"><legend>Puede</legend>{datos.tareas_disponibles.map(t => <label key={t}><input name="tareas" type="checkbox" value={t} defaultChecked />{etiquetas[t]}</label>)}</fieldset>
      <label>Motivo<input name="motivo" required minLength={3} placeholder="Pedido por el productor" /></label>
      <div className="acciones"><button type="button" onClick={() => setAgregando(false)}>Cancelar</button><button className="primario">Agregar</button></div>
    </form></Ventana>}
    {reemplazo && <Ventana titulo="Reemplazar administrador" tamano="chica" cerrar={() => setReemplazo(null)}><form className="formulario-ventana" onSubmit={reemplazar}>
      <p className="ayuda">El celular {reemplazo} pierde el acceso en la misma operación.</p>
      {errorVentana && <ErrorVisible mensaje={errorVentana} />}
      <label>Celular nuevo<input name="nuevo" inputMode="tel" required pattern="[0-9]{8,20}" placeholder="5492644567890" autoFocus /></label>
      <label>Motivo<input name="motivo" required minLength={3} /></label>
      <div className="acciones"><button type="button" onClick={() => setReemplazo(null)}>Cancelar</button><button className="primario">Reemplazar</button></div>
    </form></Ventana>}
    {baja && <Ventana titulo="Dar de baja un celular" tamano="chica" cerrar={() => setBaja(null)}><form className="formulario-ventana" onSubmit={darDeBaja}>
      <p className="ayuda">El celular {baja} deja de poder usar el bot para este productor.</p>
      {errorVentana && <ErrorVisible mensaje={errorVentana} />}
      <label>Motivo<input name="motivo" required minLength={3} autoFocus /></label>
      <div className="acciones"><button type="button" onClick={() => setBaja(null)}>Cancelar</button><button className="peligro">Dar de baja</button></div>
    </form></Ventana>}
  </Ventana>;
}

function VentanaNuevaTablet({ cerrar, creada }: { cerrar: () => void; creada: () => void }) {
  const [error, setError] = useState(""); const [clave, setClave] = useState<Clave | null>(null);
  async function crear(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setError("");
    try { setClave(await api<Clave>("guardias", { method: "POST", body: JSON.stringify({ usuario: f.get("usuario"), nombre: f.get("nombre"), sede: f.get("sede") }) })); creada(); }
    catch (x) { setError(mensaje(x, "No se pudo crear la tablet.")); }
  }
  return <Ventana titulo="Nueva tablet de guardia" tamano="chica" cerrar={cerrar}>
    {clave ? <><ClaveTemporal clave={clave} /><div className="acciones"><button className="primario" onClick={cerrar}>Listo</button></div></>
      : <form className="formulario-ventana" onSubmit={crear}>
        {error && <ErrorVisible mensaje={error} />}
        <label>Usuario<input name="usuario" pattern="[a-z0-9._-]{3,30}" title="Minúsculas, números, punto o guion" required autoFocus /></label>
        <label>Nombre<input name="nombre" minLength={3} required placeholder="Tablet portón Chimbas" /></label>
        <label>Bodega<select name="sede">{Object.entries(SEDES).map(([s, n]) => <option key={s} value={s}>{n}</option>)}</select></label>
        <div className="acciones"><button type="button" onClick={cerrar}>Cancelar</button><button className="primario">Crear</button></div>
      </form>}
  </Ventana>;
}

function VentanaTablet({ guardia, cerrar, cambio }: { guardia: Guardia; cerrar: () => void; cambio: () => void }) {
  const [nombre, setNombre] = useState(guardia.nombre); const [sede, setSede] = useState(guardia.sede);
  const [error, setError] = useState(""); const [clave, setClave] = useState<Clave | null>(null);
  const [eventos, setEventos] = useState<EventoGuardia[]>([]); const [confirmar, setConfirmar] = useState<"baja" | "clave" | null>(null);
  const cargarHistorial = () => api<EventoGuardia[]>(`guardias/${guardia.usuario}/historial`).then(setEventos).catch(() => setEventos([]));
  useEffect(() => { void cargarHistorial(); }, [guardia.usuario]);

  async function accion(hacer: () => Promise<unknown>, defecto: string) {
    setError("");
    try { await hacer(); cambio(); void cargarHistorial(); } catch (x) { setError(mensaje(x, defecto)); }
  }
  const guardar = () => accion(() => api(`guardias/${guardia.usuario}`, { method: "PUT", body: JSON.stringify({ nombre, sede }) }), "No se pudo guardar.");
  const nuevaClave = () => accion(async () => setClave(await api<Clave>(`guardias/${guardia.usuario}/clave`, { method: "POST" })), "No se pudo generar la clave.");
  const deshabilitar = () => accion(() => api(`guardias/${guardia.usuario}/baja`, { method: "POST" }), "No se pudo deshabilitar.");

  return <Ventana titulo={guardia.nombre} cerrar={cerrar}>
    {error && <ErrorVisible mensaje={error} />}
    {clave && <ClaveTemporal clave={clave} />}
    <dl className="ficha">
      <div><dt>Usuario</dt><dd>{guardia.usuario}</dd></div>
      <div><dt>Estado</dt><dd>{guardia.activo ? (guardia.debe_cambiar_clave ? "Activa · falta cambiar la clave" : "Activa") : "Deshabilitada"}</dd></div>
      <div><dt>Último ingreso</dt><dd>{fecha(guardia.ultimo_ingreso)}</dd></div>
      <div><dt>Creada por</dt><dd>{guardia.creado_por} · {fecha(guardia.creado_en)}</dd></div>
    </dl>
    <div className="form-linea">
      <label>Nombre<input value={nombre} onChange={(e) => setNombre(e.target.value)} minLength={3} /></label>
      <label>Bodega<select value={sede} onChange={(e) => setSede(e.target.value)}>{Object.entries(SEDES).map(([s, n]) => <option key={s} value={s}>{n}</option>)}</select></label>
    </div>
    {sede !== guardia.sede && <p className="ayuda">Al cambiar de bodega se cierra la sesión abierta en la tablet.</p>}
    <div className="acciones">
      {guardia.activo && <button className="peligro" onClick={() => setConfirmar("baja")}>Deshabilitar</button>}
      <button onClick={() => setConfirmar("clave")}>{guardia.activo ? "Clave nueva" : "Reactivar con clave nueva"}</button>
      <button className="primario" disabled={nombre.trim() === guardia.nombre && sede === guardia.sede} onClick={() => void guardar()}>Guardar cambios</button>
    </div>
    <h3>Historial</h3>
    {eventos.length ? <ul className="historial">{eventos.map((e, i) => <li key={i}><strong>{EVENTOS_GUARDIA[e.tipo] ?? e.tipo}</strong> · {e.actor} · {fecha(e.momento)}{e.detalle?.antes && e.detalle.despues ? ` · ${e.detalle.antes.nombre} (${SEDES[e.detalle.antes.sede] ?? e.detalle.antes.sede}) → ${e.detalle.despues.nombre} (${SEDES[e.detalle.despues.sede] ?? e.detalle.despues.sede})` : ""}</li>)}</ul> : <Vacio>Sin movimientos registrados.</Vacio>}
    <Confirmacion abierto={confirmar === "baja"} titulo="Deshabilitar tablet" detalle={`${guardia.nombre} deja de poder ingresar y se cierra su sesión.`} cancelar={() => setConfirmar(null)} confirmar={() => { setConfirmar(null); void deshabilitar(); }} />
    <Confirmacion abierto={confirmar === "clave"} titulo="Clave nueva" detalle="La clave actual deja de servir y se cierra la sesión abierta en la tablet." cancelar={() => setConfirmar(null)} confirmar={() => { setConfirmar(null); void nuevaClave(); }} />
  </Ventana>;
}

export function ContactosGestion() {
  const [productores, setProductores] = useState<Productor[] | null>(null); const [errorProductores, setErrorProductores] = useState("");
  const [productor, setProductor] = useState<Productor | null>(null);
  const [pendientes, setPendientes] = useState<Pendiente[]>([]);
  const [resolviendo, setResolviendo] = useState<Pendiente | null>(null); const [descartando, setDescartando] = useState<Pendiente | null>(null);
  const [consulta, setConsulta] = useState(""); const [resultados, setResultados] = useState<Productor[]>([]);
  const [guardias, setGuardias] = useState<Guardia[] | null>(null); const [errorGuardias, setErrorGuardias] = useState("");
  const [nuevaTablet, setNuevaTablet] = useState(false); const [guardia, setGuardia] = useState<Guardia | null>(null);
  const [errorVentana, setErrorVentana] = useState("");

  async function cargarProductores() {
    try { setProductores(await api<Productor[]>("contactos/productores/lista")); setErrorProductores(""); }
    catch (x) { setProductores([]); setErrorProductores(mensaje(x, "No se pudieron leer los productores.")); }
  }
  async function cargarPendientes() {
    try { setPendientes(await api<Pendiente[]>("contactos/pendientes/lista")); } catch { setPendientes([]); }
  }
  async function cargarGuardias() {
    try {
      const lista = await api<Guardia[]>("guardias"); setGuardias(lista); setErrorGuardias("");
      // La ventana abierta sigue mostrando la tablet con sus datos nuevos.
      setGuardia((abierta) => abierta && (lista.find((g) => g.usuario === abierta.usuario) ?? null));
    } catch (x) { setGuardias([]); setErrorGuardias(mensaje(x, "No se pudieron leer las tablets.")); }
  }
  useEffect(() => { void cargarProductores(); void cargarPendientes(); void cargarGuardias(); }, []);

  async function buscarProductores(valor: string) {
    setConsulta(valor);
    if (valor.trim().length < 2) { setResultados([]); return; }
    try { setResultados(await api<Productor[]>(`contactos/productores/buscar?q=${encodeURIComponent(valor)}`)); }
    catch (x) { setErrorVentana(mensaje(x, "No se pudo buscar productores.")); }
  }

  async function resolver(elegido: Productor) {
    if (!resolviendo) return; setErrorVentana("");
    try {
      await api(`contactos/pendientes/${resolviendo.id}/resolver?clientecuit=${encodeURIComponent(elegido.clientecuit)}`, { method: "POST", body: JSON.stringify({ telefono: resolviendo.telefono ?? resolviendo.telefono_crudo, tareas: ["ver_informes", "pedir_turnos", "administrar_contactos"], motivo: "vinculado por la bodega" }) });
      cerrarResolver(); await cargarPendientes(); await cargarProductores();
    } catch (x) { setErrorVentana(mensaje(x, "No se pudo vincular el teléfono.")); }
  }

  async function descartar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!descartando) return; setErrorVentana("");
    const nota = String(new FormData(e.currentTarget).get("nota") || "");
    try { await api(`contactos/pendientes/${descartando.id}/descartar`, { method: "POST", body: JSON.stringify({ nota }) }); setDescartando(null); await cargarPendientes(); }
    catch (x) { setErrorVentana(mensaje(x, "No se pudo descartar.")); }
  }

  function cerrarResolver() { setResolviendo(null); setConsulta(""); setResultados([]); setErrorVentana(""); }

  return <>
    <section className="tarjeta">
      <div className="titulo-fila"><div><h2>Productores</h2><p className="ayuda">Tocá un productor para ver sus celulares, cambiar qué puede hacer cada uno, agregar o dar de baja.</p></div></div>
      {errorProductores && <ErrorVisible mensaje={errorProductores} />}
      {productores === null ? <p className="ayuda">Cargando…</p> : productores.length ? <Tabla etiqueta="Productores" filas={productores} porPagina={15} alElegir={setProductor} columnas={[
        { clave: "razonsocial", titulo: "Productor" },
        { clave: "codigos", titulo: "Códigos", valor: (p) => p.codigos.join(", ") },
        { clave: "clientecuit", titulo: "CUIT", valor: (p) => cuitLegible(p.clientecuit) },
        { clave: "contactos", titulo: "Celulares", valor: (p) => p.contactos ? String(p.contactos) : "Ninguno" },
        { clave: "ultima_entrega", titulo: "Última entrega", valor: (p) => p.ultima_entrega ? new Date(`${p.ultima_entrega}T12:00:00`).toLocaleDateString("es-AR") : "—" },
      ]} /> : !errorProductores && <Vacio>Todavía no hay productores.</Vacio>}
    </section>

    {pendientes.length > 0 && <section className="tarjeta pendientes-contactos"><div className="titulo-fila"><div><h2>Teléfonos por vincular</h2><p className="ayuda">Ordenados por cantidad estimada de entregas. Elegí el productor correcto o descartá el registro.</p></div><span className="estado">{pendientes.length}</span></div>
      <div className="contactos-lista">{pendientes.map(p => <article className="contacto-fila" key={p.id}><div><strong>{p.nombre_excel}</strong><small>{p.telefono_crudo} · {p.sucursal || "Sin sucursal"} · {p.entregas} entregas</small></div><div className="acciones"><button onClick={() => { setErrorVentana(""); setResolviendo(p); void buscarProductores(p.nombre_excel); }}>Vincular</button><button className="peligro" onClick={() => { setErrorVentana(""); setDescartando(p); }}>Descartar</button></div></article>)}</div></section>}

    <section className="tarjeta">
      <div className="titulo-fila"><div><h2>Tablets de guardia</h2><p className="ayuda">Usuarios de la consola del portón. Cada tablet opera una sola bodega. Tocá una para cambiar sus datos, darle una clave nueva o deshabilitarla.</p></div>
        <button className="primario" onClick={() => setNuevaTablet(true)}>Nueva tablet</button></div>
      {errorGuardias && <ErrorVisible mensaje={errorGuardias} />}
      {guardias === null ? <p className="ayuda">Cargando…</p> : guardias.length ? <Tabla etiqueta="Tablets de guardia" filas={guardias} alElegir={setGuardia} columnas={[
        { clave: "nombre", titulo: "Nombre" },
        { clave: "usuario", titulo: "Usuario" },
        { clave: "sede", titulo: "Bodega", valor: (g) => SEDES[g.sede] ?? g.sede },
        { clave: "activo", titulo: "Estado", valor: (g) => g.activo ? "Activa" : "Deshabilitada" },
        { clave: "ultimo_ingreso", titulo: "Último ingreso", valor: (g) => fecha(g.ultimo_ingreso) },
      ]} /> : !errorGuardias && <Vacio>Todavía no hay tablets.</Vacio>}
    </section>

    {productor && <VentanaProductor productor={productor} cerrar={() => setProductor(null)} cambio={() => void cargarProductores()} />}
    {nuevaTablet && <VentanaNuevaTablet cerrar={() => setNuevaTablet(false)} creada={() => void cargarGuardias()} />}
    {guardia && <VentanaTablet key={guardia.usuario} guardia={guardia} cerrar={() => setGuardia(null)} cambio={() => void cargarGuardias()} />}
    {resolviendo && <Ventana titulo={`Vincular a ${resolviendo.nombre_excel}`} cerrar={cerrarResolver}><p className="ayuda">Sólo se crea el acceso cuando elegís un resultado. Tocá el productor correcto.</p>{errorVentana && <ErrorVisible mensaje={errorVentana} />}<label>Buscar productor<input value={consulta} onChange={e => void buscarProductores(e.target.value)} autoFocus /></label><div className="contactos-lista">{resultados.length ? resultados.map(p => <button className="resultado-productor" key={p.clientecuit} onClick={() => void resolver(p)}><strong>{p.razonsocial}</strong><small>{p.codigos.join(", ")} · CUIT {p.clientecuit}</small></button>) : <Vacio>{consulta.trim().length < 2 ? "Escribí al menos dos letras para buscar." : "No hay productores que coincidan."}</Vacio>}</div><div className="acciones"><button onClick={cerrarResolver}>Cancelar</button></div></Ventana>}
    {descartando && <Ventana tamano="chica" titulo="Descartar teléfono" cerrar={() => setDescartando(null)}><form className="formulario-ventana" onSubmit={descartar}><p><strong>{descartando.nombre_excel}</strong> · {descartando.telefono_crudo}</p>{errorVentana && <ErrorVisible mensaje={errorVentana} />}<label>Motivo para descartarlo<input name="nota" required minLength={3} autoFocus /></label><div className="acciones"><button type="button" onClick={() => setDescartando(null)}>Cancelar</button><button className="peligro">Descartar</button></div></form></Ventana>}
  </>;
}
