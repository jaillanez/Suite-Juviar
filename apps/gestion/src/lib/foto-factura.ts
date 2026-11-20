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

async function buscarQr(img: HTMLImageElement): Promise<string> {
  // Primero el lector del propio celular (Android con Chrome lo trae); si no, ZXing.
  const Nativo = (globalThis as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => Detector }).BarcodeDetector;
  if (Nativo) {
    try {
      const leidos = await new Nativo({ formats: ["qr_code"] }).detect(img);
      const qr = leidos.map(l => l.rawValue).find(esQrDeArca);
      if (qr) return qr;
    } catch { /* se prueba con ZXing */ }
  }
  const [{ BrowserQRCodeReader }, { DecodeHintType }] = await Promise.all([import("@zxing/browser"), import("@zxing/library")]);
  const lector = new BrowserQRCodeReader(new Map([[DecodeHintType.TRY_HARDER, true]]));
  // El QR suele ser chico en la foto: se prueba a dos tamaños.
  for (const lado of [1600, 2800]) {
    try {
      const texto = lector.decodeFromCanvas(lienzo(img, lado)).getText().trim();
      if (esQrDeArca(texto)) return texto;
    } catch { /* no se encontró a este tamaño */ }
    if (Math.max(img.naturalWidth, img.naturalHeight) <= lado) break;
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

/** Lee el QR (si hay) y deja la foto en JPEG de hasta 1,5 MB, lista para subir. */
export async function prepararFoto(archivo: File): Promise<{ qr: string; foto_base64: string; vista: string }> {
  const img = await cargarImagen(archivo);
  const [qr, blob] = await Promise.all([buscarQr(img), comprimir(img)]);
  return { qr, foto_base64: await base64(blob), vista: URL.createObjectURL(blob) };
}
