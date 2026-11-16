-- DMZ: ofertas de uva de la temporada y asignación de días por la bodega.
--
-- El productor (por WhatsApp) o la bodega (desde Gestión) cargan cuántos kilos ofrecen de
-- cada variedad para toda la temporada. El bot ya no reserva días: la oferta queda
-- pendiente y la bodega le asigna los días corridos (sin domingos) desde Gestión.
-- Al asignar se crean los turnos de cada día en fila.turno —los mismos que ven la
-- consola del guardia y Báscula— y se deja un aviso para el productor por WhatsApp.
--
-- Gestión calcula el reparto día por día (Python, con pruebas) y la base sólo comprueba
-- que el reparto sea válido antes de guardarlo. Pasarse de la capacidad del día NO
-- bloquea: Gestión lo avisa antes de confirmar (decisión de la bodega).
--
-- APLICAR ANTES de desplegar el bot y Gestión que traen "Ofrecer uva". Idempotente.

-- Alta preliminar de productores que todavía no están en Oracle (CUIT y nombre).
ALTER TABLE fila.productor ADD COLUMN IF NOT EXISTS alta_preliminar_por text;

CREATE TABLE IF NOT EXISTS fila.oferta (
    id bigserial PRIMARY KEY,
    pedido uuid NOT NULL,                 -- agrupa las variedades ofrecidas en un mismo mensaje
    temporada integer NOT NULL,           -- la cosecha para la que se ofrece
    sede text NOT NULL CHECK (sede ~ '^[a-z0-9_-]{2,30}$'),
    clientecuit text NOT NULL REFERENCES fila.productor(clientecuit),
    clientecodigo text,
    variedad text NOT NULL CHECK (char_length(btrim(variedad)) BETWEEN 1 AND 60),
    kg bigint NOT NULL CHECK (kg BETWEEN 1000 AND 50000000),
    kg_a_programar bigint NOT NULL CHECK (kg_a_programar >= 0),
    organica boolean NOT NULL DEFAULT false,
    canal text NOT NULL CHECK (canal IN ('whatsapp', 'bodega')),
    pedido_por text NOT NULL,
    telefono text CHECK (telefono IS NULL OR telefono ~ '^[0-9]{8,20}$'),
    estado text NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'asignada', 'detenida', 'desestimada')),
    kg_dia integer,
    detenida_hasta date,
    motivo text,
    creado_en timestamptz NOT NULL DEFAULT now(),
    actualizado_por text,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_oferta_sede ON fila.oferta (sede, temporada, creado_en);
CREATE INDEX IF NOT EXISTS ix_oferta_cuit ON fila.oferta (clientecuit, creado_en);

ALTER TABLE fila.turno ADD COLUMN IF NOT EXISTS oferta_id bigint REFERENCES fila.oferta(id);
CREATE INDEX IF NOT EXISTS ix_turno_oferta ON fila.turno (oferta_id) WHERE oferta_id IS NOT NULL;
ALTER TABLE fila.evento ADD COLUMN IF NOT EXISTS oferta_id bigint REFERENCES fila.oferta(id);

-- Kilos por día que la bodega le fija a cada productor (lo recuerda para la próxima vez).
CREATE TABLE IF NOT EXISTS fila.ritmo_productor (
    clientecuit text NOT NULL,
    sede text NOT NULL,
    kg_dia integer NOT NULL CHECK (kg_dia BETWEEN 1000 AND 2000000),
    actualizado_por text NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (clientecuit, sede)
);

-- Parámetros del panel de ofertas: una sola fila, editable desde Gestión.
CREATE TABLE IF NOT EXISTS fila.parametro_ofertas (
    id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    anios_historial integer NOT NULL DEFAULT 3 CHECK (anios_historial BETWEEN 1 AND 10),
    tolerancia_sobreoferta integer NOT NULL DEFAULT 0 CHECK (tolerancia_sobreoferta BETWEEN 0 AND 500),
    kg_dia_sugerido integer NOT NULL DEFAULT 10000 CHECK (kg_dia_sugerido BETWEEN 1000 AND 2000000),
    semanas_stop integer[] NOT NULL DEFAULT '{1,2}',
    actualizado_por text,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
INSERT INTO fila.parametro_ofertas (id) VALUES (1) ON CONFLICT DO NOTHING;

-- Avisos para el productor; los manda el worker del bot.
CREATE TABLE IF NOT EXISTS fila.aviso_productor (
    id bigserial PRIMARY KEY,
    oferta_id bigint REFERENCES fila.oferta(id),
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    texto text NOT NULL CHECK (char_length(texto) BETWEEN 1 AND 3000),
    creado_en timestamptz NOT NULL DEFAULT now(),
    enviado_en timestamptz,
    wamid text,
    intentos integer NOT NULL DEFAULT 0,
    tomado_en timestamptz,
    ultimo_error text
);
ALTER TABLE fila.aviso_productor ADD COLUMN IF NOT EXISTS tomado_en timestamptz;
CREATE INDEX IF NOT EXISTS ix_aviso_pendiente ON fila.aviso_productor (creado_en) WHERE enviado_en IS NULL;


-- Teléfonos a los que se avisa: el que hizo la oferta si todavía puede pedir turnos para ese
-- productor; si no (o si la cargó la bodega), todos los que hoy tienen ese permiso. Nunca un
-- teléfono dado de baja o al que le quitaron el permiso.
CREATE OR REPLACE FUNCTION fila._encolar_aviso(p_oferta fila.oferta, p_texto text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_n integer;
BEGIN
    IF p_texto IS NULL OR btrim(p_texto) = '' THEN
        RETURN 0;
    END IF;
    WITH habilitados AS (
        SELECT tp.telefono FROM consulta.telefono_productor tp
         WHERE tp.clientecuit = p_oferta.clientecuit AND tp.activo
           AND 'pedir_turnos' = ANY(tp.tareas) AND tp.telefono ~ '^[0-9]{8,20}$'
    ), destino AS (
        SELECT telefono FROM habilitados WHERE telefono = p_oferta.telefono
        UNION
        SELECT telefono FROM habilitados
         WHERE NOT EXISTS (SELECT 1 FROM habilitados h WHERE h.telefono = p_oferta.telefono)
    )
    INSERT INTO fila.aviso_productor (oferta_id, telefono, texto)
    SELECT p_oferta.id, telefono, left(p_texto, 3000) FROM destino;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $$;


-- Una oferta hecha de junio en adelante es para la cosecha del año siguiente.
CREATE OR REPLACE FUNCTION fila._temporada_oferta() RETURNS integer
LANGUAGE sql STABLE SET search_path = fila, pg_temp AS $$
    SELECT (extract(year FROM d) + CASE WHEN extract(month FROM d) >= 6 THEN 1 ELSE 0 END)::int
      FROM (SELECT (now() AT TIME ZONE 'America/Argentina/San_Juan')::date AS d) x;
$$;


CREATE OR REPLACE FUNCTION fila._validar_oferta(
    p_sede text, p_cuit text, p_variedad text, p_kg bigint, p_organica boolean
) RETURNS void
LANGUAGE plpgsql SET search_path = fila, pg_temp AS $$
BEGIN
    IF p_sede IS NULL OR p_sede !~ '^[a-z0-9_-]{2,30}$' THEN
        RAISE EXCEPTION 'bodega inválida' USING ERRCODE = 'P0001';
    END IF;
    IF p_variedad IS NULL OR char_length(btrim(p_variedad)) NOT BETWEEN 1 AND 60 THEN
        RAISE EXCEPTION 'falta la variedad' USING ERRCODE = 'P0001';
    END IF;
    IF p_kg IS NULL OR p_kg NOT BETWEEN 1000 AND 50000000 THEN
        RAISE EXCEPTION 'los kilos ofrecidos tienen que estar entre 1.000 y 50.000.000' USING ERRCODE = 'P0001';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM fila.productor WHERE clientecuit = p_cuit) THEN
        RAISE EXCEPTION 'el productor no está en la lista' USING ERRCODE = 'P0001';
    END IF;
    IF COALESCE(p_organica, false) AND NOT EXISTS (
        SELECT 1 FROM fila.productor_organico
         WHERE clientecuit = p_cuit AND (vence IS NULL OR vence >= (now() AT TIME ZONE 'America/Argentina/San_Juan')::date)
    ) THEN
        RAISE EXCEPTION 'el productor no tiene certificado orgánico vigente' USING ERRCODE = 'P0001';
    END IF;
END $$;


-- El bot: siempre canal whatsapp y el teléfono que escribió. Reenviar el mismo pedido
-- y variedad no duplica (el worker puede reintentar).
CREATE OR REPLACE FUNCTION fila.ofrecer_uva_whatsapp(
    p_pedido uuid, p_sede text, p_cuit text, p_codigo text, p_variedad text, p_kg bigint,
    p_organica boolean, p_telefono text
) RETURNS fila.oferta
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.oferta;
BEGIN
    IF p_telefono IS NULL OR p_telefono !~ '^[0-9]{8,20}$' THEN
        RAISE EXCEPTION 'teléfono inválido' USING ERRCODE = 'P0001';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM consulta.telefono_productor
                    WHERE telefono = p_telefono AND clientecuit = p_cuit AND activo
                      AND 'pedir_turnos' = ANY(tareas)) THEN
        RAISE EXCEPTION 'este número no puede ofrecer uva para esa cuenta' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v FROM fila.oferta
     WHERE pedido = p_pedido AND lower(btrim(variedad)) = lower(btrim(p_variedad));
    IF v.id IS NOT NULL THEN
        RETURN v;
    END IF;
    PERFORM fila._validar_oferta(p_sede, p_cuit, p_variedad, p_kg, p_organica);
    INSERT INTO fila.oferta (pedido, temporada, sede, clientecuit, clientecodigo, variedad, kg, kg_a_programar,
                             organica, canal, pedido_por, telefono)
    VALUES (p_pedido, fila._temporada_oferta(), p_sede, p_cuit, NULLIF(btrim(p_codigo), ''), btrim(p_variedad), p_kg, p_kg,
            COALESCE(p_organica, false), 'whatsapp', 'whatsapp:' || p_telefono, p_telefono)
    RETURNING * INTO v;
    INSERT INTO fila.evento (oferta_id, tipo, actor) VALUES (v.id, 'oferta_whatsapp', 'whatsapp:' || p_telefono);
    RETURN v;
END $$;


-- Gestión: carga una oferta. Si el CUIT no está en la lista y viene el nombre, da de alta
-- al productor de forma preliminar (productor nuevo, sin pesadas en Oracle).
CREATE OR REPLACE FUNCTION fila.cargar_oferta_bodega(
    p_sede text, p_cuit text, p_nombre_nuevo text, p_codigo text, p_variedad text,
    p_kg bigint, p_organica boolean, p_actor text
) RETURNS fila.oferta
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.oferta;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién carga la oferta' USING ERRCODE = 'P0001';
    END IF;
    IF p_cuit IS NULL OR p_cuit !~ '^[0-9]{11}$' THEN
        RAISE EXCEPTION 'el CUIT tiene que tener 11 números' USING ERRCODE = 'P0001';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM fila.productor WHERE clientecuit = p_cuit) THEN
        IF p_nombre_nuevo IS NULL OR char_length(btrim(p_nombre_nuevo)) NOT BETWEEN 2 AND 120 THEN
            RAISE EXCEPTION 'el productor no está en la lista: cargá su nombre para darlo de alta' USING ERRCODE = 'P0001';
        END IF;
        INSERT INTO fila.productor (clientecuit, razonsocial, busqueda, alta_preliminar_por)
        VALUES (p_cuit, upper(btrim(p_nombre_nuevo)), lower(btrim(p_nombre_nuevo)) || ' ' || p_cuit,
                left(p_actor, 100));
    END IF;
    PERFORM fila._validar_oferta(p_sede, p_cuit, p_variedad, p_kg, p_organica);
    INSERT INTO fila.oferta (pedido, temporada, sede, clientecuit, clientecodigo, variedad, kg, kg_a_programar,
                             organica, canal, pedido_por)
    VALUES (gen_random_uuid(), fila._temporada_oferta(), p_sede, p_cuit, NULLIF(btrim(p_codigo), ''), btrim(p_variedad), p_kg, p_kg,
            COALESCE(p_organica, false), 'bodega', left(p_actor, 100))
    RETURNING * INTO v;
    INSERT INTO fila.evento (oferta_id, tipo, actor) VALUES (v.id, 'oferta_bodega', left(p_actor, 100));
    RETURN v;
END $$;


-- Gestión: asigna los días. Recibe el reparto ya calculado (un elemento por día) y
-- comprueba: días futuros, sin domingos, sin repetir, la suma igual a lo que falta
-- programar y cada día dentro de los rangos de un turno. Crea un turno por día.
CREATE OR REPLACE FUNCTION fila.asignar_oferta(
    p_id bigint, p_fechas date[], p_camiones integer[], p_kg_por_camion integer[],
    p_kg_dia integer, p_actor text, p_aviso text
) RETURNS SETOF fila.turno
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v_hoy date := (now() AT TIME ZONE 'America/Argentina/San_Juan')::date;
    v fila.oferta;
    v_total bigint := 0;
    v_turno fila.turno;
    i integer;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién asigna' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v FROM fila.oferta WHERE id = p_id FOR UPDATE;
    IF v.id IS NULL THEN
        RAISE EXCEPTION 'la oferta no existe' USING ERRCODE = 'P0001';
    END IF;
    IF v.estado NOT IN ('pendiente', 'detenida') THEN
        RAISE EXCEPTION 'la oferta ya tiene días asignados o fue desestimada' USING ERRCODE = 'P0001';
    END IF;
    IF p_kg_dia IS NULL OR p_kg_dia NOT BETWEEN 1000 AND 2000000 THEN
        RAISE EXCEPTION 'kilos por día fuera de rango' USING ERRCODE = 'P0001';
    END IF;
    IF p_fechas IS NULL OR cardinality(p_fechas) = 0
       OR cardinality(p_fechas) <> cardinality(p_camiones)
       OR cardinality(p_fechas) <> cardinality(p_kg_por_camion) THEN
        RAISE EXCEPTION 'el reparto de días está incompleto' USING ERRCODE = 'P0001';
    END IF;
    IF cardinality(p_fechas) > 120 THEN
        RAISE EXCEPTION 'son demasiados días para una oferta' USING ERRCODE = 'P0001';
    END IF;
    IF (SELECT count(DISTINCT f) FROM unnest(p_fechas) f) <> cardinality(p_fechas) THEN
        RAISE EXCEPTION 'hay días repetidos' USING ERRCODE = 'P0001';
    END IF;
    FOR i IN 1 .. cardinality(p_fechas) LOOP
        IF p_fechas[i] < v_hoy OR p_fechas[i] > v_hoy + 365 THEN
            RAISE EXCEPTION 'los días tienen que ser de hoy en adelante y dentro del año' USING ERRCODE = 'P0001';
        END IF;
        IF extract(isodow FROM p_fechas[i]) = 7 THEN
            RAISE EXCEPTION 'no se asignan domingos' USING ERRCODE = 'P0001';
        END IF;
        IF p_camiones[i] NOT BETWEEN 1 AND 50 OR p_kg_por_camion[i] NOT BETWEEN 1000 AND 40000 THEN
            RAISE EXCEPTION 'un día quedó fuera de los rangos de camiones o kilos' USING ERRCODE = 'P0001';
        END IF;
        v_total := v_total + p_camiones[i]::bigint * p_kg_por_camion[i];
    END LOOP;
    -- El reparto redondea camiones enteros: se admite hasta un camión de diferencia por día.
    IF abs(v_total - v.kg_a_programar) > cardinality(p_fechas)::bigint * 1000 THEN
        RAISE EXCEPTION 'el reparto no suma los kilos ofrecidos' USING ERRCODE = 'P0001';
    END IF;
    IF v.organica AND NOT EXISTS (
        SELECT 1 FROM fila.productor_organico
         WHERE clientecuit = v.clientecuit AND (vence IS NULL OR vence >= p_fechas[cardinality(p_fechas)])
    ) THEN
        RAISE EXCEPTION 'el productor no tiene certificado orgánico vigente para esos días' USING ERRCODE = 'P0001';
    END IF;

    FOR i IN 1 .. cardinality(p_fechas) LOOP
        INSERT INTO fila.turno (sede, fecha, clientecuit, clientecodigo, camiones, kg_por_camion,
                                declara_organica, pedido_por, canal, oferta_id)
        VALUES (v.sede, p_fechas[i], v.clientecuit, v.clientecodigo, p_camiones[i], p_kg_por_camion[i],
                v.organica, left(p_actor, 100), 'bodega', v.id)
        RETURNING * INTO v_turno;
        RETURN NEXT v_turno;
    END LOOP;

    UPDATE fila.oferta SET estado = 'asignada', kg_dia = p_kg_dia, detenida_hasta = NULL,
           actualizado_por = left(p_actor, 100), actualizado_en = now()
     WHERE id = v.id RETURNING * INTO v;
    INSERT INTO fila.ritmo_productor (clientecuit, sede, kg_dia, actualizado_por)
    VALUES (v.clientecuit, v.sede, p_kg_dia, left(p_actor, 100))
    ON CONFLICT (clientecuit, sede) DO UPDATE
        SET kg_dia = EXCLUDED.kg_dia, actualizado_por = EXCLUDED.actualizado_por, actualizado_en = now();
    INSERT INTO fila.evento (oferta_id, tipo, actor, detalle)
    VALUES (v.id, 'oferta_asignada', left(p_actor, 100),
            jsonb_build_object('desde', p_fechas[1], 'hasta', p_fechas[cardinality(p_fechas)],
                               'dias', cardinality(p_fechas), 'kg_dia', p_kg_dia));
    PERFORM fila._encolar_aviso(v, p_aviso);
END $$;


-- Gestión: "Stop por falta de grado". Cancela los días que todavía no recibieron
-- camiones (de hoy en adelante) y deja la oferta detenida hasta la fecha indicada, con
-- los kilos de esos días pendientes de volver a programar.
CREATE OR REPLACE FUNCTION fila.detener_oferta(
    p_id bigint, p_hasta date, p_actor text, p_aviso text
) RETURNS fila.oferta
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v_hoy date := (now() AT TIME ZONE 'America/Argentina/San_Juan')::date;
    v fila.oferta;
    v_kg bigint;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién detiene' USING ERRCODE = 'P0001';
    END IF;
    IF p_hasta IS NULL OR p_hasta <= v_hoy OR p_hasta > v_hoy + 120 THEN
        RAISE EXCEPTION 'la fecha hasta la que se detiene no es válida' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v FROM fila.oferta WHERE id = p_id FOR UPDATE;
    IF v.id IS NULL THEN
        RAISE EXCEPTION 'la oferta no existe' USING ERRCODE = 'P0001';
    END IF;
    IF v.estado NOT IN ('pendiente', 'asignada') THEN
        RAISE EXCEPTION 'la oferta ya está detenida o fue desestimada' USING ERRCODE = 'P0001';
    END IF;
    WITH cancelados AS (
        UPDATE fila.turno SET estado = 'cancelado'
         WHERE oferta_id = v.id AND estado = 'activo' AND camiones_usados = 0 AND fecha >= v_hoy
        RETURNING id, camiones::bigint * kg_por_camion AS kg
    ), eventos AS (
        INSERT INTO fila.evento (turno_id, oferta_id, tipo, actor, motivo)
        SELECT id, v.id, 'turno_cancelado', left(p_actor, 100), 'falta de grado' FROM cancelados
    )
    SELECT COALESCE(sum(kg), 0) INTO v_kg FROM cancelados;
    UPDATE fila.oferta
       SET estado = 'detenida', detenida_hasta = p_hasta, motivo = 'falta de grado',
           kg_a_programar = CASE WHEN v.estado = 'pendiente' THEN v.kg_a_programar ELSE v_kg END,
           actualizado_por = left(p_actor, 100), actualizado_en = now()
     WHERE id = v.id RETURNING * INTO v;
    INSERT INTO fila.evento (oferta_id, tipo, actor, motivo, detalle)
    VALUES (v.id, 'oferta_detenida', left(p_actor, 100), 'falta de grado',
            jsonb_build_object('hasta', p_hasta, 'kg_a_programar', v.kg_a_programar));
    PERFORM fila._encolar_aviso(v, p_aviso);
    RETURN v;
END $$;


-- Gestión: deja una oferta fuera de la temporada (por ejemplo, en años de sobreoferta).
-- Sólo si todavía no tiene días asignados. No avisa al productor.
CREATE OR REPLACE FUNCTION fila.desestimar_oferta(p_id bigint, p_motivo text, p_actor text)
RETURNS fila.oferta
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.oferta;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién desestima' USING ERRCODE = 'P0001';
    END IF;
    IF p_motivo IS NULL OR char_length(btrim(p_motivo)) NOT BETWEEN 3 AND 300 THEN
        RAISE EXCEPTION 'escribí el motivo' USING ERRCODE = 'P0001';
    END IF;
    UPDATE fila.oferta
       SET estado = 'desestimada', motivo = btrim(p_motivo),
           actualizado_por = left(p_actor, 100), actualizado_en = now()
     WHERE id = p_id AND estado IN ('pendiente', 'detenida')
    RETURNING * INTO v;
    IF v.id IS NULL THEN
        RAISE EXCEPTION 'la oferta no existe o ya tiene días asignados' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.evento (oferta_id, tipo, actor, motivo)
    VALUES (v.id, 'oferta_desestimada', left(p_actor, 100), btrim(p_motivo));
    RETURN v;
END $$;


CREATE OR REPLACE FUNCTION fila.fijar_parametro_ofertas(
    p_anios integer, p_tolerancia integer, p_kg_dia integer, p_semanas integer[], p_actor text
) RETURNS fila.parametro_ofertas
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.parametro_ofertas;
BEGIN
    IF p_semanas IS NULL OR cardinality(p_semanas) NOT BETWEEN 1 AND 8
       OR EXISTS (SELECT 1 FROM unnest(p_semanas) s WHERE s NOT BETWEEN 1 AND 12) THEN
        RAISE EXCEPTION 'las semanas de postergación tienen que ir de 1 a 12' USING ERRCODE = 'P0001';
    END IF;
    UPDATE fila.parametro_ofertas
       SET anios_historial = p_anios, tolerancia_sobreoferta = p_tolerancia, kg_dia_sugerido = p_kg_dia,
           semanas_stop = (SELECT array_agg(DISTINCT s ORDER BY s) FROM unnest(p_semanas) s),
           actualizado_por = left(p_actor, 100), actualizado_en = now()
     WHERE id = 1 RETURNING * INTO v;
    RETURN v;
END $$;


-- El worker del bot toma los avisos pendientes y marca el resultado. Tomar un aviso lo
-- reserva por 10 minutos (aunque haya dos workers o se corte a mitad del envío no sale dos
-- veces en ese lapso). Si el envío falla queda reservado igual: se reintenta a los 10 minutos,
-- hasta 5 intentos.
CREATE OR REPLACE FUNCTION fila.tomar_avisos(p_lote integer)
RETURNS TABLE (id bigint, telefono text, texto text)
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.aviso_productor a
       SET tomado_en = now(), intentos = a.intentos + 1
     WHERE a.id IN (
        SELECT x.id FROM fila.aviso_productor x
         WHERE x.enviado_en IS NULL AND x.intentos < 5
           AND (x.tomado_en IS NULL OR x.tomado_en < now() - interval '10 minutes')
         ORDER BY x.creado_en LIMIT LEAST(GREATEST(p_lote, 1), 50)
         FOR UPDATE SKIP LOCKED)
    RETURNING a.id, a.telefono, a.texto;
$$;

CREATE OR REPLACE FUNCTION fila.marcar_aviso(p_id bigint, p_wamid text, p_error text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.aviso_productor
       SET enviado_en = CASE WHEN p_error IS NULL THEN now() END,
           wamid = left(p_wamid, 200), ultimo_error = left(p_error, 300)
     WHERE id = p_id AND enviado_en IS NULL;
$$;


REVOKE ALL ON FUNCTION fila._encolar_aviso(fila.oferta, text), fila._temporada_oferta(),
    fila._validar_oferta(text, text, text, bigint, boolean),
    fila.ofrecer_uva_whatsapp(uuid, text, text, text, text, bigint, boolean, text),
    fila.cargar_oferta_bodega(text, text, text, text, text, bigint, boolean, text),
    fila.asignar_oferta(bigint, date[], integer[], integer[], integer, text, text),
    fila.detener_oferta(bigint, date, text, text),
    fila.desestimar_oferta(bigint, text, text),
    fila.fijar_parametro_ofertas(integer, integer, integer, integer[], text),
    fila.tomar_avisos(integer), fila.marcar_aviso(bigint, text, text)
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    fila.cargar_oferta_bodega(text, text, text, text, text, bigint, boolean, text),
    fila.asignar_oferta(bigint, date[], integer[], integer[], integer, text, text),
    fila.detener_oferta(bigint, date, text, text),
    fila.desestimar_oferta(bigint, text, text),
    fila.fijar_parametro_ofertas(integer, integer, integer, integer[], text)
    TO gestion_tablero;
GRANT SELECT ON fila.oferta, fila.ritmo_productor, fila.parametro_ofertas TO gestion_tablero;
GRANT SELECT (oferta_id, telefono, creado_en, enviado_en, intentos, ultimo_error)
    ON fila.aviso_productor TO gestion_tablero;
GRANT SELECT (oferta_id) ON fila.turno TO gestion_tablero;
-- Historial de entregas de cada productor para comparar con lo que ofrece.
GRANT SELECT (clientecuit) ON consulta.descarga_publica TO gestion_tablero;

GRANT EXECUTE ON FUNCTION
    fila.ofrecer_uva_whatsapp(uuid, text, text, text, text, bigint, boolean, text),
    fila.tomar_avisos(integer), fila.marcar_aviso(bigint, text, text)
    TO consulta_bot;
-- "Mis turnos" en el bot: sus ofertas y en qué quedaron.
GRANT SELECT (id, temporada, sede, clientecuit, clientecodigo, variedad, kg, kg_a_programar, organica, estado,
              detenida_hasta, creado_en)
    ON fila.oferta TO consulta_bot;
GRANT SELECT (oferta_id) ON fila.turno TO consulta_bot;
