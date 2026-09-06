# Módulo RRHH / Higiene y Seguridad — entrega de EPP

Etapa 2 del plan de construcción. Digitaliza el formulario **RD 062/11**
(entrega de ropa de trabajo y EPP) con conformidad del trabajador en tablet.

Corre **sin Nexus**: los legajos salen de un archivo YAML que devuelve
exactamente las mismas columnas que va a devolver la Vista de Nexus. Es una
prueba funcional completa, no una maqueta.

---

## Cómo levantarlo

```bash
pip install -r requirements.txt
uvicorn modulos.rrhh_epp.api.app:app --reload --port 8000
```

Abrir `http://localhost:8000` para la pantalla del depósito y
`http://localhost:8000/matriz` para la revisión de la matriz que va a mirar
Higiene y Seguridad. Legajos cargados para probar: **1042** Quiroga
(bodega), **1077** Olivares (clarificación), **1103** Funes (autoelevador en
pañol: muestra cómo el puesto se suma al sector),
**1210** Aciar (pañol, Jubiar), **1444** Villegas (cosechero temporario, sector
sin matriz definida) y
**0988** Páez, que está dado de baja para ver el rechazo.

Las pruebas:

```bash
pytest -q        # 58 pruebas
```

---

## Qué hace

1. El operario del depósito busca al trabajador por legajo, apellido o DNI.
2. El sistema trae **nombre, DNI y puesto** de la fuente de legajos y arma la
   grilla de EPP que corresponde a ese puesto según la matriz de Higiene y
   Seguridad. Marca cuándo se le entregó cada cosa por última vez.
3. El operario tilda lo que entrega y ajusta cantidades. **No puede escribir
   productos a mano**: todo sale del catálogo RD 068/11.
4. El trabajador firma en la pantalla.
5. Queda el comprobante con el formato del RD 062/11 y un asiento en la
   bitácora.

---

## Lo que está simulado, y se nota

| Pieza | Hoy | Real |
|---|---|---|
| Legajos | `datos/nexus_simulado.yaml` | Vista `dbo.vw_legajos_activos` en Nexus, por VPN |
| Catálogo de EPP | **real**: 145 elementos del RD 068/11 V 02 | ya está; se regenera con el importador cuando salga la V 03 |
| Vida útil de cada elemento | tabla referencial que investigamos, en `datos/vida_util_referencial.yaml` | la que confirme HyS |
| Matriz sector/puesto vs. EPP | `datos/matriz_sector_puesto_epp.yaml`, propuesta nuestra | La que apruebe y firme Higiene y Seguridad |
| Firma | trazo guardado con la hora del servidor | Motor de firma de `plataforma/firma` |
| Guardado | SQLite local | PostgreSQL de la suite |

Mientras la fuente sea simulada, **la pantalla lleva una franja roja y cada
constancia sale marcada como documento sin validez legal**. Es a propósito: la
diferencia entre una prueba y un papel que alguien presenta en una inspección
tiene que ser visible de lejos.

La aplicación **se niega a arrancar** con `ENTORNO=produccion` si la fuente de
legajos no es Nexus.

---

## Cómo se reemplaza el YAML por Nexus

El único archivo que se toca es `config.py`, y sólo por variables de entorno:

```bash
FUENTE_LEGAJOS=nexus
NEXUS_CONEXION="DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=...;UID=...;PWD=..."
```

Los tres pasos, en orden:

1. Pedirle al responsable de Nexus que cree la Vista de
   `sql/vw_legajos_activos.sql` y un usuario con **SELECT sobre la Vista y
   nada más**. Los nombres de tablas de ese archivo son hipótesis; hay que
   confirmarlos.
2. Completar `_conectar()` en `adaptadores/legajos_nexus.py` (son tres líneas
   con `pyodbc`) y agregar `"nexus"` a la lista de fuentes en
   `tests/test_contrato_legajos.py`.
3. Correr `pytest tests/test_contrato_legajos.py`. Esas nueve pruebas dicen si
   la Vista devuelve lo que el módulo espera. Si pasan, se cambia la variable
   de entorno y listo. Si la Vista devuelve otros nombres de columna, se
   corrige la Vista, no el código.

Si el catálogo real de EPP no coincide con esta estructura, se cambia el YAML;
la aplicación valida al arrancar que la matriz no apunte a códigos que no
existen y se niega a levantar si hay inconsistencias.

---

## Estructura

```
datos/                          los tres archivos que reemplazan a las fuentes reales
sql/vw_legajos_activos.sql      lo que hay que pedirle a Nexus
modulos/rrhh_epp/
  dominio/                      modelos, puertos y reglas. Sin framework ni base de datos.
    modelos.py
    puertos.py                  las interfaces que después implementa lo real
    servicios.py                consultar legajo y registrar entrega
  adaptadores/
    legajos_yaml.py             fuente simulada
    legajos_nexus.py            fuente real, sin terminar a propósito
    catalogo_yaml.py            RD 068/11 + matriz
    persistencia.py             SQLite + bitácora
    firma_simulada.py           trazo y sello de tiempo, sin valor legal
  api/                          FastAPI, pantalla de la tablet y revisión de matriz
  config.py                     qué adaptador se enchufa a cada puerto
herramientas/importar_rd068.py  regenera el catálogo desde el Excel de RRHH
ESTADO_Y_PEDIDO_MINIMO.md       qué resolvimos y los cinco puntos que faltan
tests/                          58 pruebas
```

El dominio no importa nada de `adaptadores` ni de `api`. Cuando esto se integre
al repositorio grande, esa regla es la que van a verificar los contratos de
import-linter.

---

## Reglas de la base común que ya están cubiertas

| Regla | Cómo |
|---|---|
| 1 — No inventa personas | No hay tabla de empleados. Sólo lectura de la fuente de legajos. |
| 2 — No escribe en Nexus | El adaptador de Nexus sólo tiene `SELECT`; la Vista es de solo lectura. |
| 3 — Nada de texto libre | Todo código se valida contra el catálogo antes de aceptar la entrega. |
| 4 — Usa el motor de firma de la base | El módulo invoca el puerto `MotorFirma`. Hoy lo satisface un adaptador de prueba. |
| 5 — Deja bitácora | Cada entrega registra quién, qué, cuándo y desde qué fuente. |
| 6 — Dueño del dato | Catálogo y matriz declaran a Higiene y Seguridad en el encabezado del YAML. |
| 7 — Falla de forma clara | Sin conexión no está resuelto todavía. Ver pendientes. |

---

## Pendientes

**Insumos que faltan** (sin esto no se pasa de prueba a producción):

- Matriz de EPP aprobada y firmada por Higiene y Seguridad. La actual es una
  propuesta nuestra y **no sirve como criterio de protección real**.
- El RGRL presentado a la ART, para contrastar la matriz contra los riesgos que
  la empresa ya declaró.
Ver `ESTADO_Y_PEDIDO_MINIMO.md`: son cinco puntos y ninguno más.
- Credenciales y parámetros de la VPN al servidor de Santa Fe.
- Confirmar las razones sociales de las unidades (ENAV / ANAP / Jubiar), que
  define si el legajo es único global o único por empresa.
- Elegir el método de firma electrónica del trabajador con el asesor legal:
  trazo en tablet, PIN o biometría. Hoy están habilitados los dos primeros.

**Deuda técnica anotada:**

| Qué | Por qué importa | Cuándo |
|---|---|---|
| SQLite en vez de PostgreSQL | No aguanta varias tablets entregando a la vez | Antes de la primera prueba en un depósito real |
| No funciona sin conexión | En el depósito la red se cae y se pierde la entrega | Antes de producción. Regla 7. |
| No genera el PDF firmado | La constancia se ve en pantalla; falta el archivo original con metadatos de firma | Junto con el motor de firma real |
| La pantalla no pide identificación del operario de depósito | El usuario viene fijo en `"deposito"` | Cuando exista el módulo de identidad de la base |
| Falta el control de stock del depósito | La entrega no descuenta inventario | Etapa posterior |
