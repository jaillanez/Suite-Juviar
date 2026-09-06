# Estado de ejecución — instrucciones del agente

Fecha de corte: 2026-09-06. Rama: `codex/rrhh-epp-unificado`.

Este documento distingue código construido de operación real. Ninguna fuente,
credencial, aprobación o dato corporativo faltante se reemplazó por una invención.

## Construido

| Ola / paso | Estado del código | Límite operativo visible |
|---|---|---|
| 0.1 Catálogo de dos niveles | CONSTRUIDO | Los 435 ítems `SIM-*` deben reemplazarse por el Excel de HyS. |
| 0.2 Constancia individual | PARCIAL | PDF individual e inmutable construido; firma digital real y versionado de reposiciones pendientes. |
| 0.3 Dos circuitos | CONSTRUIDO | Matriz y volumen diario siguen sin validación empresarial. |
| 0.4 Stock | CONSTRUIDO | Existencias/mínimos simulados; canal corporativo a Compras pendiente. |
| 0.5 Deuda de EPP | PARCIAL | PostgreSQL y offline construidos; identidad real y certificado de firma pendientes. |
| 1.1 Postulante | CONSTRUIDO | Vive en Terceros, con dueño RRHH; persistencia cifrada pendiente. |
| 1.2 Ingesta | BASE CONSTRUIDA | Ruta Chimbas y credenciales de correo pendientes; originales aún sin repositorio durable. |
| 1.3 Extracción | BASE CONSTRUIDA | Reglas marcadas simuladas; OCR y validación con CV reales pendientes. |
| 1.4 Ranking | BASE CONSTRUIDA | Criterios y notificador simulados; perfil real de acceso RRHH pendiente. |
| 2 Capacitaciones | BASE CONSTRUIDA | Persistencia/API/perfil real y motor de firma con certificado pendientes. |

`apps/web` y `apps/consulta` no fueron modificados. Nexus continúa como fuente
externa de sólo lectura y ningún componente escribe en Nexus o Time.

## Condiciones de no inicio respetadas

- **Ola 3 — Analítica EPP:** no se crea el módulo hasta acumular tres meses de
  entregas reales. Hoy sólo hay datos simulados, por lo que cualquier comparación
  de proveedores sería ficticia.
- **Ola 4 — Legajo y salud:** no se crea el módulo hasta contar con conexión real
  a Nexus, definición de perfiles para datos sensibles y criterios del aviso del
  artículo 208. El DSN y las credenciales no fueron suministrados.
- **Ola 5 — Turnos:** no se escribe ningún adaptador sobre tablas supuestas. Faltan
  el diccionario de Time y el protocolo mínimo de reporte de cambios de turno.

## Decisiones o datos requeridos para continuar

1. Validación firmada de la matriz EPP y catálogo real de ítems por HyS.
2. Certificado empresarial, proveedor de sello de tiempo y visto del asesor legal.
3. Autenticador de `plataforma/identidad` y perfiles reales de RRHH/Capacitación/Salud.
4. Ruta de sólo lectura de Chimbas y cuenta de la bandeja de CV.
5. DSN/credenciales de sólo lectura de Nexus.
6. Diccionario de Time y protocolo de cambios de turno.
7. Confirmación del orden EPP → Selección → Capacitaciones → resto.

La Base Común v0.4 y los otros dos documentos que estas instrucciones declaran
como lectura conjunta no están presentes en el repositorio ni en los archivos
entregados. Por eso no se modificó §6.2 ni se reconstruyeron decisiones ausentes.

