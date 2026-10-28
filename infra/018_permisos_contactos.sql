-- Suite: tareas, invitaciones y auditoría de contactos del productor.
ALTER TABLE terceros.contacto_whatsapp
    ADD COLUMN IF NOT EXISTS tareas text[] NOT NULL DEFAULT '{ver_informes}',
    ADD COLUMN IF NOT EXISTS importado_en timestamptz;

ALTER TABLE terceros.contacto_whatsapp DROP CONSTRAINT IF EXISTS ck_contacto_tareas;
ALTER TABLE terceros.contacto_whatsapp ADD CONSTRAINT ck_contacto_tareas CHECK (
    cardinality(tareas) > 0
    AND tareas <@ ARRAY['ver_informes','pedir_turnos','administrar_contactos']
);

ALTER TABLE terceros.contacto_whatsapp
    DROP CONSTRAINT IF EXISTS contacto_whatsapp_origen_check;

UPDATE terceros.contacto_whatsapp
   SET tareas = ARRAY['ver_informes','pedir_turnos','administrar_contactos'],
       importado_en = COALESCE(importado_en, alta_en),
       origen = 'importacion_bodega'
 WHERE origen = 'importacion_inicial';

ALTER TABLE terceros.contacto_whatsapp
    ADD CONSTRAINT contacto_whatsapp_origen_check
    CHECK (origen IN ('importacion_bodega', 'alta_manual', 'prueba', 'invitacion'));

CREATE TABLE IF NOT EXISTS terceros.invitacion_contacto (
    id bigserial PRIMARY KEY,
    clientecuit text NOT NULL,
    telefono_invitado text NOT NULL CHECK (telefono_invitado ~ '^[0-9]{8,20}$'),
    codigo_hash text NOT NULL,
    tareas text[] NOT NULL DEFAULT '{ver_informes}',
    invitado_por text NOT NULL,
    creada_en timestamptz NOT NULL DEFAULT now(),
    intentos integer NOT NULL DEFAULT 0 CHECK (intentos BETWEEN 0 AND 3),
    estado text NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente','consumida','anulada','vencida')),
    cerrada_en timestamptz,
    CHECK (cardinality(tareas) > 0),
    CHECK (tareas <@ ARRAY['ver_informes','pedir_turnos']),
    CHECK (NOT ('administrar_contactos' = ANY (tareas)))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_invitacion_viva
    ON terceros.invitacion_contacto (clientecuit, telefono_invitado)
    WHERE estado = 'pendiente';

CREATE TABLE IF NOT EXISTS terceros.contacto_evento (
    id bigserial PRIMARY KEY,
    clientecuit text NOT NULL,
    telefono text NOT NULL,
    tipo text NOT NULL CHECK (tipo IN (
        'importacion_bodega','invitado','validado','intento_fallido',
        'invitacion_anulada','permisos_cambiados','baja','reemplazo_administrador'
    )),
    actor text NOT NULL,
    antes text[],
    despues text[],
    detalle jsonb,
    momento timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_contacto_evento_cuit
    ON terceros.contacto_evento (clientecuit, momento DESC);

INSERT INTO terceros.contacto_evento
       (clientecuit, telefono, tipo, actor, despues, detalle, momento)
SELECT c.clientecuit, c.telefono, 'importacion_bodega', c.alta_por, c.tareas,
       jsonb_build_object('origen', 'importacion de la bodega'), c.alta_en
FROM terceros.contacto_whatsapp c
WHERE c.origen = 'importacion_bodega'
  AND NOT EXISTS (
      SELECT 1 FROM terceros.contacto_evento e
      WHERE e.clientecuit = c.clientecuit AND e.telefono = c.telefono
        AND e.tipo = 'importacion_bodega'
  );

GRANT SELECT, INSERT, UPDATE ON terceros.invitacion_contacto,
    terceros.contacto_evento TO terceros_gestor;
GRANT USAGE ON SEQUENCE terceros.invitacion_contacto_id_seq,
    terceros.contacto_evento_id_seq TO terceros_gestor;
