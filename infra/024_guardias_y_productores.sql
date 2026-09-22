-- DMZ: identidad de guardias y copia mínima para el buscador autenticado.
CREATE TABLE IF NOT EXISTS fila.guardia (
    usuario text PRIMARY KEY CHECK (usuario ~ '^[a-z0-9._-]{3,30}$'),
    nombre text NOT NULL,
    sede text NOT NULL,
    clave_hash text NOT NULL,
    activo boolean NOT NULL DEFAULT true,
    debe_cambiar_clave boolean NOT NULL DEFAULT true,
    creado_por text NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    ultimo_ingreso timestamptz
);
CREATE TABLE IF NOT EXISTS fila.sesion_guardia (
    token_hash text PRIMARY KEY,
    usuario text NOT NULL REFERENCES fila.guardia(usuario),
    sede text NOT NULL,
    creada_en timestamptz NOT NULL DEFAULT now(),
    vence timestamptz NOT NULL,
    cerrada_en timestamptz
);
CREATE INDEX IF NOT EXISTS ix_sesion_vigente ON fila.sesion_guardia(usuario)
    WHERE cerrada_en IS NULL;
CREATE TABLE IF NOT EXISTS fila.intento_ingreso (
    id bigserial PRIMARY KEY,
    usuario text NOT NULL,
    exito boolean NOT NULL,
    ip inet,
    momento timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_intento_usuario ON fila.intento_ingreso(usuario,momento);
CREATE TABLE IF NOT EXISTS fila.productor (
    clientecuit text PRIMARY KEY,
    razonsocial text NOT NULL,
    busqueda text NOT NULL,
    codigos text[] NOT NULL DEFAULT '{}',
    ultima_entrega date,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_productor_busqueda ON fila.productor USING gin
    (string_to_array(busqueda,' '));
CREATE INDEX IF NOT EXISTS ix_productor_reciente
    ON fila.productor(ultima_entrega DESC NULLS LAST);
ALTER TABLE fila.viaje ADD COLUMN IF NOT EXISTS productor_revision_manual boolean NOT NULL DEFAULT false;

GRANT SELECT,UPDATE ON fila.guardia TO fila_guardia;
GRANT SELECT,INSERT,UPDATE ON fila.sesion_guardia TO fila_guardia;
GRANT INSERT,SELECT ON fila.intento_ingreso TO fila_guardia;
GRANT USAGE,SELECT ON SEQUENCE fila.intento_ingreso_id_seq TO fila_guardia;
GRANT SELECT ON fila.productor TO fila_guardia;

DO $$ BEGIN CREATE ROLE fila_publicador LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
REVOKE ALL ON SCHEMA public FROM fila_publicador;
GRANT USAGE ON SCHEMA fila TO fila_publicador;
GRANT SELECT,INSERT,UPDATE,DELETE ON fila.productor TO fila_publicador;
GRANT SELECT,INSERT,UPDATE ON fila.guardia TO fila_publicador;
GRANT USAGE ON SCHEMA fila TO consulta_publicador;
GRANT SELECT,INSERT,UPDATE,DELETE ON fila.productor TO consulta_publicador;
GRANT SELECT,INSERT,UPDATE ON fila.guardia,fila.sesion_guardia TO consulta_publicador;
-- fila_publico queda deliberadamente sin permiso sobre fila.productor.
