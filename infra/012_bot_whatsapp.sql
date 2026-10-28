-- Base DMZ: cola durable del bot y proyección teléfono-productor.
CREATE TABLE IF NOT EXISTS consulta.bot_entrada (
    id bigserial PRIMARY KEY,
    wamid text NOT NULL UNIQUE,
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    tipo text NOT NULL,
    texto text,
    enviado_en timestamptz,
    recibido_en timestamptz NOT NULL DEFAULT now(),
    estado text NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'tomado', 'respondido', 'ignorado', 'error')),
    tomado_en timestamptz,
    intentos integer NOT NULL DEFAULT 0 CHECK (intentos BETWEEN 0 AND 5),
    respuesta text,
    wamid_salida text,
    error text,
    procesado_en timestamptz
);
CREATE INDEX IF NOT EXISTS ix_bot_pendientes
    ON consulta.bot_entrada (recibido_en) WHERE estado IN ('pendiente', 'tomado');
CREATE INDEX IF NOT EXISTS ix_bot_telefono_hora
    ON consulta.bot_entrada (telefono, procesado_en) WHERE estado = 'respondido';

CREATE TABLE IF NOT EXISTS consulta.telefono_productor (
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    nroinscripto text NOT NULL,
    activo boolean NOT NULL DEFAULT true,
    PRIMARY KEY (telefono, nroinscripto)
);

DO $$ BEGIN CREATE ROLE consulta_webhook LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE consulta_bot LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

REVOKE ALL ON SCHEMA public FROM consulta_webhook, consulta_bot;
REVOKE ALL ON SCHEMA consulta FROM consulta_webhook, consulta_bot;
REVOKE ALL ON ALL TABLES IN SCHEMA consulta FROM consulta_webhook, consulta_bot;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA consulta FROM consulta_webhook, consulta_bot;

GRANT USAGE ON SCHEMA consulta TO consulta_webhook;
GRANT INSERT ON consulta.bot_entrada TO consulta_webhook;
GRANT USAGE ON SEQUENCE consulta.bot_entrada_id_seq TO consulta_webhook;

GRANT USAGE ON SCHEMA consulta TO consulta_bot;
GRANT SELECT, UPDATE ON consulta.bot_entrada TO consulta_bot;
GRANT SELECT ON consulta.telefono_productor, consulta.descarga_publica,
                consulta.sincronizacion TO consulta_bot;
GRANT INSERT ON consulta.bitacora_consulta TO consulta_bot;
GRANT USAGE ON SEQUENCE consulta.bitacora_consulta_id_seq TO consulta_bot;

GRANT SELECT, INSERT, UPDATE, DELETE ON consulta.telefono_productor TO consulta_publicador;
