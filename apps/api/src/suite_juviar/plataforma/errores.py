"""Traducción central de excepciones de dominio al formato de FastAPI."""

from collections.abc import Callable, Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

CodigoPorExcepcion = tuple[type[BaseException], int]
LLAVE = "detail"


def registrar_manejadores(app: FastAPI, tabla: Iterable[CodigoPorExcepcion]) -> None:
    for excepcion, codigo in tabla:
        app.add_exception_handler(excepcion, _manejador(codigo))


def _manejador(codigo: int) -> Callable[[Request, Exception], JSONResponse]:
    async def manejar(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=codigo, content={LLAVE: str(exc)})

    return manejar
