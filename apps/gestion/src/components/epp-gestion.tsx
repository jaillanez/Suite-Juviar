"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { abrirArchivo, api } from "@/lib/api";
import { ErrorVisible, Tabla, Vacio } from "./compartidos";

type Catalogo = Record<string, unknown> & { codigo: string; producto: string; tipo_modelo: string; marca: string; posee_certificacion: boolean; certificacion: string | null; unidad: string; vida_util_dias: number | null; familia: string; destino_declarado: string | null; criterio_vida_util: string; activo: boolean; simulado: boolean; items: Array<{ codigo_interno: string; marca: string; modelo: string; talle: string; activo: boolean }> };
type Stock = Record<string, unknown> & { item_codigo: string; disponible: number; minimo: number; estado: string };
type Aviso = Record<string, unknown> & { id: number; identificador: string; estado: string; intentos: number; proximo_reintento?: string };
type Entrega = Record<string, unknown> & { id: string; persona: string; legajo: string; sector: string; fecha: string; motivo: string };
type PlanProgramado = { fecha: string; temporada: string; legajo: string; nombre_completo: string; puesto: string; sector: string; sector_codigo: string; elementos: Array<{ codigo: string; cantidad: number; origen: string }> };
type Matriz = { estado: string; validacion?: { firmada_por: string; firmada_en: string }; historial: Array<Record<string, unknown>> };
type Puesto = { codigo: string; nombre: string };
type Requisito = { codigo: string; cantidad: number; frecuencia: string; temporada: string; obligatorio: boolean; fundamento: string };
type Vista = "catalogo" | "matriz" | "stock" | "planillas" | "entregas";

const etiquetaPuesto = (puesto: Puesto) => `${puesto.nombre} · ${puesto.codigo}`;
const etiquetaElemento = (elemento: Catalogo) => `${elemento.producto} · ${elemento.familia} · ${elemento.codigo}`;

export function EppGestion() {
  const cargaInicial = useRef(false);
  const [vista, setVista] = useState<Vista>("catalogo");
  const [catalogo, setCatalogo] = useState<Catalogo[]>([]); const [stock, setStock] = useState<Stock[]>([]);
  const [puestos, setPuestos] = useState<Puesto[]>([]);
  const [codigoElemento, setCodigoElemento] = useState(""); const [nombreElemento, setNombreElemento] = useState(""); const [familiaElemento, setFamiliaElemento] = useState("");
  const [avisos, setAvisos] = useState<Aviso[]>([]); const [avisosVedados, setAvisosVedados] = useState(false); const [entregas, setEntregas] = useState<Entrega[]>([]);
  const [fechaPlanilla, setFechaPlanilla] = useState(hoyLocal()); const [temporadaPlanilla, setTemporadaPlanilla] = useState<"VERANO" | "INVIERNO">("VERANO"); const [sectorPlanilla, setSectorPlanilla] = useState(""); const [planes, setPlanes] = useState<PlanProgramado[]>([]); const [planillaConsultada, setPlanillaConsultada] = useState(false);
  const [matriz, setMatriz] = useState<Matriz>({ estado: "SIN_VALIDAR", historial: [] });
  const [error, setError] = useState(""); const [mensaje, setMensaje] = useState(""); const [previa, setPrevia] = useState<Record<string, unknown> | null>(null);
  const [confirmarReemplazo, setConfirmarReemplazo] = useState(false); const [limpieza, setLimpieza] = useState<Record<string, number> | null>(null); const [fraseLimpieza, setFraseLimpieza] = useState("");
  const hoy = new Date().toISOString().slice(0, 10); const inicio = `${new Date().getFullYear()}-01-01`;
  const informar = (e: unknown) => setError(e instanceof Error ? e.message : "No fue posible completar la operación.");
  const nombreElementoPlan = (codigo: string) => catalogo.find(item => item.codigo === codigo)?.producto ?? `Elemento ${codigo}`;
  async function recargar() {
    setError("");
    try {
      const [c, s, m, p] = await Promise.all([api<Catalogo[]>("rrhh-epp/catalogo"), api<Stock[]>("rrhh-epp/stock"), api<Matriz>("rrhh-epp/matriz/estado"), api<Puesto[]>("rrhh-epp/matriz/puestos")]);
      setCatalogo(c); setStock(s); setMatriz(m); setPuestos(p);
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
    e.preventDefault();
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
      setCodigoElemento(""); setNombreElemento(""); setFamiliaElemento("");
      recargar();
    } catch (x) { informar(x); }
  }
  async function importar(archivo?: File) { if (!archivo) return; const contenido_base64 = await new Promise<string>((ok, mal) => { const l = new FileReader(); l.onerror = mal; l.onload = () => ok(String(l.result).split(",")[1]); l.readAsDataURL(archivo); }); try { setConfirmarReemplazo(false); setPrevia(await api("rrhh-epp/catalogo/importaciones", { method: "POST", body: JSON.stringify({ contenido_base64 }) })); } catch (x) { informar(x); } }
  async function aplicar() { if (!previa?.identificador) return; try { await api(`rrhh-epp/catalogo/importaciones/${previa.identificador}/aplicar`, { method: "POST" }); setMensaje("Reemplazo aplicado; los ítems ausentes quedaron inactivos."); setPrevia(null); recargar(); } catch (x) { informar(x); } }
  async function guardarMatriz(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formulario = e.currentTarget;
    const f = Object.fromEntries(new FormData(formulario));
    const puesto = puestos.find(p => etiquetaPuesto(p) === f.puesto || p.codigo === f.puesto);
    const elemento = catalogo.find(item => etiquetaElemento(item) === f.elemento || item.codigo === f.elemento);
    if (!puesto) { setError("Elegí un puesto de la lista."); return; }
    if (!elemento) { setError("Elegí un elemento del catálogo."); return; }
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
      recargar();
    } catch (x) { informar(x); }
  }
  async function mover(e: FormEvent<HTMLFormElement>) { e.preventDefault(); const f = Object.fromEntries(new FormData(e.currentTarget)); try { await api(`rrhh-epp/stock/${f.item}/movimientos`, { method: "POST", body: JSON.stringify({ cantidad: Number(f.cantidad), tipo: f.tipo, motivo: f.motivo }) }); setMensaje("Movimiento registrado."); recargar(); } catch (x) { informar(x); } }
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
    {vista === "catalogo" && <div className="rejilla"><section className="tarjeta"><div className="titulo-fila"><h2>Catálogo RD 062/11</h2></div><Tabla etiqueta="Catálogo EPP" filas={catalogo} columnas={[{ clave: "codigo", titulo: "Código" }, { clave: "producto", titulo: "Elemento" }, { clave: "familia", titulo: "Familia" }, { clave: "activo", titulo: "Estado", valor: f => f.activo ? "Activo" : "Baja lógica" }]} /></section><section className="tarjeta"><h2>Agregar o editar elemento</h2><p className="ayuda">Escribí un código existente para cargar sus datos, o uno nuevo para agregarlo.</p><form className="form-grid" onSubmit={guardarElemento}><label>Código o elemento<input name="codigo" list="catalogo-codigos" value={codigoElemento} onChange={e => cambiarCodigoElemento(e.target.value)} placeholder="Buscá por código o nombre" autoComplete="off" required /></label><datalist id="catalogo-codigos">{catalogo.map(item => <option key={item.codigo} value={item.codigo}>{item.producto} · {item.familia}</option>)}</datalist>{codigoElemento && <p className="ayuda">{catalogo.some(item => item.codigo.toLocaleLowerCase("es") === codigoElemento.trim().toLocaleLowerCase("es")) ? "Elemento encontrado: podés editar sus datos." : "Código nuevo: completá sus datos."}</p>}<label>Elemento<input name="producto" value={nombreElemento} onChange={e => setNombreElemento(e.target.value)} required /></label><label>Familia<input name="familia" value={familiaElemento} onChange={e => setFamiliaElemento(e.target.value)} required /></label><button className="primario">{catalogo.some(item => item.codigo.toLocaleLowerCase("es") === codigoElemento.trim().toLocaleLowerCase("es")) ? "Guardar cambios" : "Agregar elemento"}</button></form></section><section className="tarjeta"><h2>Reemplazar desde Excel de HyS</h2><input aria-label="Excel de HyS" type="file" accept=".xlsx" onChange={e => importar(e.target.files?.[0])} />{previa && <div className="previsualizacion"><p className="preliminar"><strong>{Number(previa.entregas_afectadas)} entregas quedarían vinculadas a ítems dados de baja.</strong> Se conservan sus constancias y referencias históricas.</p><pre>{JSON.stringify(previa, null, 2)}</pre><label><input type="checkbox" checked={confirmarReemplazo} onChange={e => setConfirmarReemplazo(e.target.checked)} /> Confirmo que revisé altas, cambios, desapariciones y entregas afectadas</label><button className="primario" disabled={!confirmarReemplazo} onClick={aplicar}>Aplicar reemplazo</button></div>}</section>{limpieza && <section className="tarjeta"><h2>Restablecer demostración</h2><p>Se eliminarán {limpieza.entregas} entregas y {limpieza.constancias} constancias cargadas durante las pruebas.</p><label>Escribí REINICIAR DEMOSTRACIÓN<input value={fraseLimpieza} onChange={e => setFraseLimpieza(e.target.value)} /></label><button className="peligro" disabled={fraseLimpieza !== "REINICIAR DEMOSTRACIÓN"} onClick={limpiarPruebas}>Restablecer demostración</button></section>}</div>}
    {vista === "matriz" && <div className="rejilla"><section className="tarjeta"><h2>Asignar protección a un puesto</h2><p className="ayuda">Buscá por nombre. Los códigos se muestran sólo como referencia.</p><form className="form-grid" onSubmit={guardarMatriz}><label>Buscar puesto<input name="puesto" list="puestos-epp" placeholder="Ej.: Operario de Bodega" autoComplete="off" required /></label><datalist id="puestos-epp">{puestos.map(puesto => <option key={puesto.codigo} value={etiquetaPuesto(puesto)} />)}</datalist><label>Buscar elemento<input name="elemento" list="elementos-epp" placeholder="Ej.: Calzado de seguridad" autoComplete="off" required /></label><datalist id="elementos-epp">{catalogo.filter(item => item.activo).map(elemento => <option key={elemento.codigo} value={etiquetaElemento(elemento)} />)}</datalist><label>Cantidad<input name="cantidad" type="number" min="1" defaultValue="1" required /></label><label>Motivo de la asignación<input name="fundamento" placeholder="Ej.: riesgo mecánico en el puesto" required /></label><button className="primario">Asignar al puesto</button></form></section><section className="tarjeta"><h2>Cambios recientes</h2>{matriz.historial.length ? <pre>{JSON.stringify(matriz.historial, null, 2)}</pre> : <Vacio>Sin cambios registrados.</Vacio>}</section></div>}
    {vista === "stock" && <div className="rejilla"><section className="tarjeta"><h2>Existencias y mínimos</h2><Tabla etiqueta="Stock" filas={stock} columnas={[{ clave: "item_codigo", titulo: "Ítem" }, { clave: "disponible", titulo: "Disponible" }, { clave: "minimo", titulo: "Mínimo" }, { clave: "estado", titulo: "Estado" }]} /></section><section className="tarjeta"><h2>Registrar movimiento</h2><form className="form-grid" onSubmit={mover}><label>Ítem<input name="item" required /></label><label>Cantidad con signo<input name="cantidad" type="number" required /></label><label>Tipo<select name="tipo"><option>AJUSTE</option><option>INGRESO</option><option>EGRESO</option></select></label><label>Motivo<input name="motivo" required /></label><button className="primario">Registrar</button></form></section><section className="tarjeta"><h2>Outbox de avisos a Compras</h2>{avisos.length ? <Tabla etiqueta="Avisos" filas={avisos} columnas={[{ clave: "identificador", titulo: "Identificador" }, { clave: "estado", titulo: "Estado" }, { clave: "intentos", titulo: "Intentos" }, { clave: "proximo_reintento", titulo: "Próximo reintento", valor: f => f.proximo_reintento ?? "Pendiente" }, { clave: "accion", titulo: "Acción", valor: f => <button onClick={() => reenviar(Number(f.id))}>Reenviar</button> }]} /> : <Vacio>{avisosVedados ? "Este perfil no puede ver el outbox de Compras. No significa que esté vacío." : "No hay avisos en el outbox."}</Vacio>}</section></div>}
    {vista === "planillas" && <section className="tarjeta planilla-epp"><div className="titulo-fila"><div><h2>Planilla de entrega por sector</h2><p className="ayuda">Elegí la temporada y la fecha. La lista trae cada trabajador con los elementos definidos para su puesto.</p></div>{planes.length > 0 && <button type="button" onClick={() => window.print()}>Imprimir planilla</button>}</div><form className="filtros-planilla" onSubmit={armarPlanilla}><label>Temporada<select value={temporadaPlanilla} onChange={e => setTemporadaPlanilla(e.target.value as "VERANO" | "INVIERNO")}><option value="VERANO">Verano</option><option value="INVIERNO">Invierno</option></select></label><label>Fecha de entrega<input type="date" value={fechaPlanilla} onChange={e => setFechaPlanilla(e.target.value)} required /></label><label>Sector (opcional)<input value={sectorPlanilla} onChange={e => setSectorPlanilla(e.target.value)} placeholder="Todos los sectores" /></label><button className="primario">Armar planilla</button></form>{planillaConsultada && planes.length === 0 && <Vacio>No hay trabajadores con entregas programadas para esos filtros.</Vacio>}{planesPorSector.map(([sector, filas]) => <section className="sector-planilla" key={sector}><header><div><h3>{sector}</h3><p>{fechaPlanilla.split("-").reverse().join("/")} · {temporadaPlanilla === "VERANO" ? "Verano" : "Invierno"}</p></div><strong>{filas.length} trabajador{filas.length === 1 ? "" : "es"}</strong></header><div className="tabla-planilla"><table><thead><tr><th>Legajo</th><th>Trabajador</th><th>Puesto</th><th>Elementos a entregar</th><th>Firma</th></tr></thead><tbody>{filas.map(plan => <tr key={plan.legajo}><td>{plan.legajo}</td><td>{plan.nombre_completo}</td><td>{plan.puesto}</td><td><ul>{plan.elementos.map(elemento => <li key={elemento.codigo}>{elemento.cantidad} × {nombreElementoPlan(elemento.codigo)}</li>)}</ul></td><td className="firma-planilla" aria-label={`Firma de ${plan.nombre_completo}`} /></tr>)}</tbody></table></div></section>)}</section>}
    {vista === "entregas" && <section className="tarjeta"><h2>Entregas y constancias versionadas</h2>{entregas.length ? <Tabla etiqueta="Entregas" filas={entregas} columnas={[{ clave: "fecha", titulo: "Fecha" }, { clave: "persona", titulo: "Persona" }, { clave: "sector", titulo: "Sector" }, { clave: "motivo", titulo: "Motivo / reclamo" }, { clave: "constancia", titulo: "Constancia", valor: f => <button type="button" onClick={() => void verConstancia(String(f.id))}>Ver constancia</button> }]} /> : <Vacio>No hay entregas en el período actual.</Vacio>}</section>}
  </>;
}

function hoyLocal() {
  const ahora = new Date();
  return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}-${String(ahora.getDate()).padStart(2, "0")}`;
}
