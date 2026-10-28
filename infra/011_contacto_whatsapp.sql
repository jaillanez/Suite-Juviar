-- Base Suite: vínculo administrado entre un WhatsApp y un productor externo.
CREATE SCHEMA IF NOT EXISTS terceros;

CREATE TABLE IF NOT EXISTS terceros.contacto_whatsapp (
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    nroinscripto text NOT NULL CHECK (length(btrim(nroinscripto)) BETWEEN 1 AND 40),
    activo boolean NOT NULL DEFAULT true,
    origen text NOT NULL CHECK (origen IN ('importacion_inicial', 'alta_manual')),
    alta_por text NOT NULL CHECK (length(btrim(alta_por)) > 0),
    alta_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (telefono, nroinscripto)
);

GRANT USAGE ON SCHEMA terceros TO recepcion_worker;
GRANT SELECT ON terceros.contacto_whatsapp TO recepcion_worker;
