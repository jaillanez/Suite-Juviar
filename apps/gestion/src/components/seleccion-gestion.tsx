"use client";

import { ChangeEvent, FormEvent, ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Tabla, Vacio, Ventana } from "./compartidos";

type Busqueda = Record<string, unknown> & { id: string; nombre: string; perfil: string; definido_por: string; definido_en: string; edad_minima?: number | null; edad_maxima?: number | null; secundaria_completa?: boolean };
type Campo = { nombre: string; valor: string; fragmento_fuente?: string; fragmento?: string; verificado: boolean };
type Resultado = { cumple?: boolean; requiere_revision?: boolean; puntaje: number; razones: string[] };
type Cv = Record<string, unknown> & { id: string; nombre: string; requiere_revision: boolean; campos?: Campo[]; campos_pendientes?: string[]; resultado?: Resultado | null };
type Ficha = { id: string; nombre: string; campos: Campo[]; pendientes: string[]; confirmaciones: Array<{ campo: string; valor: string; confirmado_por: string; confirmado_en: string }>; resultado?: Resultado | null };

const PERFILES: Record<string, string> = { BODEGA: "Bodega", MANTENIMIENTO: "Mantenimiento", ADMINISTRACION: "Administración" };
const CAMPOS: Record<string, string> = { edad_o_fecha_nacimiento: "Edad o fecha de nacimiento", nivel_estudios: "Nivel de estudios", experiencia: "Experiencia", oficio: "Oficio o perfil", localidad: "Localidad", contacto: "Contacto" };
const RAZONES: Record<string, { texto: string; clase: string }> = { DENTRO: { texto: "Cumple", clase: "estado" }, FUERA: { texto: "No cumple", clase: "estado estado-alerta" }, REVISAR: { texto: "Revisar", clase: "estado estado-revisar" } };
const perfil = (p: string) => PERFILES[p] ?? p;
const campo = (c: string) => CAMPOS[c] ?? c.replaceAll("_", " ");
const mensaje = (e: unknown) => e instanceof Error ? e.message : "No se pudo completar la operación.";
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

function requisitos(b: Busqueda) {
  const edad = b.edad_minima != null && b.edad_maxima != null ? `${b.edad_minima} a ${b.edad_maxima} años` : b.edad_minima != null ? `desde ${b.edad_minima} años` : b.edad_maxima != null ? `hasta ${b.edad_maxima} años` : "";
  return [`Experiencia en ${perfil(b.perfil).toLowerCase()}`, edad, b.secundaria_completa ? "secundaria completa" : ""].filter(Boolean).join(" · ");
}

function veredicto(r?: Resultado | null) {
  if (!r) return { texto: "Sin evaluar", clase: "estado estado-neutro" };
  if (r.cumple) return { texto: "Encaja", clase: "estado" };
  if (r.requiere_revision) return { texto: "Revisar a mano", clase: "estado estado-revisar" };
  return { texto: "No encaja", clase: "estado estado-alerta" };
}

function Razones({ razones }: { razones: string[] }): ReactNode {
  return <ul className="razones">{razones.map((r, i) => { const [prefijo, ...resto] = r.split(":"); const tipo = RAZONES[prefijo.trim()]; const texto = (tipo ? resto.join(":") : r).trim().replace(/\b(BODEGA|MANTENIMIENTO|ADMINISTRACION)\b/g, m => perfil(m).toLowerCase()); return <li key={i}>{tipo && <span className={tipo.clase}>{tipo.texto}</span>}<span>{texto.charAt(0).toUpperCase() + texto.slice(1)}</span></li>; })}</ul>;
}

function leerBase64(archivo: File) { return new Promise<string>((ok, mal) => { const l = new FileReader(); l.onerror = mal; l.onload = () => ok(String(l.result).split(",")[1]); l.readAsDataURL(archivo); }); }

type FichaIA = { nombre_completo?: string | null; localidad?: string | null; resumen?: string | null; oficios?: string[]; estudios?: string[]; idiomas?: string[]; experiencia?: Array<{ puesto?: string; empresa?: string; periodo?: string }>; edad?: number | string | null };
type Candidato = { id: string; encaje: "ALTO" | "MEDIO" | "BAJO"; motivos: string[]; faltan: string[]; nombre_archivo: string; nombre?: string | null; localidad?: string | null; resumen?: string | null };
const ENCAJE: Record<string, string> = { ALTO: "Encaja bien", MEDIO: "Puede encajar", BAJO: "Encaja poco" };
const tipoArchivo = (nombre: string) => /\.png$/i.test(nombre) ? "image/png" : /\.jpe?g$/i.test(nombre) ? "image/jpeg" : /\.webp$/i.test(nombre) ? "image/webp" : "application/pdf";

export function SeleccionGestion() {
  const [iaEstado, setIaEstado] = useState<{ disponible: boolean; total: number; leidos: number } | null>(null); const [fichasIA, setFichasIA] = useState<Record<string, FichaIA>>({});
  const [pedido, setPedido] = useState(""); const [candidatos, setCandidatos] = useState<Candidato[] | null>(null); const [sinLeer, setSinLeer] = useState(0); const [buscandoIA, setBuscandoIA] = useState(false); const [errorIA, setErrorIA] = useState(""); const [progresoIA, setProgresoIA] = useState("");
  const [verBajos, setVerBajos] = useState(false);
  async function refrescarIA() { try { setIaEstado(await api("seleccion/ia/estado")); setFichasIA(await api("seleccion/ia/fichas")); } catch { setIaEstado(null); } }
  async function leerConIA(ids: string[]) {
    for (let i = 0; i < ids.length; i++) { setProgresoIA(`Leyendo con IA ${i + 1} de ${ids.length}…`); try { await api(`seleccion/cvs/${ids[i]}/leer-ia`, { method: "POST" }); } catch (x) { setErrorIA(`${mensaje(x)} (archivo ${i + 1})`); } }
    setProgresoIA(""); await refrescarIA();
  }
  async function buscarIA(e: FormEvent<HTMLFormElement>) { e.preventDefault(); setErrorIA(""); setBuscandoIA(true); setCandidatos(null); setVerBajos(false); try { const r = await api<{ candidatos: Candidato[]; sin_leer: number }>("seleccion/ia/buscar", { method: "POST", body: JSON.stringify({ pedido }) }); setCandidatos(r.candidatos); setSinLeer(r.sin_leer); } catch (x) { setErrorIA(mensaje(x)); } finally { setBuscandoIA(false); } }
  const [busquedas, setBusquedas] = useState<Busqueda[]>([]); const [cvs, setCvs] = useState<Cv[]>([]); const [revision, setRevision] = useState<Cv[]>([]); const [ranking, setRanking] = useState<Cv[]>([]);
  const [busqueda, setBusqueda] = useState(""); const [creando, setCreando] = useState(false); const [ficha, setFicha] = useState<Ficha | null>(null); const [original, setOriginal] = useState(""); const [subiendo, setSubiendo] = useState(false); const [aviso, setAviso] = useState(""); const [cargandoRanking, setCargandoRanking] = useState(false);
  const [error, setError] = useState(""); const [errorCreacion, setErrorCreacion] = useState(""); const [errorBusqueda, setErrorBusqueda] = useState(""); const [errorVentana, setErrorVentana] = useState("");
  const informar = (e: unknown) => setError(mensaje(e));
  const abierta = busquedas.find(b => b.id === busqueda);
  async function recargar(id = busqueda, avisar: (e: unknown) => void = informar) { try { const [b, c, r, k] = await Promise.all([api<Busqueda[]>("seleccion/busquedas"), api<Cv[]>("seleccion/cvs"), api<Cv[]>("seleccion/revision"), id ? api<Cv[]>(`seleccion/cvs?busqueda_id=${id}`) : Promise.resolve([] as Cv[])]); setBusquedas(b); setCvs(c); setRevision(r); setRanking(k); } catch (e) { avisar(e); } }
  useEffect(() => { recargar(); refrescarIA(); }, []);
  function abrirBusqueda(id: string) { setBusqueda(id); setRanking([]); setAviso(""); setErrorBusqueda(""); setCargandoRanking(true); recargar(id, e => setErrorBusqueda(mensaje(e))).finally(() => setCargandoRanking(false)); }
  function cerrarBusqueda() { setBusqueda(""); setRanking([]); setAviso(""); setErrorBusqueda(""); }
  async function crear(e: FormEvent<HTMLFormElement>) { e.preventDefault(); setErrorCreacion(""); const f = Object.fromEntries(new FormData(e.currentTarget)); try { const creada = await api<Busqueda>("seleccion/busquedas", { method: "POST", body: JSON.stringify({ ...f, edad_minima: f.edad_minima ? Number(f.edad_minima) : null, edad_maxima: f.edad_maxima ? Number(f.edad_maxima) : null, secundaria_completa: f.secundaria_completa === "on" }) }); setCreando(false); abrirBusqueda(creada.id); } catch (x) { setErrorCreacion(mensaje(x)); } }
  async function cargar(e: ChangeEvent<HTMLInputElement>, avisar: (e: unknown) => void) {
    const entrada = e.currentTarget; const archivos = entrada.files; if (!archivos?.length) return; setSubiendo(true); setAviso(""); avisar(null);
    try { const lote = await Promise.all(Array.from(archivos).map(async archivo => ({ nombre: archivo.name, contenido_base64: await leerBase64(archivo) }))); const r = await api<{ incorporados?: string[] }>("seleccion/cvs/lote", { method: "POST", body: JSON.stringify({ archivos: lote }) }); const n = r?.incorporados?.length ?? lote.length; if (iaEstado?.disponible && r?.incorporados?.length) void leerConIA(r.incorporados.filter(id => !fichasIA[id])); setAviso(`${plural(n, "currículum leído", "currículums leídos")}. ${busqueda ? "Abajo ves cómo quedó cada uno para esta búsqueda." : "Ya los podés ver en la lista."}`); await recargar(busqueda, avisar); }
    catch (x) { avisar(x); } finally { setSubiendo(false); entrada.value = ""; }
  }
  const avisarBusqueda = (e: unknown) => setErrorBusqueda(e ? mensaje(e) : "");
  const avisarPagina = (e: unknown) => setError(e ? mensaje(e) : "");
  async function abrir(cv: Cv) { setErrorVentana(""); let abiertaFicha = Boolean(ficha); if (cv.id !== ficha?.id) setOriginal(""); try { setFicha(await api<Ficha>(`seleccion/cvs/${cv.id}${busqueda ? `?busqueda_id=${busqueda}` : ""}`)); abiertaFicha = true; const o = await api<{ contenido_base64: string }>(`seleccion/cvs/${cv.id}/original`); setOriginal(`data:${tipoArchivo(cv.nombre ?? ficha?.nombre ?? "")};base64,${o.contenido_base64}`); } catch (x) { if (abiertaFicha) setErrorVentana(mensaje(x)); else if (busqueda) setErrorBusqueda(mensaje(x)); else informar(x); } }
  async function confirmar(c: Campo) { if (!ficha) return; try { await api(`seleccion/cvs/${ficha.id}/campos/${c.nombre}/confirmacion`, { method: "PUT", body: JSON.stringify({ valor: c.valor }) }); await abrir({ id: ficha.id } as Cv); } catch (x) { setErrorVentana(mensaje(x)); } }
  function cerrarFicha() { setFicha(null); setOriginal(""); setErrorVentana(""); }
  const filasRanking: Array<Cv & { posicion: string }> = ranking.map((c, i) => ({ ...c, posicion: String(i + 1).padStart(3, "0") }));
  const cuenta = { encajan: ranking.filter(c => c.resultado?.cumple).length, revisar: ranking.filter(c => !c.resultado?.cumple && c.resultado?.requiere_revision).length, fuera: ranking.filter(c => c.resultado && !c.resultado.cumple && !c.resultado.requiere_revision).length };
  const botonSubir = (avisar: (e: unknown) => void, primario: boolean) => <label className={`carga${primario ? " carga-primaria" : ""}`} aria-disabled={subiendo}>{subiendo ? "Subiendo y leyendo…" : "Subir currículums (PDF o foto)"}<input type="file" multiple accept="application/pdf,image/png,image/jpeg,image/webp" disabled={subiendo} onChange={e => cargar(e, avisar)} /></label>;
  const verFicha = { clave: "abrir", titulo: "", valor: (f: Cv) => <button onClick={e => { e.stopPropagation(); abrir(f); }}>Ver ficha</button> } as const;
  return <>{error && <ErrorVisible mensaje={error} />}
    <div className="ayuda-contextual"><strong>Cómo funciona:</strong> abrí una búsqueda para un puesto, subí los currículums que recibiste y el sistema los lee y ordena quién encaja, explicando por qué. RRHH revisa y confirma los datos: nada se decide automáticamente.</div>
    <section className="tarjeta buscador-ia"><h2>Buscar candidatos</h2>
      <p className="ayuda">Escribí con tus palabras a quién necesitás. La IA lee los currículums cargados y te propone quiénes encajan, explicando por qué. La decisión es siempre de RRHH.</p>
      {iaEstado && !iaEstado.disponible && <p className="ayuda">La lectura con IA no está habilitada en este servidor.</p>}
      <form onSubmit={buscarIA} className="form-buscador"><textarea value={pedido} onChange={e => setPedido(e.target.value)} rows={3} minLength={5} required placeholder="Ej.: Necesito un capataz de finca con experiencia en cosecha que viva cerca de Caucete" /><button className="primario" disabled={buscandoIA || !iaEstado?.disponible}>{buscandoIA ? "Buscando…" : "Buscar candidatos"}</button></form>
      {iaEstado && <p className="ayuda">{iaEstado.leidos} de {iaEstado.total} currículums leídos con IA.{iaEstado.disponible && iaEstado.leidos < iaEstado.total && !progresoIA && <> <button className="enlace" onClick={() => leerConIA(cvs.map(c => c.id).filter(id => !fichasIA[id]))}>Leer los {iaEstado.total - iaEstado.leidos} que faltan</button></>}{progresoIA && ` ${progresoIA}`}</p>}
      {errorIA && <ErrorVisible mensaje={errorIA} />}
      {candidatos && (candidatos.length ? <><ul className="candidatos">{candidatos.filter(c => verBajos || c.encaje !== "BAJO").map(c => <li key={c.id} className={`candidato encaje-${c.encaje}`} tabIndex={0} onClick={() => abrir({ id: c.id, nombre: c.nombre_archivo } as Cv)} onKeyDown={e => { if (e.key === "Enter") abrir({ id: c.id, nombre: c.nombre_archivo } as Cv); }}>
        <div className="titulo-fila"><strong>{c.nombre || c.nombre_archivo}</strong><span className={`estado estado-${c.encaje}`}>{ENCAJE[c.encaje]}</span></div>
        {(c.localidad || c.resumen) && <p className="ayuda">{[c.localidad, c.resumen].filter(Boolean).join(" · ")}</p>}
        {c.motivos.length > 0 && <ul className="motivos">{c.motivos.map((m, i) => <li key={i} className="cumple">{m}</li>)}</ul>}
        {c.faltan.length > 0 && <ul className="motivos">{c.faltan.map((m, i) => <li key={i} className="falta">{m}</li>)}</ul>}
      </li>)}</ul>{!verBajos && candidatos.some(c => c.encaje === "BAJO") && <button className="enlace" onClick={() => setVerBajos(true)}>Ver también los {candidatos.filter(c => c.encaje === "BAJO").length} que encajan poco</button>}</> : <Vacio>No hay currículums leídos con IA para comparar.</Vacio>)}
      {candidatos && sinLeer > 0 && <p className="ayuda">Quedaron {sinLeer} currículums sin leer con IA que no entraron en esta búsqueda.</p>}
    </section>
    <div className="rejilla">
      <section className="tarjeta"><div className="titulo-fila"><h2>Búsquedas con reglas fijas</h2><button className="primario" onClick={() => { setErrorCreacion(""); setCreando(true); }}>Nueva búsqueda</button></div>
        {busquedas.length ? <><p className="ayuda">Tocá una búsqueda para subir currículums y ver quién encaja.</p><Tabla etiqueta="Búsquedas" filas={busquedas} alElegir={b => abrirBusqueda(b.id)} columnas={[{ clave: "nombre", titulo: "Puesto" }, { clave: "perfil", titulo: "Perfil", valor: b => perfil(b.perfil) }, { clave: "edad_minima", titulo: "Requisitos", valor: b => requisitos(b) }, { clave: "definido_por", titulo: "Abierta por" }, { clave: "definido_en", titulo: "Fecha", valor: b => new Date(b.definido_en).toLocaleDateString("es-AR") }]} /></> : <Vacio>Todavía no hay búsquedas. Tocá «Nueva búsqueda» para definir el puesto y sus requisitos.</Vacio>}</section>
      <section className="tarjeta"><div className="titulo-fila"><h2>Currículums recibidos</h2>{botonSubir(avisarPagina, false)}</div><p className="ayuda">Todos los currículums cargados. Cada uno se evalúa contra todas las búsquedas abiertas. Tocá uno para ver los datos leídos y el PDF original.</p>{!busqueda && aviso && <div className="aviso-exito" role="status">{aviso}</div>}
        {cvs.length ? <Tabla etiqueta="Currículums recibidos" filas={cvs} alElegir={f => abrir(f as Cv)} columnas={[{ clave: "nombre", titulo: "Archivo" }, { clave: "requiere_revision", titulo: "Lectura", valor: f => f.requiere_revision ? <span className="estado estado-revisar">Faltan datos por leer</span> : <span className="estado">Leído completo</span> }, { clave: "campos", titulo: "Datos leídos", valor: f => f.campos?.length ? f.campos.map(c => campo(c.nombre)).join(", ") : "Ninguno" }, verFicha]} /> : <Vacio>Todavía no se cargó ningún currículum. Abrí una búsqueda y tocá «Subir currículums».</Vacio>}</section>
      <section className="tarjeta"><div className="titulo-fila"><h2>Para revisar a mano</h2>{revision.length > 0 && <span className="estado estado-revisar">{plural(revision.length, "pendiente", "pendientes")}</span>}</div><p className="ayuda">Currículums en los que el sistema no pudo leer algún dato. Abrilos y completá la revisión mirando el PDF.</p>{revision.length ? <Tabla etiqueta="Para revisar a mano" filas={revision} alElegir={f => abrir(f as Cv)} columnas={[{ clave: "nombre", titulo: "Archivo" }, { clave: "campos_pendientes", titulo: "No se pudo leer", valor: f => f.campos_pendientes?.length ? f.campos_pendientes.map(campo).join(", ") : "—" }, verFicha]} /> : <Vacio>No hay currículums pendientes de revisión.</Vacio>}</section>
    </div>
    {creando && <Ventana tamano="chica" titulo="Nueva búsqueda" cerrar={() => setCreando(false)}>{errorCreacion && <ErrorVisible mensaje={errorCreacion} />}<p className="ayuda">Definí el puesto y los requisitos. Después vas a poder subir los currículums y ver quién encaja.</p><form className="form-grid seleccion-form" onSubmit={crear}><label className="campo-ancho">Nombre del puesto<input name="nombre" required placeholder="Ej.: Operario de bodega, vendimia 2027" /></label><label className="campo-ancho">Perfil<select name="perfil">{Object.entries(PERFILES).map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label><label>Edad mínima<input name="edad_minima" type="number" min="0" placeholder="Sin mínimo" /></label><label>Edad máxima<input name="edad_maxima" type="number" min="0" placeholder="Sin máximo" /></label><label className="campo-ancho"><input name="secundaria_completa" type="checkbox" /><span>Exigir secundaria completa</span></label><div className="acciones campo-ancho"><button type="button" onClick={() => setCreando(false)}>Cancelar</button><button className="primario">Crear búsqueda</button></div></form></Ventana>}
    {busqueda && <Ventana tamano="amplia" titulo={abierta ? `Búsqueda: ${abierta.nombre}` : "Búsqueda"} cerrar={cerrarBusqueda}>
      {abierta && <p className="ayuda">{requisitos(abierta)} · abierta por {abierta.definido_por} el {new Date(abierta.definido_en).toLocaleDateString("es-AR")}</p>}
      <div className="seleccion-subir">{botonSubir(avisarBusqueda, true)}<p>Podés elegir varios PDF a la vez. El sistema los lee y los ordena según los requisitos de esta búsqueda.</p></div>
      {errorBusqueda && <ErrorVisible mensaje={errorBusqueda} />}{aviso && <div className="aviso-exito" role="status">{aviso}</div>}
      {ranking.length ? <><div className="seleccion-resumen"><span className="estado">{plural(cuenta.encajan, "encaja", "encajan")}</span><span className="estado estado-revisar">{cuenta.revisar} para revisar a mano</span><span className="estado estado-alerta">{plural(cuenta.fuera, "no encaja", "no encajan")}</span></div>
        <p className="preliminar">El orden es una ayuda, no una decisión: se arma con datos leídos automáticamente y todavía sin confirmar. Tocá un currículum para compararlo con el PDF y confirmar los datos.</p>
        <Tabla etiqueta="Ranking de la búsqueda" porPagina={10} filas={filasRanking} alElegir={f => abrir(f)} columnas={[{ clave: "posicion", titulo: "#", valor: f => Number(f.posicion) }, { clave: "nombre", titulo: "Currículum" }, { clave: "resultado", titulo: "Resultado", valor: f => { const v = veredicto(f.resultado); return <span className={v.clase}>{v.texto}</span>; } }, { clave: "motivo", titulo: "Por qué", valor: f => f.resultado?.razones?.length ? <Razones razones={f.resultado.razones} /> : "Sin evaluación" }, { clave: "puntaje", titulo: "Requisitos cumplidos", valor: f => f.resultado ? `${f.resultado.puntaje} de ${f.resultado.razones.length}` : "—" }, verFicha]} /></>
        : cargandoRanking ? <Vacio>Cargando los currículums de esta búsqueda…</Vacio> : <Vacio>Todavía no subiste currículums para esta búsqueda. Tocá «Subir currículums».</Vacio>}
    </Ventana>}
    {ficha && <Ventana tamano="amplia" titulo={`Currículum: ${ficha.nombre}`} cerrar={cerrarFicha}>{fichasIA[ficha.id] && (() => { const f = fichasIA[ficha.id]; return <section className="ficha-ia"><h3>Lo que leyó la IA</h3>{f.resumen && <p>{f.resumen}</p>}<dl className="ficha">{f.nombre_completo && <div><dt>Nombre</dt><dd>{f.nombre_completo}</dd></div>}{f.localidad && <div><dt>Localidad</dt><dd>{f.localidad}</dd></div>}{f.edad && <div><dt>Edad</dt><dd>{String(f.edad)}</dd></div>}{f.oficios?.length ? <div><dt>Oficios</dt><dd>{f.oficios.join(", ")}</dd></div> : null}{f.estudios?.length ? <div><dt>Estudios</dt><dd>{f.estudios.join(" · ")}</dd></div> : null}{f.idiomas?.length ? <div><dt>Idiomas</dt><dd>{f.idiomas.join(", ")}</dd></div> : null}</dl>{f.experiencia?.length ? <><h4>Experiencia</h4><ul>{f.experiencia.map((x, i) => <li key={i}>{[x.puesto, x.empresa, x.periodo].filter(Boolean).join(" · ")}</li>)}</ul></> : null}<p className="ayuda">Revisalo contra el original antes de decidir.</p></section>; })()}{errorVentana && <ErrorVisible mensaje={errorVentana} />}
      {ficha.resultado && abierta && <div className="ficha-resultado"><div className="titulo-fila"><h3>Para «{abierta.nombre}»</h3>{(() => { const v = veredicto(ficha.resultado); return <span className={v.clase}>{v.texto}</span>; })()}</div><Razones razones={ficha.resultado.razones} /></div>}
      <div className="ficha-doble"><div><p className="ayuda">Compará cada dato con el PDF original y confirmalo. Nada cuenta como confirmado hasta que lo hagas vos.</p>
        {ficha.pendientes.length > 0 && <p className="preliminar">No se pudo leer: {ficha.pendientes.map(campo).join(", ")}. Buscalo en el PDF.</p>}
        {ficha.campos.length ? ficha.campos.map(c => { const hecha = ficha.confirmaciones.find(x => x.campo === c.nombre); const fragmento = c.fragmento_fuente ?? c.fragmento; return <article className="campo-extraido" key={c.nombre}><span className="ayuda">{campo(c.nombre)}</span><strong>{c.valor}</strong>{fragmento && <p>Leído en el PDF: “{fragmento}”</p>}{hecha ? <span className="estado">Confirmado por {hecha.confirmado_por}</span> : <div className="acciones-inlinea"><span className="estado estado-revisar">Sin confirmar</span><button onClick={() => confirmar(c)}>Confirmar este dato</button></div>}</article>; }) : <Vacio>El sistema no pudo leer datos de este currículum. Revisalo en el PDF.</Vacio>}</div>
        {original ? <iframe className="visor visor-original" title="Currículum original" src={original} /> : <Vacio>Cargando el PDF original…</Vacio>}</div>
    </Ventana>}
  </>;
}
