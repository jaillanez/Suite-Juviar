# Guía rápida — Suite Juviar Gestión

## Levantar el entorno de prueba

Desde la raíz del repositorio:

```bash
./iniciar_prueba.sh
```

El puerto de la API se configura con `SJ_API_PORT` (predeterminado `8000`). Si
está ocupado, use por ejemplo:

```bash
SJ_API_PORT=8011 ./iniciar_prueba.sh
```

El mismo script pasa ese puerto a Tablet y Gestión mediante `API_INTERNAL_URL`;
no hay que modificar archivos ni URLs internas.

El comando abre tres servicios y los mantiene activos hasta presionar `Ctrl+C`:

- Gestión interna: <http://localhost:3002>
- Tablet de depósito: <http://localhost:3001>
- API y documentación: <http://127.0.0.1:8000/docs>

## Construcción para la red interna

```bash
pnpm --filter @suite-juviar/gestion build:static
```

El resultado queda en `apps/gestion/out`. Son archivos estáticos: Node se usa
para construirlos, pero no debe quedar ejecutándose en el servidor. El servidor
HTTP interno publica ese directorio y deriva `/api/v1/*` a FastAPI en el mismo
origen. Véase ADR 0004.

## Perfiles de Gestión

El ingreso de escritorio ofrece un selector visible porque identidad todavía es
simulada. Use RRHH para Selección, Legajos y aprobación de Turnos; Servicio
Médico para Salud; Higiene y Seguridad para EPP y Capacitaciones; Compras para
Stock y Analítica; Supervisión para Cronogramas.

Prueba negativa obligatoria: ingrese como RRHH y abra directamente
<http://localhost:3002/salud>. La aplicación debe rechazar el acceso y Salud no
debe aparecer en el menú. El mensaje debe decir `API respondió 403`; una negativa
producida únicamente por el navegador no alcanza. Luego cambie a Servicio Médico: sólo Resumen y Salud
deben quedar visibles.

## Cobertura del Bloque 2

Los recorridos de navegador están en `apps/gestion/e2e/bloque-2.spec.ts`; los
casos que requieren sustituir SMTP o mutar dependencias corren como integración
API porque no dependen de la red ni del navegador.

| Módulo | Caso | Prueba |
|---|---|---|
| EPP | Catálogo, matriz, stock y entregas | Playwright |
| EPP | Reposición y constancia anterior inmutable | `test_constancia_versionada.py` |
| EPP | Reemplazo informa entregas afectadas y limpieza confirmada | `test_gestion_escritorio.py` |
| EPP | URL/operación sin permiso | Playwright + `test_autorizacion.py` |
| EPP | Entrega sin existencias | `test_stock.py` |
| EPP | SMTP inválido/casilla inexistente | `test_stock.py` |
| EPP | Mutación: falso éxito SMTP debe ser detectado | `test_stock.py` |
| Selección | Búsqueda, lote, ranking, revisión y original | Playwright |
| Selección | Perfil sin permiso | `test_api_gestion.py` |
| Selección | Ilegible apartado, nunca descartado | Playwright + `test_api_gestion.py` |
| Selección | Confirmación manual explícita con autor | `test_api_gestion.py` |

Antes del reemplazo real, la previsualización debe indicar `entregas_afectadas`.
La limpieza está disponible en Catálogo sólo para `SJ_ENTORNO=prueba` y requiere
escribir exactamente `LIMPIAR DATOS SIMULADOS`. Elimina entregas, constancias y
stock `SIM-*`; conserva la bitácora y no modifica el catálogo hasta que HyS aplique
el reemplazo por separado.

## Cobertura del Bloque 3

Los recorridos de navegador están en `apps/gestion/e2e/bloque-3.spec.ts`.
Capacitaciones cubre convocatoria, dos tandas, deduplicación por persona y tema,
anulación visible, ausencia de porcentaje sin convocatoria y rechazo 403. La carga
histórica usa un `.xlsx` con previsualización y conserva las desapariciones.

Analítica cubre filtros, comparación entre dos ítems del mismo elemento, N y fecha
de corte visibles, y el bloqueo explicado de exportación ante `SIM-*`. La duración
sólo se cierra ante reposición por rotura o desgaste; los casos estacionales y la
muestra insuficiente se verifican en `test_analitica.py`.

## Tablet

En <http://localhost:3001>, ingrese con el legajo `1210` (depósito) y busque al
trabajador de muestra `1042`. Los datos simulados se identifican con una franja
roja. Las entregas de prueba conservan la constancia exacta y pueden incluir un
reclamo de calidad opcional por ítem.

## Límites de esta etapa

Ningún dato de muestra tiene validez productiva. SMTP, precios de Compras,
identidad, firma digital, Time, catálogo médico y muestra real de CV continúan
pendientes de sus fuentes o credenciales reales. La aplicación no debe arrancar
en producción con esos adaptadores simulados.
