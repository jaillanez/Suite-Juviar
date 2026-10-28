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

El inventario detallado y priorizado se mantiene en
[`ENDPOINTS_GESTION_PENDIENTES.md`](ENDPOINTS_GESTION_PENDIENTES.md). Selección
y Capacitaciones ya tienen una primera API de gestión en memoria; no se consideran
cerradas hasta incorporar autorización, persistencia y todos los recorridos de
sus pantallas.

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

## Estado de la autorización

El menú por perfil y el rechazo de rutas de `apps/gestion` son controles de
experiencia de usuario, no controles de seguridad. La identidad actual es
declarada por el navegador. `X-Rol` y `X-Legajo-Usuario` pueden falsificarse y no
constituyen autenticación.

Hasta conectar identidad real, sólo se puede demostrar el comportamiento de la
interfaz. La demostración no debe afirmar que RRHH está técnicamente impedido de
consultar Salud. La condición de cierre será que la API obtenga actor, empresa y
roles de una sesión firmada y rechace cada endpoint con `401` o `403`, con pruebas
negativas directas contra la API además del E2E.
