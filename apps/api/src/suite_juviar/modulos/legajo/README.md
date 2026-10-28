# Legajo digital

No crea personas: consulta un puerto de legajos. Conserva adjuntos completos cifrados y
emite el formato correspondiente a ENAV o Jubiar desde los mismos datos.

| Componente | Estado |
|---|---|
| Fuente de personas | Adaptador estructural sobre el puerto existente; Nexus simulado hoy, sin duplicar personas |
| Adjuntos | Cifrado AES-GCM construido; persistencia PostgreSQL pendiente |
| Pantalla/impresión | Marcada `DATOS SIMULADOS — SIN VALIDEZ` |

Deuda: adaptar Nexus real, persistir adjuntos cifrados y validar ambos formatos con RRHH.
