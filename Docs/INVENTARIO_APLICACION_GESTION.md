# Inventario y decisión — aplicación de gestión

Fecha: 2026-09-07  
Rama: `codex/rrhh-epp-unificado`

## Interfaz existente

La pantalla operativa de la tablet vive en `apps/mobile`. Está construida con
Next.js 16, React 19 y TypeScript, usando App Router, componentes de cliente,
CSS propio y `fetch` contra la API. En desarrollo, Next reescribe `/backend/*`
hacia `http://127.0.0.1:8000/api/v1/*`. Se construye con
`pnpm --filter @suite-juviar/mobile build`.

No es una interfaz de plantillas del servidor. El backend conserva dos plantillas
Jinja para constancias y matriz, pero no son el armazón de la tablet.

`apps/web` es el sitio público de DMZ. Su interfaz actual también usa Next.js 16,
React 19 y TypeScript; además conserva un servicio FastAPI público independiente.
No se modifica ni se reutiliza como aplicación interna.

## API disponible y brechas

| Módulo | Disponible | Falta para el plan de gestión |
|---|---|---|
| EPP | sesión simulada, estado, personas, entregas programadas, catálogo de lectura, stock, mínimos, alertas básicas, entrega, constancias, bitácora y matriz de lectura | CRUD/importación de catálogo, edición/validación de matriz, movimientos, outbox detallado/reenvío, búsqueda global y versiones de entregas |
| Analítica | pantalla HTML y exportación bloqueable | API JSON del tablero, comparación y detalle de muestra |
| Selección | dominio, ingesta, extracción y ranking | toda la API de gestión |
| Capacitaciones | dominio y persistencia | toda la API de gestión |
| Legajo | ficha HTML, alta y lectura de adjunto | búsqueda/listado JSON, ficha JSON, listado de adjuntos y emisión PDF |
| Salud | carga/consulta de certificado y reporte agregado | catálogo, listado, alerta art. 208 y bitácora consultable |
| Turnos | carga de cronograma, conciliación y aprobación en lote | lectura/historial, propuestas persistidas y bandeja de salida |

Una pantalla que necesite una operación de esta columna se sostendrá agregando el
endpoint y su prueba al backend. La interfaz no reconstruirá esas reglas.

## Decisión tecnológica

`apps/gestion` vive como aplicación separada para red interna. Usa la misma pila
ya operativa en la tablet: Next.js 16 + React 19 + TypeScript + CSS propio. Consume
exclusivamente `/api/v1` por HTTP mediante un rewrite de Next.

La decisión sigue la regla de continuidad del plan y queda aprobada por la orden
del usuario de ejecutar el plan. No se toca `apps/web`, `apps/consulta` ni se
rehace `apps/mobile`.

## Límite arquitectónico

Contrato 13: `apps/gestion` no puede importar `suite_juviar.modulos` ni
`suite_juviar.plataforma`. La aplicación sólo puede compartir contratos de datos
y componentes visuales del workspace, y comunicarse con negocio por HTTP.
