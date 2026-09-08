"use client";

import { ReactNode, useMemo, useState } from "react";

export function Simulado({ nivel = "pantalla" }: { nivel?: "campo" | "tabla" | "pantalla" }) {
  return <span className={`simulado simulado-${nivel}`}>DATOS SIMULADOS · SIN VALIDEZ</span>;
}

export function ErrorVisible({ mensaje }: { mensaje: string }) {
  return <div className="aviso-error" role="alert"><strong>No se pudo completar.</strong><span>{mensaje}</span></div>;
}

export function Vacio({ children = "Todavía no hay datos para mostrar." }: { children?: ReactNode }) {
  return <div className="vacio">{children}</div>;
}

export type Columna<T> = { clave: keyof T; titulo: string; valor?: (fila: T) => ReactNode };

export function Tabla<T extends Record<string, unknown>>({ filas, columnas, etiqueta, porPagina = 8 }: {
  filas: T[]; columnas: Columna<T>[]; etiqueta: string; porPagina?: number;
}) {
  const [filtro, setFiltro] = useState("");
  const [pagina, setPagina] = useState(1);
  const [orden, setOrden] = useState<keyof T>(columnas[0].clave);
  const filtradas = useMemo(() => filas.filter((fila) => JSON.stringify(fila).toLowerCase().includes(filtro.toLowerCase()))
    .toSorted((a, b) => String(a[orden] ?? "").localeCompare(String(b[orden] ?? ""))), [filas, filtro, orden]);
  const paginas = Math.max(1, Math.ceil(filtradas.length / porPagina));
  const visibles = filtradas.slice((pagina - 1) * porPagina, pagina * porPagina);
  return <section className="tabla-contenedor" aria-label={etiqueta}>
    <div className="tabla-herramientas"><label>Filtrar <input value={filtro} onChange={(e) => { setFiltro(e.target.value); setPagina(1); }} /></label><span>{filtradas.length} resultados</span></div>
    <div className="tabla-scroll"><table><thead><tr>{columnas.map((c) => <th key={String(c.clave)}><button onClick={() => setOrden(c.clave)}>{c.titulo}</button></th>)}</tr></thead>
      <tbody>{visibles.map((fila, i) => <tr key={i}>{columnas.map((c) => <td key={String(c.clave)}>{c.valor ? c.valor(fila) : String(fila[c.clave] ?? "—")}</td>)}</tr>)}</tbody></table></div>
    {filtradas.length === 0 && <Vacio>No hay coincidencias.</Vacio>}
    <nav className="paginacion" aria-label="Paginación"><button disabled={pagina === 1} onClick={() => setPagina(pagina - 1)}>Anterior</button><span>Página {pagina} de {paginas}</span><button disabled={pagina === paginas} onClick={() => setPagina(pagina + 1)}>Siguiente</button></nav>
  </section>;
}

export function Confirmacion({ abierto, titulo, detalle, confirmar, cancelar }: { abierto: boolean; titulo: string; detalle: string; confirmar: () => void; cancelar: () => void }) {
  if (!abierto) return null;
  return <div className="modal-fondo" role="presentation" onMouseDown={cancelar}><div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="modal-titulo" onMouseDown={(e) => e.stopPropagation()}><h2 id="modal-titulo">{titulo}</h2><p>{detalle}</p><div className="acciones"><button onClick={cancelar}>Cancelar</button><button className="peligro" onClick={confirmar}>Confirmar</button></div></div></div>;
}
