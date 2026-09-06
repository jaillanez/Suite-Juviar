-- CV y extracción en la base local de la suite. Todo contenido personal se
-- cifra en la aplicación; sólo quedan visibles claves técnicas y estados.

CREATE SCHEMA IF NOT EXISTS seleccion;

CREATE TABLE IF NOT EXISTS seleccion.cv_original (
    id                  text PRIMARY KEY,
    origen              text NOT NULL,
    referencia_hmac     char(64) NOT NULL UNIQUE,
    referencia_cif      bytea NOT NULL,
    nombre_cif          bytea NOT NULL,
    contenido_cif       bytea NOT NULL,
    sha256              char(64) NOT NULL,
    recibido_en         timestamptz NOT NULL,
    incorporado_en      timestamptz NOT NULL,
    dueno_dato          text NOT NULL,
    fuente_simulada     boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS seleccion.extraccion_cv (
    id_original         text PRIMARY KEY REFERENCES seleccion.cv_original(id),
    datos_cif           bytea NOT NULL,
    extraido_en         timestamptz NOT NULL,
    estado              text NOT NULL
);

COMMENT ON SCHEMA seleccion IS 'Dueño funcional y de los datos: RRHH';
COMMENT ON TABLE seleccion.cv_original IS
    'Original inmutable cifrado. Dueño del dato: RRHH.';

