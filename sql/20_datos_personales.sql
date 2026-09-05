-- Patrón de dos columnas para todo dato personal.
-- El índice único va sobre el HMAC; el valor viaja cifrado. La clave del HMAC
-- vive fuera de la base, inyectada por el orquestador.
--
-- Ejemplo aplicado al registro de terceros:

\connect suite_juviar

-- ALTER TABLE plataforma.chofer
--   ADD COLUMN dni_hmac  char(64) NOT NULL,
--   ADD COLUMN dni_cif   bytea    NOT NULL;
-- CREATE UNIQUE INDEX ix_chofer_dni_hmac ON plataforma.chofer (dni_hmac);
--
-- Regla: ninguna tabla guarda un DNI o CUIT en claro. Si aparece una columna
-- `dni text`, es un bug de esquema, no una decisión de conveniencia.
