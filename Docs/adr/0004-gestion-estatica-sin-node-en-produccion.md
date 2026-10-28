# ADR 0004 — Gestión se despliega estática, sin Node en producción

- Estado: ACEPTADA E IMPLEMENTADA
- Fecha: 2026-09-08

## Contexto

La red interna debe conservar infraestructura simple y ya dispone de FastAPI y
PostgreSQL local, sin Docker. `apps/gestion` y la tablet usan Next.js/React por
continuidad, pero ejecutar `next start` agregaría un proceso de aplicación, la
supervisión de Node y otra capa de proxy.

## Decisión

Next.js y Node se usan en desarrollo y compilación. El artefacto productivo de
`apps/gestion` será una exportación estática. Un único origen HTTP interno servirá
los archivos y enviará `/api/v1/*` a FastAPI. Puede utilizarse el servidor web ya
disponible o, si no existe, el despliegue de FastAPI. No requiere Docker ni un
proceso Node persistente.

Las rutas de Gestión se exportarán explícitamente y deberán funcionar al recargar
o entrar por URL directa. La API será relativa al mismo origen para permitir una
sesión segura sin CORS permanente.

## Consecuencias

- Se mantiene Next/React en tablet y escritorio.
- Producción opera FastAPI/PostgreSQL más archivos estáticos; Node no es servicio.
- Los rewrites de Next quedan sólo para desarrollo.
- `pnpm --filter @suite-juviar/gestion build:static` genera las ocho rutas en
  `apps/gestion/out`, listas para servir como directorios estáticos.
- Ocultar o servir una ruta estática nunca es autorización: la seguridad sigue
  perteneciendo a la API.
