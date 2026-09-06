# RRHH / EPP

Módulo único de entrega de ropa de trabajo y elementos de protección personal.
Funciona en entorno de prueba con legajos simulados, catálogo RD 068/11 real,
matriz `PROPUESTA_SIN_VALIDAR`, firma simulada y persistencia SQLite.

## Funcionalidad incorporada

- Catálogo normativo de 145 elementos y matriz compuesta por base, sector y puesto.
- Perfiles operativos resueltos por Parametría, sin perfil permisivo por defecto.
- Vida útil `REFERENCIAL_INVESTIGADO` y auditoría no bloqueante del catálogo.
- Cola offline en la tablet: guarda antes de enviar, muestra pendientes, reintenta con
  espera exponencial y no ofrece constancia hasta la confirmación idempotente del servidor.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Persistencia concurrente en PostgreSQL | PENDIENTE | Reemplazar SQLite antes de usar más de una tablet. |
| Umbral offline de 20 entregas o 24 horas | PROPUESTA_SIN_VALIDAR | Confirmación de Operaciones y de Higiene y Seguridad. |
| Identidad real del operario | PENDIENTE | Integrar `plataforma/identidad`; el header local es suplantable. |
| PDF y firma digital de la empresa | PENDIENTE | Certificado y motor real de `plataforma/firma`. |
| Catálogo de marcas, modelos, talles y colores | PENDIENTE | Excel maestro y numeración mantenida por Higiene y Seguridad. |
