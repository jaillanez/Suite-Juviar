# Analítica EPP para Compras

Módulo de sólo lectura sobre un puerto de entregas. No crea tablas ni modifica RRHH/EPP.

| Componente | Estado |
|---|---|
| Fuente de entregas | Proyección de sólo lectura de RRHH/EPP; conserva la marca si contiene ítems `SIM-*` |
| Precios | SIMULADOS/SIN DATOS; dueño Compras |
| Duración | Sólo entrega → reposición por rotura/desgaste. Estacional, baja, cambio de puesto o talle no cierran vida útil; no publica promedio con menos de `N` casos concluyentes |
| Reclamos | Proporción sobre entregas del mismo ítem, conteo absoluto y N visibles |
| Comparador | Sólo ítems del mismo elemento normativo y ambos con muestra suficiente |
| Costos | Vacíos mientras falte cualquier precio; nunca se presentan como cero |
| Exportación | Bloqueada si existen fuentes o ítems simulados |

Deuda: recibir precios de Compras y validar el valor operativo de `N`.
