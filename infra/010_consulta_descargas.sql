-- Base DMZ: proyección mínima expuesta a la API de Consulta.
CREATE SCHEMA IF NOT EXISTS consulta;

CREATE TABLE IF NOT EXISTS consulta.descarga_publica (
    sede text NOT NULL,
    ciu text NOT NULL,
    id_origen text NOT NULL,
    fecha timestamp,
    nroinscripto text,
    neto bigint,
    variedad text,
    azucar numeric,
    estado text NOT NULL,
    actualizado_en timestamptz NOT NULL,
    PRIMARY KEY (sede, ciu, id_origen)
);
CREATE INDEX IF NOT EXISTS ix_publica_productor
    ON consulta.descarga_publica (nroinscripto, fecha DESC);

CREATE TABLE IF NOT EXISTS consulta.sincronizacion (
    sede text PRIMARY KEY,
    ultima_ok timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS consulta.bitacora_consulta (
    id bigserial PRIMARY KEY,
    momento timestamptz NOT NULL DEFAULT now(),
    cliente text NOT NULL,
    nroinscripto text NOT NULL,
    recurso text NOT NULL,
    filas integer NOT NULL,
    ip_origen inet
);

DO $$ BEGIN CREATE ROLE consulta_publicador LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE consulta_lector LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM consulta_publicador, consulta_lector;
GRANT USAGE ON SCHEMA consulta TO consulta_publicador;
GRANT SELECT, INSERT, UPDATE ON consulta.descarga_publica TO consulta_publicador;
GRANT SELECT, INSERT, UPDATE ON consulta.sincronizacion TO consulta_publicador;
GRANT USAGE ON SCHEMA consulta TO consulta_lector;
GRANT SELECT ON consulta.descarga_publica, consulta.sincronizacion TO consulta_lector;
GRANT INSERT ON consulta.bitacora_consulta TO consulta_lector;
GRANT USAGE ON SEQUENCE consulta.bitacora_consulta_id_seq TO consulta_lector;
