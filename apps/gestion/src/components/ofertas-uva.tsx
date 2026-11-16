"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, FormularioVentana, Vacio, Ventana } from "./compartidos";

type Anio = { temporada: number; kg: number; desde: string | null; hasta: string | null; variedades: { variedad: string; kg: number }[] };
type Historial = { anios: Anio[]; anios_con_entregas: number; promedio_kg: number | null; entrego_ultimo: boolean };
type Oferta = {
  id: number; cuit: string; codigo: string | null; productor: string; productor_nuevo: boolean; variedad: string; kg: number; kg_a_programar: number;
  organica: boolean; canal: string; pedido_por: string; estado: string; motivo: string | null; detenida_hasta: string | null; creado_en: string;
  kg_dia: number; kg_dia_propio: boolean; dias_estimados: number; desde: string | null; hasta: string | null; dias: number;
  avisado_en: string | null; avisos_pendientes: number; historial: Historial; constancia: string; ofrecido_total_kg: number; sobreoferta_kg: number;
};
type Parametros = { anios_historial: number; tolerancia_sobreoferta: number; kg_dia_sugerido: number; semanas_stop: number[] };
type Listado = { temporada: number; parametros: Parametros; ofertas: Oferta[] };
type DiaPlan = { fecha: string; kg: number; camiones: number; kg_por_camion: number; libre_kg: number | null; exceso_kg: number };
type Previa = { dias: DiaPlan[]; kg_por_camion: number | null; exceso_kg: number; aviso: string };
type Productor = { cuit: string; razon_social: string; codigos: string[] };

const SEDES = [["chimbas", "Chimbas"], ["lavalle", "Lavalle"], ["media-agua", "Media Agua"]] as const;
const kg = (n: number) => `${n.toLocaleString("es-AR")} kg`;
const t = (n: number) => `${(n / 1000).toLocaleString("es-AR", { maximumFractionDigits: 1 })} t`;
const fecha = (f: string) => new Date(`${f.slice(0, 10)}T12:00:00`).toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" });
const diaLargo = (f: string) => { const s = new Date(`${f}T12:00:00`).toLocaleDateString("es-AR", { weekday: "long", day: "2-digit", month: "2-digit" }); return s[0].toUpperCase() + s.slice(1); };
const mensaje = (x: unknown) => x instanceof Error ? x.message : "No se pudo completar.";
const diaLocal = (mas: number) => { const d = new Date(); d.setDate(d.getDate() + mas); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const CONSTANCIA: Record<string, string> = { constante: "Entregó todos los años", algunos: "Entregó algunos años", solo_ultimo: "Sólo el último año", nuevo: "Sin entregas anteriores" };

function Estado({ o }: { o: Oferta }) {
  if (o.estado === "asignada" && o.desde && o.hasta) return <span className="estado estado-regularizado">Del {fecha(o.desde)} al {fecha(o.hasta)} · {o.dias} {o.dias === 1 ? "día" : "días"}</span>;
  if (o.estado === "detenida") return <span className="estado estado-alerta">Detenida por falta de grado{o.detenida_hasta ? ` hasta el ${fecha(o.detenida_hasta)}` : ""}</span>;
  if (o.estado === "desestimada") return <span className="estado estado-neutro" title={o.motivo ?? ""}>Desestimada{o.motivo ? `: ${o.motivo}` : ""}</span>;
  return <span className="estado estado-revisar">Sin días asignados</span>;
}

export function OfertasUva() {
  const [sede, setSede] = useState("chimbas"); const [datos, setDatos] = useState<Listado | null>(null);
  const [error, setError] = useState(""); const [aviso, setAviso] = useState("");
  const [estado, setEstado] = useState("todas"); const [prioridad, setPrioridad] = useState("todos"); const [variedad, setVariedad] = useState("");
  const [asignando, setAsignando] = useState<Oferta | null>(null); const [deteniendo, setDeteniendo] = useState<Oferta | null>(null);
  const [desestimando, setDesestimando] = useState<Oferta | null>(null); const [viendo, setViendo] = useState<Oferta | null>(null);
  const [cargando, setCargando] = useState(false); const [editandoParametros, setEditandoParametros] = useState(false);

  async function cargar() { try { setDatos(await api<Listado>(`turnos-bodega/ofertas?sede=${sede}`)); setError(""); } catch (x) { setError(mensaje(x)); } }
  useEffect(() => { cargar(); }, [sede]);

  const ofertas = datos?.ofertas ?? [];
  const variedades = useMemo(() => [...new Set(ofertas.map((o) => o.variedad))].sort(), [ofertas]);
  const visibles = ofertas.filter((o) =>
    (estado === "todas" || (estado === "pendiente" ? o.estado === "pendiente" : o.estado === estado))
    && (prioridad === "todos" || (prioridad === "alerta" ? o.sobreoferta_kg > 0 : o.constancia === prioridad))
    && (!variedad || o.variedad === variedad));
  const enPie = ofertas.filter((o) => o.estado !== "desestimada");
  const anios = datos?.parametros.anios_historial ?? 3;
  const listo = (texto: string) => { setAviso(texto); cerrarTodo(); cargar(); };
  function cerrarTodo() { setAsignando(null); setDeteniendo(null); setDesestimando(null); setViendo(null); setCargando(false); setEditandoParametros(false); }

  return <>
    {error && <ErrorVisible mensaje={error} />}
    {aviso && <div className="aviso-exito" role="status">{aviso}</div>}
    <section className="tarjeta">
      <div className="titulo-fila">
        <div><h2>Ofertas de uva · Cosecha {datos?.temporada ?? ""}</h2><p className="ayuda">Lo que cada productor ofrece para toda la temporada. Asignale los días corridos (sin domingos): se crean los turnos de cada día y se le avisa por WhatsApp.</p></div>
        <div className="acciones"><button onClick={() => setEditandoParametros(true)} disabled={!datos}>Parámetros</button><button className="primario" onClick={() => setCargando(true)}>Cargar oferta</button></div>
      </div>
      <div className="barra-filtros">
        <label>Bodega<select value={sede} onChange={(e) => setSede(e.target.value)}>{SEDES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>
        <label>Estado<select value={estado} onChange={(e) => setEstado(e.target.value)}><option value="todas">Todas</option><option value="pendiente">Sin días asignados</option><option value="asignada">Con días asignados</option><option value="detenida">Detenidas por falta de grado</option><option value="desestimada">Desestimadas</option></select></label>
        <label>Productores<select value={prioridad} onChange={(e) => setPrioridad(e.target.value)}><option value="todos">Todos</option><option value="constante">Entregaron los {anios} años</option><option value="algunos">Entregaron algunos años</option><option value="solo_ultimo">Sólo el último año</option><option value="nuevo">Sin entregas anteriores</option><option value="alerta">Ofrecen más que su promedio</option></select></label>
        <label>Variedad<select value={variedad} onChange={(e) => setVariedad(e.target.value)}><option value="">Todas</option>{variedades.map((v) => <option key={v}>{v}</option>)}</select></label>
      </div>
      <div className="metricas">
        <article><span>Ofrecido</span><strong>{t(enPie.reduce((s, o) => s + o.kg, 0))}</strong><small>{enPie.length} ofertas</small></article>
        <article><span>Sin días</span><strong>{t(enPie.filter((o) => o.estado !== "asignada").reduce((s, o) => s + o.kg_a_programar, 0))}</strong><small>{enPie.filter((o) => o.estado !== "asignada").length} ofertas</small></article>
        <article><span>Con días</span><strong>{t(enPie.filter((o) => o.estado === "asignada").reduce((s, o) => s + o.kg_a_programar, 0))}</strong><small>{enPie.filter((o) => o.estado === "asignada").length} ofertas</small></article>
        <article><span>Más que su promedio</span><strong>{new Set(enPie.filter((o) => o.sobreoferta_kg > 0).map((o) => o.cuit)).size}</strong><small>productores</small></article>
      </div>
      {visibles.length ? <div className="tabla-scroll"><table className="tabla-ofertas"><thead><tr><th>Productor</th><th>Variedad ofrecida</th><th>Últimos {anios} años</th><th>Días</th><th>Estado</th><th><span className="solo-lectores">Acciones</span></th></tr></thead><tbody>
        {visibles.map((o) => <tr key={o.id}>
          <td><strong>{o.productor}</strong>{o.codigo && <small> · {o.codigo}</small>}{o.productor_nuevo && <> <span className="estado estado-alerta">Productor nuevo</span></>}<br /><small>{o.canal === "whatsapp" ? "Por WhatsApp" : "Cargada por la bodega"} · {fecha(o.creado_en)}{o.organica ? " · Orgánica" : ""}</small></td>
          <td><strong>{o.variedad}</strong><br />{kg(o.kg)}{o.kg_a_programar !== o.kg && <><br /><small>Falta programar {kg(o.kg_a_programar)}</small></>}</td>
          <td><button className="enlace" onClick={() => setViendo(o)}>{o.historial.promedio_kg != null ? `Promedio ${t(o.historial.promedio_kg)}` : "Sin entregas"}</button><br /><small>{CONSTANCIA[o.constancia]}</small>
            {o.sobreoferta_kg > 0 && <><br /><span className="estado estado-alerta" title={`Ofrece ${t(o.ofrecido_total_kg)} en total esta temporada`}>En total ofrece {t(o.sobreoferta_kg)} más que su promedio</span></>}</td>
          <td>{o.estado === "asignada" ? o.dias : <>{o.dias_estimados}<br /><small>a {t(o.kg_dia)} por día{o.kg_dia_propio ? "" : " (sugerido)"}</small></>}</td>
          <td><Estado o={o} />{o.avisos_pendientes > 0 ? <><br /><small>Aviso por WhatsApp pendiente de envío</small></> : o.avisado_en ? <><br /><small>Avisado por WhatsApp el {fecha(o.avisado_en)}</small></> : null}</td>
          <td><div className="acciones-oferta">
            {(o.estado === "pendiente" || o.estado === "detenida") && <button className="primario" onClick={() => setAsignando(o)}>Asignar días</button>}
            {(o.estado === "pendiente" || o.estado === "asignada") && <button onClick={() => setDeteniendo(o)}>Stop por falta de grado</button>}
            {(o.estado === "pendiente" || o.estado === "detenida") && <button onClick={() => setDesestimando(o)}>Desestimar</button>}
          </div></td>
        </tr>)}
      </tbody></table></div> : <Vacio>{ofertas.length ? "Ninguna oferta coincide con los filtros." : "Todavía no hay ofertas para esta bodega."}</Vacio>}
    </section>
    {asignando && datos && <Asignar oferta={asignando} sugerido={datos.parametros.kg_dia_sugerido} cerrar={cerrarTodo} listo={listo} />}
    {deteniendo && datos && <FormularioVentana titulo="Stop por falta de grado" boton="Detener y avisar" cerrar={cerrarTodo} enviar={async (f) => {
      const r = await api<{ hasta: string }>(`turnos-bodega/ofertas/${deteniendo.id}/detener`, { method: "POST", body: JSON.stringify({ semanas: Number(f.get("semanas")) }) });
      listo(`${deteniendo.productor}: ${deteniendo.variedad} detenida hasta el ${fecha(r.hasta)}. Se le avisa por WhatsApp.`);
    }}>
      <p><strong>{deteniendo.productor}</strong> · {deteniendo.variedad} · {kg(deteniendo.kg_a_programar)}</p>
      <p className="ayuda">Se cancelan los días que todavía no recibieron camiones y la oferta queda para volver a asignarle días cuando la uva tenga el grado.</p>
      <label>Postergar<select name="semanas" defaultValue={datos.parametros.semanas_stop[0]}>{datos.parametros.semanas_stop.map((s) => <option key={s} value={s}>{s} {s === 1 ? "semana" : "semanas"}</option>)}</select></label>
    </FormularioVentana>}
    {desestimando && <FormularioVentana titulo="Desestimar oferta" boton="Desestimar" cerrar={cerrarTodo} enviar={async (f) => {
      await api(`turnos-bodega/ofertas/${desestimando.id}/desestimar`, { method: "POST", body: JSON.stringify({ motivo: String(f.get("motivo")) }) });
      listo(`Oferta de ${desestimando.productor} desestimada.`);
    }}>
      <p><strong>{desestimando.productor}</strong> · {desestimando.variedad} · {kg(desestimando.kg)}</p>
      <p className="ayuda">La oferta queda fuera de esta temporada. Al productor no se le envía ningún mensaje.</p>
      <label>Motivo<input name="motivo" required minLength={3} maxLength={300} autoFocus /></label>
    </FormularioVentana>}
    {viendo && <Ventana titulo={`Entregas de ${viendo.productor}`} cerrar={cerrarTodo}>
      <div className="tabla-scroll"><table><thead><tr><th>Cosecha</th><th>Kilos</th><th>Entregó</th><th>Variedades</th></tr></thead><tbody>
        {viendo.historial.anios.map((a) => <tr key={a.temporada}><td>{a.temporada}</td><td>{a.kg ? kg(a.kg) : "Sin entregas"}</td><td>{a.desde && a.hasta ? `Del ${fecha(a.desde)} al ${fecha(a.hasta)}` : "—"}</td><td>{a.variedades.map((v) => `${v.variedad} (${t(v.kg)})`).join(", ") || "—"}</td></tr>)}
      </tbody></table></div>
      <p>Promedio: <strong>{viendo.historial.promedio_kg != null ? kg(viendo.historial.promedio_kg) : "sin entregas"}</strong> · Ofrece esta temporada: <strong>{kg(viendo.ofrecido_total_kg)}</strong>{viendo.sobreoferta_kg > 0 && <> · <span className="estado estado-alerta">{t(viendo.sobreoferta_kg)} más que su promedio</span></>}</p>
    </Ventana>}
    {cargando && <CargarOferta sede={sede} cerrar={cerrarTodo} listo={listo} />}
    {editandoParametros && datos && <FormularioVentana titulo="Parámetros de las ofertas" boton="Guardar" cerrar={cerrarTodo} enviar={async (f) => {
      const semanas = String(f.get("semanas")).split(/[^0-9]+/).filter(Boolean).map(Number);
      await api("turnos-bodega/ofertas/parametros", { method: "PUT", body: JSON.stringify({ anios_historial: Number(f.get("anios")), tolerancia_sobreoferta: Number(f.get("tolerancia")), kg_dia_sugerido: Number(f.get("kg_dia")), semanas_stop: semanas }) });
      listo("Parámetros guardados.");
    }}>
      <label>Años de historial para comparar<input name="anios" type="number" min="1" max="10" required defaultValue={datos.parametros.anios_historial} /></label>
      <label>Margen antes de avisar que ofrece de más (%)<input name="tolerancia" type="number" min="0" max="500" required defaultValue={datos.parametros.tolerancia_sobreoferta} /></label>
      <label>Kilos por día sugeridos para un productor sin ritmo cargado<input name="kg_dia" type="number" min="1000" step="500" required defaultValue={datos.parametros.kg_dia_sugerido} /></label>
      <label>Semanas para postergar por falta de grado (separadas por coma)<input name="semanas" required defaultValue={datos.parametros.semanas_stop.join(", ")} /></label>
    </FormularioVentana>}
  </>;
}

function Asignar({ oferta, sugerido, cerrar, listo }: { oferta: Oferta; sugerido: number; cerrar: () => void; listo: (texto: string) => void }) {
  const [inicio, setInicio] = useState(diaLocal(1)); const [kgDia, setKgDia] = useState(String(oferta.kg_dia_propio ? oferta.kg_dia : sugerido)); const [kgCamion, setKgCamion] = useState("");
  const [previa, setPrevia] = useState<Previa | null>(null); const [error, setError] = useState(""); const [ocupado, setOcupado] = useState(false);
  const cuerpo = () => JSON.stringify({ inicio, kg_dia: Number(kgDia), kg_por_camion: kgCamion ? Number(kgCamion) : null });
  async function calcular(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setOcupado(true);
    try { const p = await api<Previa>(`turnos-bodega/ofertas/${oferta.id}/vista-previa`, { method: "POST", body: cuerpo() }); setPrevia(p); if (!kgCamion && p.kg_por_camion) setKgCamion(String(p.kg_por_camion)); } catch (x) { setError(mensaje(x)); setPrevia(null); }
    setOcupado(false);
  }
  async function confirmar() {
    setError(""); setOcupado(true);
    try { const r = await api<{ dias: number; desde: string; hasta: string }>(`turnos-bodega/ofertas/${oferta.id}/asignar`, { method: "POST", body: cuerpo() }); listo(`${oferta.productor}: ${r.dias} días asignados, del ${fecha(r.desde)} al ${fecha(r.hasta)}. Se le avisa por WhatsApp.`); } catch (x) { setError(mensaje(x)); }
    setOcupado(false);
  }
  return <Ventana titulo="Asignar días" cerrar={cerrar}>
    <p><strong>{oferta.productor}</strong> · {oferta.variedad} · {kg(oferta.kg_a_programar)}{oferta.organica ? " · Orgánica" : ""}</p>
    {error && <ErrorVisible mensaje={error} />}
    <form className="form-grid" onSubmit={calcular}>
      <label>Primer día<input type="date" required min={diaLocal(0)} value={inicio} onChange={(e) => { setInicio(e.target.value); setPrevia(null); }} /></label>
      <label>Kilos por día de este productor<input type="number" min="1000" step="500" required value={kgDia} onChange={(e) => { setKgDia(e.target.value); setPrevia(null); }} /></label>
      <label>Kilos por camión<input type="number" min="1000" max="40000" step="500" placeholder="Según sus últimas descargas" value={kgCamion} onChange={(e) => { setKgCamion(e.target.value); setPrevia(null); }} /></label>
      <button disabled={ocupado}>Calcular días</button>
    </form>
    {previa && <>
      {previa.exceso_kg > 0 && <p className="estado estado-alerta" role="alert">Hay días en que la bodega se pasa de su capacidad ({t(previa.exceso_kg)} en total). Podés asignarlo igual o cambiar el primer día.</p>}
      <div className="tabla-scroll"><table><thead><tr><th>Día</th><th>Camiones</th><th>Kilos</th><th>Libre en la bodega</th></tr></thead><tbody>
        {previa.dias.map((d) => <tr key={d.fecha} className={d.exceso_kg ? "fila-alerta" : ""}><td>{diaLargo(d.fecha)}</td><td>{d.camiones} de {kg(d.kg_por_camion)}</td><td>{kg(d.camiones * d.kg_por_camion)}</td><td>{d.libre_kg == null ? "Sin capacidad definida" : d.exceso_kg ? <span className="estado estado-alerta">Se pasa {t(d.exceso_kg)}</span> : t(d.libre_kg)}</td></tr>)}
      </tbody></table></div>
      <label className="aviso-whatsapp">Mensaje que recibe el productor<textarea readOnly rows={Math.min(14, previa.aviso.split("\n").length + 1)} value={previa.aviso} /></label>
    </>}
    <div className="acciones"><button type="button" onClick={cerrar}>Cancelar</button><button className="primario" disabled={!previa || ocupado} onClick={confirmar}>Asignar {previa ? `${previa.dias.length} días` : "días"} y avisar</button></div>
  </Ventana>;
}

function CargarOferta({ sede, cerrar, listo }: { sede: string; cerrar: () => void; listo: (texto: string) => void }) {
  const [nuevo, setNuevo] = useState(false); const [busqueda, setBusqueda] = useState(""); const [resultados, setResultados] = useState<Productor[]>([]);
  const [productor, setProductor] = useState<Productor | null>(null); const [variedades, setVariedades] = useState<string[]>([]);
  useEffect(() => { api<string[]>("turnos-bodega/ofertas/variedades").then(setVariedades).catch(() => setVariedades([])); }, []);
  useEffect(() => { const q = busqueda.trim(); if (nuevo || q.length < 2 || productor) { setResultados([]); return; } const r = setTimeout(() => api<Productor[]>(`turnos-bodega/ofertas/productores?q=${encodeURIComponent(q)}`).then(setResultados).catch(() => setResultados([])), 250); return () => clearTimeout(r); }, [busqueda, productor, nuevo]);
  return <FormularioVentana titulo="Cargar oferta" boton="Guardar oferta" cerrar={cerrar} enviar={async (f) => {
    const cuit = nuevo ? String(f.get("cuit")).replace(/\D/g, "") : productor?.cuit;
    if (!cuit) throw new Error("Elegí el productor de la lista o marcá que es un productor nuevo.");
    await api("turnos-bodega/ofertas", { method: "POST", body: JSON.stringify({ sede, cuit, nombre_nuevo: nuevo ? String(f.get("nombre")) : null, codigo: productor?.codigos[0] ?? null, variedad: String(f.get("variedad")), kg: Number(f.get("kg")), organica: f.get("organica") === "si" }) });
    listo("Oferta cargada.");
  }}>
    <label className="casilla"><input type="checkbox" checked={nuevo} onChange={(e) => { setNuevo(e.target.checked); setProductor(null); setBusqueda(""); }} /> Productor nuevo (todavía no está en la lista)</label>
    {nuevo ? <>
      <label>CUIT<input name="cuit" required inputMode="numeric" pattern="[0-9-]{11,13}" placeholder="20-12345678-9" /></label>
      <label>Nombre o razón social<input name="nombre" required minLength={2} maxLength={120} /></label>
    </> : <label className="campo-buscable">Productor (nombre, CUIT o código)<input value={busqueda} onChange={(e) => { setBusqueda(e.target.value); setProductor(null); }} placeholder="Escribí al menos 2 letras" autoComplete="off" autoFocus />
      {resultados.length > 0 && <div className="resultados-busqueda">{resultados.map((p) => <button type="button" key={p.cuit} onClick={() => { setProductor(p); setBusqueda(p.razon_social); setResultados([]); }}><strong>{p.razon_social}</strong><span>CUIT {p.cuit}{p.codigos.length ? ` · ${p.codigos.join(", ")}` : ""}</span></button>)}</div>}
      {productor && <small>Elegido: {productor.razon_social}</small>}</label>}
    <label>Variedad<input name="variedad" required maxLength={60} list="variedades-oferta" /><datalist id="variedades-oferta">{variedades.map((v) => <option key={v} value={v} />)}</datalist></label>
    <label>Kilos para toda la temporada<input name="kg" type="number" min="1000" step="500" required /></label>
    <label>Uva orgánica<select name="organica" defaultValue="no"><option value="no">No</option><option value="si">Sí (requiere certificado vigente)</option></select></label>
  </FormularioVentana>;
}
