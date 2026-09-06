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
- Corrección sin borrado: una asistencia se anula con motivo, actor y fecha; el
  registro original permanece y deja de computar en reportes.
- El rol PostgreSQL `suite_capacitacion_rrhh` queda aislado de EPP y Selección;
  la prueba local de §6.5 ejecuta consultas permitidas y prohibidas bajo el rol real.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Certificado y sello de tiempo real | PENDIENTE | Reemplazar `MotorFirmaSimulado` por el motor corporativo antes de dejar el papel. |
| Umbral de supervisores | PROPUESTA_SIN_VALIDAR | RRHH debe aprobar el 80% o definir otro valor. |
| API con identidad | PENDIENTE | Exponer el repositorio PostgreSQL sólo cuando exista el perfil real autorizado. |
| Bitácora de consultas | PENDIENTE | Registrar quién consulta planillas y reportes al incorporar la API con identidad. |
| Transporte de avisos a supervisores | PENDIENTE | Definir destinatarios y conectar el notificador cuando exista la API con identidad. |
