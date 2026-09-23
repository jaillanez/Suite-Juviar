-- DMZ: estado del diálogo y archivos temporales del bot.

CREATE TABLE IF NOT EXISTS consulta.bot_sesion (
    telefono      text PRIMARY KEY,
    paso          text        NOT NULL DEFAULT 'menu',
    clientecuit   text,
    pedido        text,
    actualizado   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS consulta.bot_archivo (
    token       text PRIMARY KEY,
    extension   text        NOT NULL CHECK (extension IN ('png','pdf')),
    nombre      text        NOT NULL,
    contenido   bytea       NOT NULL,
    telefono    text        NOT NULL,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    vence       timestamptz NOT NULL,
    descargas   integer     NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_archivo_vence ON consulta.bot_archivo (vence);

-- El rol del bot crea archivos y sesiones; el que los sirve SÓLO lee por token
-- y no puede listar la tabla entera.
GRANT SELECT, INSERT, UPDATE, DELETE ON consulta.bot_sesion TO consulta_bot;
GRANT SELECT, INSERT, DELETE ON consulta.bot_archivo TO consulta_bot;

DO $$ BEGIN CREATE ROLE consulta_archivos LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
REVOKE ALL ON SCHEMA public FROM consulta_archivos;
GRANT USAGE ON SCHEMA consulta TO consulta_archivos;

CREATE OR REPLACE FUNCTION consulta.leer_archivo(p_token text)
RETURNS TABLE(extension text, nombre text, contenido bytea)
LANGUAGE sql SECURITY DEFINER SET search_path = consulta, pg_temp AS $$
    UPDATE consulta.bot_archivo SET descargas = descargas + 1
    WHERE token = p_token AND vence > now()
    RETURNING extension, nombre, contenido;
$$;
REVOKE ALL ON FUNCTION consulta.leer_archivo(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consulta.leer_archivo(text) TO consulta_archivos;
GRANT USAGE ON SCHEMA fila TO consulta_bot;
GRANT SELECT ON fila.productor TO consulta_bot;
