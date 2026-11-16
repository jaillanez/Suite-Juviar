"use client";

import { useCallback, useEffect, useState } from "react";
import { abrirArchivo, api } from "@/lib/api";
import { ErrorVisible, Vacio } from "./compartidos";
import { ControlOrganica, EstadoOrganica } from "./sesion-organica";

type Camion = {
  id: number; foto: boolean; recibida_como: "organica" | "convencional" | null;
  numero: number | null; patente: string; productor: string | null; estado: string; organico: boolean;
  variedad_declarada: string | null; variedad_bascula: string | null; neto: number | null; azucar: number | null;
  registrado_en: string; llamado_en: string | null;
};
type Sede = {
  sede: string; nombre: string; anotados_hoy: number; en_espera: number; llamados: number;
  en_bascula: number; descargados_hoy: number; organica: EstadoOrganica | null; camiones: Camion[];
};
type Tablero = { fecha: string; sedes: Sede[] };

const ESTADOS: Record<string, string> = {
  pendiente: "Por confirmar", en_espera: "En espera", llamado: "Llamado",
  en_bascula: "En báscula", descargado: "Descargado",
};
const ORDEN: Record<string, number> = { llamado: 0, en_bascula: 1, en_espera: 2, pendiente: 3, descargado: 4 };

function hora(valor: string | null) {
  return valor ? new Date(valor).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" }) : "";
}

function useTablero(intervalo = 30_000) {
  const [datos, setDatos] = useState<Tablero | null>(null);
  const [error, setError] = useState(""); const [vuelta, setVuelta] = useState(0);
  const recargar = useCallback(() => setVuelta((v) => v + 1), []);
  useEffect(() => {
    let vivo = true;
    const leer = () => api<Tablero>("fila-tablero")
      .then((d) => { if (vivo) { setDatos(d); setError(""); } })
      .catch((x) => { if (vivo) setError(x instanceof Error ? x.message : "No se pudo leer la fila."); });
    leer();
    const reloj = window.setInterval(leer, intervalo);
    return () => { vivo = false; window.clearInterval(reloj); };
  }, [intervalo, vuelta]);
  return { datos, error, recargar };
}

function TarjetaCamion({ c }: { c: Camion }) {
  return <li className={`camion camion-${c.estado}`}>
    <div className="camion-cabecera">
      <strong>{c.numero ? `${c.numero} · ` : ""}{c.patente}</strong>
      <span className={`estado-camion estado-${c.estado}`}>{ESTADOS[c.estado] ?? c.estado}</span>
    </div>
    {c.productor && <span className="camion-productor">{c.productor}</span>}
    <dl className="camion-uva">
      <div><dt>Uva declarada</dt><dd>{c.variedad_declarada ?? "Sin declarar"}</dd></div>
      {(c.variedad_bascula || c.estado === "descargado") && <div><dt>Uva en báscula</dt><dd>{c.variedad_bascula ?? "Sin informar"}{c.neto ? ` · ${c.neto.toLocaleString("es-AR")} kg` : ""}{c.azucar !== null ? ` · azúcar ${c.azucar.toLocaleString("es-AR")}` : ""}</dd></div>}
    </dl>
    <small>{c.organico ? "Orgánico · " : ""}{c.recibida_como ? `Entra como ${c.recibida_como === "organica" ? "orgánica" : "convencional"} · ` : ""}Anotado {hora(c.registrado_en)}{c.llamado_en ? ` · llamado ${hora(c.llamado_en)}` : ""}</small>
    {c.foto && <button className="enlace" onClick={() => abrirArchivo(`fila-tablero/fotos/${c.id}`).catch(() => undefined)}>Ver foto de la patente</button>}
  </li>;
}

export function TableroFila({ puedeOperarOrganica = false }: { puedeOperarOrganica?: boolean }) {
  const { datos, error, recargar } = useTablero();
  if (error && !datos) return <ErrorVisible mensaje={error} />;
  if (!datos) return <section className="tarjeta"><p className="ayuda">Leyendo la fila de las bodegas…</p></section>;
  return <section className="tablero-fila" aria-label="Fila de camiones por bodega">
    {datos.sedes.map((s) => <article key={s.sede} className="tarjeta columna-bodega">
      <header><h2>{s.nombre}</h2><p className="ayuda">{s.anotados_hoy} anotados hoy · {s.descargados_hoy} descargados</p></header>
      <ControlOrganica sede={s.sede} estado={s.organica} puedeOperar={puedeOperarOrganica} cambio={recargar} />
      <div className="contadores-fila"><span><strong>{s.en_espera}</strong> en espera</span><span><strong>{s.llamados}</strong> llamados</span><span><strong>{s.en_bascula}</strong> en báscula</span></div>
      {s.camiones.length ? <ul className="lista-camiones">{s.camiones.toSorted((a, b) => (ORDEN[a.estado] ?? 9) - (ORDEN[b.estado] ?? 9)).map((c) => <TarjetaCamion key={`${c.patente}-${c.registrado_en}`} c={c} />)}</ul> : <Vacio>Sin camiones hoy.</Vacio>}
    </article>)}
    {error && <p className="ayuda">Última actualización con error: {error}</p>}
  </section>;
}

export function ResumenFila() {
  const { datos, error } = useTablero(60_000);
  if (error || !datos) return null;
  return <section className="resumen-produccion" aria-label="Producción">
    <h2>Producción · camiones anotados hoy</h2>
    <div className="metricas">{datos.sedes.map((s) => <article key={s.sede}><span>{s.nombre}</span><strong>{s.anotados_hoy}</strong><small>{s.en_espera} en espera · {s.descargados_hoy} descargados</small></article>)}</div>
  </section>;
}
