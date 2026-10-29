"use client";

import { ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";

export function ErrorVisible({ mensaje }: { mensaje: string }) {
  return <div className="aviso-error" role="alert"><strong>No se pudo completar.</strong><span>{mensaje}</span></div>;
}

export function Vacio({ children = "Todavía no hay datos para mostrar." }: { children?: ReactNode }) {
  return <div className="vacio">{children}</div>;
}

export type Columna<T> = { clave: keyof T; titulo: string; valor?: (fila: T) => ReactNode };

export function Tabla<T extends Record<string, unknown>>({ filas, columnas, etiqueta, porPagina = 8, alElegir }: {
  filas: T[]; columnas: Columna<T>[]; etiqueta: string; porPagina?: number; alElegir?: (fila: T) => void;
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
      <tbody>{visibles.map((fila, i) => <tr key={i} {...(alElegir ? { className: "fila-elegible", tabIndex: 0, onClick: () => alElegir(fila), onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alElegir(fila); } } } : {})}>{columnas.map((c) => <td key={String(c.clave)}>{c.valor ? c.valor(fila) : String(fila[c.clave] ?? "—")}</td>)}</tr>)}</tbody></table></div>
    {filtradas.length === 0 && <Vacio>No hay coincidencias.</Vacio>}
    <nav className="paginacion" aria-label="Paginación"><button disabled={pagina === 1} onClick={() => setPagina(pagina - 1)}>Anterior</button><span>Página {pagina} de {paginas}</span><button disabled={pagina === paginas} onClick={() => setPagina(pagina + 1)}>Siguiente</button></nav>
  </section>;
}

export function Confirmacion({ abierto, titulo, detalle, confirmar, cancelar }: { abierto: boolean; titulo: string; detalle: string; confirmar: () => void; cancelar: () => void }) {
  if (!abierto) return null;
  return <div className="modal-fondo" role="presentation" onMouseDown={cancelar}><div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="modal-titulo" onMouseDown={(e) => e.stopPropagation()}><h2 id="modal-titulo">{titulo}</h2><p>{detalle}</p><div className="acciones"><button onClick={cancelar}>Cancelar</button><button className="peligro" onClick={confirmar}>Confirmar</button></div></div></div>;
}

// Pila de ventanas abiertas: Escape cierra sólo la de arriba cuando hay una encima de otra.
const ventanasAbiertas: symbol[] = [];

export function Ventana({ titulo, cerrar, children, tamano = "ancha" }: { titulo: string; cerrar: () => void; children: ReactNode; tamano?: "chica" | "ancha" | "amplia" }) {
  const alCerrar = useRef(cerrar);
  useEffect(() => { alCerrar.current = cerrar; }, [cerrar]);
  const id = useId();
  useEffect(() => {
    const propia = Symbol("ventana"); ventanasAbiertas.push(propia);
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape" && ventanasAbiertas.at(-1) === propia) alCerrar.current(); };
    document.addEventListener("keydown", tecla);
    return () => { document.removeEventListener("keydown", tecla); ventanasAbiertas.splice(ventanasAbiertas.indexOf(propia), 1); };
  }, []);
  return <div className="modal-fondo" role="presentation" onMouseDown={cerrar}><div className={`modal modal-ancho${tamano === "ancha" ? "" : ` modal-${tamano}`}`} role="dialog" aria-modal="true" aria-labelledby={id} onMouseDown={(e) => e.stopPropagation()}><div className="titulo-fila"><h2 id={id}>{titulo}</h2><button onClick={cerrar} aria-label="Cerrar" autoFocus>✕</button></div>{children}</div></div>;
}

// Chrome no muestra PDF «data:» dentro de un iframe: se arma una dirección blob local.
export function urlDeArchivo(base64: string, tipo: string): string {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: tipo }));
}
