"use client";

import { useEffect, useRef, useState } from "react";
import { esQrDeArca, fotoDesdeVideo } from "@/lib/foto-factura";

type Leida = { qr: string; foto_base64: string; vista: string };

function motivo(x: unknown) {
  const nombre = x instanceof Error ? x.name : "";
  if (nombre === "NotAllowedError") return "El celular no dio permiso para usar la cámara. Habilitalo para esta página y probá de nuevo.";
  if (nombre === "NotFoundError" || nombre === "OverconstrainedError") return "No se encontró la cámara.";
  if (nombre === "NotReadableError") return "La cámara está ocupada por otra app. Cerrala y probá de nuevo.";
  return "No se pudo abrir la cámara.";
}

/** Cámara en vivo: lee cuadro por cuadro hasta encontrar el QR de ARCA y guarda ese cuadro como foto. */
export function LectorQrFactura({ leida, cancelar }: { leida: (f: Leida) => void; cancelar: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const alLeer = useRef(leida);
  useEffect(() => { alLeer.current = leida; }, [leida]);
  const [error, setError] = useState("");
  const [otroCodigo, setOtroCodigo] = useState(false);

  useEffect(() => {
    let controles: { stop: () => void } | undefined; let vigente = true;
    if (!navigator.mediaDevices?.getUserMedia) { setError("La cámara sólo funciona entrando por la dirección segura (https)."); return; }
    (async () => {
      try {
        const [{ BrowserQRCodeReader }, { DecodeHintType }] = await Promise.all([import("@zxing/browser"), import("@zxing/library")]);
        if (!vigente || !video.current) return;
        const lector = new BrowserQRCodeReader(new Map([[DecodeHintType.TRY_HARDER, true]]), { delayBetweenScanAttempts: 150 });
        controles = await lector.decodeFromConstraints(
          { video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } } }, video.current,
          (resultado, _error, c) => {
            if (!resultado || !vigente || !video.current) return;
            const texto = resultado.getText().trim();
            // Otros QR (de la empresa, de un pago) no cortan la búsqueda.
            if (!esQrDeArca(texto)) { setOtroCodigo(true); return; }
            vigente = false;
            void fotoDesdeVideo(video.current, texto)
              .then(f => { c.stop(); alLeer.current(f); })
              .catch(x => { c.stop(); setError(x instanceof Error ? x.message : "No se pudo tomar la imagen."); });
          });
        if (!vigente) controles.stop();
      } catch (x) { if (vigente) setError(motivo(x)); }
    })();
    return () => { vigente = false; controles?.stop(); };
  }, []);

  return <div className="cel-camara">
    {error ? <p className="cel-error" role="alert">{error}</p> : <>
      <div className="lector-camara"><video ref={video} muted playsInline /></div>
      <p className="cel-texto">Apuntá al código QR de la factura y acercate hasta que ocupe buena parte de la pantalla. Se lee solo.</p>
      {otroCodigo && <p className="cel-aviso">Ese código no es el QR de ARCA de la factura. Apuntá al que está abajo, junto al logo de ARCA.</p>}
    </>}
    <button className="cel-boton cel-secundario" onClick={cancelar}>Cancelar</button>
  </div>;
}
