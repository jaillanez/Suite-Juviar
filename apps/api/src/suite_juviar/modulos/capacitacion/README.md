# Capacitaciones

Un tema puede tener varios dictados. La asistencia se registra por dictado, pero
los porcentajes se calculan sobre el tema. El mismo motor compartido de Firma se
usa para la conformidad electrónica; mientras sea simulado todo resultado lleva
la marca `SIN VALIDEZ LEGAL` y también puede imprimirse para firma en papel.

## Funcionalidad incorporada

- Temas, dictados, asistencia electrónica o en papel, porcentajes por tema y persona,
  horas anuales por legajo y alerta exclusiva de supervisores bajo el umbral.
- Repositorio PostgreSQL con legajo y nombre cifrados; el umbral vive en un YAML
  `PROPUESTA_SIN_VALIDAR` cuyo dueño declarado es RRHH.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Certificado y sello de tiempo real | PENDIENTE | Reemplazar `MotorFirmaSimulado` por el motor corporativo antes de dejar el papel. |
| Umbral de supervisores | PROPUESTA_SIN_VALIDAR | RRHH debe aprobar el 80% o definir otro valor. |
| API con identidad | PENDIENTE | Exponer el repositorio PostgreSQL sólo cuando exista el perfil real autorizado. |
| Bitácora y anulación de asistencia | PENDIENTE | Registrar consultas/cambios y modelar corrección por anulación, nunca borrado. |
