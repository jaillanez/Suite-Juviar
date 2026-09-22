-- Suite: habilita vínculos identificables y eliminables del simulador.
ALTER TABLE terceros.contacto_whatsapp
    DROP CONSTRAINT IF EXISTS contacto_whatsapp_origen_check;
ALTER TABLE terceros.contacto_whatsapp
    ADD CONSTRAINT contacto_whatsapp_origen_check
    CHECK (origen IN ('importacion_inicial', 'alta_manual', 'prueba'));

DO $$ BEGIN CREATE ROLE terceros_gestor LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
REVOKE ALL ON SCHEMA public FROM terceros_gestor;
GRANT USAGE ON SCHEMA terceros, recepcion TO terceros_gestor;
GRANT SELECT, INSERT, UPDATE, DELETE ON terceros.contacto_whatsapp TO terceros_gestor;
GRANT SELECT ON recepcion.descarga TO terceros_gestor;
