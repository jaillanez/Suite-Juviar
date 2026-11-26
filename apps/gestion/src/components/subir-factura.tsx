"use client";

import { useEffect, useState } from "react";
import { api, ErrorApi, usarIngresoSubida } from "@/lib/api";
import { codigoDelLink, LARGO_PIN, teclaPin } from "@/lib/subida";
import { ControlarFactura } from "./celular";

// Pantalla /subir: para quien sólo saca fotos de facturas. Entra con su link personal y su PIN;
// no ve nada más de Gestión. El celular queda recordado 30 días (cookie HttpOnly del servidor).

type Yo = { nombre: string; empresas: string[] };
const TECLAS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "borrar"];

export default function SubirFactura() {
  const [estado, setEstado] = useState<"cargando" | "pin" | "sin_link" | "listo">("cargando");
  const [codigo, setCodigo] = useState("");
  const [yo, setYo] = useState<Yo | null>(null);

  useEffect(() => {
    usarIngresoSubida();
    const delLink = codigoDelLink(window.location.hash);
    setCodigo(delLink);
    api<Yo>("subir/yo").then(y => { setYo(y); setEstado("listo"); ocultarCodigo(); })
      .catch(() => setEstado(delLink ? "pin" : "sin_link"));
  }, []);

  async function salir() {
    if (!window.confirm("¿Salir? Para volver a entrar vas a necesitar el link y el PIN.")) return;
    await api("subir/salir", { method: "POST" }).catch(() => null);
    setYo(null); setEstado(codigo ? "pin" : "sin_link");
  }

  if (estado === "cargando") return <main className="cel" aria-busy="true"><p className="cel-cargando">Cargando…</p></main>;
  if (estado === "sin_link") return <main className="cel cel-ingreso">
    <span className="cel-logo">SJ</span>
    <h1 className="cel-titulo">Subir facturas</h1>
    <p className="cel-texto">Para entrar, abrí el link personal que te mandó Administración (por ejemplo por WhatsApp).</p>
    <p className="cel-pie">Si no lo tenés o dejó de andar, pedile uno nuevo a Administración.</p>
  </main>;
  if (estado === "pin" || !yo) return <TecladoPin codigo={codigo} entrar={y => { setYo(y); setEstado("listo"); ocultarCodigo(); }} />;
  return <ControlarFactura volver={() => undefined} subida={{ salir: () => void salir() }} />;
}

/** Ya adentro, el código del link no queda a la vista en la barra de direcciones. */
function ocultarCodigo() {
  if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
}

function TecladoPin({ codigo, entrar }: { codigo: string; entrar: (yo: Yo) => void }) {
  const [pin, setPin] = useState(""); const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(""); const [sinTeclado, setSinTeclado] = useState(false);

  async function enviar(completo: string) {
    setEnviando(true); setError("");
    try { entrar(await api<Yo>("subir/ingreso", { method: "POST", body: JSON.stringify({ codigo, pin: completo }) })); }
    catch (x) {
      const estado = x instanceof ErrorApi ? x.estado : 0;
      const texto = x instanceof Error && x.message ? x.message : "No pudimos entrar. Revisá la conexión y probá de nuevo.";
      setError(texto);
      // Link que no sirve o desactivado: probar otro PIN no cambia nada.
      setSinTeclado(estado === 403 || (estado === 401 && !texto.startsWith("PIN")));
      setPin("");
    } finally { setEnviando(false); }
  }
  function tocar(tecla: string) {
    if (enviando) return;
    const nuevo = teclaPin(pin, tecla);
    setPin(nuevo);
    if (nuevo.length === LARGO_PIN && pin.length < LARGO_PIN) void enviar(nuevo);
  }
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => { if (/^[0-9]$/.test(e.key)) tocar(e.key); else if (e.key === "Backspace") tocar("borrar"); };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  });

  return <main className="cel cel-ingreso">
    <span className="cel-logo">SJ</span>
    <h1 className="cel-titulo">Subir facturas</h1>
    {sinTeclado ? <p className="cel-error" role="alert">{error}</p> : <>
      <p className="cel-texto">Escribí tu PIN de {LARGO_PIN} números.</p>
      <div className="cel-pin" aria-label={`PIN: ${pin.length} de ${LARGO_PIN} números`} role="status">
        {Array.from({ length: LARGO_PIN }, (_, i) => <span key={i} className={i < pin.length ? "lleno" : ""} />)}
      </div>
      {error && <p className="cel-error" role="alert">{error}</p>}
      {enviando && <p className="cel-cargando">Entrando…</p>}
      <div className="cel-teclado">{TECLAS.map((t, i) => t
        ? <button key={t} type="button" disabled={enviando} onClick={() => tocar(t)} aria-label={t === "borrar" ? "Borrar el último número" : t}>{t === "borrar" ? "⌫" : t}</button>
        : <span key={`vacio-${i}`} />)}</div>
      <p className="cel-pie">¿No te acordás el PIN? Pedile uno nuevo a Administración.</p>
    </>}
  </main>;
}
