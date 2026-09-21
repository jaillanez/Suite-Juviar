-- Base de Suite: almacenamiento durable de la vista Oracle de Juviar-ENAV.
CREATE SCHEMA IF NOT EXISTS recepcion;

CREATE TABLE IF NOT EXISTS recepcion.descarga (
    id bigserial PRIMARY KEY,
    sede text NOT NULL,
    ciu text NOT NULL,
    id_origen text,
    nro_delegacion integer,
    fecha timestamp,
    nroinscripto text,
    razonsocial text,
    cuit text,
    clientecodigo text,
    clienterazonsocial text,
    clientecuit text,
    bruto bigint,
    tara bigint,
    neto bigint,
    codigotransporte text,
    modelo text,
    chofercode text,
    choferdescripcion text,
    codigovariedad text,
    descvariedad text,
    azucar numeric,
    tipocomercializacion text,
    observacion text,
    cosecha text,
    tipocosecha text,
    tipouva text,
    estado text NOT NULL CHECK (
        estado IN ('en_descarga', 'descargado', 'ausente_en_origen')
    ),
    huella_origen text NOT NULL,
    pendiente_publicar boolean NOT NULL DEFAULT true,
    primera_vez_visto timestamptz NOT NULL DEFAULT now(),
    ultima_vez_visto timestamptz NOT NULL DEFAULT now(),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_descarga_sede_ciu UNIQUE (sede, ciu)
);

CREATE INDEX IF NOT EXISTS ix_descarga_ventana ON recepcion.descarga (sede, fecha);
CREATE INDEX IF NOT EXISTS ix_descarga_productor
    ON recepcion.descarga (nroinscripto, fecha DESC);
CREATE INDEX IF NOT EXISTS ix_descarga_pendiente
    ON recepcion.descarga (id) WHERE pendiente_publicar;

CREATE TABLE IF NOT EXISTS recepcion.descarga_cambio (
    id bigserial PRIMARY KEY,
    descarga_id bigint NOT NULL REFERENCES recepcion.descarga (id),
    detectado_en timestamptz NOT NULL DEFAULT now(),
    huella_anterior text NOT NULL,
    huella_nueva text NOT NULL,
    valores_anteriores jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cambio_descarga
    ON recepcion.descarga_cambio (descarga_id);

CREATE TABLE IF NOT EXISTS recepcion.corrida (
    id bigserial PRIMARY KEY,
    sede text NOT NULL,
    modo text NOT NULL CHECK (modo IN ('ventana', 'nocturna', 'inicial')),
    ventana_desde timestamp NOT NULL,
    inicio timestamptz NOT NULL DEFAULT now(),
    fin timestamptz,
    leidas integer,
    nuevas integer,
    modificadas integer,
    ausentes integer,
    aviso text,
    error text
);
CREATE INDEX IF NOT EXISTS ix_corrida_sede_inicio
    ON recepcion.corrida (sede, inicio DESC);
