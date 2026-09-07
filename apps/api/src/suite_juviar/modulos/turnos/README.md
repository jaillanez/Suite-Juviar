# Conciliación de turnos

El supervisor carga cronogramas con autor y fecha; el sistema concilia, propone y RRHH
aprueba en lote. Nunca imputa automáticamente ni escribe en Time.

| Componente | Estado |
|---|---|
| Fuente de fichadas | SIMULADA |
| Exportación | Bandeja JSON local marcada, no Time |
| Adaptador Time | Deliberadamente incompleto hasta recibir diccionario |
| Identidad/roles | Simulados; integrar servicio real |

Deuda: persistencia PostgreSQL, perfiles reales, protocolo organizacional y contrato del proveedor.
