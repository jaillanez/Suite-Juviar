-- DMZ: RRHH por WhatsApp (fase 5).
--
--   * CV por WhatsApp: un número que no es productor ni personal manda un PDF o una foto; el bot
--     lo deja acá y Gestión lo toma y lo incorpora a Selección (igual que los CV del mail de RRHH).
--   * Certificados médicos y pedidos de EPP del personal cargado en «Personal en el bot»: quedan
--     pendientes de revisión en la bandeja de RRHH de Gestión. Del certificado, Gestión lee los
--     datos y le pide al empleado que confirme los días y las fechas (1 = sí / 2 = no).
--   * Aviso del micro de personal: la guardia toca «Llegó el micro» eligiendo el recorrido y el
--     bot avisa por WhatsApp al personal activo de ese recorrido.
--
-- Gestión, el bot y la guardia no escriben las tablas: usan las funciones de abajo, que validan
-- y dejan quién hizo cada cosa. Los archivos se borran de la DMZ apenas Gestión confirma que los
-- guardó (en Gestión quedan cifrados). Se aplica antes de instalar el código. Es idempotente.

-- --- Recorridos del micro de personal ---------------------------------------------------

CREATE TABLE IF NOT EXISTS fila.recorrido_micro (
    id bigserial PRIMARY KEY,
    sede text NOT NULL CHECK (sede ~ '^[a-z0-9_-]{2,30}$'),
    nombre text NOT NULL CHECK (length(btrim(nombre)) BETWEEN 2 AND 80),
    activo boolean NOT NULL DEFAULT true,
    creado_por text NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    actualizado_por text NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_recorrido_micro_nombre ON fila.recorrido_micro (sede, lower(btrim(nombre)));

ALTER TABLE consulta.telefono_personal ADD COLUMN IF NOT EXISTS recorrido_id bigint
    REFERENCES fila.recorrido_micro(id);
CREATE INDEX IF NOT EXISTS ix_personal_recorrido ON consulta.telefono_personal (recorrido_id)
    WHERE activo AND recorrido_id IS NOT NULL;

-- Cada vez que la guardia avisó que llegó el micro de un recorrido.
CREATE TABLE IF NOT EXISTS fila.aviso_micro (
    id bigserial PRIMARY KEY,
    recorrido_id bigint NOT NULL REFERENCES fila.recorrido_micro(id),
    sede text NOT NULL,
    guardia text NOT NULL,
    destinatarios integer NOT NULL DEFAULT 0,
    creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_aviso_micro_recorrido ON fila.aviso_micro (recorrido_id, creado_en DESC);

-- --- Mensajes del personal para RRHH (certificado médico / pedido de EPP) ------------------

CREATE TABLE IF NOT EXISTS fila.mensaje_rrhh (
    id bigserial PRIMARY KEY,
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    legajo text NOT NULL,
    nombre text NOT NULL,
    empresa text NOT NULL,
    tipo text NOT NULL CHECK (tipo IN ('certificado', 'epp')),
    texto text NOT NULL DEFAULT '' CHECK (length(texto) <= 1000),
    archivo bytea CHECK (archivo IS NULL OR octet_length(archivo) BETWEEN 200 AND 5000000),
    archivo_tipo text CHECK (archivo_tipo IS NULL
        OR archivo_tipo IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')),
    archivo_nombre text CHECK (archivo_nombre IS NULL OR length(archivo_nombre) BETWEEN 1 AND 120),
    recibido_en timestamptz NOT NULL DEFAULT now(),
    tomado_en timestamptz,
    -- Confirmación del empleado de lo que se leyó del certificado.
    confirmacion text NOT NULL DEFAULT 'sin_pedir'
        CHECK (confirmacion IN ('sin_pedir', 'esperando', 'corrigiendo', 'confirmado', 'no_coincide')),
    confirmacion_vence timestamptz,
    correccion text CHECK (correccion IS NULL OR length(correccion) <= 500),
    respondido_en timestamptz,
    CHECK ((archivo IS NULL) = (archivo_tipo IS NULL)),
    CHECK (tipo = 'epp' OR archivo IS NOT NULL OR tomado_en IS NOT NULL),
    CHECK (archivo IS NOT NULL OR length(btrim(texto)) > 0 OR tomado_en IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_mensaje_rrhh_pendiente ON fila.mensaje_rrhh (id) WHERE tomado_en IS NULL;
CREATE INDEX IF NOT EXISTS ix_mensaje_rrhh_confirmacion ON fila.mensaje_rrhh (telefono, id DESC)
    WHERE confirmacion IN ('esperando', 'corrigiendo');

-- --- CV que llegan por WhatsApp ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fila.cv_whatsapp (
    id bigserial PRIMARY KEY,
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    nombre_archivo text NOT NULL CHECK (length(nombre_archivo) BETWEEN 1 AND 120),
    contenido bytea CHECK (contenido IS NULL OR octet_length(contenido) BETWEEN 200 AND 5000000),
    tipo text NOT NULL CHECK (tipo IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')),
    recibido_en timestamptz NOT NULL DEFAULT now(),
    tomado_en timestamptz,
    CHECK (contenido IS NOT NULL OR tomado_en IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_cv_whatsapp_pendiente ON fila.cv_whatsapp (id) WHERE tomado_en IS NULL;

-- --- Cola de mensajes al personal (aviso del micro y lectura del certificado) --------------

CREATE TABLE IF NOT EXISTS fila.aviso_personal (
    id bigserial PRIMARY KEY,
    tipo text NOT NULL CHECK (tipo IN ('micro', 'certificado')),
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    aviso_micro_id bigint REFERENCES fila.aviso_micro(id),
    recorrido text,
    mensaje_rrhh_id bigint REFERENCES fila.mensaje_rrhh(id),
    texto text CHECK (texto IS NULL OR char_length(texto) BETWEEN 1 AND 1500),
    creado_en timestamptz NOT NULL DEFAULT now(),
    enviado_en timestamptz,
    wamid text,
    intentos integer NOT NULL DEFAULT 0,
    tomado_en timestamptz,
    ultimo_error text,
    -- El texto del aviso del micro lo arma el worker (un solo lugar, para pasarlo a plantilla).
    CHECK ((tipo = 'micro' AND aviso_micro_id IS NOT NULL AND recorrido IS NOT NULL)
        OR (tipo = 'certificado' AND mensaje_rrhh_id IS NOT NULL AND texto IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_aviso_personal_pendiente ON fila.aviso_personal (creado_en) WHERE enviado_en IS NULL;


-- === Bot ===================================================================================

CREATE OR REPLACE FUNCTION fila._tipo_archivo_valido(p_tipo text) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path = fila, pg_temp AS $$
    SELECT p_tipo IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')
$$;

-- Certificado o pedido de EPP de un celular activo en «Personal en el bot». Tope por celular y hora.
CREATE OR REPLACE FUNCTION fila.recibir_mensaje_rrhh(
    p_telefono text, p_tipo text, p_texto text, p_archivo bytea, p_archivo_tipo text, p_archivo_nombre text
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v consulta.telefono_personal;
    v_id bigint;
BEGIN
    SELECT * INTO v FROM consulta.telefono_personal tp WHERE tp.telefono = p_telefono AND tp.activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ese celular no está activo en Personal en el bot' USING ERRCODE = 'P0001';
    END IF;
    IF p_tipo NOT IN ('certificado', 'epp') THEN
        RAISE EXCEPTION 'tipo de mensaje desconocido' USING ERRCODE = 'P0001';
    END IF;
    IF p_tipo = 'certificado' AND p_archivo IS NULL THEN
        RAISE EXCEPTION 'falta la foto o el PDF del certificado' USING ERRCODE = 'P0001';
    END IF;
    IF p_archivo IS NOT NULL AND NOT fila._tipo_archivo_valido(p_archivo_tipo) THEN
        RAISE EXCEPTION 'el archivo tiene que ser PDF, JPG, PNG o WEBP' USING ERRCODE = 'P0001';
    END IF;
    IF (SELECT count(*) FROM fila.mensaje_rrhh
         WHERE telefono = p_telefono AND recibido_en > now() - interval '1 hour') >= 20 THEN
        RAISE EXCEPTION 'tope de mensajes por hora' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.mensaje_rrhh (telefono, legajo, nombre, empresa, tipo, texto, archivo, archivo_tipo,
                                   archivo_nombre)
    VALUES (p_telefono, v.legajo, v.nombre, v.empresa, p_tipo, left(COALESCE(p_texto, ''), 1000), p_archivo,
            CASE WHEN p_archivo IS NULL THEN NULL ELSE p_archivo_tipo END,
            CASE WHEN p_archivo IS NULL THEN NULL ELSE left(COALESCE(NULLIF(btrim(p_archivo_nombre), ''), 'archivo'), 120) END)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- CV de un número que no es productor ni personal de la empresa.
CREATE OR REPLACE FUNCTION fila.recibir_cv_whatsapp(
    p_telefono text, p_nombre_archivo text, p_contenido bytea, p_tipo text
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_id bigint;
BEGIN
    IF p_telefono IS NULL OR p_telefono !~ '^[0-9]{8,20}$' THEN
        RAISE EXCEPTION 'teléfono inválido' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM consulta.telefono_personal WHERE telefono = p_telefono AND activo)
       OR EXISTS (SELECT 1 FROM consulta.telefono_productor WHERE telefono = p_telefono AND activo) THEN
        RAISE EXCEPTION 'ese celular es de un productor o del personal' USING ERRCODE = 'P0001';
    END IF;
    IF NOT fila._tipo_archivo_valido(p_tipo) THEN
        RAISE EXCEPTION 'el CV tiene que ser PDF, JPG, PNG o WEBP' USING ERRCODE = 'P0001';
    END IF;
    IF (SELECT count(*) FROM fila.cv_whatsapp
         WHERE telefono = p_telefono AND recibido_en > now() - interval '1 hour') >= 5 THEN
        RAISE EXCEPTION 'tope de archivos por hora' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.cv_whatsapp (telefono, nombre_archivo, contenido, tipo)
    VALUES (p_telefono, left(COALESCE(NULLIF(btrim(p_nombre_archivo), ''), 'cv'), 120), p_contenido, p_tipo)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- ¿Ese celular tiene un certificado esperando su respuesta? Devuelve 'esperando', 'corrigiendo' o NULL.
CREATE OR REPLACE FUNCTION fila.confirmacion_certificado_pendiente(p_telefono text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT m.confirmacion FROM fila.mensaje_rrhh m
     WHERE m.telefono = p_telefono AND m.confirmacion IN ('esperando', 'corrigiendo')
       AND m.confirmacion_vence > now()
     ORDER BY m.id DESC LIMIT 1
$$;

-- Respuesta del empleado: 'si' (1), 'no' (2) o 'correccion' (el texto que manda después del 2).
-- Devuelve el estado nuevo, o NULL si no había nada esperando esa respuesta.
CREATE OR REPLACE FUNCTION fila.responder_certificado(p_telefono text, p_respuesta text, p_correccion text)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.mensaje_rrhh;
BEGIN
    SELECT * INTO v FROM fila.mensaje_rrhh m
     WHERE m.telefono = p_telefono AND m.confirmacion IN ('esperando', 'corrigiendo')
       AND m.confirmacion_vence > now()
     ORDER BY m.id DESC LIMIT 1 FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    IF v.confirmacion = 'esperando' AND p_respuesta = 'si' THEN
        UPDATE fila.mensaje_rrhh SET confirmacion = 'confirmado', respondido_en = now() WHERE id = v.id;
        RETURN 'confirmado';
    ELSIF v.confirmacion = 'esperando' AND p_respuesta = 'no' THEN
        UPDATE fila.mensaje_rrhh SET confirmacion = 'corrigiendo', respondido_en = now() WHERE id = v.id;
        RETURN 'corrigiendo';
    ELSIF v.confirmacion = 'corrigiendo' AND p_respuesta = 'correccion'
          AND length(btrim(COALESCE(p_correccion, ''))) > 0 THEN
        UPDATE fila.mensaje_rrhh SET confirmacion = 'no_coincide', respondido_en = now(),
               correccion = left(btrim(p_correccion), 500)
         WHERE id = v.id;
        RETURN 'no_coincide';
    END IF;
    RETURN NULL;
END $$;

-- El worker toma los mensajes al personal y marca el resultado (como fila.tomar_avisos de 038).
-- La reserva dura 2 minutos; hasta 5 intentos. Un aviso del micro que no salió en 30 minutos ya no
-- sirve y no se manda; la lectura del certificado se manda dentro de las 23 horas (ventana de Meta).
CREATE OR REPLACE FUNCTION fila.tomar_avisos_personal(p_lote integer)
RETURNS TABLE (id bigint, telefono text, tipo text, recorrido text, texto text)
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.aviso_personal a
       SET tomado_en = now(), intentos = a.intentos + 1
     WHERE a.id IN (
        SELECT x.id FROM fila.aviso_personal x
         WHERE x.enviado_en IS NULL AND x.intentos < 5
           AND (x.tomado_en IS NULL OR x.tomado_en < now() - interval '2 minutes')
           AND x.creado_en > now() - CASE WHEN x.tipo = 'micro' THEN interval '30 minutes' ELSE interval '23 hours' END
         ORDER BY x.creado_en LIMIT LEAST(GREATEST(p_lote, 1), 50)
         FOR UPDATE SKIP LOCKED)
    RETURNING a.id, a.telefono, a.tipo, a.recorrido, a.texto;
$$;

CREATE OR REPLACE FUNCTION fila.marcar_aviso_personal(p_id bigint, p_wamid text, p_error text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.aviso_personal
       SET enviado_en = CASE WHEN p_error IS NULL THEN now() END,
           wamid = left(p_wamid, 200), ultimo_error = left(p_error, 300)
     WHERE id = p_id AND enviado_en IS NULL;
$$;


-- === Gestión ===============================================================================

-- Toma los mensajes para RRHH y confirma cuáles guardó: sólo entonces dejan de estar pendientes,
-- y el archivo se borra de la DMZ (en Gestión queda cifrado).
CREATE OR REPLACE FUNCTION fila.mensajes_rrhh_pendientes(p_limite integer)
RETURNS TABLE(id bigint, telefono text, legajo text, nombre text, empresa text, tipo text, texto text,
              archivo bytea, archivo_tipo text, archivo_nombre text, recibido_en timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT m.id, m.telefono, m.legajo, m.nombre, m.empresa, m.tipo, m.texto, m.archivo, m.archivo_tipo,
           m.archivo_nombre, m.recibido_en
      FROM fila.mensaje_rrhh m
     WHERE m.tomado_en IS NULL
     ORDER BY m.id
     LIMIT LEAST(GREATEST(COALESCE(p_limite, 20), 1), 50)
$$;

CREATE OR REPLACE FUNCTION fila.confirmar_mensajes_rrhh(p_ids bigint[]) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.mensaje_rrhh SET tomado_en = now(), archivo = NULL, archivo_tipo = NULL
     WHERE id = ANY(p_ids) AND tomado_en IS NULL
$$;

-- Gestión leyó el certificado: le manda al empleado lo que se leyó. Con p_pide_confirmacion el
-- certificado queda esperando su respuesta (1 / 2) durante 24 horas.
CREATE OR REPLACE FUNCTION fila.avisar_lectura_certificado(p_id bigint, p_texto text, p_pide_confirmacion boolean)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.mensaje_rrhh;
BEGIN
    SELECT * INTO v FROM fila.mensaje_rrhh WHERE id = p_id FOR UPDATE;
    IF NOT FOUND OR v.tipo <> 'certificado' THEN
        RAISE EXCEPTION 'ese certificado no existe' USING ERRCODE = 'P0001';
    END IF;
    IF v.confirmacion <> 'sin_pedir' OR EXISTS (
        SELECT 1 FROM fila.aviso_personal a WHERE a.mensaje_rrhh_id = p_id) THEN
        RETURN;  -- ya se le avisó: volver a sincronizar no le manda dos mensajes
    END IF;
    IF p_texto IS NULL OR btrim(p_texto) = '' THEN
        RAISE EXCEPTION 'falta el texto para el empleado' USING ERRCODE = 'P0001';
    END IF;
    IF p_pide_confirmacion THEN
        -- Si tenía otro certificado esperando, ese deja de esperar: las respuestas van al último.
        UPDATE fila.mensaje_rrhh SET confirmacion_vence = now()
         WHERE telefono = v.telefono AND id <> p_id AND confirmacion IN ('esperando', 'corrigiendo')
           AND confirmacion_vence > now();
        UPDATE fila.mensaje_rrhh SET confirmacion = 'esperando', confirmacion_vence = now() + interval '24 hours'
         WHERE id = p_id;
    END IF;
    INSERT INTO fila.aviso_personal (tipo, telefono, mensaje_rrhh_id, texto)
    VALUES ('certificado', v.telefono, p_id, left(p_texto, 1500));
END $$;

-- Lo que respondieron los empleados de esos certificados.
CREATE OR REPLACE FUNCTION fila.confirmaciones_certificados(p_ids bigint[])
RETURNS TABLE(id bigint, confirmacion text, confirmacion_vence timestamptz, correccion text,
              respondido_en timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT m.id, m.confirmacion, m.confirmacion_vence, m.correccion, m.respondido_en
      FROM fila.mensaje_rrhh m WHERE m.id = ANY(p_ids)
$$;

CREATE OR REPLACE FUNCTION fila.cvs_whatsapp_pendientes(p_limite integer)
RETURNS TABLE(id bigint, telefono text, nombre_archivo text, contenido bytea, tipo text, recibido_en timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT c.id, c.telefono, c.nombre_archivo, c.contenido, c.tipo, c.recibido_en
      FROM fila.cv_whatsapp c
     WHERE c.tomado_en IS NULL
     ORDER BY c.id
     LIMIT LEAST(GREATEST(COALESCE(p_limite, 20), 1), 50)
$$;

CREATE OR REPLACE FUNCTION fila.confirmar_cvs_whatsapp(p_ids bigint[]) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.cv_whatsapp SET tomado_en = now(), contenido = NULL WHERE id = ANY(p_ids) AND tomado_en IS NULL
$$;

-- Recorridos: alta (p_id NULL) o cambio. Nunca se borran: se desactivan.
CREATE OR REPLACE FUNCTION fila.guardar_recorrido_micro(
    p_id bigint, p_sede text, p_nombre text, p_activo boolean, p_actor text
) RETURNS fila.recorrido_micro
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.recorrido_micro;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién hace el cambio' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM fila.recorrido_micro r
                WHERE r.sede = p_sede AND lower(btrim(r.nombre)) = lower(btrim(p_nombre))
                  AND r.id IS DISTINCT FROM p_id) THEN
        RAISE EXCEPTION 'ya hay un recorrido con ese nombre en esa bodega' USING ERRCODE = 'P0001';
    END IF;
    IF p_id IS NULL THEN
        INSERT INTO fila.recorrido_micro (sede, nombre, activo, creado_por, actualizado_por)
        VALUES (p_sede, btrim(p_nombre), COALESCE(p_activo, true), left(p_actor, 100), left(p_actor, 100))
        RETURNING * INTO v;
    ELSE
        UPDATE fila.recorrido_micro SET sede = p_sede, nombre = btrim(p_nombre), activo = COALESCE(p_activo, true),
               actualizado_por = left(p_actor, 100), actualizado_en = now()
         WHERE id = p_id
        RETURNING * INTO v;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ese recorrido no existe' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('recorrido_micro', left(p_actor, 100), to_jsonb(v));
    RETURN v;
END $$;

-- Asigna (o quita, con NULL) el recorrido del micro de un empleado del bot; queda en su historial.
CREATE OR REPLACE FUNCTION consulta.asignar_recorrido_personal(p_telefono text, p_recorrido_id bigint, p_actor text)
RETURNS consulta.telefono_personal
LANGUAGE plpgsql SECURITY DEFINER SET search_path = consulta, pg_temp AS $$
DECLARE
    v_antes consulta.telefono_personal;
    v consulta.telefono_personal;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién hace el cambio' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_antes FROM consulta.telefono_personal WHERE telefono = p_telefono AND activo FOR UPDATE;
    IF v_antes.telefono IS NULL THEN
        RAISE EXCEPTION 'ese celular no está activo' USING ERRCODE = 'P0001';
    END IF;
    IF p_recorrido_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM fila.recorrido_micro WHERE id = p_recorrido_id AND activo) THEN
        RAISE EXCEPTION 'ese recorrido no existe o está inactivo' USING ERRCODE = 'P0001';
    END IF;
    IF v_antes.recorrido_id IS NOT DISTINCT FROM p_recorrido_id THEN
        RETURN v_antes;
    END IF;
    UPDATE consulta.telefono_personal
       SET recorrido_id = p_recorrido_id, actualizado_por = left(p_actor, 100), actualizado_en = now()
     WHERE telefono = p_telefono
    RETURNING * INTO v;
    INSERT INTO consulta.personal_evento (telefono, tipo, actor, antes, despues)
    VALUES (p_telefono, 'cambio', left(p_actor, 100), to_jsonb(v_antes), to_jsonb(v));
    RETURN v;
END $$;


-- === Guardia ===============================================================================

CREATE OR REPLACE FUNCTION fila.recorridos_micro(p_sede text)
RETURNS TABLE(id bigint, nombre text, personas integer, ultimo_aviso_en timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT r.id, r.nombre,
           (SELECT count(*)::int FROM consulta.telefono_personal tp WHERE tp.recorrido_id = r.id AND tp.activo),
           (SELECT max(a.creado_en) FROM fila.aviso_micro a WHERE a.recorrido_id = r.id)
      FROM fila.recorrido_micro r
     WHERE r.sede = p_sede AND r.activo
     ORDER BY lower(r.nombre)
$$;

-- «Llegó el micro»: encola un aviso por WhatsApp a cada empleado activo del recorrido. Dos toques
-- seguidos no avisan dos veces: no se acepta otro aviso del mismo recorrido dentro de 5 minutos.
CREATE OR REPLACE FUNCTION fila.avisar_llegada_micro(p_recorrido_id bigint, p_sede text, p_guardia text)
RETURNS TABLE(aviso_id bigint, recorrido text, destinatarios integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v fila.recorrido_micro;
    v_ultimo timestamptz;
    v_aviso bigint;
    v_n integer;
BEGIN
    IF p_guardia IS NULL OR btrim(p_guardia) = '' THEN
        RAISE EXCEPTION 'falta quién avisa' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v FROM fila.recorrido_micro r WHERE r.id = p_recorrido_id FOR UPDATE;
    IF NOT FOUND OR v.sede <> p_sede OR NOT v.activo THEN
        RAISE EXCEPTION 'ese recorrido no es de esta bodega' USING ERRCODE = 'P0001';
    END IF;
    SELECT max(a.creado_en) INTO v_ultimo FROM fila.aviso_micro a WHERE a.recorrido_id = p_recorrido_id;
    IF v_ultimo > now() - interval '5 minutes' THEN
        RAISE EXCEPTION 'ya se avisó la llegada de ese micro a las %',
            to_char(v_ultimo AT TIME ZONE 'America/Argentina/San_Juan', 'HH24:MI') USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.aviso_micro (recorrido_id, sede, guardia) VALUES (p_recorrido_id, p_sede, left(p_guardia, 100))
    RETURNING id INTO v_aviso;
    INSERT INTO fila.aviso_personal (tipo, telefono, aviso_micro_id, recorrido)
    SELECT 'micro', tp.telefono, v_aviso, v.nombre
      FROM consulta.telefono_personal tp
     WHERE tp.recorrido_id = p_recorrido_id AND tp.activo;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    UPDATE fila.aviso_micro SET destinatarios = v_n WHERE id = v_aviso;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('aviso_micro', left(p_guardia, 100),
            jsonb_build_object('recorrido', v.nombre, 'sede', p_sede, 'destinatarios', v_n));
    RETURN QUERY SELECT v_aviso, v.nombre, v_n;
END $$;


-- === Permisos ==============================================================================

REVOKE ALL ON FUNCTION fila._tipo_archivo_valido(text),
    fila.recibir_mensaje_rrhh(text, text, text, bytea, text, text),
    fila.recibir_cv_whatsapp(text, text, bytea, text),
    fila.confirmacion_certificado_pendiente(text),
    fila.responder_certificado(text, text, text),
    fila.tomar_avisos_personal(integer),
    fila.marcar_aviso_personal(bigint, text, text),
    fila.mensajes_rrhh_pendientes(integer),
    fila.confirmar_mensajes_rrhh(bigint[]),
    fila.avisar_lectura_certificado(bigint, text, boolean),
    fila.confirmaciones_certificados(bigint[]),
    fila.cvs_whatsapp_pendientes(integer),
    fila.confirmar_cvs_whatsapp(bigint[]),
    fila.guardar_recorrido_micro(bigint, text, text, boolean, text),
    consulta.asignar_recorrido_personal(text, bigint, text),
    fila.recorridos_micro(text),
    fila.avisar_llegada_micro(bigint, text, text)
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION fila.recibir_mensaje_rrhh(text, text, text, bytea, text, text),
    fila.recibir_cv_whatsapp(text, text, bytea, text),
    fila.confirmacion_certificado_pendiente(text),
    fila.responder_certificado(text, text, text),
    fila.tomar_avisos_personal(integer),
    fila.marcar_aviso_personal(bigint, text, text)
    TO consulta_bot;

GRANT EXECUTE ON FUNCTION fila.mensajes_rrhh_pendientes(integer),
    fila.confirmar_mensajes_rrhh(bigint[]),
    fila.avisar_lectura_certificado(bigint, text, boolean),
    fila.confirmaciones_certificados(bigint[]),
    fila.cvs_whatsapp_pendientes(integer),
    fila.confirmar_cvs_whatsapp(bigint[]),
    fila.guardar_recorrido_micro(bigint, text, text, boolean, text),
    consulta.asignar_recorrido_personal(text, bigint, text)
    TO gestion_tablero;
GRANT SELECT ON fila.recorrido_micro TO gestion_tablero;
GRANT SELECT (id, recorrido_id, sede, guardia, destinatarios, creado_en) ON fila.aviso_micro TO gestion_tablero;

GRANT EXECUTE ON FUNCTION fila.recorridos_micro(text), fila.avisar_llegada_micro(bigint, text, text)
    TO fila_guardia;

-- Webhook: los documentos llegan con nombre y tipo del archivo; el bot los baja después.
ALTER TABLE consulta.bot_entrada ADD COLUMN IF NOT EXISTS media_nombre text
    CHECK (media_nombre IS NULL OR length(media_nombre) BETWEEN 1 AND 120);
ALTER TABLE consulta.bot_entrada ADD COLUMN IF NOT EXISTS media_tipo text
    CHECK (media_tipo IS NULL OR media_tipo IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp'));

CREATE OR REPLACE FUNCTION consulta.encolar_bot_archivo(
    p_wamid text, p_telefono text, p_tipo text, p_texto text, p_enviado_en timestamptz, p_media_id text,
    p_media_nombre text, p_media_tipo text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, consulta AS $$
BEGIN
    INSERT INTO consulta.bot_entrada (wamid, telefono, tipo, texto, enviado_en, media_id, media_nombre, media_tipo)
    VALUES (p_wamid, p_telefono, p_tipo, p_texto, p_enviado_en, p_media_id, p_media_nombre, p_media_tipo)
    ON CONFLICT (wamid) DO NOTHING;
    RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION consulta.encolar_bot_archivo(text, text, text, text, timestamptz, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consulta.encolar_bot_archivo(text, text, text, text, timestamptz, text, text, text)
    TO consulta_webhook;
