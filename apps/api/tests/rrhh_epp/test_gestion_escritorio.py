import base64
import io
import zipfile


def xlsx_items(filas: list[list[str]]) -> bytes:
    cadenas = [valor for fila in filas for valor in fila]
    compartidas = "".join(f"<si><t>{valor}</t></si>" for valor in cadenas)
    indice = iter(range(len(cadenas)))
    filas_xml = "".join(
        f'<row r="{numero}">' + "".join(
            f'<c t="s"><v>{next(indice)}</v></c>' for _ in fila
        ) + "</row>"
        for numero, fila in enumerate(filas, 1)
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as libro:
        libro.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + compartidas + "</sst>",
        )
        libro.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + filas_xml + "</sheetData></worksheet>",
        )
    return salida.getvalue()


def test_hys_previsualiza_y_aplica_reemplazo_sin_borrar_historicos(cliente):
    filas = [
        ["elemento_codigo", "codigo_interno", "marca", "modelo", "talle", "color"],
        ["68", "REAL-68-01", "Marca", "Modelo", "42", "Negro"],
    ]
    cabecera = {"X-Perfil-Simulado": "HYS"}
    previa = cliente.post(
        "/catalogo/importaciones",
        headers=cabecera,
        json={"contenido_base64": base64.b64encode(xlsx_items(filas)).decode()},
    )
    assert previa.status_code == 200
    assert "REAL-68-01" in previa.json()["agrega"]
    aplicado = cliente.post(
        f"/catalogo/importaciones/{previa.json()['id']}/aplicar", headers=cabecera
    )
    assert aplicado.json()["modo"] == "REEMPLAZO"
    antiguo = cliente.get("/catalogo", headers={"X-Legajo-Usuario": "1210"}).json()
    item_simulado = next(item for e in antiguo for item in e["items"] if item["codigo_interno"] == "SIM-68-01")
    assert item_simulado["activo"] is False


def test_catalogo_exige_sesion_y_permiso(cliente):
    cuerpo = {"producto": "Prueba"}
    assert cliente.post("/catalogo/elementos/X", headers={"X-Legajo-Usuario": ""}, json=cuerpo).status_code == 401
    assert cliente.post("/catalogo/elementos/X", headers={"X-Perfil-Simulado": "RRHH"}, json=cuerpo).status_code == 403


def test_movimiento_y_reenvio_conservan_identificador(cliente, contenedor):
    compras = {"X-Perfil-Simulado": "COMPRAS"}
    movimiento = cliente.post(
        "/stock/SIM-68-01/movimientos", headers=compras,
        json={"cantidad": 1, "tipo": "ENTRADA", "motivo": "Reposición"},
    )
    assert movimiento.status_code == 200
    contenedor.stock.configurar("SIM-68-01", 21, 20)
    from .test_stock import _entregar
    _entregar(contenedor, id_entrega="GESTION-AVISO-1")
    aviso = cliente.get("/avisos-compras", headers=compras).json()[0]
    reenviado = cliente.post(f"/avisos-compras/{aviso['id']}/reenviar", headers=compras)
    assert reenviado.json()["identificador"] == aviso["identificador"]
