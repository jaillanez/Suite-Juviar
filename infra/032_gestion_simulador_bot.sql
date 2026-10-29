-- DMZ: el simulador del bot dentro de Gestión lee lo que el bot respondió en modo simulado.
-- Sólo esa tabla (la API filtra además por los teléfonos de prueba). Sin acceso a los
-- teléfonos reales de productores. Se aplica antes de instalar el código. Idempotente.

GRANT USAGE ON SCHEMA consulta TO gestion_tablero;
GRANT SELECT ON consulta.bot_salida_simulada TO gestion_tablero;
