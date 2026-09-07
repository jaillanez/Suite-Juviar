# Analítica EPP para Compras

Módulo de sólo lectura sobre un puerto de entregas. No crea tablas ni modifica RRHH/EPP.

| Componente | Estado |
|---|---|
| Fuente de entregas | SIMULADA; reemplazar por proyección de sólo lectura de RRHH/EPP |
| Precios | SIMULADOS/SIN DATOS; dueño Compras |
| Duración | Construida; no publica promedio con menos de `N` reposiciones |
| Costos | Vacíos mientras falte cualquier precio; nunca se presentan como cero |
| Exportación | Bloqueada si existen fuentes o ítems simulados |

Deuda: conectar la fuente real de lectura, recibir precios de Compras y validar `N`.
