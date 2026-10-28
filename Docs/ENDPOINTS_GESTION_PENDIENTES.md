# Inventario de endpoints para Gestión

Fecha de corte: 2026-09-08. Los nombres son contratos propuestos. Cada endpoint
se implementará en su módulo, con autorización y pruebas; la interfaz sólo lo
consumirá por HTTP.

## Transversal

| Método y ruta propuesta | Uso | Estado |
|---|---|---|
| `POST /api/v1/sesion` | autenticar identidad real | FALTA; hoy el perfil se declara |
| `GET /api/v1/sesion` | actor, empresas y permisos efectivos | FALTA común; EPP tiene una sesión simulada móvil |
| `POST /api/v1/sesion/empresa` | cambiar a una empresa permitida | FALTA |
| `DELETE /api/v1/sesion` | cerrar sesión | FALTA |
| `GET /api/v1/estado-fuentes` | fuentes reales/simuladas por módulo | FALTA contrato común |

Todos los endpoints siguientes deben resolver empresa, actor y roles desde esa
sesión, nunca desde parámetros o encabezados libres del navegador.

## Paso 2 — EPP de escritorio (prioridad inmediata)

### Catálogo

| Método y ruta | Estado / brecha |
|---|---|
| `GET /rrhh-epp/catalogo` | EXISTE lectura; falta filtro y paginación de servidor |
| `POST /rrhh-epp/catalogo/elementos` | FALTA alta de elemento RD 068/11 |
| `PUT /rrhh-epp/catalogo/elementos/{codigo}` | FALTA edición |
| `DELETE /rrhh-epp/catalogo/elementos/{codigo}` | FALTA baja lógica con control de uso |
| `POST /rrhh-epp/catalogo/items` | FALTA alta de ítem comercial |
| `PUT /rrhh-epp/catalogo/items/{codigo}` | FALTA edición |
| `DELETE /rrhh-epp/catalogo/items/{codigo}` | FALTA baja lógica |
| `POST /rrhh-epp/catalogo/importaciones` | FALTA subir y validar Excel de HyS |
| `GET /rrhh-epp/catalogo/importaciones/{id}/previsualizacion` | FALTA diferencias y errores |
| `POST /rrhh-epp/catalogo/importaciones/{id}/aplicar` | FALTA reemplazo atómico, nunca fusión |

### Matriz Puesto–EPP

| Método y ruta | Estado / brecha |
|---|---|
| `GET /rrhh-epp/matriz` | EXISTE sólo HTML y lectura; falta JSON editable |
| `PUT /rrhh-epp/matriz/{empresa}/{sector}/{puesto}` | FALTA edición versionada |
| `POST /rrhh-epp/matriz/versiones/{id}/validar` | FALTA firma, actor y fecha de HyS |
| `GET /rrhh-epp/matriz/versiones` | FALTA historial y estado visible |

### Stock y avisos

| Método y ruta | Estado / brecha |
|---|---|
| `GET /rrhh-epp/stock` | EXISTE; falta filtro, paginación y consumo asociado |
| `PUT /rrhh-epp/stock/{item}` | EXISTE para saldo/mínimo; no registra un movimiento separado |
| `GET /rrhh-epp/stock/{item}/movimientos` | FALTA entradas, salidas y ajustes |
| `POST /rrhh-epp/stock/{item}/movimientos` | FALTA entrada/ajuste con motivo y auditoría |
| `GET /rrhh-epp/stock/alertas` | EXISTE alerta básica; no expone el outbox real |
| `GET /rrhh-epp/avisos-compras` | FALTA episodio, saldo, mínimo, ritmo, estado e intentos |
| `GET /rrhh-epp/avisos-compras/{id}/intentos` | FALTA diagnóstico sin secretos |
| `POST /rrhh-epp/avisos-compras/{id}/reenviar` | FALTA reintento manual idempotente |

### Entregas y constancias

| Método y ruta | Estado / brecha |
|---|---|
| `POST /rrhh-epp/entregas` | EXISTE |
| `GET /rrhh-epp/entregas` | FALTA buscar por persona, sector, empresa y período |
| `GET /rrhh-epp/entregas/{id}` | FALTA ficha JSON completa |
| `GET /rrhh-epp/entregas/{id}/constancias` | FALTA versiones y relación de anulación |
| `GET /rrhh-epp/constancias/{id}.pdf` | EXISTE para la constancia vigente de una entrega |
| `GET /rrhh-epp/constancias/versiones/{version}.pdf` | FALTA bytes exactos de cada versión |

E2E del bloque: catálogo → reemplazo previsualizado → matriz → entrega tablet →
constancia → reposición → episodio de aviso → fallo SMTP → reintento. Incluye
acceso sin permiso contra interfaz y directamente contra API.

## Paso 3 — Analítica

| Método y ruta | Estado / brecha |
|---|---|
| `GET /epp-analitica/metricas` | FALTA JSON; hoy sólo hay tabla HTML |
| `GET /epp-analitica/consumo` | FALTA serie y tamaño de muestra |
| `GET /epp-analitica/duracion` | FALTA agrupación JSON y suficiencia |
| `GET /epp-analitica/reclamos` | FALTA agrupación JSON por motivo |
| `GET /epp-analitica/comparaciones?item_a=&item_b=` | FALTA precio/duración con nulos explícitos |
| `GET /epp-analitica/exportar` | EXISTE y bloquea simulados; falta autorización real |

E2E: período → muestra suficiente/insuficiente → costo vacío → comparación →
exportación bloqueada.

## Paso 4 — Selección (segunda prioridad)

| Método y ruta | Estado / brecha |
|---|---|
| `GET/POST /seleccion/busquedas` | EXISTE memoria; falta persistencia, filtros y autorización |
| `GET/PUT /seleccion/busquedas/{id}` | FALTA detalle, cierre y cambio auditado de criterio |
| `POST /seleccion/cvs/lote` | EXISTE base64/memoria; falta multipart, límites y persistencia cifrada |
| `GET /seleccion/cvs` | EXISTE básico; falta búsqueda, filtro por estado y paginación |
| `GET /seleccion/cvs/{id}` | FALTA ficha, evidencias y ranking |
| `GET /seleccion/cvs/{id}/original` | EXISTE base64; debe responder PDF protegido para visor |
| `GET /seleccion/revision` | FALTA bandeja explícita de ilegibles |
| `POST /seleccion/cvs/{id}/reprocesar` | FALTA reproceso versionado |
| `PUT /seleccion/cvs/{id}/campos/{campo}/verificacion` | FALTA verificación humana auditada |

E2E: búsqueda → lote → filtros → ranking explicado → original → revisión de
ilegible, más rechazo por URL y API sin rol RRHH.

## Paso 5 — Capacitaciones

| Método y ruta | Estado / brecha |
|---|---|
| `GET/POST /capacitaciones/temas` | EXISTE memoria; falta persistencia y autorización |
| `GET/PUT /capacitaciones/temas/{id}` | FALTA detalle y edición |
| `POST /capacitaciones/dictados` | EXISTE; falta autorización y auditoría |
| `GET/PUT /capacitaciones/dictados/{id}` | FALTA ficha y edición controlada |
| `GET/POST /capacitaciones/dictados/{id}/asistencias` | EXISTE base; falta firma real |
| `GET /capacitaciones/dictados/{id}/planilla.pdf` | FALTA PDF; hoy devuelve texto |
| `POST /capacitaciones/dictados/{id}/asistencias/{legajo}/anular` | EXISTE; falta consulta de auditoría |
| `GET /capacitaciones/reportes` | EXISTE cálculo base; faltan contratos separados/paginables |
| `GET /capacitaciones/supervisores/alertas` | FALTA bandeja específica |

E2E: tema → tandas → asistencia/firma → planilla → reportes → alerta de
supervisor → anulación visible, más rechazo por URL y API.

## Paso 6 — Legajo y Salud

### Legajo

| Método y ruta | Estado / brecha |
|---|---|
| `GET /legajo` | FALTA buscador/listado JSON |
| `GET /legajo/{legajo}` | EXISTE HTML mínimo; falta ficha JSON completa |
| `GET /legajo/{legajo}/adjuntos` | FALTA listado de metadatos |
| `POST /legajo/adjuntos` | EXISTE base64/memoria; falta multipart, persistencia y autorización |
| `GET /legajo/adjuntos/{id}` | EXISTE base64; falta streaming protegido |
| `GET /legajo/{legajo}/emision.pdf` | FALTA emisión ENAV/Jubiar en PDF |

### Salud

| Método y ruta | Estado / brecha |
|---|---|
| `GET /salud/catalogo` | EXISTE muestra; falta fuente médica real |
| `GET/POST /salud/certificados` | POST EXISTE; falta listado, adjunto y persistencia cifrada |
| `GET /salud/certificados/{id}` | EXISTE y audita; el rol aún viaja en encabezado falsificable |
| `GET /salud/reportes` | EXISTE agregado básico |
| `GET /salud/bitacora` | EXISTE básico; falta filtro, paginación y actor de sesión |
| `GET /salud/articulo-208` | EXISTE preliminar; falta antigüedad y cargas reales |

E2E: RRHH no ve Salud y recibe `403` de la API; Médico carga y consulta,
visualiza art. 208 preliminar, reporte agregado y bitácora.

## Paso 7 — Turnos

| Método y ruta | Estado / brecha |
|---|---|
| `POST /turnos/cronogramas` | EXISTE memoria |
| `GET /turnos/cronogramas` | FALTA consulta por sector/período |
| `GET /turnos/cronogramas/{id}/historial` | FALTA cambios con actor y fecha |
| `PUT /turnos/cronogramas/{id}` | FALTA modificación auditada |
| `POST /turnos/conciliar` | EXISTE cálculo; no conserva la corrida |
| `GET /turnos/conciliaciones/{id}` | FALTA vista día por día |
| `GET /turnos/propuestas` | FALTA bandeja persistida |
| `POST /turnos/aprobar-lote` | EXISTE base; falta autorización y resultado detallado |
| `GET /turnos/salidas-time` | FALTA bandeja y estados |
| `POST /turnos/salidas-time/{id}/exportar` | FALTA; bloqueado hasta el diccionario Time |

E2E: cronograma → historial → conciliación → desvíos → propuestas → aprobación
RRHH → bandeja Time, más supervisor intentando aprobar y rechazo de API.

## Regla de entrega

No habrá una fase E2E separada al final. Cada bloque de los pasos 2 a 7 se cierra
con su recorrido positivo y sus rechazos de API/URL automatizados. Un endpoint
“existente” no está terminado si usa identidad declarada, memoria volátil o una
respuesta técnica que no sostiene la pantalla.
