"use client";

import { useEffect, useRef, useState } from "react";
import { escalaAjustada, zoom } from "@/lib/seleccion";
import { Ventana } from "./compartidos";

type Archivo = { nombre: string; tipo: "imagen" | "pdf"; url: string; miniatura?: string | null; paginas?: number | null };

/** Miniatura del archivo entero; al tocarla se abre la vista previa grande. */
export function MiniaturaArchivo({ archivo }: { archivo: Archivo }) {
  const [abierta, setAbierta] = useState(false);
  const imagen = archivo.tipo === "imagen" ? archivo.url : archivo.miniatura;
  return <>
    <button type="button" className="miniatura-archivo" onClick={() => setAbierta(true)} aria-label={`Ver ${archivo.nombre} en grande`}>
      {imagen ? <img src={imagen} alt={`Vista del currículum ${archivo.nombre}`} /> : <span className="miniatura-pdf"><span className="miniatura-pdf-icono" aria-hidden="true">PDF</span><strong>{archivo.nombre}</strong>{archivo.paginas ? <small>{archivo.paginas === 1 ? "1 página" : `${archivo.paginas} páginas`}</small> : null}</span>}
      <span className="miniatura-ayuda">Tocá para ver en grande{archivo.tipo === "pdf" && archivo.paginas && archivo.paginas > 1 ? ` (${archivo.paginas} páginas)` : ""}</span>
    </button>
    {abierta && <VistaPrevia archivo={archivo} cerrar={() => setAbierta(false)} />}
  </>;
}

function VistaPrevia({ archivo, cerrar }: { archivo: Archivo; cerrar: () => void }) {
  const caja = useRef<HTMLDivElement>(null);
  const [natural, setNatural] = useState({ ancho: 0, alto: 0 });
  const [escala, setEscala] = useState<number | null>(null); // null: ajustada a la pantalla
  const [ajustada, setAjustada] = useState(1);
  useEffect(() => {
    const medir = () => { const c = caja.current; if (c) setAjustada(escalaAjustada(natural, { ancho: c.clientWidth - 16, alto: c.clientHeight - 16 })); };
    medir(); window.addEventListener("resize", medir); return () => window.removeEventListener("resize", medir);
  }, [natural]);
  const actual = escala ?? ajustada;
  return <Ventana tamano="completa" titulo={archivo.nombre} cerrar={cerrar}>
    <div className="vista-previa-barra">
      {archivo.tipo === "imagen" && <div className="acciones" role="group" aria-label="Zoom">
        <button type="button" onClick={() => setEscala(zoom(escala, ajustada, -1))} aria-label="Achicar">−</button>
        <span className="vista-previa-zoom" aria-live="polite">{Math.round(actual * 100)}%</span>
        <button type="button" onClick={() => setEscala(zoom(escala, ajustada, 1))} aria-label="Agrandar">+</button>
        <button type="button" onClick={() => setEscala(null)} disabled={escala === null}>Ajustar</button>
      </div>}
      <a className="boton" href={archivo.url} download={archivo.nombre}>Descargar original</a>
    </div>
    {archivo.tipo === "imagen"
      ? <div ref={caja} className={`vista-previa-lienzo${escala === null ? " ajustada" : ""}`}>
        <img src={archivo.url} alt={`Currículum ${archivo.nombre}`} onLoad={e => setNatural({ ancho: e.currentTarget.naturalWidth, alto: e.currentTarget.naturalHeight })}
          style={escala === null ? undefined : { width: natural.ancho * escala, height: natural.alto * escala, maxWidth: "none", maxHeight: "none" }} />
      </div>
      : <iframe className="vista-previa-pdf" title={`Currículum ${archivo.nombre}`} src={archivo.url} />}
  </Ventana>;
}
