"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible } from "./compartidos";

type Mensaje = { id: string; de: "productor" | "bot"; texto: string; hora: string };
type Telefono = { telefono: string };

const hora = (valor?: string) => (valor ? new Date(valor) : new Date()).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });

export function SimuladorBot() {
  const [habilitado, setHabilitado] = useState<boolean | null>(null);
  const [telefonos, setTelefonos] = useState<Telefono[]>([]); const [telefono, setTelefono] = useState("");
  const [mensajes, setMensajes] = useState<Mensaje[]>([]); const [texto, setTexto] = useState(""); const [error, setError] = useState("");
  const ultimo = useRef(0); const fondo = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<{ habilitado: boolean }>("simulador-bot/estado").then((e) => {
      setHabilitado(e.habilitado);
      if (e.habilitado) api<Telefono[]>("simulador-bot/telefonos").then((t) => { setTelefonos(t); if (t[0]) setTelefono(t[0].telefono); }).catch(() => null);
    }).catch(() => setHabilitado(false));
  }, []);

  useEffect(() => {
    if (!telefono) return;
    setMensajes([]); ultimo.current = 0;
    let vivo = true;
    const leer = async () => {
      try {
        const nuevos = await api<Array<{ id: number; texto: string; creado_en: string }>>(`simulador-bot/respuestas?telefono=${telefono}&desde_id=${ultimo.current}`);
        if (!vivo || !nuevos.length) return;
        ultimo.current = nuevos[nuevos.length - 1].id;
        setMensajes((m) => [...m, ...nuevos.map((n) => ({ id: `b${n.id}`, de: "bot" as const, texto: n.texto, hora: hora(n.creado_en) }))]);
      } catch { /* se reintenta en la próxima vuelta */ }
    };
    // Al cambiar de teléfono se arranca desde lo último, sin repetir conversaciones viejas.
    api<Array<{ id: number }>>(`simulador-bot/respuestas?telefono=${telefono}&desde_id=0`).then((viejos) => { if (viejos.length) ultimo.current = viejos[viejos.length - 1].id; }).catch(() => null);
    const reloj = window.setInterval(leer, 1500);
    return () => { vivo = false; window.clearInterval(reloj); };
  }, [telefono]);

  useEffect(() => { fondo.current?.scrollIntoView({ block: "end" }); }, [mensajes]);

  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const t = texto.trim(); if (!t || !telefono) return; setError("");
    setMensajes((m) => [...m, { id: `p${Date.now()}`, de: "productor", texto: t, hora: hora() }]); setTexto("");
    try { await api("simulador-bot/enviar", { method: "POST", body: JSON.stringify({ telefono, texto: t }) }); } catch (x) { setError(x instanceof Error ? x.message : "No se pudo enviar."); }
  }

  if (habilitado === null) return <section className="tarjeta"><p className="ayuda">Conectando con el bot…</p></section>;
  if (!habilitado) return <section className="tarjeta"><h2>Simulador del bot</h2><p className="ayuda">El simulador no está habilitado en este servidor.</p></section>;
  return <section className="tarjeta simulador">
    <div className="titulo-fila"><div><h2>Simulador de WhatsApp</h2><p className="ayuda">Escribile al bot como si fueras el productor. Nada sale por WhatsApp de verdad: las respuestas aparecen acá. Probá con «Hola» o «Pedir turno».</p></div>
      <label>Teléfono de prueba<select value={telefono} onChange={(e) => setTelefono(e.target.value)}>{telefonos.map((t) => <option key={t.telefono} value={t.telefono}>{t.telefono}</option>)}</select></label></div>
    {error && <ErrorVisible mensaje={error} />}
    <div className="chat" aria-live="polite">{mensajes.length ? mensajes.map((m) => <div key={m.id} className={`burbuja burbuja-${m.de}`}><span>{m.texto}</span><small>{m.hora}</small></div>) : <p className="ayuda chat-vacio">Escribí un mensaje para empezar.</p>}<div ref={fondo} /></div>
    <form className="chat-envio" onSubmit={enviar}><input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Escribí un mensaje" maxLength={1000} aria-label="Mensaje" /><button className="primario" disabled={!texto.trim()}>Enviar</button></form>
    <div className="atajos">{["Hola", "Pedir turno", "Mis turnos", "1", "2", "3", "Sí", "No"].map((a) => <button key={a} type="button" onClick={() => setTexto(a)}>{a}</button>)}</div>
  </section>;
}
