# Controles ARCA (ex AFIP)

Sección **Controles ARCA** de Gestión (grupo Administración). Por cada factura de proveedor
se hacen cinco controles y cada uno deja su constancia en PDF. Si alguno da mal, la factura
queda **en rojo** («Alerta») en la lista.

| N.º | Control | Cómo se hace |
|-----|---------|--------------|
| 1 | Control impositivo (Reproweb, agente de retención, consulta puntual) | A mano: necesita clave fiscal. Gestión lo deja **pendiente** con los enlaces; la persona baja el PDF de ARCA y lo sube. Si ese día ya se subió para el mismo proveedor con otra factura, se reusa. |
| 2 | Constancia de inscripción | Servicio web `ws_sr_constancia_inscripcion` (padrón A5, `getPersona_v2`). Alerta si no existe, la clave no está activa, ARCA no da la constancia o no tiene impuestos. |
| 3 | Facturas apócrifas | Listado completo de ARCA, cruzado por CUIT. Alerta si figura. |
| 4 | Autorización de la factura (CAE / CAEA / CAI) | Servicio web `wscdc` (`ComprobanteConstatar`). Alerta si ARCA no la aprueba. Las facturas de **controlador fiscal no se controlan** (se puede cambiar en Parámetros; si se apaga la excepción queda pendiente de control a mano). |
| 5 | Agentes de retención (RG 18) | Listado completo de ARCA. Es informativo: nunca da alerta. |

Estados: bien, alerta, pendiente, no corresponde, falta configurar (sin certificado o sin
CUIT de la empresa) y no se pudo consultar (ARCA no respondió: volver a correr). En los
estados pendiente, falta configurar y no se pudo consultar se puede subir a mano el PDF.

**Nombre de los PDF**: `CUIT_N_DD-MM-AAAA` (ej. `30693135679_1_26-09-2017`) y, para el
control 4, `CUIT_4_NNNNNNNN_DD-MM-AAAA` (ej. `30693135679_4_00000001_26-09-2017`). La fecha
es la del control (hora de Argentina). Los PDF de los controles automáticos los arma Gestión
con el resultado, la fecha y hora y la fuente consultada.

## Listados de ARCA (verificados el 18-11-2026)

- Apócrifas: `https://servicioscf.afip.gob.ar/Facturacion/facturasApocrifas/DownloadFile.aspx`
  → ZIP con `FacturasApocrifas.txt` (latin-1, comas: CUIT, fecha condición, fecha publicación, descripción; ~45.900 CUIT).
- RG 18: `https://servicioscf.afip.gob.ar/Publico/rg18/Archivos/RG18.csv`
  → CSV latin-1 con `;`: CUIT, razón social, fecha desde, fecha hasta, inciso (~3.000 CUIT).

Se bajan solos una vez por día (hilo `padrones-arca`) y con el botón «Actualizar ahora».
`SJ_DESCARGA_PADRONES=0` apaga la bajada automática (en pruebas viene apagada). Si un listado
viene vacío o no se puede bajar, se conserva el anterior.

## Parámetros (requiere `parametros.gestionar`)

- Controles activos (1 a 5) y la excepción de controlador fiscal.
- Ambiente: homologación o producción (cada ambiente tiene su propio certificado).
- CUIT del representante (20172238832) y CUIT de ENAV y de JUBIAR (a cargar).
- Direcciones de los listados (sólo sitios `afip.gob.ar`, `afip.gov.ar` o `arca.gob.ar`, con https) y enlaces del control impositivo.

## Certificado: paso a paso

La clave privada **nunca** sale del servidor: no viaja por chat ni por mail ni se sube desde
una PC. Se guarda cifrada con `SJ_CLAVE_PARAMETROS` (derivación y contexto propios del módulo);
ninguna pantalla ni la API la devuelven.

1. En **Parámetros → Controles de ARCA**, elegí el ambiente y tocá **«Generar pedido de certificado»**.
   El servidor genera la clave (RSA 2048) y se baja el pedido `.csr`.
2. Con la clave fiscal de 20172238832 entrá a ARCA → **«Administración de Certificados Digitales»**
   (para homologación: «WSASS»), agregá el alias que figura en el pedido y subí el `.csr`.
3. Bajá el certificado `.crt` que da ARCA y subilo en Gestión con **«Subir certificado de ARCA»**.
   Gestión comprueba que sea del pedido generado, del CUIT del representante y que no esté vencido.
4. En el **«Administrador de Relaciones de Clave Fiscal»** asociá el certificado (alias) a
   `ws_sr_constancia_inscripcion` y a `wscdc`. ENAV y JUBIAR tienen que delegar esos dos
   servicios en 20172238832.

Para renovar, se repite desde el paso 1: el certificado anterior sigue funcionando hasta que se
carga el nuevo.

## Técnica

Módulo `apps/api/src/suite_juviar/modulos/controles_arca` (dominio, servicio, adaptadores, API en
`/api/v1/controles-arca`). WSAA: TRA firmado en CMS/PKCS#7 (SHA-256) con el certificado; el permiso
(token y firma, ~12 h) se guarda cifrado y se reusa hasta 5 minutos antes de vencer, porque ARCA no
da otro mientras siga vigente. SOAP con `httpx` y XML a mano (sin zeep). Algunos servidores de
ARCA usan claves DH cortas: el cliente baja el nivel de cifrado aceptado (`SECLEVEL=1`) pero sigue
verificando el certificado del servidor. Permisos: `controles_fiscales.operar` (perfiles
Administración y Compras) y `parametros.gestionar` para Parámetros.
