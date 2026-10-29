-- DMZ: el simulador del bot dentro de Gestión lee lo que el bot respondió en modo simulado
-- y la lista de teléfonos registrados para elegir con cuál probar. Sólo lectura.
-- Se aplica antes de instalar el código. Idempotente.

GRANT USAGE ON SCHEMA consulta TO gestion_tablero;
GRANT SELECT ON consulta.bot_salida_simulada, consulta.telefono_productor TO gestion_tablero;
