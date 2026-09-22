-- SUITE: revisión y resolución de teléfonos no vinculados.
CREATE TABLE IF NOT EXISTS terceros.contacto_pendiente (
    id bigserial PRIMARY KEY,
    telefono_crudo text NOT NULL,
    telefono text,
    nombre_excel text NOT NULL,
    sucursal text,
    motivo text NOT NULL CHECK (motivo IN ('sin_coincidencia','ambiguo','telefono_invalido')),
    candidatos jsonb NOT NULL DEFAULT '[]',
    estado text NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente','resuelto','descartado')),
    resuelto_por text,
    resuelto_en timestamptz,
    clientecuit text,
    nota text,
    cargado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pendiente_estado
    ON terceros.contacto_pendiente(estado,id);
GRANT SELECT,INSERT,UPDATE ON terceros.contacto_pendiente TO terceros_gestor;
GRANT USAGE,SELECT ON SEQUENCE terceros.contacto_pendiente_id_seq TO terceros_gestor;

CREATE TABLE IF NOT EXISTS terceros.productor_publicacion (
    clientecuit text PRIMARY KEY,
    razonsocial text NOT NULL,
    busqueda text NOT NULL,
    codigos text[] NOT NULL DEFAULT '{}',
    ultima_entrega date,
    version bigint NOT NULL DEFAULT 1,
    pendiente_desde timestamptz NOT NULL DEFAULT now(),
    publicado_en timestamptz,
    intentos integer NOT NULL DEFAULT 0,
    ultimo_error text
);
GRANT SELECT,INSERT,UPDATE,DELETE ON terceros.productor_publicacion TO terceros_gestor;
GRANT SELECT,INSERT,UPDATE,DELETE ON terceros.productor_publicacion TO contactos_publicador_suite;
GRANT USAGE ON SCHEMA recepcion TO contactos_publicador_suite;
GRANT SELECT ON recepcion.descarga TO contactos_publicador_suite;
