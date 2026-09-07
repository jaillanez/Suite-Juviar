"""Adaptador real deliberadamente incompleto.

Solicitar al proveedor: diccionario de campos, zona horaria, semántica de entrada/salida,
identificador estable de empleado, correcciones/anulaciones, paginación, disponibilidad,
método de autenticación y ejemplos anonimizados. Nada se escribirá en Time: el contrato
real será exclusivamente de lectura y debe pasar `test_contrato_fuente_fichadas.py`.
"""


class FuenteFichadasTimePendiente:
    simulada = False

    def listar(self, desde, hasta):
        raise RuntimeError(
            "Falta el diccionario contractual de Time; no se inventan nombres de campos."
        )
