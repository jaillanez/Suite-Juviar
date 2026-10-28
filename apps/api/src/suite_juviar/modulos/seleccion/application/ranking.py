"""Filtros defendibles: toda inclusión, exclusión o revisión explica su causa."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from ..domain.modelos import (
    AvisoCoincidencia,
    Busqueda,
    ExtraccionCV,
    ResultadoPostulante,
)
from ..domain.puertos import CriteriosPerfil, NotificadorCoincidencias


class EvaluarBusqueda:
    def __init__(self, perfiles: CriteriosPerfil) -> None:
        self._perfiles = perfiles

    def ejecutar(self, busqueda: Busqueda, extraccion: ExtraccionCV) -> ResultadoPostulante:
        campos = {campo.nombre: campo.valor for campo in extraccion.campos}
        razones: list[str] = []
        cumple = True
        puntaje = 0

        texto_edad = campos.get("edad_o_fecha_nacimiento")
        if busqueda.edad_minima is not None or busqueda.edad_maxima is not None:
            edad = self._edad(texto_edad)
            if edad is None:
                razones.append("REVISAR: no se pudo determinar la edad")
            elif busqueda.edad_minima is not None and edad < busqueda.edad_minima:
                cumple = False
                razones.append(f"FUERA: edad {edad} menor que {busqueda.edad_minima}")
            elif busqueda.edad_maxima is not None and edad > busqueda.edad_maxima:
                cumple = False
                razones.append(f"FUERA: edad {edad} mayor que {busqueda.edad_maxima}")
            else:
                puntaje += 1
                razones.append("DENTRO: edad en el rango definido")

        if busqueda.secundaria_completa:
            estudios = campos.get("nivel_estudios", "").casefold()
            if not estudios:
                razones.append("REVISAR: nivel de estudios no leído")
            elif "secundari" in estudios and "complet" in estudios:
                puntaje += 1
                razones.append("DENTRO: secundaria completa declarada")
            else:
                cumple = False
                razones.append("FUERA: no declara secundaria completa")

        palabras = self._perfiles.palabras_clave(busqueda.perfil)
        texto_perfil = " ".join(
            campos.get(nombre, "") for nombre in ("experiencia", "oficio")
        ).casefold()
        if not texto_perfil.strip():
            razones.append("REVISAR: experiencia y oficio no leídos")
        elif any(palabra.casefold() in texto_perfil for palabra in palabras):
            puntaje += 1
            razones.append(f"DENTRO: experiencia compatible con {busqueda.perfil.value}")
        else:
            cumple = False
            razones.append(f"FUERA: sin evidencia del perfil {busqueda.perfil.value}")

        requiere_revision = any(razon.startswith("REVISAR:") for razon in razones)
        return ResultadoPostulante(
            id_original=extraccion.id_original,
            cumple=cumple and not requiere_revision,
            requiere_revision=requiere_revision,
            puntaje=puntaje,
            razones=tuple(razones),
        )

    @staticmethod
    def _edad(texto: str | None) -> int | None:
        if not texto:
            return None
        coincidencia = re.search(r"\b(\d{1,3})\b", texto)
        if coincidencia is None:
            return None
        edad = int(coincidencia.group(1))
        return edad if 14 <= edad <= 100 else None


def ordenar_resultados(resultados: list[ResultadoPostulante]) -> list[ResultadoPostulante]:
    """Coincidencias, revisiones y no coincidencias; nunca oculta ni descarta."""
    return sorted(
        resultados,
        key=lambda resultado: (
            0 if resultado.cumple else 1 if resultado.requiere_revision else 2,
            -resultado.puntaje,
            resultado.id_original,
        ),
    )


class AvisarNuevaCoincidencia:
    def __init__(self, evaluar: EvaluarBusqueda, notificador: NotificadorCoincidencias) -> None:
        self._evaluar = evaluar
        self._notificador = notificador

    def ejecutar(
        self,
        busquedas: list[Busqueda],
        extraccion: ExtraccionCV,
    ) -> list[AvisoCoincidencia]:
        avisos: list[AvisoCoincidencia] = []
        for busqueda in busquedas:
            if not busqueda.abierta:
                continue
            resultado = self._evaluar.ejecutar(busqueda, extraccion)
            if not resultado.cumple:
                continue
            aviso = AvisoCoincidencia(
                busqueda_id=busqueda.id,
                id_original=extraccion.id_original,
                destinatario=busqueda.definido_por,
                creado_en=datetime.now(UTC),
            )
            self._notificador.avisar(aviso)
            avisos.append(aviso)
        return avisos

