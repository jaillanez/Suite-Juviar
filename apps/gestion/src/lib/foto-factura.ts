// Foto de la factura del proveedor tomada con el celular: se busca el QR de ARCA en el
// navegador y la foto se achica a JPEG antes de subirla. Los datos del QR los valida el servidor.

export const TOPE_FOTO = 1.5 * 1024 * 1024;
const LADO_FOTO = 2000;

/** ¿El texto leído es el QR de una factura electrónica de ARCA (o AFIP)? */
export function esQrDeArca(texto: string): boolean {
  try {
    const url = new URL(texto.trim());
    return url.protocol === "https:" && /^(www\.)?(afip|arca)\.gob\.ar$/i.test(url.hostname)
      && /\/fe\/qr\/?$/i.test(url.pathname) && url.searchParams.has("p");
  } catch { return false; }
}

/** Importe escrito a mano: «12.100,50» (con coma decimal) o «12100.50». */
export function importeEscrito(texto: string): number {
  const limpio = texto.trim().replace(/\s|\$/g, "");
  if (limpio.includes(",")) return Number(limpio.replace(/\./g, "").replace(",", "."));
  // «12.100» sin coma es doce mil cien (punto de miles), no doce coma uno.
  return Number(/^\d{1,3}(\.\d{3})+$/.test(limpio) ? limpio.replace(/\./g, "") : limpio);
}

async function cargarImagen(archivo: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(archivo);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } catch {
    throw new Error("No se pudo abrir la foto. Sacala de nuevo.");
  } finally {
    URL.revokeObjectURL(url);
  }
}

function lienzo(img: HTMLImageElement, lado: number): HTMLCanvasElement {
  const escala = Math.min(1, lado / Math.max(img.naturalWidth, img.naturalHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(img.naturalWidth * escala));
  canvas.height = Math.max(1, Math.round(img.naturalHeight * escala));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Este celular no deja procesar la foto.");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas;
}

type Detector = { detect: (fuente: CanvasImageSource) => Promise<Array<{ rawValue: string }>> };

/** Copia con más contraste en blanco y negro: ayuda con fotos de pantalla, reflejos o poca luz. */
function contrastado(origen: HTMLCanvasElement): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = origen.width; canvas.height = origen.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return origen;
  ctx.drawImage(origen, 0, 0);
  const datos = ctx.getImageData(0, 0, canvas.width, canvas.height); const p = datos.data;
  let min = 255, max = 0;
  for (let i = 0; i < p.length; i += 4) { const g = (p[i] * 299 + p[i + 1] * 587 + p[i + 2] * 114) / 1000; p[i] = g; if (g < min) min = g; if (g > max) max = g; }
  const rango = Math.max(1, max - min);
  for (let i = 0; i < p.length; i += 4) { const g = ((p[i] - min) * 255) / rango; const v = g < 128 ? 0 : 255; p[i] = p[i + 1] = p[i + 2] = v; }
  ctx.putImageData(datos, 0, 0);
  return canvas;
}

/** Recortes de la foto (3×3 con solapamiento): un QR chico se lee mejor cuando ocupa más del cuadro. */
function recortes(origen: HTMLCanvasElement): HTMLCanvasElement[] {
  const salida: HTMLCanvasElement[] = [];
  const ancho = Math.round(origen.width / 2), alto = Math.round(origen.height / 2);
  for (const fy of [0, 0.25, 0.5]) for (const fx of [0, 0.25, 0.5]) {
    const c = document.createElement("canvas"); c.width = ancho; c.height = alto;
    const ctx = c.getContext("2d"); if (!ctx) continue;
    ctx.drawImage(origen, Math.round(origen.width * fx), Math.round(origen.height * fy), ancho, alto, 0, 0, ancho, alto);
    salida.push(c);
  }
  // Abajo a la izquierda, donde ARCA pone el QR, primero.
  return [salida[6], salida[7], salida[3], ...salida.filter((_, i) => ![6, 7, 3].includes(i))];
}

async function leerCanvas(canvas: HTMLCanvasElement, nativo: Detector | null,
                          zxing: { decodeFromCanvas: (c: HTMLCanvasElement) => { getText: () => string } }): Promise<string> {
  if (nativo) {
    try { const qr = (await nativo.detect(canvas)).map(l => l.rawValue).find(esQrDeArca); if (qr) return qr.trim(); } catch { /* sigue ZXing */ }
  }
  try { const texto = zxing.decodeFromCanvas(canvas).getText().trim(); if (esQrDeArca(texto)) return texto; } catch { /* no estaba */ }
  return "";
}

async function buscarQr(img: HTMLImageElement): Promise<string> {
  // Varias pasadas antes de darlo por perdido: tamaños, contraste y recortes por zona.
  const Nativo = (globalThis as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => Detector }).BarcodeDetector;
  let nativo: Detector | null = null;
  try { nativo = Nativo ? new Nativo({ formats: ["qr_code"] }) : null; } catch { nativo = null; }
  const [{ BrowserQRCodeReader }, { DecodeHintType }] = await Promise.all([import("@zxing/browser"), import("@zxing/library")]);
  const zxing = new BrowserQRCodeReader(new Map([[DecodeHintType.TRY_HARDER, true]]));
  const mayor = Math.max(img.naturalWidth, img.naturalHeight);
  const lados = [1200, 1800, 2600, mayor].filter((l, i, t) => l <= mayor && t.indexOf(l) === i);
  for (const lado of lados) {
    const base = lienzo(img, lado);
    for (const c of [base, contrastado(base)]) { const qr = await leerCanvas(c, nativo, zxing); if (qr) return qr; }
  }
  const grande = lienzo(img, Math.min(mayor, 3200));
  for (const c of recortes(grande)) {
    for (const v of [c, contrastado(c)]) { const qr = await leerCanvas(v, nativo, zxing); if (qr) return qr; }
  }
  return "";
}

function aBlob(canvas: HTMLCanvasElement, calidad: number): Promise<Blob> {
  return new Promise((ok, mal) => canvas.toBlob(b => b ? ok(b) : mal(new Error("No se pudo preparar la foto.")), "image/jpeg", calidad));
}

async function comprimir(img: HTMLImageElement): Promise<Blob> {
  for (const lado of [LADO_FOTO, 1600, 1200]) {
    const canvas = lienzo(img, lado);
    for (const calidad of [0.82, 0.7, 0.6]) {
      const blob = await aBlob(canvas, calidad);
      if (blob.size <= TOPE_FOTO) return blob;
    }
  }
  throw new Error("La foto es muy pesada. Sacala de nuevo un poco más lejos.");
}

async function base64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let texto = "";
  for (let i = 0; i < bytes.length; i += 0x8000) texto += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(texto);
}

/** Cuadro tomado de la cámara en vivo cuando reconoció el QR: queda como foto de la factura. */
export async function fotoDesdeVideo(video: HTMLVideoElement, qr: string): Promise<{ qr: string; foto_base64: string; vista: string }> {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx || !canvas.width) throw new Error("No se pudo tomar la imagen de la cámara.");
  ctx.drawImage(video, 0, 0);
  let blob: Blob | null = null;
  for (const calidad of [0.85, 0.7, 0.55]) { blob = await aBlob(canvas, calidad); if (blob.size <= TOPE_FOTO) break; }
  if (!blob || blob.size > TOPE_FOTO) throw new Error("La imagen de la cámara es muy pesada.");
  return { qr, foto_base64: await base64(blob), vista: URL.createObjectURL(blob) };
}

/** Lee el QR (si hay) y deja la foto en JPEG de hasta 1,5 MB, lista para subir. */
export async function prepararFoto(archivo: File): Promise<{ qr: string; foto_base64: string; vista: string }> {
  const img = await cargarImagen(archivo);
  const [qr, blob] = await Promise.all([buscarQr(img), comprimir(img)]);
  return { qr, foto_base64: await base64(blob), vista: URL.createObjectURL(blob) };
}
