"""Punto de entrada del proceso que despacha avisos de stock a Compras."""

from suite_juviar.modulos.rrhh_epp.mvp import construir, construir_despachador_compras


def main() -> None:
    contenedor = construir()
    resultado = construir_despachador_compras(contenedor).ejecutar()
    print(f"Avisos a Compras: {resultado['enviados']} enviados, {resultado['fallidos']} fallidos")


if __name__ == "__main__":
    main()
