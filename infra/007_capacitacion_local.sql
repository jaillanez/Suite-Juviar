-- Persistencia local de capacitación. Legajo y nombre se cifran en aplicación.

CREATE SCHEMA IF NOT EXISTS capacitacion;

CREATE TABLE IF NOT EXISTS capacitacion.tema (
    id          text PRIMARY KEY,
    nombre      text NOT NULL,
    horas       numeric(8,2) NOT NULL CHECK (horas > 0),
    periodicidad_meses integer CHECK (periodicidad_meses > 0),
    dueno_dato  text NOT NULL DEFAULT 'RRHH'
);

CREATE TABLE IF NOT EXISTS capacitacion.dictado (
    id          text PRIMARY KEY,
    tema_id     text NOT NULL REFERENCES capacitacion.tema(id),
    fecha       date NOT NULL,
    instructor  text NOT NULL
    ,duracion_horas numeric(8,2) NOT NULL DEFAULT 1 CHECK (duracion_horas > 0)
    ,convocatoria_tipo text CHECK (convocatoria_tipo IN ('SECTOR','PUESTO','LISTA'))
    ,convocatoria_detalle text
    ,convocados_json jsonb NOT NULL DEFAULT '[]'::jsonb
);

ALTER TABLE capacitacion.tema ADD COLUMN IF NOT EXISTS periodicidad_meses integer CHECK (periodicidad_meses > 0);
ALTER TABLE capacitacion.dictado ADD COLUMN IF NOT EXISTS duracion_horas numeric(8,2) NOT NULL DEFAULT 1 CHECK (duracion_horas > 0);
ALTER TABLE capacitacion.dictado ADD COLUMN IF NOT EXISTS convocatoria_tipo text CHECK (convocatoria_tipo IN ('SECTOR','PUESTO','LISTA'));
ALTER TABLE capacitacion.dictado ADD COLUMN IF NOT EXISTS convocatoria_detalle text;
ALTER TABLE capacitacion.dictado ADD COLUMN IF NOT EXISTS convocados_json jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS capacitacion.asistencia (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dictado_id          text NOT NULL REFERENCES capacitacion.dictado(id),
    legajo_hmac         char(64) NOT NULL,
    legajo_cif          bytea NOT NULL,
    nombre_cif          bytea NOT NULL,
    supervisor          boolean NOT NULL,
    presente            boolean NOT NULL,
    firma_id            uuid,
    estado_firma        text NOT NULL,
    registrado_en       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dictado_id, legajo_hmac)
);

CREATE TABLE IF NOT EXISTS capacitacion.asistencia_anulacion (
    asistencia_id  bigint PRIMARY KEY REFERENCES capacitacion.asistencia(id),
    motivo         text NOT NULL,
    anulada_por_hmac char(64) NOT NULL,
    anulada_por_cif bytea NOT NULL,
    anulada_en     timestamptz NOT NULL
);

COMMENT ON SCHEMA capacitacion IS 'Dueño funcional y de maestros: RRHH';
COMMENT ON TABLE capacitacion.tema IS 'Maestro de temas. Dueño del dato: RRHH.';
