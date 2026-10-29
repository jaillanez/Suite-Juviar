-- DMZ: Gestión muestra las conversaciones con el bot (mensaje recibido + respuesta).
-- Sólo lectura y sólo las columnas que se muestran; el nombre sale de los contactos
-- registrados. Se aplica antes de instalar el código. Idempotente.

GRANT USAGE ON SCHEMA consulta, fila TO gestion_tablero;
GRANT SELECT (id, telefono, tipo, texto, recibido_en, estado, respuesta, procesado_en)
    ON consulta.bot_entrada TO gestion_tablero;
GRANT SELECT (telefono, clientecuit, activo) ON consulta.telefono_productor TO gestion_tablero;
