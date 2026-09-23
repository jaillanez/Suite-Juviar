"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Tabla, Vacio } from "./compartidos";

type Catalogo = Record<string, unknown> & { codigo: string; producto: string; familia: string; activo: boolean; simulado: boolean; items: Array<{ codigo_interno: string; marca: string; modelo: string; talle: string; activo: boolean }> };
type Stock = Record<string, unknown> & { item_codigo: string; disponible: number; minimo: number; estado: string };
type Aviso = Record<string, unknown> & { id: number; identificador: string; estado: string; intentos: number; proximo_reintento?: string };
type Entrega = Record<string, unknown> & { id: string; persona: string; legajo: string; sector: string; fecha: string; motivo: string };
type Matriz = { estado: string; validacion?: { firmada_por: string; firmada_en: string }; historial: Array<Record<string, unknown>> };
type Puesto = { codigo: string; nombre: string };
type Requisito = { codigo: string; cantidad: number; frecuencia: string; temporada: string; obligatorio: boolean; fundamento: string };
type Vista = "catalogo" | "matriz" | "stock" | "entregas";

const etiquetaPuesto = (puesto: Puesto) => `${puesto.nombre} · ${puesto.codigo}`;
const etiquetaElemento = (elemento: Catalogo) => `${elemento.producto} · ${elemento.familia} · ${elemento.codigo}`;

export function EppGestion() {
  const [vista, setVista] = useState<Vista>("catalogo");
  const [catalogo, setCatalogo] = useState<Catalogo[]>([]); const [stock, setStock] = useState<Stock[]>([]);
  const [puestos, setPuestos] = useState<Puesto[]>([]);
  const [avisos, setAvisos] = useState<Aviso[]>([]); const [avisosVedados, setAvisosVedados] = useState(false); const [entregas, setEntregas] = useState<Entrega[]>([]);
  const [matriz, setMatriz] = useState<Matriz>({ estado: "SIN_VALIDAR", historial: [] });
  const [error, setError] = useState(""); const [mensaje, setMensaje] = useState(""); const [previa, setPrevia] = useState<Record<string, unknown> | null>(null);
  const [confirmarReemplazo, setConfirmarReemplazo] = useState(false); const [limpieza, setLimpieza] = useState<Record<string, number> | null>(null); const [fraseLimpieza, setFraseLimpieza] = useState("");
  const hoy = new Date().toISOString().slice(0, 10); const inicio = `${new Date().getFullYear()}-01-01`;
  const informar = (e: unknown) => setError(e instanceof Error ? e.message : "No fue posible completar la operación.");
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
  useEffect(() => { recargar(); }, []);
  async function guardarElemento(e: FormEvent<HTMLFormElement>) { e.preventDefault(); const formulario = e.currentTarget; const f = Object.fromEntries(new FormData(formulario)); try { await api(`rrhh-epp/catalogo/elementos/${f.codigo}`, { method: "POST", body: JSON.stringify({ producto: f.producto, familia: f.familia }) }); setMensaje("Elemento guardado."); formulario.reset(); recargar(); } catch (x) { informar(x); } }
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
  return <><div className="metricas"><article><span>Elementos</span><strong>{catalogo.length || "—"}</strong><small>Catálogo disponible</small></article><article><span>Bajo mínimo</span><strong>{stock.filter(x => x.disponible < x.minimo).length || "0"}</strong><small>Generan avisos, no pedidos</small></article><article><span>Matriz</span><strong>{matriz.validacion ? "Firmada" : "Pendiente"}</strong><small>{matriz.validacion ? `${matriz.validacion.firmada_por} · ${new Date(matriz.validacion.firmada_en).toLocaleString("es-AR")}` : "Revisión de Higiene y Seguridad"}</small></article></div>
    {error && <ErrorVisible mensaje={error} />}{mensaje && <div className="aviso-exito" role="status">{mensaje}</div>}
    <nav className="pestanas" aria-label="Áreas de EPP">{(["catalogo", "matriz", "stock", "entregas"] as Vista[]).map(v => <button key={v} className={vista === v ? "activo" : ""} onClick={() => setVista(v)}>{v[0].toUpperCase() + v.slice(1)}</button>)}</nav>
    {vista === "catalogo" && <div className="rejilla"><section className="tarjeta"><div className="titulo-fila"><h2>Catálogo RD 062/11</h2></div><Tabla etiqueta="Catálogo EPP" filas={catalogo} columnas={[{ clave: "codigo", titulo: "Código" }, { clave: "producto", titulo: "Elemento" }, { clave: "familia", titulo: "Familia" }, { clave: "activo", titulo: "Estado", valor: f => f.activo ? "Activo" : "Baja lógica" }]} /></section><section className="tarjeta"><h2>Alta de elemento</h2><form className="form-grid" onSubmit={guardarElemento}><label>Código<input name="codigo" required /></label><label>Elemento<input name="producto" required /></label><label>Familia<input name="familia" required /></label><button className="primario">Guardar</button></form></section><section className="tarjeta"><h2>Reemplazar desde Excel de HyS</h2><input aria-label="Excel de HyS" type="file" accept=".xlsx" onChange={e => importar(e.target.files?.[0])} />{previa && <div className="previsualizacion"><p className="preliminar"><strong>{Number(previa.entregas_afectadas)} entregas quedarían vinculadas a ítems dados de baja.</strong> Se conservan sus constancias y referencias históricas.</p><pre>{JSON.stringify(previa, null, 2)}</pre><label><input type="checkbox" checked={confirmarReemplazo} onChange={e => setConfirmarReemplazo(e.target.checked)} /> Confirmo que revisé altas, cambios, desapariciones y entregas afectadas</label><button className="primario" disabled={!confirmarReemplazo} onClick={aplicar}>Aplicar reemplazo</button></div>}</section>{limpieza && <section className="tarjeta"><h2>Restablecer demostración</h2><p>Se eliminarán {limpieza.entregas} entregas y {limpieza.constancias} constancias cargadas durante las pruebas.</p><label>Escribí REINICIAR DEMOSTRACIÓN<input value={fraseLimpieza} onChange={e => setFraseLimpieza(e.target.value)} /></label><button className="peligro" disabled={fraseLimpieza !== "REINICIAR DEMOSTRACIÓN"} onClick={limpiarPruebas}>Restablecer demostración</button></section>}</div>}
    {vista === "matriz" && <div className="rejilla"><section className="tarjeta"><h2>Asignar protección a un puesto</h2><p className="ayuda">Buscá por nombre. Los códigos se muestran sólo como referencia.</p><form className="form-grid" onSubmit={guardarMatriz}><label>Buscar puesto<input name="puesto" list="puestos-epp" placeholder="Ej.: Operario de Bodega" autoComplete="off" required /></label><datalist id="puestos-epp">{puestos.map(puesto => <option key={puesto.codigo} value={etiquetaPuesto(puesto)} />)}</datalist><label>Buscar elemento<input name="elemento" list="elementos-epp" placeholder="Ej.: Calzado de seguridad" autoComplete="off" required /></label><datalist id="elementos-epp">{catalogo.filter(item => item.activo).map(elemento => <option key={elemento.codigo} value={etiquetaElemento(elemento)} />)}</datalist><label>Cantidad<input name="cantidad" type="number" min="1" defaultValue="1" required /></label><label>Motivo de la asignación<input name="fundamento" placeholder="Ej.: riesgo mecánico en el puesto" required /></label><button className="primario">Asignar al puesto</button></form></section><section className="tarjeta"><h2>Cambios recientes</h2>{matriz.historial.length ? <pre>{JSON.stringify(matriz.historial, null, 2)}</pre> : <Vacio>Sin cambios registrados.</Vacio>}</section></div>}
    {vista === "stock" && <div className="rejilla"><section className="tarjeta"><h2>Existencias y mínimos</h2><Tabla etiqueta="Stock" filas={stock} columnas={[{ clave: "item_codigo", titulo: "Ítem" }, { clave: "disponible", titulo: "Disponible" }, { clave: "minimo", titulo: "Mínimo" }, { clave: "estado", titulo: "Estado" }]} /></section><section className="tarjeta"><h2>Registrar movimiento</h2><form className="form-grid" onSubmit={mover}><label>Ítem<input name="item" required /></label><label>Cantidad con signo<input name="cantidad" type="number" required /></label><label>Tipo<select name="tipo"><option>AJUSTE</option><option>INGRESO</option><option>EGRESO</option></select></label><label>Motivo<input name="motivo" required /></label><button className="primario">Registrar</button></form></section><section className="tarjeta"><h2>Outbox de avisos a Compras</h2>{avisos.length ? <Tabla etiqueta="Avisos" filas={avisos} columnas={[{ clave: "identificador", titulo: "Identificador" }, { clave: "estado", titulo: "Estado" }, { clave: "intentos", titulo: "Intentos" }, { clave: "proximo_reintento", titulo: "Próximo reintento", valor: f => f.proximo_reintento ?? "Pendiente" }, { clave: "accion", titulo: "Acción", valor: f => <button onClick={() => reenviar(Number(f.id))}>Reenviar</button> }]} /> : <Vacio>{avisosVedados ? "Este perfil no puede ver el outbox de Compras. No significa que esté vacío." : "No hay avisos en el outbox."}</Vacio>}</section></div>}
    {vista === "entregas" && <section className="tarjeta"><h2>Entregas y constancias versionadas</h2>{entregas.length ? <Tabla etiqueta="Entregas" filas={entregas} columnas={[{ clave: "fecha", titulo: "Fecha" }, { clave: "persona", titulo: "Persona" }, { clave: "sector", titulo: "Sector" }, { clave: "motivo", titulo: "Motivo / reclamo" }, { clave: "constancia", titulo: "Constancia", valor: f => <a href={`${process.env.NEXT_PUBLIC_API_URL ?? "/backend"}/rrhh-epp/constancias/${f.id}.pdf`} target="_blank">Ver constancia</a> }]} /> : <Vacio>No hay entregas en el período actual.</Vacio>}</section>}
  </>;
}
