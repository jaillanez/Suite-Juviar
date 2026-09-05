-- Base de la DMZ. NO es la base de la suite.
-- Se ejecuta con un rol que sólo tiene permisos sobre el esquema `web`.

CREATE SCHEMA IF NOT EXISTS web;

CREATE SEQUENCE IF NOT EXISTS web.seq_referencia_solicitud START 1;

-- Bandeja de entrada. apps/web sólo INSERTA acá.
CREATE TABLE IF NOT EXISTS web.bandeja_solicitudes (
    id              bigserial PRIMARY KEY,
    referencia      text        NOT NULL UNIQUE,
    recibido_en     timestamptz NOT NULL,
    ip_origen       inet,
    user_agent      text,
    idioma          text        NOT NULL DEFAULT 'es',
    carga           jsonb       NOT NULL,
    estado          text        NOT NULL DEFAULT 'pendiente'
                    CHECK (estado IN ('pendiente', 'tomada', 'procesada', 'descartada')),
    tomada_en       timestamptz,
    procesada_en    timestamptz,
    error           text
);

CREATE INDEX IF NOT EXISTS ix_bandeja_pendientes
    ON web.bandeja_solicitudes (recibido_en)
    WHERE estado = 'pendiente';

-- Copia de catálogos, replicada desde plataforma/parametria por el worker.
CREATE TABLE IF NOT EXISTS web.catalogo (
    tipo        text    NOT NULL CHECK (tipo IN ('linea_producto', 'formato_despacho', 'certificacion')),
    codigo      text    NOT NULL,
    nombre_es   text    NOT NULL,
    nombre_en   text    NOT NULL,
    orden       integer NOT NULL DEFAULT 0,
    vigente     boolean NOT NULL DEFAULT true,
    PRIMARY KEY (tipo, codigo)
);

-- Permisos: el usuario del sitio inserta solicitudes y lee catálogos. Nada más.
DO $$
BEGIN
    CREATE ROLE web_sitio LOGIN;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;
GRANT USAGE ON SCHEMA web TO web_sitio;
GRANT INSERT ON web.bandeja_solicitudes TO web_sitio;
GRANT USAGE ON SEQUENCE web.seq_referencia_solicitud TO web_sitio;
GRANT USAGE, SELECT ON SEQUENCE web.bandeja_solicitudes_id_seq TO web_sitio;
GRANT SELECT ON web.catalogo TO web_sitio;
-- Deliberadamente NO se otorga SELECT sobre bandeja_solicitudes:
-- si el sitio pudiera leerla, un lead vería los de los demás.

-- El worker interno usa otro rol, con lectura y actualización de estado.
DO $$
BEGIN
    CREATE ROLE web_worker LOGIN;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;
GRANT USAGE ON SCHEMA web TO web_worker;
GRANT SELECT, UPDATE ON web.bandeja_solicitudes TO web_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON web.catalogo TO web_worker;
