-- La bitácora es inmutable a nivel del motor, no por disciplina del código.
-- Aunque alguien escriba SQL crudo con el rol de la aplicación, PostgreSQL lo
-- rechaza. Corregir un asiento es imposible; solo se puede agregar otro.

\connect suite_juviar

REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA bitacora FROM sj_app;

ALTER DEFAULT PRIVILEGES FOR ROLE sj_owner IN SCHEMA bitacora
  REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM sj_app;

ALTER DEFAULT PRIVILEGES FOR ROLE sj_owner IN SCHEMA bitacora
  GRANT SELECT, INSERT ON TABLES TO sj_app;

-- Refuerzo: mismo criterio para los documentos firmados. Un PDF con firma
-- re-guardado pierde validez, así que tampoco se actualiza.
REVOKE UPDATE, DELETE ON plataforma.documento_firmado FROM sj_app;
