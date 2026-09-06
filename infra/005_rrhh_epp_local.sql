-- Persistencia local de RRHH/EPP en PostgreSQL 18.6.
-- Ejecutar contra juviar_suite_local. Nexus no participa: sigue siendo una
-- fuente externa de legajos de solo lectura.

CREATE SCHEMA IF NOT EXISTS rrhh_epp;

CREATE TABLE IF NOT EXISTS rrhh_epp.entrega_epp (
    id                text PRIMARY KEY,
    legajo            text NOT NULL,
    fecha_entrega     date NOT NULL,
    usuario_deposito  text NOT NULL,
    circuito          text NOT NULL,
    motivo            text NOT NULL,
    observaciones     text NOT NULL DEFAULT '',
    firma_metodo      text NOT NULL,
    firma_evidencia   text NOT NULL,
    firma_sello       timestamptz NOT NULL,
    firma_simulada    boolean NOT NULL,
    cabecera_json     jsonb NOT NULL,
    lineas_json       jsonb NOT NULL,
    creado_en         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rrhh_epp_entrega_legajo
    ON rrhh_epp.entrega_epp (legajo);

CREATE TABLE IF NOT EXISTS rrhh_epp.constancia_original (
    id_entrega   text PRIMARY KEY REFERENCES rrhh_epp.entrega_epp(id),
    contenido    bytea NOT NULL,
    sha256       text NOT NULL,
    generado_en  timestamptz NOT NULL,
    firmado      boolean NOT NULL,
    simulado     boolean NOT NULL,
    version      integer NOT NULL DEFAULT 1,
    anula_a      text,
    entregas_json jsonb NOT NULL DEFAULT '[]'::jsonb
);

ALTER TABLE rrhh_epp.constancia_original
    ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS anula_a text,
    ADD COLUMN IF NOT EXISTS entregas_json jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS rrhh_epp.stock_item (
    item_codigo  text PRIMARY KEY,
    disponible   integer NOT NULL CHECK (disponible >= 0),
    minimo       integer NOT NULL CHECK (minimo >= 0),
    estado       text NOT NULL,
    dueno_dato   text NOT NULL
);

CREATE TABLE IF NOT EXISTS rrhh_epp.aviso_compras (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_codigo  text NOT NULL REFERENCES rrhh_epp.stock_item(item_codigo),
    disponible   integer NOT NULL,
    minimo       integer NOT NULL,
    creado_en    timestamptz NOT NULL DEFAULT now(),
    estado       text NOT NULL DEFAULT 'PENDIENTE'
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rrhh_epp_aviso_pendiente
    ON rrhh_epp.aviso_compras (item_codigo) WHERE estado = 'PENDIENTE';

CREATE TABLE IF NOT EXISTS rrhh_epp.bitacora (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    momento   timestamptz NOT NULL DEFAULT now(),
    evento    text NOT NULL,
    usuario   text NOT NULL,
    detalle   jsonb NOT NULL
);

COMMENT ON SCHEMA rrhh_epp IS
    'Dueño funcional: RRHH; stock y mínimos: Depósito; catálogo: Higiene y Seguridad';
COMMENT ON TABLE rrhh_epp.stock_item IS
    'Maestro operativo de existencias. Dueño del dato: Depósito.';
