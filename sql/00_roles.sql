-- Dos roles. Uno migra y es dueño del esquema; el otro corre la aplicación y
-- no puede crear ni alterar tablas. Las credenciales del dueño no viven en el
-- entorno de la app.

CREATE ROLE sj_owner LOGIN PASSWORD :'owner_password';
CREATE ROLE sj_app   LOGIN PASSWORD :'app_password';

CREATE DATABASE suite_juviar OWNER sj_owner;
\connect suite_juviar

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- El rol de aplicación nunca crea objetos.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE suite_juviar FROM PUBLIC;
GRANT CONNECT ON DATABASE suite_juviar TO sj_app;

DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['plataforma','bitacora','turnos','rrhh_epp','cosecha','recepcion','ddjj','lectura']
  LOOP
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION sj_owner', s);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO sj_app', s);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE sj_owner IN SCHEMA %I '
      'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sj_app', s);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE sj_owner IN SCHEMA %I '
      'GRANT USAGE, SELECT ON SEQUENCES TO sj_app', s);
  END LOOP;
END $$;
