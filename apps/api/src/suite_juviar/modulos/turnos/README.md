# Conciliación de turnos

El supervisor carga cronogramas semanales con autor y fecha de conocimiento; el
sistema concilia, propone y RRHH aprueba, rechaza o cambia en lote. Los días
cerrados no se reescriben: el cambio tardío crea una versión y alimenta el reporte
por sector. Nunca imputa automáticamente ni escribe en Time.

| Componente | Estado |
|---|---|
| Fuente de fichadas | SIMULADA |
| Exportación | Bandeja JSON local marcada, no Time |
| Cambios tardíos | Versionados y reportados por sector |
| Pendientes | Permanecen como propuesta, con antigüedad visible |
| Adaptador Time | Deliberadamente incompleto hasta recibir diccionario |
| Identidad/roles | Simulados; integrar servicio real |

Deuda: persistencia PostgreSQL, perfiles reales, protocolo organizacional y contrato del proveedor.
