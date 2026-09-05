-- Esquema mínimo de la suite, sólo lo que toca la ingesta. Si el repo ya
-- tiene la migración real de comercial, usar esa y borrar este archivo.
CREATE SCHEMA IF NOT EXISTS comercial;

CREATE TABLE IF NOT EXISTS comercial.solicitud_muestra (
    referencia        text PRIMARY KEY,
    tercero_id        bigint,
    linea_producto    text        NOT NULL,
    volumen_anual_t   numeric,
    formato_despacho  text        NOT NULL,
    especificacion    jsonb       NOT NULL,
    certificaciones   text[]      NOT NULL DEFAULT '{}',
    idioma            text        NOT NULL DEFAULT 'es',
    recibido_en       timestamptz NOT NULL,
    planta_asignada   text,
    sitio_asignado    text,
    creado_en         timestamptz NOT NULL DEFAULT now()
);
