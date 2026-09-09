"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Tabla, Vacio } from "./compartidos";

type Metrica = Record<string, unknown> & { item_codigo: string; sector: string; puesto: string; consumo: number; reclamos_total: number; reclamos_proporcion: number; muestra_entregas: number; muestra_duracion: number; duracion_promedio_dias: number | null; estado_duracion: string };
type Tablero = { metricas: Metrica[]; fecha_corte: string; desde: string; hasta: string; costo: null; costo_leyenda: string; exportacion: { habilitada: boolean; motivo?: string }; datos_simulados: boolean };

export function AnaliticaGestion() {
  const hoy = new Date().toISOString().slice(0, 10); const [desde, setDesde] = useState(`${new Date().getFullYear()}-01-01`); const [hasta, setHasta] = useState(hoy);
  const [sector, setSector] = useState(""); const [puesto, setPuesto] = useState(""); const [datos, setDatos] = useState<Tablero | null>(null); const [comparacion, setComparacion] = useState<Record<string, unknown> | null>(null); const [error, setError] = useState("");
  async function cargar() { try { setDatos(await api(`epp-analitica/tablero?desde=${desde}&hasta=${hasta}${sector ? `&sector=${encodeURIComponent(sector)}` : ""}${puesto ? `&puesto=${encodeURIComponent(puesto)}` : ""}`)); } catch (x) { setError(x instanceof Error ? x.message : "No se pudo cargar el tablero."); } }
  useEffect(() => { cargar(); }, []);
  async function filtrar(e: FormEvent) { e.preventDefault(); await cargar(); }
  async function comparar(e: FormEvent<HTMLFormElement>) { e.preventDefault(); const f = new FormData(e.currentTarget); try { setComparacion(await api(`epp-analitica/comparador?item_a=${f.get("item_a")}&item_b=${f.get("item_b")}&desde=${desde}&hasta=${hasta}`)); } catch (x) { setError(x instanceof Error ? x.message : "Comparación inválida."); } }
  return <>{error && <ErrorVisible mensaje={error} />}<section className="tarjeta"><form className="form-linea" onSubmit={filtrar}><label>Desde<input type="date" value={desde} onChange={e => setDesde(e.target.value)} /></label><label>Hasta<input type="date" value={hasta} onChange={e => setHasta(e.target.value)} /></label><label>Sector<input value={sector} onChange={e => setSector(e.target.value)} /></label><label>Puesto<input value={puesto} onChange={e => setPuesto(e.target.value)} /></label><button className="primario">Aplicar filtros</button></form></section>
    {datos && <><div className="metricas"><article><span>Costo</span><strong>—</strong><small>{datos.costo_leyenda}</small></article><article><span>Exportación</span><strong>{datos.exportacion.habilitada ? "Habilitada" : "Bloqueada"}</strong><small>{datos.exportacion.motivo ?? "Datos reales verificados"}</small></article><article><span>Fecha de corte</span><strong>{datos.fecha_corte}</strong><small>{datos.desde} a {datos.hasta}</small></article></div><section className="tarjeta"><h2>Consumo, duración y reclamos</h2>{datos.metricas.length ? <Tabla etiqueta="Tablero analítico" filas={datos.metricas} columnas={[{ clave: "item_codigo", titulo: "Ítem" }, { clave: "sector", titulo: "Sector" }, { clave: "puesto", titulo: "Puesto" }, { clave: "consumo", titulo: "Consumo" }, { clave: "duracion", titulo: "Duración", valor: f => f.duracion_promedio_dias === null ? `Sin datos suficientes (N=${f.muestra_duracion})` : `${f.duracion_promedio_dias} días (N=${f.muestra_duracion})` }, { clave: "reclamos", titulo: "Reclamos", valor: f => `${f.reclamos_total} de ${f.muestra_entregas} (${(f.reclamos_proporcion * 100).toFixed(1)}%)` }]} /> : <Vacio>Sin entregas para estos filtros.</Vacio>}</section></>}
    <section className="tarjeta"><h2>Comparador del mismo elemento normativo</h2><p className="ayuda">La API verifica que ambos ítems pertenezcan al mismo elemento; la interfaz no decide esa equivalencia.</p><form className="form-linea" onSubmit={comparar}><label>Ítem A<input name="item_a" required /></label><label>Ítem B<input name="item_b" required /></label><button className="primario">Comparar</button></form>{comparacion && <pre>{JSON.stringify(comparacion, null, 2)}</pre>}</section>
  </>;
}
