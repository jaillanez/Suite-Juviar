"""Lectura del QR de la factura en el servidor, cuando el celular no lo pudo leer.

Las facturas que llegan escaneadas e impresas suelen tener el QR algo borroso: el lector del
navegador no lo encuentra, pero ZXing en C++ (``zxing-cpp``) sí, sobre todo si se le dan
varias versiones de la foto: tal cual, en grises con más contraste, con umbral adaptativo,
más nítida, agrandada y recortada por zonas (primero abajo a la izquierda, donde ARCA pone
el QR). Las pasadas se cortan al primer QR de ARCA o al pasar el tiempo máximo.

La foto no sale del servidor. Si la librería no está instalada o la foto no se puede abrir,
devuelve una lista vacía y se sigue con la lectura del texto.
"""

from __future__ import annotations

import io
import logging
import time
from collections.abc import Callable, Iterator

from PIL import Image, ImageChops, ImageFilter, ImageOps

from ..domain.lectura import QRInvalido, leer_qr

try:
    import zxingcpp
except ImportError:  # pragma: no cover - la imagen de Gestión la instala
    zxingcpp = None

_registro = logging.getLogger(__name__)

TIEMPO_MAXIMO = 4.0  # segundos para todas las pasadas
MAXIMO_PIXELES = 25_000_000  # una foto de 2 MB más grande que esto no es una foto de celular
LADO_TRABAJO = 2400  # la foto se achica a esto antes de empezar
LADO_MAXIMO_AGRANDADA = 3200


def _es_de_arca(texto: str) -> bool:
    try:
        leer_qr(texto)
    except QRInvalido:
        return False
    return True


def _abrir(contenido: bytes) -> Image.Image | None:
    try:
        imagen = Image.open(io.BytesIO(contenido))
        if imagen.width * imagen.height > MAXIMO_PIXELES:
            return None
        # JPEG: se decodifica ya achicado, sin pasar por la foto entera en memoria.
        imagen.draft("RGB", (LADO_TRABAJO, LADO_TRABAJO))
        imagen = ImageOps.exif_transpose(imagen)  # fotos de celular giradas por EXIF
        imagen.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    if imagen.mode not in {"L", "RGB"}:
        fondo = Image.new("RGB", imagen.size, "white")
        convertida = imagen.convert("RGBA")
        fondo.paste(convertida, mask=convertida.getchannel("A"))
        imagen = fondo
    if max(imagen.size) > LADO_TRABAJO:
        imagen.thumbnail((LADO_TRABAJO, LADO_TRABAJO), Image.Resampling.LANCZOS)
    return imagen


def _grises(imagen: Image.Image) -> Image.Image:
    return ImageOps.autocontrast(imagen.convert("L"), cutoff=1)


def _umbral_adaptativo(imagen: Image.Image) -> Image.Image:
    """Negro donde el punto es más oscuro que su zona: aguanta sombras y tinta gastada."""
    gris = imagen.convert("L")
    radio = max(8, min(gris.size) // 40)
    zona = gris.filter(ImageFilter.BoxBlur(radio))
    diferencia = ImageChops.subtract(zona, gris)
    return diferencia.point(lambda v: 0 if v > 6 else 255)


def _nitida(imagen: Image.Image, radio: float, fuerza: int) -> Image.Image:
    """Dos pasadas de máscara de enfoque: recupera bordes de módulos de una impresión borrosa.

    Probado con QR desenfocados: hasta un desenfoque de ~0,6 módulos se lee con el radio
    cerca de la mitad del módulo; sin enfocar, ZXing deja de leer en ~0,4.
    """
    gris = _grises(imagen)
    filtro = ImageFilter.UnsharpMask(radius=radio, percent=fuerza, threshold=0)
    return gris.filter(filtro).filter(filtro)


def _escalada(imagen: Image.Image, factor: float) -> Image.Image:
    factor = min(factor, LADO_MAXIMO_AGRANDADA / max(imagen.size))
    if factor <= 1:
        return imagen
    return imagen.resize((round(imagen.width * factor), round(imagen.height * factor)), Image.Resampling.LANCZOS)


def _recortes(imagen: Image.Image) -> Iterator[Image.Image]:
    """Mitades de la foto en una grilla de 3×3 solapada, empezando abajo a la izquierda."""
    ancho, alto = imagen.width // 2, imagen.height // 2
    orden = [(0, 2), (1, 2), (0, 1), (2, 2), (1, 1), (0, 0), (2, 1), (1, 0), (2, 0)]
    for columna, fila in orden:
        x, y = columna * imagen.width // 4, fila * imagen.height // 4
        yield imagen.crop((x, y, x + ancho, y + alto))


def _pasadas(imagen: Image.Image) -> Iterator[tuple[Image.Image, bool]]:
    """(imagen, binarizador global): de lo más barato a lo más caro.

    El enfoque rinde sobre los recortes, donde el QR ocupa buena parte del cuadro; sobre la
    hoja entera ZXing no encuentra el QR enfocado.
    """
    gris = _grises(imagen)
    yield imagen, False
    yield gris, True
    yield _umbral_adaptativo(gris), False
    yield _nitida(imagen, 2, 300), False
    # Los recortes salen de la foto sin tocar: el contraste se ajusta en cada recorte. Si se
    # ajusta antes sobre la hoja entera, lo oscuro del QR borroso se satura y el enfoque ya
    # no tiene de dónde recuperar los bordes.
    for recorte in _recortes(imagen.convert("L")):
        yield _grises(recorte), False
        yield _nitida(recorte, 2, 300), False
        yield _nitida(recorte, 3, 500), True
        yield _umbral_adaptativo(recorte), False
        doble = _escalada(recorte, 2)
        yield _grises(doble), False
        yield _nitida(doble, 3, 400), False
    yield _escalada(gris, 1.5), False


class LectorQRServidor:
    def __init__(self, tiempo_maximo: float = TIEMPO_MAXIMO, reloj: Callable[[], float] = time.monotonic) -> None:
        self.tiempo_maximo = tiempo_maximo
        self._reloj = reloj

    @property
    def disponible(self) -> bool:
        return zxingcpp is not None

    def leer(self, contenido: bytes) -> list[str]:
        if zxingcpp is None:
            return []
        imagen = _abrir(contenido)
        if imagen is None:
            return []
        limite = self._reloj() + self.tiempo_maximo
        encontrados: list[str] = []
        for variante, global_ in _pasadas(imagen):
            try:
                codigos = zxingcpp.read_barcodes(
                    variante, formats=zxingcpp.BarcodeFormat.QRCode,
                    binarizer=zxingcpp.Binarizer.GlobalHistogram if global_ else zxingcpp.Binarizer.LocalAverage)
            except (ValueError, RuntimeError) as exc:
                _registro.debug("Pasada de lectura de QR fallida: %s", exc)
                codigos = []
            for codigo in codigos:
                texto = (codigo.text or "").strip()
                if texto and texto not in encontrados:
                    encontrados.append(texto)
            if any(_es_de_arca(t) for t in encontrados) or self._reloj() > limite:
                break
        return encontrados
