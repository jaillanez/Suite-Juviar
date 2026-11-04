"use client";

import { useEffect, useRef, useState } from "react";
import { Ventana } from "./compartidos";

function motivo(x: unknown) {
  const nombre = x instanceof Error ? x.name : "";
  if (nombre === "NotAllowedError") return "La tablet no dio permiso para usar la cámara. Habilitalo en los permisos de la app y probá de nuevo.";
  if (nombre === "NotFoundError" || nombre === "OverconstrainedError") return "No se encontró una cámara en este equipo.";
  if (nombre === "NotReadableError") return "La cámara está ocupada por otra app. Cerrala y probá de nuevo.";
  return "No se pudo abrir la cámara.";
}

/** Lee códigos de barras y QR con la cámara trasera de la tablet o el celular. */
export function LectorCamara({ leido, cerrar }: { leido: (codigo: string) => void; cerrar: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const alLeer = useRef(leido);
  useEffect(() => { alLeer.current = leido; }, [leido]);
  const [error, setError] = useState("");

  useEffect(() => {
    let controles: { stop: () => void } | undefined; let vigente = true;
    if (!navigator.mediaDevices?.getUserMedia) { setError("La cámara sólo funciona entrando por la dirección segura (https)."); return; }
    (async () => {
      try {
        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        if (!vigente || !video.current) return;
        controles = await new BrowserMultiFormatReader().decodeFromConstraints(
          { video: { facingMode: "environment" } }, video.current,
          (resultado, _error, c) => { if (resultado && vigente) { vigente = false; c.stop(); alLeer.current(resultado.getText().trim()); } });
        if (!vigente) controles.stop();
      } catch (x) { if (vigente) setError(motivo(x)); }
    })();
    return () => { vigente = false; controles?.stop(); };
  }, []);

  return <Ventana titulo="Leer con la cámara" tamano="chica" cerrar={cerrar}>
    {error ? <p className="error">{error}</p> : <>
      <div className="lector-camara"><video ref={video} muted playsInline /></div>
      <p className="ayuda">Apuntá a la etiqueta del equipo. Se abre sola cuando lee el código de barras o el QR.</p>
    </>}
    <div className="acciones"><button onClick={cerrar}>Cancelar</button></div>
  </Ventana>;
}
