# Capacitaciones

Un tema puede tener varios dictados. La asistencia se registra por dictado, pero
los porcentajes se calculan sobre el tema. El mismo motor compartido de Firma se
usa para la conformidad electrónica; mientras sea simulado todo resultado lleva
la marca `SIN VALIDEZ LEGAL` y también puede imprimirse para firma en papel.

## Funcionalidad incorporada

- Temas, dictados, asistencia electrónica o en papel, porcentajes por tema y persona,
  horas anuales por legajo y alerta exclusiva de supervisores bajo el umbral.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Certificado y sello de tiempo real | PENDIENTE | Reemplazar `MotorFirmaSimulado` por el motor corporativo antes de dejar el papel. |
| Umbral de supervisores | PROPUESTA_SIN_VALIDAR | RRHH debe aprobar el 80% o definir otro valor. |
| Persistencia y API con identidad | PENDIENTE | Conectar repositorio PostgreSQL y perfiles reales; hoy el adaptador es sólo de prueba. |

