"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, ErrorApi } from "@/lib/api";
import { CLAVE_MINIMA, problemaDeClave, tokenDelEnlace } from "@/lib/recuperacion";

// «¿Olvidaste tu contraseña?»: /recuperar pide el correo y /restablecer (el enlace del correo)
// deja elegir la contraseña nueva. Sirven igual en la computadora y en el celular.

const RESPUESTA = "Si el correo está registrado, te mandamos un enlace para elegir una contraseña nueva. Revisá tu bandeja de entrada (y la de correo no deseado). El enlace vence en 30 minutos.";

export function RecuperarClave() {
  const [enviando, setEnviando] = useState(false);
  const [listo, setListo] = useState("");
  const [error, setError] = useState("");
  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setEnviando(true);
    const email = String(new FormData(e.currentTarget).get("email") ?? "").trim();
    try { setListo((await api<{ mensaje: string }>("ingreso/recuperar", { method: "POST", body: JSON.stringify({ email }) })).mensaje || RESPUESTA); }
    catch (x) { setError(x instanceof ErrorApi && x.estado >= 500 ? "Ahora no podemos mandar el enlace. Probá en un rato." : "No pudimos mandar el pedido. Revisá la conexión y probá de nuevo."); }
    finally { setEnviando(false); }
  }
  return <main className="cel cel-ingreso">
    <span className="cel-logo">SJ</span>
    <h1 className="cel-titulo">Recuperar contraseña</h1>
    {listo ? <>
      <p className="cel-exito" role="status">{listo}</p>
      <p className="cel-pie"><Link href="/">Volver al ingreso</Link></p>
    </> : <>
      <p className="cel-texto">Escribí el correo con el que entrás a Gestión. Te mandamos un enlace para elegir una contraseña nueva.</p>
      <form className="cel-form" onSubmit={enviar}>
        {error && <p className="cel-error" role="alert">{error}</p>}
        <label>Correo<input name="email" type="email" inputMode="email" autoComplete="username" autoCapitalize="none" required autoFocus /></label>
        <button className="cel-boton" disabled={enviando}>{enviando ? "Enviando…" : "Mandarme el enlace"}</button>
      </form>
      <p className="cel-pie"><Link href="/">Volver al ingreso</Link></p>
    </>}
  </main>;
}

export function RestablecerClave() {
  const [token, setToken] = useState<string | null>(null);
  const [ver, setVer] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");
  const [vencido, setVencido] = useState(false);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    setToken(tokenDelEnlace(window.location.hash));
    // El código no queda a la vista en la barra de direcciones ni en el historial.
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
  }, []);

  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError("");
    const clave = String(new FormData(e.currentTarget).get("clave") ?? "");
    const problema = problemaDeClave(clave);
    if (problema) { setError(problema); return; }
    setEnviando(true);
    try { await api("ingreso/restablecer", { method: "POST", body: JSON.stringify({ token, clave }) }); setListo(true); }
    catch (x) {
      if (x instanceof ErrorApi && x.estado === 410) setVencido(true);
      setError(x instanceof Error && x.message ? x.message : "No pudimos guardar la contraseña. Revisá la conexión y probá de nuevo.");
    } finally { setEnviando(false); }
  }

  if (token === null) return <main className="cel" aria-busy="true"><p className="cel-cargando">Cargando…</p></main>;
  return <main className="cel cel-ingreso">
    <span className="cel-logo">SJ</span>
    <h1 className="cel-titulo">Elegí una contraseña nueva</h1>
    {listo ? <>
      <p className="cel-exito" role="status">Listo, ya cambiaste la contraseña. Por seguridad se cerraron las sesiones que tenías abiertas.</p>
      <Link className="cel-boton" href="/" style={{ textAlign: "center", textDecoration: "none" }}>Ir al ingreso</Link>
    </> : !token || vencido ? <>
      <p className="cel-error" role="alert">{error || "El enlace no está completo, ya se usó o venció."}</p>
      <p className="cel-texto">Pedí uno nuevo: llega al correo y sirve por 30 minutos.</p>
      <Link className="cel-boton" href="/recuperar" style={{ textAlign: "center", textDecoration: "none" }}>Pedir otro enlace</Link>
    </> : <>
      <p className="cel-texto">Tiene que tener al menos {CLAVE_MINIMA} letras, números o signos, y no empezar ni terminar con espacios.</p>
      <form className="cel-form" onSubmit={enviar}>
        {error && <p className="cel-error" role="alert">{error}</p>}
        <label>Contraseña nueva<span className="cel-clave"><input name="clave" type={ver ? "text" : "password"} minLength={CLAVE_MINIMA} autoComplete="new-password" required autoFocus /><button type="button" aria-pressed={ver} onClick={() => setVer(v => !v)}>{ver ? "Ocultar" : "Ver"}</button></span></label>
        <button className="cel-boton" disabled={enviando}>{enviando ? "Guardando…" : "Guardar contraseña"}</button>
      </form>
    </>}
  </main>;
}
