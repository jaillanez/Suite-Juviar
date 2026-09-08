# Estado de ejecución — instrucciones del agente

Fecha de corte: 2026-09-07. Rama: `codex/rrhh-epp-unificado`.

Este documento distingue código construido de operación real. Ninguna fuente,
credencial, aprobación o dato corporativo faltante se reemplazó por una invención.

## Construido

| Ola / paso | Estado del código | Límite operativo visible |
|---|---|---|
| 0.1 Catálogo de dos niveles | CONSTRUIDO | Los 435 ítems `SIM-*` deben reemplazarse por el Excel de HyS. |
| 0.2 Constancia individual | CONSTRUIDO | PDF individual y versionado inmutable; firma digital real pendiente. |
| 0.3 Dos circuitos | CONSTRUIDO | Matriz y volumen diario siguen sin validación empresarial. |
| 0.4 Stock | CONSTRUIDO | Existencias/mínimos simulados; aviso informativo con consumo real de 30 días, episodio único, outbox y SMTP construidos. Configuración corporativa pendiente. |
| 0.5 Deuda de EPP | PARCIAL | PostgreSQL y offline construidos; identidad real y certificado de firma pendientes. |
| 1.1 Postulante | CONSTRUIDO | Vive en Terceros, con dueño RRHH; persistencia cifrada pendiente. |
| 1.2 Ingesta | BASE CONSTRUIDA | Originales cifrados en PostgreSQL; 20 a 30 CV por correo alcanzan para calibrar sin esperar la ruta Chimbas. |
| 1.3 Extracción | BASE CONSTRUIDA | Campos y fragmentos cifrados; OCR y validación con CV reales pendientes. |
| 1.4 Ranking | BASE CONSTRUIDA | Criterios y notificador simulados; perfil real de acceso RRHH pendiente. |
| 2 Capacitaciones | BASE CONSTRUIDA | Persistencia PostgreSQL cifrada; API/perfil real y motor con certificado pendientes. |
| 3 Analítica EPP | CONSTRUIDA CON ADAPTADORES | Sólo lectura; precios vacíos, muestra mínima configurable y exportación bloqueada con simulados. |
| 4 Legajo digital | CONSTRUIDO CON ADAPTADORES | Reutiliza el puerto de legajos; adjuntos cifrados en memoria de prueba, PostgreSQL pendiente. |
| 4 Salud | CONSTRUIDO CON ADAPTADORES | Rol médico, bitácora de lectura, catálogo muestra, reportes agregados y art. 208 preliminar. |
| 5 Turnos | CONSTRUIDO CON ADAPTADORES | Cronograma, conciliación, propuesta y aprobación construidos; Time confinado al adaptador pendiente. |
| Aplicación de gestión | ARMAZÓN OPERABLE | Next/React separado, menú por rol, empresa, marcas simuladas y conexión HTTP; faltan completar operaciones detalladas y los recorridos E2E de todos los pasos del plan. |

`apps/web` y `apps/consulta` no fueron modificados. Nexus continúa como fuente
externa de sólo lectura y ningún componente escribe en Nexus o Time.

La aplicación interna vive en `apps/gestion`. Selección y Capacitaciones ya
exponen una API de gestión en memoria para pruebas; no sustituyen la persistencia,
identidad ni fuentes corporativas pendientes.

El rechazo por ruta y el menú por perfil son únicamente UX mientras la identidad
sea declarada; no se consideran seguridad. La API deberá autorizar desde una
sesión real. El despliegue de Gestión se decidió como exportación estática, sin
Node persistente en producción (ADR 0004).

## Controles de prueba y de acceso

- La aplicación y cada constancia muestran `SIN VALIDEZ LEGAL` mientras la firma
  o las fuentes sean simuladas.
- Producción no arranca si faltan identidad real, firma empresarial, Nexus o si el
  catálogo conserva ítems `SIM-*`; fuera de `prueba` tampoco se registra una entrega
  simulada.
- Los roles PostgreSQL de EPP, Selección y Capacitación se aplican mediante
  `infra/008_roles_modulos_local.sql`. La verificación ejecuta consultas con esos
  roles y confirma tanto el permiso propio como los rechazos cruzados.
- Los README de los tres módulos conservan su tabla de deuda técnica actualizada.

## Límites de los adaptadores respetados

- **Ola 3 — Analítica EPP:** la lógica y pantalla existen, pero no publican
  promedios insuficientes, no convierten precios faltantes en cero y no exportan
  comparaciones simuladas como evidencia.
- **Ola 4 — Legajo y salud:** la lógica está separada desde el inicio. Nexus,
  catálogo médico, Identidad y persistencia real siguen confinados a adaptadores.
- **Ola 5 — Turnos:** el flujo existe sin nombres de campos supuestos. El adaptador
  real falla de forma explícita hasta recibir el diccionario contractual de Time.

## Decisiones o datos requeridos para continuar

1. Validación firmada de la matriz EPP y catálogo real de ítems por HyS.
2. Certificado empresarial, proveedor de sello de tiempo y visto del asesor legal.
   Iniciar el trámite durante la semana del 7 de septiembre de 2026.
3. Autenticador de `plataforma/identidad` y perfiles reales de RRHH/Capacitación/Salud.
4. Muestra de 20 a 30 CV por un canal seguro de RRHH antes de diciembre de 2026.
   La ruta de sólo lectura de Chimbas puede resolverse después de la calibración.
5. DSN/credenciales de sólo lectura de Nexus.
6. Diccionario de Time y protocolo de cambios de turno.
7. Canal a Compras: correo implementado con outbox durable y reintentos; falta
   configurar `SJ_COMPRAS_EMAIL`, host/remitente SMTP y credenciales del entorno.

El orden EPP → Selección → Capacitaciones → resto quedó confirmado en §6.2 de
la Base Común v0.4. La Base, el README fuente de EPP y el plan se conservan en
`Docs/` como fuentes canónicas para los pasos siguientes.
