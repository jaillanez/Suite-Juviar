-- DMZ: salida durable del transporte simulado y rol de lectura del simulador.
CREATE TABLE IF NOT EXISTS consulta.bot_salida_simulada (
    id bigserial PRIMARY KEY,
    telefono text NOT NULL,
    texto text NOT NULL,
    wamid_salida text NOT NULL UNIQUE,
    creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_simulada_telefono
    ON consulta.bot_salida_simulada (telefono, id);

GRANT INSERT ON consulta.bot_salida_simulada TO consulta_bot;
GRANT USAGE ON SEQUENCE consulta.bot_salida_simulada_id_seq TO consulta_bot;

DO $$ BEGIN CREATE ROLE consulta_simulador LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
REVOKE ALL ON SCHEMA public FROM consulta_simulador;
REVOKE ALL ON SCHEMA consulta FROM consulta_simulador;
REVOKE ALL ON ALL TABLES IN SCHEMA consulta FROM consulta_simulador;
GRANT USAGE ON SCHEMA consulta TO consulta_simulador;
GRANT SELECT ON consulta.bot_salida_simulada, consulta.telefono_productor
    TO consulta_simulador;
