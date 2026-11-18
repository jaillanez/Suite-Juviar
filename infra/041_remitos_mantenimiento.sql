-- DMZ: remitos de salida de equipos y herramientas, y mensajes de WhatsApp de mantenimiento.
--
-- Reunión del 15-11, punto 5:
--   * Nada sale de la planta sin un remito autorizado por el Encargado de Mantenimiento.
--     Gestión publica acá el remito ya firmado; la guardia de esa bodega lo ve en su consola
--     y marca la salida. Gestión lee la salida y pasa los equipos a «en taller».
--   * El personal de mantenimiento manda foto y texto por WhatsApp; el bot lo deja acá y
--     Gestión lo toma (como borrador o directo, según Parámetros).
--
-- Gestión y el bot no escriben las tablas: usan las funciones de abajo, que validan y dejan
-- quién hizo cada cosa. Se aplica antes de instalar el código. Es idempotente.

CREATE TABLE IF NOT EXISTS fila.remito_salida (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f-]{36}$'),
    numero integer NOT NULL UNIQUE CHECK (numero > 0),
    sede text NOT NULL CHECK (sede ~ '^[a-z0-9_-]{2,30}$'),
    destino text NOT NULL CHECK (length(btrim(destino)) BETWEEN 1 AND 120),
    motivo text NOT NULL CHECK (length(btrim(motivo)) BETWEEN 1 AND 300),
    items jsonb NOT NULL CHECK (jsonb_typeof(items) = 'array' AND jsonb_array_length(items) BETWEEN 1 AND 50),
    firma text NOT NULL CHECK (firma IN ('celular', 'papel')),
    autorizado_por text NOT NULL,
    autorizado_en timestamptz NOT NULL DEFAULT now(),
    anulado_en timestamptz,
    anulado_por text,
    salio_en timestamptz,
    salio_por text,
    CHECK ((salio_en IS NULL) = (salio_por IS NULL)),
    CHECK (anulado_en IS NULL OR salio_en IS NULL)
);
CREATE INDEX IF NOT EXISTS ix_remito_por_salir ON fila.remito_salida (sede)
    WHERE salio_en IS NULL AND anulado_en IS NULL;

CREATE TABLE IF NOT EXISTS fila.mensaje_mantenimiento (
    id bigserial PRIMARY KEY,
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    nombre text NOT NULL,
    texto text NOT NULL DEFAULT '' CHECK (length(texto) <= 1000),
    foto bytea CHECK (foto IS NULL OR octet_length(foto) BETWEEN 1000 AND 3000000),
    foto_tipo text CHECK (foto_tipo IS NULL OR foto_tipo IN ('image/jpeg', 'image/png', 'image/webp')),
    recibido_en timestamptz NOT NULL DEFAULT now(),
    tomado_en timestamptz,
    CHECK (foto IS NOT NULL OR length(btrim(texto)) > 0)
);
CREATE INDEX IF NOT EXISTS ix_mensaje_mantenimiento_pendiente ON fila.mensaje_mantenimiento (id)
    WHERE tomado_en IS NULL;

-- Gestión: publica un remito firmado. Mientras no salió, volver a publicarlo lo actualiza.
CREATE OR REPLACE FUNCTION fila.publicar_remito(
    p_id text, p_numero integer, p_sede text, p_destino text, p_motivo text, p_items jsonb,
    p_firma text, p_autorizado_por text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.remito_salida;
BEGIN
    IF p_autorizado_por IS NULL OR btrim(p_autorizado_por) = '' THEN
        RAISE EXCEPTION 'falta quién autoriza el remito' USING ERRCODE = 'P0001';
    END IF;
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_items) i
         WHERE jsonb_typeof(i) <> 'object' OR length(btrim(COALESCE(i->>'descripcion', ''))) NOT BETWEEN 1 AND 200
    ) THEN
        RAISE EXCEPTION 'ítems del remito inválidos' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v FROM fila.remito_salida WHERE id = p_id FOR UPDATE;
    IF FOUND AND (v.salio_en IS NOT NULL OR v.anulado_en IS NOT NULL) THEN
        RAISE EXCEPTION 'ese remito ya salió o está anulado' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.remito_salida (id, numero, sede, destino, motivo, items, firma, autorizado_por)
    VALUES (p_id, p_numero, p_sede, btrim(p_destino), btrim(p_motivo), p_items, p_firma, left(p_autorizado_por, 100))
    ON CONFLICT (id) DO UPDATE SET sede = EXCLUDED.sede, destino = EXCLUDED.destino, motivo = EXCLUDED.motivo,
        items = EXCLUDED.items, firma = EXCLUDED.firma, autorizado_por = EXCLUDED.autorizado_por,
        autorizado_en = now();
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('remito_autorizado', left(p_autorizado_por, 100),
            jsonb_build_object('remito', p_numero, 'sede', p_sede, 'firma', p_firma));
END $$;

CREATE OR REPLACE FUNCTION fila.anular_remito(p_id text, p_actor text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.remito_salida;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién anula el remito' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v FROM fila.remito_salida WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;  -- nunca llegó a la guardia: no hay nada que anular acá
    END IF;
    IF v.salio_en IS NOT NULL THEN
        RAISE EXCEPTION 'ese remito ya salió de la planta' USING ERRCODE = 'P0001';
    END IF;
    UPDATE fila.remito_salida SET anulado_en = now(), anulado_por = left(p_actor, 100)
     WHERE id = p_id AND anulado_en IS NULL;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('remito_anulado', left(p_actor, 100), jsonb_build_object('remito', v.numero, 'sede', v.sede));
END $$;

CREATE OR REPLACE FUNCTION fila.salidas_remitos(p_ids text[])
RETURNS TABLE(id text, salio_en timestamptz, salio_por text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT r.id, r.salio_en, r.salio_por FROM fila.remito_salida r
     WHERE r.id = ANY(p_ids) AND r.salio_en IS NOT NULL
$$;

-- Guardia: remitos autorizados de su bodega que todavía no salieron.
CREATE OR REPLACE FUNCTION fila.remitos_por_salir(p_sede text)
RETURNS TABLE(id text, numero integer, destino text, motivo text, items jsonb, firma text,
              autorizado_por text, autorizado_en timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT r.id, r.numero, r.destino, r.motivo, r.items, r.firma, r.autorizado_por, r.autorizado_en
      FROM fila.remito_salida r
     WHERE r.sede = p_sede AND r.salio_en IS NULL AND r.anulado_en IS NULL
     ORDER BY r.numero
$$;

CREATE OR REPLACE FUNCTION fila.marcar_salida_remito(p_id text, p_sede text, p_guardia text)
RETURNS TABLE(numero integer, salio_en timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.remito_salida;
BEGIN
    IF p_guardia IS NULL OR btrim(p_guardia) = '' THEN
        RAISE EXCEPTION 'falta quién marca la salida' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v FROM fila.remito_salida WHERE id = p_id FOR UPDATE;
    IF NOT FOUND OR v.sede <> p_sede THEN
        RAISE EXCEPTION 'ese remito no es de esta bodega' USING ERRCODE = 'P0001';
    END IF;
    IF v.anulado_en IS NOT NULL THEN
        RAISE EXCEPTION 'ese remito está anulado: no puede salir' USING ERRCODE = 'P0001';
    END IF;
    IF v.salio_en IS NOT NULL THEN
        RAISE EXCEPTION 'ese remito ya salió' USING ERRCODE = 'P0001';
    END IF;
    UPDATE fila.remito_salida r SET salio_en = now(), salio_por = left(p_guardia, 100) WHERE r.id = p_id;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('remito_salida', left(p_guardia, 100), jsonb_build_object('remito', v.numero, 'sede', v.sede));
    RETURN QUERY SELECT r.numero, r.salio_en FROM fila.remito_salida r WHERE r.id = p_id;
END $$;

-- Bot: foto y texto de un celular activo en «Personal en el bot». Tope por celular y por hora.
CREATE OR REPLACE FUNCTION fila.recibir_mensaje_mantenimiento(
    p_telefono text, p_texto text, p_foto bytea, p_foto_tipo text
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v_nombre text;
    v_id bigint;
BEGIN
    SELECT tp.nombre INTO v_nombre FROM consulta.telefono_personal tp
     WHERE tp.telefono = p_telefono AND tp.activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ese celular no está activo en Personal en el bot' USING ERRCODE = 'P0001';
    END IF;
    IF (SELECT count(*) FROM fila.mensaje_mantenimiento
         WHERE telefono = p_telefono AND recibido_en > now() - interval '1 hour') >= 30 THEN
        RAISE EXCEPTION 'tope de mensajes por hora' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.mensaje_mantenimiento (telefono, nombre, texto, foto, foto_tipo)
    VALUES (p_telefono, v_nombre, left(COALESCE(p_texto, ''), 1000), p_foto, p_foto_tipo)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Gestión: toma los mensajes y confirma cuáles guardó (sólo entonces dejan de estar pendientes).
CREATE OR REPLACE FUNCTION fila.mensajes_mantenimiento_pendientes(p_limite integer)
RETURNS TABLE(id bigint, telefono text, nombre text, texto text, foto bytea, foto_tipo text,
              recibido_en timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT m.id, m.telefono, m.nombre, m.texto, m.foto, m.foto_tipo, m.recibido_en
      FROM fila.mensaje_mantenimiento m
     WHERE m.tomado_en IS NULL
     ORDER BY m.id
     LIMIT LEAST(GREATEST(COALESCE(p_limite, 50), 1), 200)
$$;

CREATE OR REPLACE FUNCTION fila.confirmar_mensajes_mantenimiento(p_ids bigint[]) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.mensaje_mantenimiento SET tomado_en = now() WHERE id = ANY(p_ids) AND tomado_en IS NULL
$$;

-- Webhook: las fotos llegan con el identificador del archivo en WhatsApp; el bot lo baja después.
ALTER TABLE consulta.bot_entrada ADD COLUMN IF NOT EXISTS media_id text
    CHECK (media_id IS NULL OR media_id ~ '^[A-Za-z0-9._-]{1,200}$');

CREATE OR REPLACE FUNCTION consulta.encolar_bot_media(
    p_wamid text, p_telefono text, p_tipo text, p_texto text, p_enviado_en timestamptz, p_media_id text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, consulta AS $$
BEGIN
    INSERT INTO consulta.bot_entrada (wamid, telefono, tipo, texto, enviado_en, media_id)
    VALUES (p_wamid, p_telefono, p_tipo, p_texto, p_enviado_en, p_media_id)
    ON CONFLICT (wamid) DO NOTHING;
    RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION consulta.encolar_bot_media(text, text, text, text, timestamptz, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consulta.encolar_bot_media(text, text, text, text, timestamptz, text) TO consulta_webhook;

REVOKE ALL ON FUNCTION fila.publicar_remito(text, integer, text, text, text, jsonb, text, text),
    fila.anular_remito(text, text),
    fila.salidas_remitos(text[]),
    fila.remitos_por_salir(text),
    fila.marcar_salida_remito(text, text, text),
    fila.recibir_mensaje_mantenimiento(text, text, bytea, text),
    fila.mensajes_mantenimiento_pendientes(integer),
    fila.confirmar_mensajes_mantenimiento(bigint[])
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION fila.publicar_remito(text, integer, text, text, text, jsonb, text, text),
    fila.anular_remito(text, text),
    fila.salidas_remitos(text[]),
    fila.mensajes_mantenimiento_pendientes(integer),
    fila.confirmar_mensajes_mantenimiento(bigint[])
    TO gestion_tablero;
GRANT EXECUTE ON FUNCTION fila.remitos_por_salir(text), fila.marcar_salida_remito(text, text, text)
    TO fila_guardia;
GRANT EXECUTE ON FUNCTION fila.recibir_mensaje_mantenimiento(text, text, bytea, text) TO consulta_bot;
