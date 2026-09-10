# Estado de ejecución — instrucciones del agente

Fecha de corte: 2026-09-10. Rama: `codex/rrhh-epp-unificado`.

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
| Aplicación de gestión — Bloques 2 a 5 | COMPLETA CON ADAPTADORES | Las seis olas tienen pantalla operable; autorización efectiva en API y E2E por bloque. Identidad corporativa y datos reales siguen pendientes. |

`apps/web` y `apps/consulta` no fueron modificados. Nexus continúa como fuente
externa de sólo lectura y ningún componente escribe en Nexus o Time.

La aplicación interna vive en `apps/gestion`. Selección, Capacitaciones, Legajo y
Salud exponen una API de gestión en memoria para pruebas; no sustituyen la
persistencia, identidad ni fuentes corporativas pendientes. En Salud, la bitácora
es inmutable, no registra diagnósticos, y el cálculo preliminar del artículo 208
no admite impresión ni exportación.

El menú por perfil es únicamente UX. El rechazo efectivo ya lo realiza la API con
permisos declarados por ruta; `resolver_sesion()` mantiene aislada la identidad
simulada y producción no arranca sin proveedor real. El despliegue de Gestión se
decidió como exportación estática, sin Node persistente en producción (ADR 0004).

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
- Una prueba recorre las rutas reales, incluidas subaplicaciones montadas, y falla
  si alguna carece de permiso. Los E2E de los Bloques 2, 3 y 4 se ejecutan con
  `pnpm --filter @suite-juviar/gestion test:e2e` y servicios locales aislados.

## Límites de los adaptadores respetados

- **Ola 3 — Analítica EPP:** la lógica y pantalla existen, pero no publican
  promedios insuficientes, no convierten precios faltantes en cero y no exportan
  comparaciones simuladas como evidencia.
- **Ola 4 — Legajo y salud:** la lógica está separada desde el inicio. Nexus,
  catálogo médico, Identidad y persistencia real siguen confinados a adaptadores.
- **Ola 5 — Turnos:** el flujo existe sin nombres de campos supuestos. El adaptador
  real falla de forma explícita hasta recibir el diccionario contractual de Time.
  El cronograma no reescribe días cerrados: versiona cambios tardíos con fecha de
  conocimiento. Las propuestas nunca se autoimputan, RRHH las resuelve en lote y
  la bandeja simulada sólo genera un archivo local.

## Llaves de la empresa que destraban la operación real

1. **Catálogo y matriz EPP firmada por HyS:** reemplaza los `SIM-*`, habilita la
   asignación real por puesto y permite limpiar las entregas de demostración.
2. **Certificado empresarial, sello de tiempo y visto legal:** habilita constancias
   con validez probatoria; el trámite externo continúa siendo crítico por su plazo.
3. **Identidad y perfiles corporativos:** reemplaza el selector simulado y vincula
   permisos, actores y sectores del supervisor con usuarios reales.
4. **Precios de Compras:** habilita impacto económico y comparaciones monetarias
   sin convertir datos faltantes en cero.
5. **Nexus de sólo lectura:** aporta legajos, antigüedad y cargas familiares reales;
   vuelve definitivo el aviso del artículo 208.
6. **Diccionario contractual de Time y protocolo de cambios:** permite leer fichadas
   reales y definir el archivo de intercambio sin contaminar dominio ni pantallas.

Además hace falta la **instancia PostgreSQL definitiva con claves administradas**:
destraba persistencia productiva de Legajo, Salud, Selección, Capacitaciones y
Turnos. Hasta entonces no se cargan certificados médicos ni documentación real.

Dependencias operativas ya construidas: el aviso a Compras usa outbox durable y
reintentos, pero faltan casilla y credenciales SMTP. La muestra segura de 20 a 30
CV sigue requerida antes de diciembre de 2026 para calibrar extracción y ranking.

El orden EPP → Selección → Capacitaciones → resto quedó confirmado en §6.2 de
la Base Común v0.4. La Base, el README fuente de EPP y el plan se conservan en
`Docs/` como fuentes canónicas para los pasos siguientes.
