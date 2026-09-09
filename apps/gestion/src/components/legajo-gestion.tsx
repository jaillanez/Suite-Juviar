"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Simulado, Tabla, Vacio } from "./compartidos";

type Persona = Record<string, unknown> & { legajo: string; nombre_completo: string; empresa: string; sector: string; puesto: string };
type Ficha = Persona & { formato: string; origen: string; solo_lectura: boolean; marca?: string };
type Adjunto = Record<string, unknown> & { id: string; nombre: string; activo: boolean; motivo_baja?: string; dado_baja_por?: string };

async function base64(archivo: File) {
  return new Promise<string>((ok, mal) => { const lector = new FileReader(); lector.onerror = mal; lector.onload = () => ok(String(lector.result).split(",")[1]); lector.readAsDataURL(archivo); });
}

export function LegajoGestion() {
  const [personas, setPersonas] = useState<Persona[]>([]); const [ficha, setFicha] = useState<Ficha | null>(null);
  const [adjuntos, setAdjuntos] = useState<Adjunto[]>([]); const [error, setError] = useState("");
  const [visor, setVisor] = useState<{ nombre: string; url: string } | null>(null);
  const informar = (x: unknown) => setError(x instanceof Error ? x.message : "No se pudo completar la operación.");
  async function buscar(e: FormEvent<HTMLFormElement>) { e.preventDefault(); setError(""); const f = new FormData(e.currentTarget); const q = new URLSearchParams(); for (const clave of ["apellido", "legajo", "sector", "empresa"]) { const valor = String(f.get(clave) || "").trim(); if (valor) q.set(clave, valor); } try { setPersonas(await api(`legajo/personas?${q}`)); } catch (x) { informar(x); } }
  async function abrir(legajo: string) { try { setFicha(await api(`legajo/personas/${legajo}`)); setAdjuntos(await api(`legajo/personas/${legajo}/adjuntos`)); setVisor(null); } catch (x) { informar(x); } }
  async function adjuntar(e: FormEvent<HTMLFormElement>) { e.preventDefault(); if (!ficha) return; const form = e.currentTarget; const archivo = (new FormData(form).get("archivo") as File); if (!archivo?.size) return; try { await api("legajo/adjuntos", { method: "POST", body: JSON.stringify({ legajo: ficha.legajo, nombre: archivo.name, contenido_base64: await base64(archivo) }) }); form.reset(); setAdjuntos(await api(`legajo/personas/${ficha.legajo}/adjuntos`)); } catch (x) { informar(x); } }
  async function ver(adjunto: Adjunto) { try { const dato = await api<{ nombre: string; contenido_base64: string }>(`legajo/adjuntos/${adjunto.id}`); setVisor({ nombre: dato.nombre, url: `data:application/pdf;base64,${dato.contenido_base64}` }); } catch (x) { informar(x); } }
  async function baja(adjunto: Adjunto) { const motivo = window.prompt("Motivo obligatorio de la baja lógica"); if (!motivo || !ficha) return; try { await api(`legajo/adjuntos/${adjunto.id}/baja`, { method: "POST", body: JSON.stringify({ motivo }) }); setAdjuntos(await api(`legajo/personas/${ficha.legajo}/adjuntos`)); } catch (x) { informar(x); } }
  return <>{error && <ErrorVisible mensaje={error} />}<div className="rejilla">
    <section className="tarjeta"><div className="titulo-fila"><h2>Buscar persona</h2><Simulado nivel="tabla" /></div><form className="form-grid" onSubmit={buscar}><label>Apellido<input name="apellido" /></label><label>Legajo<input name="legajo" /></label><label>Sector<input name="sector" /></label><label>Empresa<select name="empresa"><option value="">Todas</option><option>ENAV</option><option>JUBIAR</option></select></label><button className="primario">Buscar</button></form></section>
    <section className="tarjeta"><h2>Resultados</h2>{personas.length ? <Tabla etiqueta="Personas" filas={personas} columnas={[{ clave: "legajo", titulo: "Legajo" }, { clave: "nombre_completo", titulo: "Persona" }, { clave: "empresa", titulo: "Empresa" }, { clave: "sector", titulo: "Sector" }, { clave: "puesto", titulo: "Puesto" }, { clave: "accion", titulo: "Ficha", valor: p => <button onClick={() => abrir(p.legajo)}>Abrir</button> }]} /> : <Vacio>Usá uno o más filtros para buscar.</Vacio>}</section>
    {ficha && <section className="tarjeta"><div className="titulo-fila"><div><h2>{ficha.nombre_completo}</h2><p className="ayuda">Legajo {ficha.legajo} · {ficha.empresa} · {ficha.sector} · {ficha.puesto}</p></div><span className="estado">{ficha.origen} · sólo lectura</span></div><p>Formato determinado por la empresa del legajo: <strong>{ficha.formato}</strong>.</p><a className="boton" target="_blank" href={`${process.env.NEXT_PUBLIC_API_URL ?? "/backend"}/legajo/personas/${ficha.legajo}/formato`}>Abrir formato imprimible</a></section>}
    {ficha && <section className="tarjeta"><h2>Documentación adjunta</h2><p className="ayuda">El original se conserva cifrado. La baja es lógica y exige un motivo.</p><form className="form-linea" onSubmit={adjuntar}><label>Archivo original<input name="archivo" type="file" required /></label><button className="primario">Adjuntar</button></form>{adjuntos.length ? <Tabla etiqueta="Adjuntos del legajo" filas={adjuntos} columnas={[{ clave: "nombre", titulo: "Archivo" }, { clave: "activo", titulo: "Estado", valor: a => a.activo ? "Activo" : `Baja: ${a.motivo_baja}` }, { clave: "dado_baja_por", titulo: "Auditado por" }, { clave: "accion", titulo: "Acciones", valor: a => <span className="acciones-inlinea"><button onClick={() => ver(a)}>Ver original</button>{a.activo && <button onClick={() => baja(a)}>Dar de baja</button>}</span> }]} /> : <Vacio>Sin documentación adjunta.</Vacio>}{visor && <div><h3>{visor.nombre}</h3><iframe className="visor" title={`Original ${visor.nombre}`} src={visor.url} /></div>}</section>}
  </div></>;
}
