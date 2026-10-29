"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Confirmacion, ErrorVisible, Tabla, Vacio, Ventana } from "./compartidos";

type Tipo = "personal" | "mando_medio";
type Registro = Record<string, unknown> & { telefono: string; legajo: string; nombre: string; empresa: string; tipo: Tipo; activo: boolean; alta_por: string; alta_en: string; actualizado_por: string; actualizado_en: string };
type Persona = { legajo: string; nombre: string; empresa: string; sector: string; puesto: string };
type Evento = { tipo: string; actor: string; antes: Partial<Registro> | null; despues: Partial<Registro> | null; momento: string };

const TIPOS: Record<Tipo, string> = { personal: "Personal", mando_medio: "Mando medio" };
const EVENTOS: Record<string, string> = { alta: "Alta", cambio: "Cambio", baja: "Baja" };
const celular = (t: string) => t.startsWith("549") ? `+54 9 ${t.slice(3, 6)} ${t.slice(6)}` : `+${t}`;
const fecha = (v: string) => new Date(v).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

function ElegirTipo({ valor, cambiar }: { valor: Tipo; cambiar: (t: Tipo) => void }) {
  return <fieldset className="opciones-tipo"><legend>Tipo</legend>{(Object.keys(TIPOS) as Tipo[]).map((t) => <label key={t}><input type="radio" name="tipo" checked={valor === t} onChange={() => cambiar(t)} />{TIPOS[t]}</label>)}</fieldset>;
}

function Alta({ cerrar, listo }: { cerrar: () => void; listo: () => void }) {
  const [consulta, setConsulta] = useState(""); const [resultados, setResultados] = useState<Persona[]>([]);
  const [persona, setPersona] = useState<Persona | null>(null); const [tipo, setTipo] = useState<Tipo>("personal");
  const [telefono, setTelefono] = useState(""); const [error, setError] = useState(""); const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    const q = consulta.trim(); if (q.length < 2 || persona) { setResultados([]); return; }
    const reloj = setTimeout(() => api<Persona[]>(`personal-bot/personas?q=${encodeURIComponent(q)}`).then(setResultados).catch(() => setResultados([])), 250);
    return () => clearTimeout(reloj);
  }, [consulta, persona]);

  async function guardar(e: FormEvent) {
    e.preventDefault(); if (!persona) return; setError(""); setGuardando(true);
    try { await api("personal-bot", { method: "POST", body: JSON.stringify({ telefono, legajo: persona.legajo, tipo }) }); listo(); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo guardar."); }
    finally { setGuardando(false); }
  }

  return <Ventana titulo="Agregar persona al bot" cerrar={cerrar}>
    <form className="formulario-ventana" onSubmit={guardar}>
      {error && <ErrorVisible mensaje={error} />}
      {persona
        ? <div className="persona-elegida"><div><strong>{persona.nombre}</strong><small>Legajo {persona.legajo} · {persona.empresa} · {persona.puesto || persona.sector}</small></div><button type="button" onClick={() => { setPersona(null); setConsulta(""); }}>Cambiar</button></div>
        : <><label>Buscar por legajo o apellido<input value={consulta} onChange={(e) => setConsulta(e.target.value)} autoFocus /></label>
          <div className="contactos-lista">{resultados.length ? resultados.map((p) => <button type="button" className="resultado-productor" key={p.legajo} onClick={() => setPersona(p)}><strong>{p.nombre}</strong><small>Legajo {p.legajo} · {p.empresa} · {p.puesto || p.sector}</small></button>) : <Vacio>{consulta.trim().length < 2 ? "Escribí al menos dos letras o el número de legajo." : "No hay personas que coincidan."}</Vacio>}</div></>}
      <label>Celular<input value={telefono} onChange={(e) => setTelefono(e.target.value)} inputMode="tel" placeholder="2644567890" required /></label>
      <p className="ayuda">Código de área y número, sin 0 ni 15. Un celular de un productor no se puede cargar acá.</p>
      <ElegirTipo valor={tipo} cambiar={setTipo} />
      <div className="acciones"><button type="button" onClick={cerrar}>Cancelar</button><button className="primario" disabled={!persona || guardando}>{guardando ? "Guardando…" : "Guardar"}</button></div>
    </form>
  </Ventana>;
}

function Detalle({ registro, cerrar, listo }: { registro: Registro; cerrar: () => void; listo: () => void }) {
  const [tipo, setTipo] = useState<Tipo>(registro.tipo); const [error, setError] = useState("");
  const [eventos, setEventos] = useState<Evento[]>([]); const [confirmarBaja, setConfirmarBaja] = useState(false);
  useEffect(() => { api<Evento[]>(`personal-bot/${registro.telefono}/historial`).then(setEventos).catch(() => setEventos([])); }, [registro.telefono]);

  async function enviar(ruta: string, cuerpo?: object) {
    setError("");
    try { await api(ruta, { method: "POST", body: cuerpo ? JSON.stringify(cuerpo) : undefined }); listo(); }
    catch (x) { setError(x instanceof Error ? x.message : "No se pudo guardar."); }
  }

  return <Ventana titulo={registro.nombre} cerrar={cerrar}>
    {error && <ErrorVisible mensaje={error} />}
    <dl className="ficha">
      <div><dt>Legajo</dt><dd>{registro.legajo}</dd></div>
      <div><dt>Empresa</dt><dd>{registro.empresa}</dd></div>
      <div><dt>Celular</dt><dd>{celular(registro.telefono)}</dd></div>
      <div><dt>Estado</dt><dd>{registro.activo ? "Activo" : "De baja"}</dd></div>
      <div><dt>Cargado por</dt><dd>{registro.alta_por} · {fecha(registro.alta_en)}</dd></div>
    </dl>
    <ElegirTipo valor={tipo} cambiar={setTipo} />
    <div className="acciones">
      {registro.activo && <button className="peligro" onClick={() => setConfirmarBaja(true)}>Dar de baja</button>}
      <button className="primario" disabled={registro.activo && tipo === registro.tipo} onClick={() => void enviar("personal-bot", { telefono: registro.telefono, legajo: registro.legajo, tipo })}>{registro.activo ? "Guardar cambio" : "Volver a dar de alta"}</button>
    </div>
    <h3>Historial</h3>
    {eventos.length ? <ul className="historial">{eventos.map((e, i) => <li key={i}><strong>{EVENTOS[e.tipo] ?? e.tipo}</strong> · {e.actor} · {fecha(e.momento)}{e.tipo === "cambio" && e.antes?.tipo && e.despues?.tipo && e.antes.tipo !== e.despues.tipo ? ` · ${TIPOS[e.antes.tipo]} → ${TIPOS[e.despues.tipo]}` : ""}</li>)}</ul> : <Vacio>Sin movimientos.</Vacio>}
    <Confirmacion abierto={confirmarBaja} titulo="Dar de baja" detalle={`El bot deja de reconocer a ${registro.nombre} en ${celular(registro.telefono)}.`} cancelar={() => setConfirmarBaja(false)} confirmar={() => { setConfirmarBaja(false); void enviar(`personal-bot/${registro.telefono}/baja`); }} />
  </Ventana>;
}

/** Personal de Juviar-ENAV que el bot reconoce por su celular. */
export function PersonalBot() {
  const [lista, setLista] = useState<Registro[] | null>(null); const [error, setError] = useState("");
  const [agregando, setAgregando] = useState(false); const [abierto, setAbierto] = useState<Registro | null>(null);

  async function cargar() {
    setError("");
    try { setLista(await api<Registro[]>("personal-bot")); }
    catch (x) { setLista([]); setError(x instanceof Error ? x.message : "No se pudo leer el personal."); }
  }
  useEffect(() => { void cargar(); }, []);

  return <section className="tarjeta">
    <div className="titulo-fila"><div><h2>Personal en el bot</h2><p className="ayuda">Celulares del personal y de los mandos medios. El bot los reconoce y los saluda por su nombre. Tocá una fila para cambiar el tipo o dar de baja.</p></div>
      <button className="primario" onClick={() => setAgregando(true)}>Agregar persona</button></div>
    {error && <ErrorVisible mensaje={error} />}
    {lista === null ? <p className="ayuda">Cargando…</p> : lista.length ? <Tabla etiqueta="Personal en el bot" filas={lista} porPagina={15} alElegir={setAbierto} columnas={[
      { clave: "nombre", titulo: "Nombre" },
      { clave: "legajo", titulo: "Legajo" },
      { clave: "empresa", titulo: "Empresa" },
      { clave: "tipo", titulo: "Tipo", valor: (r) => TIPOS[r.tipo] },
      { clave: "telefono", titulo: "Celular", valor: (r) => celular(r.telefono) },
      { clave: "activo", titulo: "Estado", valor: (r) => r.activo ? "Activo" : "De baja" },
    ]} /> : <Vacio>Todavía no hay personal cargado.</Vacio>}
    {agregando && <Alta cerrar={() => setAgregando(false)} listo={() => { setAgregando(false); void cargar(); }} />}
    {abierto && <Detalle registro={abierto} cerrar={() => setAbierto(null)} listo={() => { setAbierto(null); void cargar(); }} />}
  </section>;
}
