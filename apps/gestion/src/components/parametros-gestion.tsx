"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible } from "./compartidos";

type Resultado = { leida_en: string; adjuntos: number; incorporados: number; repetidos: number; error: string | null; incompleta?: boolean };
type Correo = { empresa: string; casilla: string; clave_cargada: boolean; actualizado_por: string | null; actualizado_en: string | null; ultima_lectura: string | null; ultimo_resultado: Resultado | null };

function fecha(valor: string) {
  return new Date(valor).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}

function resumen(r: Resultado) {
  if (r.error) return `${fecha(r.leida_en)} · No se pudo leer: ${r.error}`;
  return `${fecha(r.leida_en)} · ${r.incorporados} CV nuevo(s) de ${r.adjuntos} adjunto(s); ${r.repetidos} ya estaban cargados.${r.incompleta ? " Quedaron correos: se traen en la próxima lectura." : ""}`;
}

function CasillaEmpresa({ inicial }: { inicial: Correo }) {
  const [correo, setCorreo] = useState(inicial);
  const [error, setError] = useState("");
  const [exito, setExito] = useState("");
  const [ocupado, setOcupado] = useState("");
  const ruta = `parametros/correo-rrhh/${correo.empresa}`;

  async function accion(nombre: string, hacer: () => Promise<string>) {
    setError(""); setExito(""); setOcupado(nombre);
    try { setExito(await hacer()); } catch (x) { setError(x instanceof Error ? x.message : String(x)); }
    setOcupado("");
    const actualizado = (await api<Correo[]>("parametros/correo-rrhh").catch(() => [])).find(c => c.empresa === correo.empresa);
    if (actualizado) setCorreo(actualizado);
  }

  function guardar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    accion("guardar", async () => {
      await api(ruta, { method: "PUT", body: JSON.stringify({ casilla: f.get("casilla"), clave_aplicacion: f.get("clave") || null }) });
      form.querySelector<HTMLInputElement>("input[name=clave]")!.value = "";
      return "Datos guardados.";
    });
  }

  return <section className="tarjeta">
    <h2>Correo de RRHH · {correo.empresa}</h2>
    {error && <ErrorVisible mensaje={error} />}
    {exito && <p className="aviso-exito">{exito}</p>}
    <form className="form-grid" onSubmit={guardar}>
      <label>Casilla de Gmail<input name="casilla" type="email" required defaultValue={correo.casilla} placeholder="rrhh@gmail.com" /></label>
      <label>Contraseña de aplicación<input name="clave" type="password" autoComplete="new-password" required={!correo.clave_cargada} placeholder={correo.clave_cargada ? "Cargada · dejá vacío para mantenerla" : "16 letras que da Google"} /></label>
      <button className="primario" disabled={Boolean(ocupado)}>{ocupado === "guardar" ? "Guardando…" : "Guardar"}</button>
      <button type="button" disabled={Boolean(ocupado) || !correo.clave_cargada} onClick={() => accion("probar", async () => { await api(`${ruta}/probar`, { method: "POST" }); return "Gmail aceptó la casilla y la contraseña."; })}>{ocupado === "probar" ? "Probando…" : "Probar conexión"}</button>
      <button type="button" disabled={Boolean(ocupado) || !correo.clave_cargada} onClick={() => accion("leer", async () => { const r = await api<Resultado>(`${ruta}/leer`, { method: "POST" }); return resumen(r); })}>{ocupado === "leer" ? "Leyendo…" : "Leer ahora"}</button>
    </form>
    <p className="ayuda">{correo.ultimo_resultado ? `Última lectura: ${resumen(correo.ultimo_resultado)}` : "Todavía no se leyó esta casilla."}</p>
    {correo.actualizado_en && <p className="ayuda">Modificado por {correo.actualizado_por} el {fecha(correo.actualizado_en)}</p>}
  </section>;
}

export function ParametrosGestion() {
  const [correos, setCorreos] = useState<Correo[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<Correo[]>("parametros/correo-rrhh").then(setCorreos).catch(x => setError(x instanceof Error ? x.message : String(x))); }, []);
  if (error) return <ErrorVisible mensaje={error} />;
  if (!correos) return <p className="ayuda">Cargando…</p>;
  return <>{correos.map(c => <CasillaEmpresa key={c.empresa} inicial={c} />)}</>;
}
