# ADR 0001 — Monolito modular en vez de microservicios

**Estado:** aceptado

**Contexto.** Siete módulos con un solo equipo de desarrollo, sedes conectadas
por VPN y un maestro de datos que vive fuera del sistema (Nexus, Santa Fe).

**Decisión.** Un backend desplegable, dividido internamente en módulos que no
se importan entre sí, con las fronteras verificadas por `import-linter` en CI.

**Consecuencias.** Se paga el costo de disciplina de los microservicios sin
pagar el costo operativo. Si un módulo necesita salir a un proceso propio más
adelante, ya tiene la frontera hecha. La excepción es el bot: la regla §4.3
(DMZ, sin acceso a la base de producción) no se puede cumplir dentro del
proceso, así que sale como segundo deployable desde el día uno.
