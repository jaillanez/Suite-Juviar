# Guía rápida — Suite Juviar Gestión

## Levantar el entorno de prueba

Desde la raíz del repositorio:

```bash
./iniciar_prueba.sh
```

El comando abre tres servicios y los mantiene activos hasta presionar `Ctrl+C`:

- Gestión interna: <http://localhost:3002>
- Tablet de depósito: <http://localhost:3001>
- API y documentación: <http://127.0.0.1:8000/docs>

## Perfiles de Gestión

El ingreso de escritorio ofrece un selector visible porque identidad todavía es
simulada. Use RRHH para Selección, Legajos y aprobación de Turnos; Servicio
Médico para Salud; Higiene y Seguridad para EPP y Capacitaciones; Compras para
Stock y Analítica; Supervisión para Cronogramas.

Prueba negativa obligatoria: ingrese como RRHH y abra directamente
<http://localhost:3002/salud>. La aplicación debe rechazar el acceso y Salud no
debe aparecer en el menú. Luego cambie a Servicio Médico: sólo Resumen y Salud
deben quedar visibles.

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
