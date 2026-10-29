"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Tabla, Vacio, Ventana } from "./compartidos";

type Mensaje = { id: string; de: "persona" | "bot" | "aviso"; texto: string; hora: string };
type Telefono = { telefono: string };
type Conversacion = Record<string, unknown> & { telefono: string; nombre: string | null; quien: "productor" | "personal" | "mando_medio" | null; mensajes: number; ultimo_en: string; ultimo_texto: string };

const QUIEN = { productor: "Productor", personal: "Personal", mando_medio: "Mando medio" } as const;
const hora = (valor?: string) => (valor ? new Date(valor) : new Date()).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
const momento = (valor: string) => new Date(valor).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

function Burbujas({ mensajes, vacio }: { mensajes: Mensaje[]; vacio: string }) {
  const fondo = useRef<HTMLDivElement>(null);
  useEffect(() => { fondo.current?.scrollIntoView({ block: "end" }); }, [mensajes]);
  return <div className="chat" aria-live="polite">{mensajes.length ? mensajes.map((m) => <div key={m.id} className={`burbuja burbuja-${m.de}`}><span>{m.texto}</span><small>{m.hora}</small></div>) : <p className="chat-vacio">{vacio}</p>}<div ref={fondo} /></div>;
}

function IconoWhatsapp() {
  return <svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><path fill="currentColor" d="M12 2.2a9.8 9.8 0 0 0-8.4 14.8L2.3 21.7l4.8-1.3A9.8 9.8 0 1 0 12 2.2Zm0 1.8a8 8 0 1 1-4.2 14.8l-.3-.2-2.8.8.8-2.7-.2-.3A8 8 0 0 1 12 4Zm-3.4 4c-.2 0-.5 0-.7.3-.3.3-1 1-1 2.4s1 2.8 1.2 3c.1.2 2 3.2 5 4.4 2.5 1 3 .8 3.5.7.6 0 1.7-.7 2-1.4.2-.7.2-1.2.1-1.4l-.4-.3-2-1c-.3-.1-.5-.1-.7.2l-.9 1.1c-.2.2-.3.2-.6.1a6.6 6.6 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.5l-.9-2.2c-.2-.5-.4-.5-.6-.5h-.5Z" /></svg>;
}

/** Celular de prueba: escribe al bot como un teléfono de prueba y muestra lo que responde. */
function CelularBot({ telefonos, cerrar }: { telefonos: string[]; cerrar: () => void }) {
  const [telefono, setTelefono] = useState(telefonos[0] ?? "");
  const [mensajes, setMensajes] = useState<Mensaje[]>([]); const [texto, setTexto] = useState(""); const [error, setError] = useState("");
  const ultimo = useRef(0);

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

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") cerrar(); };
    document.addEventListener("keydown", tecla); return () => document.removeEventListener("keydown", tecla);
  }, [cerrar]);

  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const t = texto.trim(); if (!t || !telefono) return; setError("");
    setMensajes((m) => [...m, { id: `p${Date.now()}`, de: "persona", texto: t, hora: hora() }]); setTexto("");
    try { await api("simulador-bot/enviar", { method: "POST", body: JSON.stringify({ telefono, texto: t }) }); } catch (x) { setError(x instanceof Error ? x.message : "No se pudo enviar."); }
  }

  return <div className="celular celular-flotante" role="dialog" aria-label="Celular de prueba del bot">
    <header className="celular-cabecera"><span className="celular-avatar" aria-hidden="true">SJ</span>
      <div><strong>Juviar</strong>{telefonos.length > 1
        ? <select aria-label="Teléfono de prueba" value={telefono} onChange={(e) => setTelefono(e.target.value)}>{telefonos.map((t) => <option key={t} value={t}>+{t}</option>)}</select>
        : <small>Escribís desde +{telefono}</small>}</div>
      <button type="button" className="celular-cerrar" onClick={cerrar} aria-label="Cerrar celular">✕</button></header>
    <Burbujas mensajes={mensajes} vacio="Escribí «Hola» para empezar. Nada sale por WhatsApp de verdad." />
    {error && <p className="celular-error" role="alert">{error}</p>}
    <div className="atajos">{["Hola", "Pedir turno", "Mis turnos", "1", "2", "3", "Sí", "No"].map((a) => <button key={a} type="button" onClick={() => setTexto(a)}>{a}</button>)}</div>
    <form className="chat-envio" onSubmit={enviar}><input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Mensaje" maxLength={1000} aria-label="Mensaje" autoFocus /><button disabled={!texto.trim()} aria-label="Enviar">➤</button></form>
  </div>;
}

/** Botón flotante de WhatsApp: abre el celular de prueba. Sólo aparece si el simulador está habilitado. */
export function BotonWhatsapp() {
  const [telefonos, setTelefonos] = useState<string[]>([]); const [abierto, setAbierto] = useState(false);
  useEffect(() => {
    api<{ habilitado: boolean }>("simulador-bot/estado").then((e) => {
      if (e.habilitado) api<Telefono[]>("simulador-bot/telefonos").then((t) => setTelefonos(t.map((x) => x.telefono))).catch(() => null);
    }).catch(() => null);
  }, []);
  if (!telefonos.length) return null;
  if (abierto) return <CelularBot telefonos={telefonos} cerrar={() => setAbierto(false)} />;
  return <button type="button" className="whatsapp-flotante" onClick={() => setAbierto(true)}>
    <span className="whatsapp-leyenda">Chateá con el bot por WhatsApp</span>
    <span className="whatsapp-icono"><IconoWhatsapp /></span>
  </button>;
}

/** Conversaciones que tuvo el bot: quién escribió, cuándo y qué le respondió. */
export function ConversacionesBot() {
  const [dias, setDias] = useState(30);
  const [lista, setLista] = useState<Conversacion[] | null>(null); const [error, setError] = useState("");
  const [abierta, setAbierta] = useState<Conversacion | null>(null); const [chat, setChat] = useState<Mensaje[] | null>(null);

  useEffect(() => {
    setError("");
    api<Conversacion[]>(`conversaciones-bot?dias=${dias}`).then(setLista).catch((x) => { setLista([]); setError(x instanceof Error ? x.message : "No se pudieron leer las conversaciones."); });
  }, [dias]);

  useEffect(() => {
    if (!abierta) { setChat(null); return; }
    api<Array<{ id: string; de: Mensaje["de"]; texto: string; momento: string }>>(`conversaciones-bot/${abierta.telefono}`)
      .then((m) => setChat(m.map((x) => ({ id: x.id, de: x.de, texto: x.texto, hora: momento(x.momento) }))))
      .catch(() => setChat([]));
  }, [abierta]);

  return <section className="tarjeta">
    <div className="titulo-fila"><div><h2>Conversaciones</h2><p className="ayuda">Quién le escribió al bot y qué le respondió. Tocá una fila para leer la conversación completa.</p></div>
      <label>Período<select value={dias} onChange={(e) => setDias(Number(e.target.value))}><option value={7}>Últimos 7 días</option><option value={30}>Últimos 30 días</option><option value={90}>Últimos 90 días</option></select></label></div>
    {error && <ErrorVisible mensaje={error} />}
    {lista === null ? <p className="ayuda">Cargando…</p> : lista.length ? <Tabla etiqueta="Conversaciones con el bot" filas={lista} porPagina={15} alElegir={setAbierta} columnas={[
      { clave: "nombre", titulo: "Quién", valor: (c) => c.nombre ?? "Sin registrar" },
      { clave: "quien", titulo: "Tipo", valor: (c) => (c.quien ? QUIEN[c.quien] : "—") },
      { clave: "telefono", titulo: "Teléfono", valor: (c) => `+${c.telefono}` },
      { clave: "ultimo_texto", titulo: "Último mensaje", valor: (c) => c.ultimo_texto.length > 60 ? `${c.ultimo_texto.slice(0, 60)}…` : c.ultimo_texto },
      { clave: "mensajes", titulo: "Mensajes" },
      { clave: "ultimo_en", titulo: "Último contacto", valor: (c) => momento(c.ultimo_en) },
    ]} /> : <Vacio>Nadie le escribió al bot en este período.</Vacio>}
    {abierta && <Ventana titulo={abierta.nombre ?? `+${abierta.telefono}`} tamano="chica" cerrar={() => setAbierta(null)}>
      <p className="ayuda">+{abierta.telefono}</p>
      <div className="chat-historial">{chat === null ? <p className="ayuda">Cargando…</p> : <Burbujas mensajes={chat} vacio="Sin mensajes." />}</div>
    </Ventana>}
  </section>;
}
