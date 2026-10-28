-- Suite: publicación durable de cambios de contactos hacia la DMZ.
CREATE TABLE IF NOT EXISTS terceros.contacto_publicacion (
    telefono text NOT NULL,
    clientecuit text NOT NULL,
    activo boolean NOT NULL,
    tareas text[] NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    pendiente_desde timestamptz NOT NULL DEFAULT now(),
    publicado_en timestamptz,
    intentos integer NOT NULL DEFAULT 0,
    ultimo_error text,
    PRIMARY KEY (telefono, clientecuit)
);

DO $$ BEGIN CREATE ROLE contactos_publicador_suite LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

GRANT USAGE ON SCHEMA terceros TO contactos_publicador_suite;
GRANT SELECT, INSERT, UPDATE ON terceros.contacto_publicacion TO terceros_gestor;
GRANT SELECT, UPDATE ON terceros.contacto_publicacion TO contactos_publicador_suite;
