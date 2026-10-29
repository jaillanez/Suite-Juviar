"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible, Tabla, Vacio, Ventana } from "./compartidos";

type Metrica = Record<string, unknown> & { item_codigo: string; sector: string; puesto: string; consumo: number; reclamos: Record<string, number>; reclamos_total: number; reclamos_proporcion: number; muestra_entregas: number; muestra_duracion: number; duracion_promedio_dias: number | null; estado_duracion: string };
type Tablero = { metricas: Metrica[]; fecha_corte: string; desde: string; hasta: string; costo: null; costo_leyenda: string; exportacion: { habilitada: boolean; motivo?: string }; datos_simulados: boolean };
type Opcion = { codigo: string; nombre: string };
type Elemento = { codigo: string; producto: string; items: Array<{ codigo_interno: string; modelo: string; talle: string }> };
type Fila = Metrica & { elemento: string; sector_nombre: string; puesto_nombre: string };
type Comparacion = { habilitado: boolean; items: Record<string, Metrica[]>; razones: Record<string, string | null>; precio_leyenda: string | null };

const MOTIVOS: Record<string, string> = { ROTURA: "Rotura", DESGASTE_PREMATURO: "Desgaste prematuro", TALLE: "Talle", MOLESTIA_USO: "Molestia al usarlo", DEFECTO_FABRICA: "Defecto de fábrica" };

function fecha(valor: string) { return new Date(`${valor}T12:00:00`).toLocaleDateString("es-AR"); }
function porcentaje(valor: number) { return `${(valor * 100).toLocaleString("es-AR", { maximumFractionDigits: 1 })}%`; }
function duracion(f: Metrica) { return f.duracion_promedio_dias === null ? `Falta historial (${f.muestra_duracion} reposiciones)` : `${Math.round(f.duracion_promedio_dias)} días`; }

export function AnaliticaGestion() {
  const hoy = new Date().toISOString().slice(0, 10);
  const [desde, setDesde] = useState(`${new Date().getFullYear()}-01-01`); const [hasta, setHasta] = useState(hoy);
  const [sector, setSector] = useState(""); const [puesto, setPuesto] = useState("");
  const [datos, setDatos] = useState<Tablero | null>(null); const [error, setError] = useState("");
  const [sectores, setSectores] = useState<Opcion[]>([]); const [puestos, setPuestos] = useState<Opcion[]>([]); const [catalogo, setCatalogo] = useState<Elemento[]>([]);
  const [detalle, setDetalle] = useState<Fila | null>(null);
  const [comparacion, setComparacion] = useState<Comparacion | null>(null); const [errorComparar, setErrorComparar] = useState("");

  async function cargar() { setError(""); try { setDatos(await api(`epp-analitica/tablero?desde=${desde}&hasta=${hasta}${sector ? `&sector=${encodeURIComponent(sector)}` : ""}${puesto ? `&puesto=${encodeURIComponent(puesto)}` : ""}`)); } catch (x) { setError(x instanceof Error ? x.message : "No se pudo cargar el tablero."); } }
  useEffect(() => {
    cargar();
    api<Opcion[]>("rrhh-epp/matriz/sectores").then(setSectores).catch(() => null);
    api<Opcion[]>("rrhh-epp/matriz/puestos").then(setPuestos).catch(() => null);
    api<Elemento[]>("rrhh-epp/catalogo").then(setCatalogo).catch(() => null);
  }, []);

  const nombreItem = useMemo(() => {
    const mapa = new Map<string, string>();
    for (const e of catalogo) for (const it of e.items) mapa.set(it.codigo_interno, [e.producto, it.modelo, it.talle && it.talle !== "SIN_DATO" ? `talle ${it.talle}` : ""].filter(Boolean).join(" · "));
    return (codigo: string) => mapa.get(codigo) ?? codigo;
  }, [catalogo]);
  const nombre = (lista: Opcion[], codigo: string) => lista.find((o) => o.codigo === codigo)?.nombre ?? codigo;
  const filas: Fila[] = (datos?.metricas ?? []).map((m) => ({ ...m, elemento: nombreItem(m.item_codigo), sector_nombre: nombre(sectores, m.sector), puesto_nombre: nombre(puestos, m.puesto) }));
  const entregados = filas.reduce((s, f) => s + f.consumo, 0);
  const reclamos = filas.reduce((s, f) => s + f.reclamos_total, 0);
  const muestra = filas.reduce((s, f) => s + f.muestra_entregas, 0);
  const masEntregados = Object.entries(filas.reduce<Record<string, number>>((acc, f) => { acc[f.elemento] = (acc[f.elemento] ?? 0) + f.consumo; return acc; }, {})).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const itemsConEntregas = [...new Set(filas.map((f) => f.item_codigo))].sort((a, b) => nombreItem(a).localeCompare(nombreItem(b)));

  async function filtrar(e: FormEvent) { e.preventDefault(); await cargar(); }
  async function comparar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setErrorComparar(""); setComparacion(null);
    const f = new FormData(e.currentTarget);
    try { setComparacion(await api(`epp-analitica/comparador?item_a=${encodeURIComponent(String(f.get("item_a")))}&item_b=${encodeURIComponent(String(f.get("item_b")))}&desde=${desde}&hasta=${hasta}`)); }
    catch (x) { setErrorComparar(x instanceof Error ? x.message : "Comparación inválida."); }
  }

  return <>
    {error && <ErrorVisible mensaje={error} />}
    <section className="tarjeta">
      <p className="ayuda-contextual"><strong>Para qué sirve:</strong> muestra cuántos elementos de protección se entregaron, cuánto duran antes de reponerse y cuántos reclamos hubo, por sector y puesto. Sirve para planificar compras y detectar productos que fallan.</p>
      <form className="form-linea" onSubmit={filtrar}>
        <label>Desde<input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></label>
        <label>Hasta<input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></label>
        <label>Sector<select value={sector} onChange={(e) => setSector(e.target.value)}><option value="">Todos los sectores</option>{sectores.map((s) => <option key={s.codigo} value={s.codigo}>{s.nombre}</option>)}</select></label>
        <label>Puesto<select value={puesto} onChange={(e) => setPuesto(e.target.value)}><option value="">Todos los puestos</option>{puestos.map((p) => <option key={p.codigo} value={p.codigo}>{p.nombre}</option>)}</select></label>
        <button className="primario">Ver</button>
      </form>
    </section>

    {datos && <>
      <div className="metricas">
        <article><span>Entregados</span><strong>{entregados.toLocaleString("es-AR")}</strong><small>Del {fecha(datos.desde)} al {fecha(datos.hasta)}</small></article>
        <article><span>Reclamos</span><strong>{reclamos.toLocaleString("es-AR")}</strong><small>{muestra ? `${porcentaje(reclamos / muestra)} de las entregas` : "Sin entregas"}</small></article>
        <article><span>Costo</span><strong>—</strong><small>{datos.costo_leyenda}</small></article>
      </div>
      {masEntregados.length > 0 && <section className="tarjeta"><h2>Lo más entregado</h2><ol className="ranking-simple">{masEntregados.map(([el, n]) => <li key={el}><span>{el}</span><strong>{n.toLocaleString("es-AR")}</strong></li>)}</ol></section>}
      <section className="tarjeta">
        <h2>Detalle por elemento, sector y puesto</h2>
        <p className="ayuda">Tocá una fila para ver el detalle. La duración se calcula recién cuando hay suficientes reposiciones del mismo elemento a la misma persona.</p>
        {filas.length ? <Tabla etiqueta="Detalle analítico" filas={filas} porPagina={10} alElegir={setDetalle} columnas={[
          { clave: "elemento", titulo: "Elemento" },
          { clave: "sector_nombre", titulo: "Sector" },
          { clave: "puesto_nombre", titulo: "Puesto" },
          { clave: "consumo", titulo: "Entregados" },
          { clave: "duracion_promedio_dias", titulo: "Duración promedio", valor: duracion },
          { clave: "reclamos_total", titulo: "Reclamos", valor: (f) => f.reclamos_total ? `${f.reclamos_total} (${porcentaje(f.reclamos_proporcion)})` : "Ninguno" },
        ]} /> : <Vacio>Sin entregas para estos filtros.</Vacio>}
      </section>
    </>}

    <section className="tarjeta">
      <h2>Comparar dos modelos del mismo elemento</h2>
      <p className="ayuda">Por ejemplo, dos marcas de calzado de seguridad: cuánto duró cada una y cuántos reclamos tuvo en el período elegido.</p>
      <form className="form-linea" onSubmit={comparar}>
        <label>Modelo A<select name="item_a" required defaultValue=""><option value="" disabled>Elegí un modelo</option>{itemsConEntregas.map((c) => <option key={c} value={c}>{nombreItem(c)}</option>)}</select></label>
        <label>Modelo B<select name="item_b" required defaultValue=""><option value="" disabled>Elegí un modelo</option>{itemsConEntregas.map((c) => <option key={c} value={c}>{nombreItem(c)}</option>)}</select></label>
        <button className="primario">Comparar</button>
      </form>
      {errorComparar && <ErrorVisible mensaje={errorComparar} />}
      {comparacion && <div className="comparacion">{Object.entries(comparacion.items).map(([codigo, metricas]) => {
        const entregas = metricas.reduce((s, m) => s + m.consumo, 0); const rec = metricas.reduce((s, m) => s + m.reclamos_total, 0);
        const conDuracion = metricas.filter((m) => m.duracion_promedio_dias !== null);
        const dias = conDuracion.length ? Math.round(conDuracion.reduce((s, m) => s + (m.duracion_promedio_dias ?? 0), 0) / conDuracion.length) : null;
        return <article key={codigo} className="tarjeta"><h3>{nombreItem(codigo)}</h3><dl className="ficha"><div><dt>Entregados</dt><dd>{entregas}</dd></div><div><dt>Duración promedio</dt><dd>{dias === null ? "Falta historial" : `${dias} días`}</dd></div><div><dt>Reclamos</dt><dd>{rec}</dd></div></dl>{comparacion.razones[codigo] && <p className="ayuda">Todavía no hay reposiciones suficientes para medir la duración.</p>}</article>;
      })}{comparacion.precio_leyenda && <p className="ayuda">{comparacion.precio_leyenda}.</p>}</div>}
    </section>

    {detalle && <Ventana titulo={detalle.elemento} cerrar={() => setDetalle(null)}>
      <dl className="ficha">
        <div><dt>Sector</dt><dd>{detalle.sector_nombre}</dd></div>
        <div><dt>Puesto</dt><dd>{detalle.puesto_nombre}</dd></div>
        <div><dt>Código</dt><dd>{detalle.item_codigo}</dd></div>
        <div><dt>Entregados</dt><dd>{detalle.consumo}</dd></div>
        <div><dt>Duración promedio</dt><dd>{duracion(detalle)}</dd></div>
        <div><dt>Reclamos</dt><dd>{detalle.reclamos_total} de {detalle.muestra_entregas} entregas ({porcentaje(detalle.reclamos_proporcion)})</dd></div>
      </dl>
      {detalle.reclamos_total > 0 && <><h3>Motivos de los reclamos</h3><ul>{Object.entries(detalle.reclamos).filter(([, n]) => n > 0).map(([motivo, n]) => <li key={motivo}>{MOTIVOS[motivo] ?? motivo}: {n}</li>)}</ul></>}
    </Ventana>}
  </>;
}
