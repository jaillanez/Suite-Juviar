"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { abrirArchivo, api, ocultarMarcasPrueba } from "@/lib/api";
import { ErrorVisible, Tabla, Vacio, Ventana } from "./compartidos";

type Catalogo = Record<string, unknown> & { codigo: string; producto: string; tipo_modelo: string; marca: string; posee_certificacion: boolean; certificacion: string | null; unidad: string; vida_util_dias: number | null; familia: string; destino_declarado: string | null; criterio_vida_util: string; activo: boolean; simulado: boolean; items: Array<{ codigo_interno: string; marca: string; modelo: string; talle: string; activo: boolean }> };
type Stock = Record<string, unknown> & { item_codigo: string; disponible: number; minimo: number; estado: string };
type Aviso = Record<string, unknown> & { id: number; identificador: string; estado: string; intentos: number; proximo_reintento?: string };
type Entrega = Record<string, unknown> & { id: string; persona: string; legajo: string; sector: string; fecha: string; motivo: string };
type PlanProgramado = { fecha: string; temporada: string; legajo: string; nombre_completo: string; puesto: string; sector: string; sector_codigo: string; elementos: Array<{ codigo: string; cantidad: number; origen: string }> };
type Matriz = { estado: string; validacion?: { firmada_por: string; firmada_en: string }; historial: Array<Record<string, unknown>> };
type Puesto = { codigo: string; nombre: string };
type Sector = { codigo: string; nombre: string };
type Requisito = { codigo: string; cantidad: number; frecuencia: string; temporada: string; obligatorio: boolean; fundamento: string };
type Vista = "catalogo" | "matriz" | "stock" | "planillas" | "entregas";

const etiquetaPuesto = (puesto: Puesto) => `${puesto.nombre} · ${puesto.codigo}`;
const etiquetaElemento = (elemento: Catalogo) => `${elemento.producto} · ${elemento.familia} · ${elemento.codigo}`;

type RequisitoResumen = { codigo: string; elemento: string; cantidad: number; frecuencia: string; temporada: string; obligatorio: boolean; fundamento: string; origen: string };
type GrupoMatriz = Record<string, unknown> & { sector_codigo: string; sector: string; puesto_codigo: string; puesto: string; personas: number; requisitos: RequisitoResumen[] };
type Movimiento = { id: number; cantidad: number; tipo: string; motivo: string; actor: string; creado_en: string };
const ORIGENES: Record<string, string> = { BASE: "Base de todo el personal", SECTOR: "Por el sector", PUESTO: "Por el puesto" };
const FRECUENCIAS: Record<string, string> = { SEMESTRAL: "Semestral", ANUAL: "Anual", A_DEMANDA: "A demanda" };
const TEMPORADAS: Record<string, string> = { VERANO: "Verano", INVIERNO: "Invierno", TODO_EL_ANIO: "Todo el año" };

export function EppGestion() {
  const cargaInicial = useRef(false);
  const [vista, setVista] = useState<Vista>("catalogo");
  const [catalogo, setCatalogo] = useState<Catalogo[]>([]); const [stock, setStock] = useState<Stock[]>([]);
  const [puestos, setPuestos] = useState<Puesto[]>([]);
  const [sectores, setSectores] = useState<Sector[]>([]);
  const [codigoElemento, setCodigoElemento] = useState(""); const [nombreElemento, setNombreElemento] = useState(""); const [familiaElemento, setFamiliaElemento] = useState("");
  const [avisos, setAvisos] = useState<Aviso[]>([]); const [avisosVedados, setAvisosVedados] = useState(false); const [entregas, setEntregas] = useState<Entrega[]>([]);
  const [fechaPlanilla, setFechaPlanilla] = useState(hoyLocal()); const [temporadaPlanilla, setTemporadaPlanilla] = useState<"VERANO" | "INVIERNO">("VERANO"); const [sectorPlanilla, setSectorPlanilla] = useState(""); const [planes, setPlanes] = useState<PlanProgramado[]>([]); const [planillaConsultada, setPlanillaConsultada] = useState(false);
  const [matriz, setMatriz] = useState<Matriz>({ estado: "SIN_VALIDAR", historial: [] });
  const [resumenMatriz, setResumenMatriz] = useState<GrupoMatriz[]>([]); const [grupoAbierto, setGrupoAbierto] = useState<GrupoMatriz | null>(null);
  const nombreItem = (codigo: string) => { for (const e of catalogo) { const it = e.items.find(i => i.codigo_interno === codigo); if (it) return [e.producto, it.modelo, it.talle !== "SIN_DATO" ? `talle ${it.talle}` : ""].filter(Boolean).join(" · "); } return codigo; };
  type FilaGrilla = { elemento: string; cantidad: number; frecuencia: string; temporada: string; obligatorio: boolean; fundamento: string };
  const filaNueva = (): FilaGrilla => ({ elemento: "", cantidad: 1, frecuencia: "ANUAL", temporada: "TODO_EL_ANIO", obligatorio: true, fundamento: "" });
  const [grilla, setGrilla] = useState<{ puesto: string; filas: FilaGrilla[] } | null>(null); const [errorGrilla, setErrorGrilla] = useState(""); const [guardandoGrilla, setGuardandoGrilla] = useState(false);
  const abrirGrilla = (puesto = "") => { setErrorGrilla(""); setGrilla({ puesto, filas: [filaNueva(), filaNueva(), filaNueva()] }); };
  const cambiarFila = (i: number, cambio: Partial<FilaGrilla>) => setGrilla(g => g && { ...g, filas: g.filas.map((f, j) => j === i ? { ...f, ...cambio } : f) });
  async function guardarGrilla() {
    if (!grilla) return; setErrorGrilla("");
    const puesto = puestos.find(p => p.codigo === grilla.puesto);
    if (!puesto) { setErrorGrilla("Elegí el puesto."); return; }
    const cargadas = grilla.filas.filter(f => f.elemento.trim());
    if (!cargadas.length) { setErrorGrilla("Cargá al menos un elemento."); return; }
    const nuevos: Requisito[] = [];
    for (const [i, f] of cargadas.entries()) {
      const elemento = catalogo.find(item => etiquetaElemento(item) === f.elemento || item.codigo === f.elemento || item.producto.toLowerCase() === f.elemento.trim().toLowerCase());
      if (!elemento) { setErrorGrilla(`Fila ${i + 1}: elegí el elemento de la lista.`); return; }
      if (!f.fundamento.trim()) { setErrorGrilla(`Fila ${i + 1}: falta el motivo.`); return; }
      nuevos.push({ codigo: elemento.codigo, cantidad: Math.max(1, Number(f.cantidad) || 1), frecuencia: f.frecuencia, temporada: f.temporada, obligatorio: f.obligatorio, fundamento: f.fundamento.trim() });
    }
    setGuardandoGrilla(true);
    try {
      const actuales = await api<Requisito[]>(`rrhh-epp/matriz/puestos/${puesto.codigo}`);
      const codigos = new Set(nuevos.map(n => n.codigo));
      await api(`rrhh-epp/matriz/puestos/${puesto.codigo}`, { method: "PUT", body: JSON.stringify({ requisitos: [...actuales.filter(r => !codigos.has(r.codigo)), ...nuevos] }) });
      setMensaje(`${nuevos.length} ${nuevos.length === 1 ? "elemento asignado" : "elementos asignados"} a ${puesto.nombre}.`);
      setGrilla(null);
      const resumen = await api<GrupoMatriz[]>("rrhh-epp/matriz/resumen"); setResumenMatriz(resumen);
      if (grupoAbierto) setGrupoAbierto(resumen.find(g => g.sector_codigo === grupoAbierto.sector_codigo && g.puesto_codigo === grupoAbierto.puesto_codigo) ?? null);
      recargar();
    } catch (x) { setErrorGrilla(x instanceof Error ? x.message : "No se pudo guardar."); } finally { setGuardandoGrilla(false); }
  }
  const [itemAbierto, setItemAbierto] = useState<Stock | null>(null); const [movimientos, setMovimientos] = useState<Movimiento[]>([]); const [errorVentanaEpp, setErrorVentanaEpp] = useState("");
  const [error, setError] = useState(""); const [mensaje, setMensaje] = useState(""); const [previa, setPrevia] = useState<Record<string, unknown> | null>(null);
  const [confirmarReemplazo, setConfirmarReemplazo] = useState(false); const [limpieza, setLimpieza] = useState<Record<string, number> | null>(null); const [fraseLimpieza, setFraseLimpieza] = useState("");
  const hoy = new Date().toISOString().slice(0, 10); const inicio = `${new Date().getFullYear()}-01-01`;
  const informar = (e: unknown) => setError(e instanceof Error ? e.message : "No fue posible completar la operación.");
  const nombreElementoPlan = (codigo: string) => catalogo.find(item => item.codigo === codigo)?.producto ?? `Elemento ${codigo}`;
  async function recargar() {
    setError("");
    try {
      const [c, s, m, p, sectoresDisponibles] = await Promise.all([api<Catalogo[]>("rrhh-epp/catalogo"), api<Stock[]>("rrhh-epp/stock"), api<Matriz>("rrhh-epp/matriz/estado"), api<Puesto[]>("rrhh-epp/matriz/puestos"), api<Sector[]>("rrhh-epp/matriz/sectores")]);
      setCatalogo(c); setStock(s); setMatriz(m); setPuestos(p); setSectores(sectoresDisponibles);
      api<GrupoMatriz[]>("rrhh-epp/matriz/resumen").then(setResumenMatriz).catch(() => setResumenMatriz([]));
      api<Aviso[]>("rrhh-epp/avisos-compras").then(a => { setAvisos(a); setAvisosVedados(false); }).catch(() => { setAvisos([]); setAvisosVedados(true); });
      api<Entrega[]>(`rrhh-epp/entregas?desde=${inicio}&hasta=${hoy}`).then(setEntregas).catch(() => setEntregas([]));
      api<Record<string, number>>("rrhh-epp/datos-prueba").then(setLimpieza).catch(() => setLimpieza(null));
    } catch (e) { informar(e); }
  }
  useEffect(() => {
    if (cargaInicial.current) return;
    cargaInicial.current = true;
    void recargar();
  }, []);
  const [detalle, setDetalle] = useState<Catalogo | null>(null);
  const [editandoElemento, setEditandoElemento] = useState(false); const [errorVentana, setErrorVentana] = useState("");
  function editarDetalle(item: Catalogo) {
    setDetalle(null); cambiarCodigoElemento(item.codigo); setErrorVentana(""); setEditandoElemento(true);
  }
  function nuevoElemento() { setCodigoElemento(""); setNombreElemento(""); setFamiliaElemento(""); setErrorVentana(""); setMensaje(""); setEditandoElemento(true); }
  function cerrarElemento() { setEditandoElemento(false); setCodigoElemento(""); setNombreElemento(""); setFamiliaElemento(""); setErrorVentana(""); }
  function cambiarCodigoElemento(valor: string) {
    setCodigoElemento(valor);
    const existente = catalogo.find(item => item.codigo.toLocaleLowerCase("es") === valor.trim().toLocaleLowerCase("es"));
    if (existente) {
      setNombreElemento(existente.producto);
      setFamiliaElemento(existente.familia);
    } else {
      setNombreElemento("");
      setFamiliaElemento("");
    }
  }
  async function guardarElemento(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setErrorVentana("");
    const codigo = codigoElemento.trim();
    const existente = catalogo.find(item => item.codigo.toLocaleLowerCase("es") === codigo.toLocaleLowerCase("es"));
    const cuerpo = existente ? {
      producto: nombreElemento,
      tipo_modelo: existente.tipo_modelo,
      marca: existente.marca,
      posee_certificacion: existente.posee_certificacion,
      certificacion: existente.certificacion,
      unidad: existente.unidad,
      vida_util_dias: existente.vida_util_dias,
      familia: familiaElemento,
      destino_declarado: existente.destino_declarado,
      criterio_vida_util: existente.criterio_vida_util,
    } : { producto: nombreElemento, familia: familiaElemento };
    try {
      await api(`rrhh-epp/catalogo/elementos/${codigo}`, { method: existente ? "PUT" : "POST", body: JSON.stringify(cuerpo) });
      setMensaje(existente ? `${nombreElemento} actualizado.` : `${nombreElemento} agregado al catálogo.`);
      setCodigoElemento(""); setNombreElemento(""); setFamiliaElemento(""); setEditandoElemento(false);
      recargar();
    } catch (x) { setErrorVentana(x instanceof Error ? x.message : "No fue posible completar la operación."); }
  }
  async function importar(archivo?: File) { if (!archivo) return; const contenido_base64 = await new Promise<string>((ok, mal) => { const l = new FileReader(); l.onerror = mal; l.onload = () => ok(String(l.result).split(",")[1]); l.readAsDataURL(archivo); }); try { setConfirmarReemplazo(false); setPrevia(await api("rrhh-epp/catalogo/importaciones", { method: "POST", body: JSON.stringify({ contenido_base64 }) })); } catch (x) { informar(x); } }
  async function aplicar() { if (!previa?.identificador) return; try { await api(`rrhh-epp/catalogo/importaciones/${previa.identificador}/aplicar`, { method: "POST" }); setMensaje("Reemplazo aplicado; los ítems ausentes quedaron inactivos."); setPrevia(null); recargar(); } catch (x) { informar(x); } }
  async function guardarMatriz(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formulario = e.currentTarget;
    const f = Object.fromEntries(new FormData(formulario));
    const puesto = grupoAbierto ? { codigo: grupoAbierto.puesto_codigo, nombre: grupoAbierto.puesto } : puestos.find(p => etiquetaPuesto(p) === f.puesto || p.codigo === f.puesto);
    const elemento = catalogo.find(item => etiquetaElemento(item) === f.elemento || item.codigo === f.elemento);
    const avisar = grupoAbierto ? setErrorVentanaEpp : setError;
    if (!puesto) { avisar("Elegí un puesto de la lista."); return; }
    if (!elemento) { avisar("Elegí un elemento del catálogo."); return; }
    try {
      const actuales = await api<Requisito[]>(`rrhh-epp/matriz/puestos/${puesto.codigo}`);
      const existente = actuales.find(requisito => requisito.codigo === elemento.codigo);
      const actualizado: Requisito = {
        codigo: elemento.codigo,
        cantidad: Number(f.cantidad),
        frecuencia: existente?.frecuencia ?? "A_DEMANDA",
        temporada: existente?.temporada ?? "TODO_EL_ANIO",
        obligatorio: existente?.obligatorio ?? true,
        fundamento: String(f.fundamento),
      };
      const requisitos = [...actuales.filter(requisito => requisito.codigo !== elemento.codigo), actualizado];
      await api(`rrhh-epp/matriz/puestos/${puesto.codigo}`, { method: "PUT", body: JSON.stringify({ requisitos }) });
      setMensaje(`${elemento.producto} quedó asignado a ${puesto.nombre}.`);
      formulario.reset();
      if (grupoAbierto) {
        const nuevos = await api<GrupoMatriz[]>("rrhh-epp/matriz/resumen");
        setResumenMatriz(nuevos);
        setGrupoAbierto(nuevos.find(g => g.sector_codigo === grupoAbierto.sector_codigo && g.puesto_codigo === grupoAbierto.puesto_codigo) ?? null);
        setErrorVentanaEpp("");
      }
      recargar();
    } catch (x) { if (grupoAbierto) setErrorVentanaEpp(x instanceof Error ? x.message : "No se pudo asignar."); else informar(x); }
  }
  async function abrirItem(item: Stock) { setItemAbierto(item); setErrorVentanaEpp(""); setMovimientos([]); try { setMovimientos(await api<Movimiento[]>(`rrhh-epp/stock/${encodeURIComponent(item.item_codigo)}/movimientos`)); } catch (x) { setErrorVentanaEpp(x instanceof Error ? x.message : "No se pudieron leer los movimientos."); } }
  async function mover(e: FormEvent<HTMLFormElement>) { e.preventDefault(); if (!itemAbierto) return; const form = e.currentTarget; const f = Object.fromEntries(new FormData(form)); try { await api(`rrhh-epp/stock/${encodeURIComponent(itemAbierto.item_codigo)}/movimientos`, { method: "POST", body: JSON.stringify({ cantidad: Number(f.cantidad), tipo: f.tipo, motivo: f.motivo }) }); form.reset(); setMensaje("Movimiento registrado."); const s = await api<Stock[]>("rrhh-epp/stock"); setStock(s); const actual = s.find(x => x.item_codigo === itemAbierto.item_codigo); if (actual) await abrirItem(actual); } catch (x) { setErrorVentanaEpp(x instanceof Error ? x.message : "No se pudo registrar."); } }
  async function reenviar(id: number) { try { await api(`rrhh-epp/avisos-compras/${id}/reenviar`, { method: "POST" }); setMensaje("Reenvío encolado con el mismo identificador."); recargar(); } catch (x) { informar(x); } }
  async function limpiarPruebas() { try { const resultado = await api<Record<string, number>>("rrhh-epp/datos-prueba/limpiar", { method: "POST", body: JSON.stringify({ confirmacion: "LIMPIAR DATOS SIMULADOS" }) }); setMensaje(`Demostración restablecida: ${resultado.entregas} entregas y ${resultado.constancias} constancias eliminadas.`); setFraseLimpieza(""); recargar(); } catch (x) { informar(x); } }
  async function armarPlanilla(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setMensaje(""); setPlanillaConsultada(false);
    try {
      const parametros = new URLSearchParams({ fecha: fechaPlanilla, temporada: temporadaPlanilla });
      if (sectorPlanilla.trim()) parametros.set("sector", sectorPlanilla.trim());
      setPlanes(await api<PlanProgramado[]>(`rrhh-epp/entregas-programadas?${parametros}`));
      setPlanillaConsultada(true);
    } catch (x) { informar(x); }
  }
  async function verConstancia(id: string) { try { await abrirArchivo(`rrhh-epp/constancias/${id}.pdf`); } catch (x) { informar(x); } }
  const planesPorSector = Object.entries(planes.reduce<Record<string, PlanProgramado[]>>((grupos, plan) => { (grupos[plan.sector] ??= []).push(plan); return grupos; }, {}));
  return <><div className="metricas"><article><span>Elementos</span><strong>{catalogo.length || "—"}</strong><small>Catálogo disponible</small></article><article><span>Bajo mínimo</span><strong>{stock.filter(x => x.disponible < x.minimo).length || "0"}</strong><small>Generan avisos, no pedidos</small></article><article><span>Matriz</span><strong>{matriz.validacion ? "Firmada" : "Pendiente"}</strong><small>{matriz.validacion ? `${matriz.validacion.firmada_por} · ${new Date(matriz.validacion.firmada_en).toLocaleString("es-AR")}` : "Revisión de Higiene y Seguridad"}</small></article></div>
    {error && <ErrorVisible mensaje={error} />}{mensaje && <div className="aviso-exito" role="status">{mensaje}</div>}
    <nav className="pestanas" aria-label="Áreas de EPP">{(["catalogo", "matriz", "stock", "planillas", "entregas"] as Vista[]).map(v => <button key={v} className={vista === v ? "activo" : ""} onClick={() => setVista(v)}>{v[0].toUpperCase() + v.slice(1)}</button>)}</nav>
    {vista === "catalogo" && <div className="rejilla"><section className="tarjeta"><div className="titulo-fila"><h2>Catálogo RD 062/11</h2><button className="primario" onClick={nuevoElemento}>Agregar o editar elemento</button></div><p className="ayuda">Tocá un elemento para ver su detalle y editarlo.</p><Tabla etiqueta="Catálogo EPP" filas={catalogo} alElegir={setDetalle} columnas={[{ clave: "codigo", titulo: "Código" }, { clave: "producto", titulo: "Elemento" }, { clave: "familia", titulo: "Familia" }, { clave: "activo", titulo: "Estado", valor: f => f.activo ? "Activo" : "Baja lógica" }]} /></section><section className="tarjeta"><h2>Reemplazar desde Excel de HyS</h2><input aria-label="Excel de HyS" type="file" accept=".xlsx" onChange={e => importar(e.target.files?.[0])} />{previa && <div className="previsualizacion"><p className="preliminar"><strong>{Number(previa.entregas_afectadas)} entregas quedarían vinculadas a ítems dados de baja.</strong> Se conservan sus constancias y referencias históricas.</p><pre>{JSON.stringify(previa, null, 2)}</pre><label><input type="checkbox" checked={confirmarReemplazo} onChange={e => setConfirmarReemplazo(e.target.checked)} /> Confirmo que revisé altas, cambios, desapariciones y entregas afectadas</label><button className="primario" disabled={!confirmarReemplazo} onClick={aplicar}>Aplicar reemplazo</button></div>}</section>{limpieza && !ocultarMarcasPrueba && <section className="tarjeta"><h2>Restablecer demostración</h2><p>Se eliminarán {limpieza.entregas} entregas y {limpieza.constancias} constancias cargadas durante las pruebas.</p><label>Escribí REINICIAR DEMOSTRACIÓN<input value={fraseLimpieza} onChange={e => setFraseLimpieza(e.target.value)} /></label><button className="peligro" disabled={fraseLimpieza !== "REINICIAR DEMOSTRACIÓN"} onClick={limpiarPruebas}>Restablecer demostración</button></section>}</div>}
    {detalle && <Ventana titulo={`${detalle.codigo} · ${detalle.producto}`} cerrar={() => setDetalle(null)}>
      <dl className="ficha">
        <div><dt>Familia</dt><dd>{detalle.familia || "—"}</dd></div>
        <div><dt>Tipo o modelo</dt><dd>{detalle.tipo_modelo || "—"}</dd></div>
        <div><dt>Marca</dt><dd>{detalle.marca || "—"}</dd></div>
        <div><dt>Certificación</dt><dd>{detalle.posee_certificacion ? detalle.certificacion || "Sí" : "No"}</dd></div>
        <div><dt>Unidad</dt><dd>{detalle.unidad || "—"}</dd></div>
        <div><dt>Vida útil</dt><dd>{detalle.vida_util_dias ? `${detalle.vida_util_dias} días` : "—"}</dd></div>
        <div><dt>Criterio de vida útil</dt><dd>{detalle.criterio_vida_util || "—"}</dd></div>
        <div><dt>Destino</dt><dd>{detalle.destino_declarado || "—"}</dd></div>
        <div><dt>Estado</dt><dd>{detalle.activo ? "Activo" : "Baja lógica"}</dd></div>
      </dl>
      <h3>Variantes ({detalle.items.length})</h3>
      {detalle.items.length ? <div className="tabla-scroll"><table><thead><tr><th>Código interno</th><th>Marca</th><th>Modelo</th><th>Talle</th><th>Estado</th></tr></thead><tbody>{detalle.items.map(item => <tr key={item.codigo_interno}><td>{item.codigo_interno}</td><td>{item.marca}</td><td>{item.modelo}</td><td>{item.talle}</td><td>{item.activo ? "Activo" : "Baja"}</td></tr>)}</tbody></table></div> : <Vacio>Sin variantes cargadas.</Vacio>}
      <div className="acciones"><button onClick={() => setDetalle(null)}>Cerrar</button><button className="primario" onClick={() => editarDetalle(detalle)}>Editar elemento</button></div>
    </Ventana>}
    {editandoElemento && <Ventana titulo={catalogo.some(item => item.codigo.toLocaleLowerCase("es") === codigoElemento.trim().toLocaleLowerCase("es")) ? "Editar elemento" : "Agregar elemento"} cerrar={cerrarElemento}><p className="ayuda">Escribí un código existente para cargar sus datos, o uno nuevo para agregarlo.</p>{errorVentana && <ErrorVisible mensaje={errorVentana} />}<form className="formulario-ventana" onSubmit={guardarElemento}><label>Código o elemento<input name="codigo" list="catalogo-codigos" value={codigoElemento} onChange={e => cambiarCodigoElemento(e.target.value)} placeholder="Buscá por código o nombre" autoComplete="off" required autoFocus /></label><datalist id="catalogo-codigos">{catalogo.map(item => <option key={item.codigo} value={item.codigo}>{item.producto} · {item.familia}</option>)}</datalist>{codigoElemento && <p className="ayuda">{catalogo.some(item => item.codigo.toLocaleLowerCase("es") === codigoElemento.trim().toLocaleLowerCase("es")) ? "Elemento encontrado: podés editar sus datos." : "Código nuevo: completá sus datos."}</p>}<label>Elemento<input name="producto" value={nombreElemento} onChange={e => setNombreElemento(e.target.value)} required /></label><label>Familia<input name="familia" value={familiaElemento} onChange={e => setFamiliaElemento(e.target.value)} required /></label><div className="acciones"><button type="button" onClick={cerrarElemento}>Cancelar</button><button className="primario">{catalogo.some(item => item.codigo.toLocaleLowerCase("es") === codigoElemento.trim().toLocaleLowerCase("es")) ? "Guardar cambios" : "Agregar elemento"}</button></div></form></Ventana>}
    {vista === "matriz" && <div className="rejilla"><section className="tarjeta"><div className="titulo-fila"><div><h2>Protección por puesto</h2><p className="ayuda">Lo que le corresponde a cada puesto: la base de todo el personal, lo de su sector y lo propio del puesto. Tocá un puesto para ver el detalle o asignarle un elemento.</p></div><div className="acciones"><span className="estado">{matriz.estado === "VALIDADA_HYS" ? "Validada por HyS" : "Propuesta sin validar"}</span><button className="primario" onClick={() => abrirGrilla()}>Nueva asignación</button></div></div><Tabla etiqueta="Matriz por puesto" filas={resumenMatriz} porPagina={12} alElegir={(g) => { setGrupoAbierto(g); setErrorVentanaEpp(""); }} columnas={[{ clave: "sector", titulo: "Sector" }, { clave: "puesto", titulo: "Puesto" }, { clave: "personas", titulo: "Personas", valor: g => String(g.personas) }, { clave: "requisitos", titulo: "Elementos", valor: g => g.requisitos.length ? `${g.requisitos.length} · ${g.requisitos.slice(0, 3).map(r => r.elemento).join(", ")}${g.requisitos.length > 3 ? "…" : ""}` : "Sin asignar" }]} /></section><section className="tarjeta"><h2>Cambios recientes</h2>{matriz.historial.length ? <Tabla etiqueta="Cambios de la matriz" filas={matriz.historial as Record<string, unknown>[]} columnas={[{ clave: "momento", titulo: "Fecha", valor: h => new Date(String(h.momento)).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) }, { clave: "puesto", titulo: "Puesto", valor: h => puestos.find(p => p.codigo === h.puesto)?.nombre ?? String(h.puesto) }, { clave: "autor", titulo: "Quién" }, { clave: "elementos", titulo: "Elementos del puesto", valor: h => (h.elementos as string[]).map(c => catalogo.find(e => e.codigo === c)?.producto ?? c).join(", ") }]} /> : <Vacio>Todavía nadie cambió la matriz.</Vacio>}</section></div>}
    {itemAbierto && <Ventana tamano="ancha" titulo={nombreItem(itemAbierto.item_codigo)} cerrar={() => setItemAbierto(null)}>
      <dl className="ficha"><div><dt>Código</dt><dd>{itemAbierto.item_codigo}</dd></div><div><dt>Disponible</dt><dd>{String(itemAbierto.disponible)}</dd></div><div><dt>Mínimo</dt><dd>{String(itemAbierto.minimo)}</dd></div><div><dt>Situación</dt><dd>{Number(itemAbierto.disponible) < Number(itemAbierto.minimo) ? "Bajo el mínimo" : "Normal"}</dd></div></dl>
      <h3>Registrar movimiento</h3>
      {errorVentanaEpp && <ErrorVisible mensaje={errorVentanaEpp} />}
      <form className="form-grid" onSubmit={mover}><label>Tipo<select name="tipo"><option value="INGRESO">Ingreso</option><option value="EGRESO">Egreso</option><option value="AJUSTE">Ajuste de inventario</option></select></label><label>Cantidad (negativa para restar en un ajuste)<input name="cantidad" type="number" required /></label><label>Motivo<input name="motivo" required placeholder="Ej.: remito 0001-00012345" /></label><div className="acciones"><button className="primario">Registrar</button></div></form>
      <h3>Últimos movimientos</h3>
      {movimientos.length ? <div className="tabla-scroll"><table><thead><tr><th>Fecha</th><th>Tipo</th><th>Cantidad</th><th>Motivo</th><th>Quién</th></tr></thead><tbody>{movimientos.slice(0, 20).map(m => <tr key={m.id}><td>{new Date(m.creado_en).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" })}</td><td>{m.tipo}</td><td>{m.cantidad}</td><td>{m.motivo}</td><td>{m.actor}</td></tr>)}</tbody></table></div> : <Vacio>Sin movimientos registrados.</Vacio>}
    </Ventana>}
    {grupoAbierto && <Ventana tamano="amplia" titulo={`${grupoAbierto.puesto} · ${grupoAbierto.sector}`} cerrar={() => setGrupoAbierto(null)}>
      <p className="ayuda">{grupoAbierto.personas} {grupoAbierto.personas === 1 ? "persona" : "personas"} en este puesto.</p>
      {grupoAbierto.requisitos.length ? <div className="tabla-scroll"><table><thead><tr><th>Elemento</th><th>Cantidad</th><th>Frecuencia</th><th>Temporada</th><th>Por qué</th></tr></thead><tbody>{grupoAbierto.requisitos.map(r => <tr key={r.codigo}><td>{r.elemento}</td><td>{r.cantidad}</td><td>{FRECUENCIAS[r.frecuencia] ?? r.frecuencia}</td><td>{TEMPORADAS[r.temporada] ?? r.temporada}</td><td>{ORIGENES[r.origen] ?? r.origen}{r.fundamento ? ` · ${r.fundamento}` : ""}</td></tr>)}</tbody></table></div> : <Vacio>Este puesto todavía no tiene elementos asignados.</Vacio>}
      <div className="acciones"><button type="button" onClick={() => setGrupoAbierto(null)}>Cerrar</button><button className="primario" onClick={() => abrirGrilla(grupoAbierto.puesto_codigo)}>Agregar elementos</button></div>
    </Ventana>}
    {grilla && <Ventana tamano="amplia" titulo="Nueva asignación" cerrar={() => setGrilla(null)}>
      <p className="ayuda">Elegí el puesto y cargá todos los elementos juntos, uno por fila. Si el elemento ya estaba asignado, se reemplaza con estos datos.</p>
      {errorGrilla && <ErrorVisible mensaje={errorGrilla} />}
      <label>Puesto<select value={grilla.puesto} onChange={e => setGrilla({ ...grilla, puesto: e.target.value })}><option value="">Elegí un puesto</option>{puestos.map(p => <option key={p.codigo} value={p.codigo}>{p.nombre}</option>)}</select></label>
      <datalist id="elementos-grilla">{catalogo.filter(item => item.activo).map(e => <option key={e.codigo} value={etiquetaElemento(e)} />)}</datalist>
      <div className="tabla-scroll"><table className="grilla-carga"><thead><tr><th>Elemento</th><th>Cantidad</th><th>Frecuencia</th><th>Temporada</th><th>Obligatorio</th><th>Motivo</th><th></th></tr></thead><tbody>{grilla.filas.map((f, i) => <tr key={i}>
        <td><input list="elementos-grilla" value={f.elemento} onChange={e => cambiarFila(i, { elemento: e.target.value })} placeholder="Buscá el elemento" aria-label={`Elemento fila ${i + 1}`} /></td>
        <td><input type="number" min="1" value={f.cantidad} onChange={e => cambiarFila(i, { cantidad: Number(e.target.value) })} aria-label={`Cantidad fila ${i + 1}`} /></td>
        <td><select value={f.frecuencia} onChange={e => cambiarFila(i, { frecuencia: e.target.value })} aria-label={`Frecuencia fila ${i + 1}`}>{Object.entries(FRECUENCIAS).map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></td>
        <td><select value={f.temporada} onChange={e => cambiarFila(i, { temporada: e.target.value })} aria-label={`Temporada fila ${i + 1}`}>{Object.entries(TEMPORADAS).map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></td>
        <td><input type="checkbox" checked={f.obligatorio} onChange={e => cambiarFila(i, { obligatorio: e.target.checked })} aria-label={`Obligatorio fila ${i + 1}`} /></td>
        <td><input value={f.fundamento} onChange={e => cambiarFila(i, { fundamento: e.target.value })} placeholder="Ej.: riesgo mecánico" aria-label={`Motivo fila ${i + 1}`} /></td>
        <td><button type="button" aria-label={`Quitar fila ${i + 1}`} onClick={() => setGrilla({ ...grilla, filas: grilla.filas.filter((_, j) => j !== i) })}>✕</button></td>
      </tr>)}</tbody></table></div>
      <div className="acciones"><button type="button" onClick={() => setGrilla({ ...grilla, filas: [...grilla.filas, filaNueva()] })}>Agregar fila</button><button type="button" onClick={() => setGrilla(null)}>Cancelar</button><button className="primario" disabled={guardandoGrilla} onClick={guardarGrilla}>{guardandoGrilla ? "Guardando…" : "Guardar asignación"}</button></div>
    </Ventana>}
    {vista === "stock" && <div className="rejilla"><section className="tarjeta"><h2>Existencias y mínimos</h2><p className="ayuda">Tocá un ítem para ver sus movimientos o registrar un ingreso, egreso o ajuste.</p><Tabla etiqueta="Stock" filas={stock.map(s => ({ ...s, elemento: nombreItem(s.item_codigo) }))} alElegir={abrirItem} columnas={[{ clave: "elemento", titulo: "Elemento" }, { clave: "item_codigo", titulo: "Código" }, { clave: "disponible", titulo: "Disponible" }, { clave: "minimo", titulo: "Mínimo" }, { clave: "estado", titulo: "Situación", valor: f => Number(f.disponible) < Number(f.minimo) ? "Bajo el mínimo" : "Normal" }]} /></section><section className="tarjeta"><h2>Outbox de avisos a Compras</h2>{avisos.length ? <Tabla etiqueta="Avisos" filas={avisos} columnas={[{ clave: "identificador", titulo: "Identificador" }, { clave: "estado", titulo: "Estado" }, { clave: "intentos", titulo: "Intentos" }, { clave: "proximo_reintento", titulo: "Próximo reintento", valor: f => f.proximo_reintento ?? "Pendiente" }, { clave: "accion", titulo: "Acción", valor: f => <button onClick={() => reenviar(Number(f.id))}>Reenviar</button> }]} /> : <Vacio>{avisosVedados ? "Este perfil no puede ver el outbox de Compras. No significa que esté vacío." : "No hay avisos en el outbox."}</Vacio>}</section></div>}
    {vista === "planillas" && <section className="tarjeta planilla-epp"><div className="titulo-fila"><div><h2>Planilla de entrega por sector</h2><p className="ayuda">Elegí la temporada y la fecha. La lista trae cada trabajador con los elementos definidos para su puesto.</p></div>{planes.length > 0 && <button type="button" onClick={() => window.print()}>Imprimir planilla</button>}</div><form className="filtros-planilla" onSubmit={armarPlanilla}><label>Temporada<select value={temporadaPlanilla} onChange={e => setTemporadaPlanilla(e.target.value as "VERANO" | "INVIERNO")}><option value="VERANO">Verano</option><option value="INVIERNO">Invierno</option></select></label><label>Fecha de entrega<input type="date" value={fechaPlanilla} onChange={e => setFechaPlanilla(e.target.value)} required /></label><label>Sector<select value={sectorPlanilla} onChange={e => setSectorPlanilla(e.target.value)}><option value="">Todos los sectores</option>{sectores.map(sector => <option key={sector.codigo} value={sector.codigo}>{sector.nombre}</option>)}</select></label><button className="primario">Armar planilla</button></form>{planillaConsultada && planes.length === 0 && <Vacio>No hay trabajadores con entregas programadas para esos filtros.</Vacio>}{planesPorSector.map(([sector, filas]) => <section className="sector-planilla" key={sector}><header><div><h3>{sector}</h3><p>{fechaPlanilla.split("-").reverse().join("/")} · {temporadaPlanilla === "VERANO" ? "Verano" : "Invierno"}</p></div><strong>{filas.length} trabajador{filas.length === 1 ? "" : "es"}</strong></header><div className="tabla-planilla"><table><thead><tr><th>Legajo</th><th>Trabajador</th><th>Puesto</th><th>Elementos a entregar</th><th>Firma</th></tr></thead><tbody>{filas.map(plan => <tr key={plan.legajo}><td>{plan.legajo}</td><td>{plan.nombre_completo}</td><td>{plan.puesto}</td><td><ul>{plan.elementos.map(elemento => <li key={elemento.codigo}>{elemento.cantidad} × {nombreElementoPlan(elemento.codigo)}</li>)}</ul></td><td className="firma-planilla" aria-label={`Firma de ${plan.nombre_completo}`} /></tr>)}</tbody></table></div></section>)}</section>}
    {vista === "entregas" && <section className="tarjeta"><h2>Entregas y constancias versionadas</h2>{entregas.length ? <Tabla etiqueta="Entregas" filas={entregas} columnas={[{ clave: "fecha", titulo: "Fecha" }, { clave: "persona", titulo: "Persona" }, { clave: "sector", titulo: "Sector" }, { clave: "motivo", titulo: "Motivo / reclamo" }, { clave: "constancia", titulo: "Constancia", valor: f => <button type="button" onClick={() => void verConstancia(String(f.id))}>Ver constancia</button> }]} /> : <Vacio>No hay entregas en el período actual.</Vacio>}</section>}
  </>;
}

function hoyLocal() {
  const ahora = new Date();
  return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}-${String(ahora.getDate()).padStart(2, "0")}`;
}
