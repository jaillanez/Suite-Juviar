-- DMZ: sesión de uva orgánica por bodega y foto de la patente tomada por el guardia.
--
-- Sesión orgánica (reunión del 15-11, punto 2):
--   * Mientras está abierta no se puede llamar ni pasar a báscula un camión convencional.
--   * La uva orgánica que entra sin sesión abierta se recibe como convencional
--     (fila.viaje.recibida_como, que se fija al llamar al camión).
--   * Durante los primeros días de cosecha (15 por defecto) la orgánica va primero en la fila.
--   * Todo es configurable por bodega (fila.parametro_organica): si recibe orgánica, quién
--     abre y cierra la sesión (guardia, báscula o ambos) y si las franjas horarias son fijas
--     por día de la semana o se abren y cierran en el momento.
--
-- Foto de la patente (punto 3): el guardia la saca con el celular y queda en
-- fila.foto_patente; Gestión la ve en el tablero de la fila.
--
-- Se aplica antes de instalar el código. Es idempotente.

CREATE TABLE IF NOT EXISTS fila.parametro_organica (
    sede text PRIMARY KEY CHECK (sede ~ '^[a-z0-9_-]{2,30}$'),
    recibe_organica boolean NOT NULL DEFAULT false,
    quien_abre text NOT NULL DEFAULT 'ambos' CHECK (quien_abre IN ('guardia', 'bascula', 'ambos')),
    modo_franjas text NOT NULL DEFAULT 'manual' CHECK (modo_franjas IN ('manual', 'fijas')),
    inicio_cosecha date,
    dias_prioridad integer NOT NULL DEFAULT 15 CHECK (dias_prioridad BETWEEN 0 AND 120),
    actualizado_por text NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
-- Según la reunión, sólo Chimbas recibe orgánica; las demás bodegas quedan sin fila aquí.
INSERT INTO fila.parametro_organica (sede, recibe_organica, actualizado_por)
VALUES ('chimbas', true, 'instalacion')
ON CONFLICT (sede) DO NOTHING;

CREATE TABLE IF NOT EXISTS fila.franja_organica (
    id bigserial PRIMARY KEY,
    sede text NOT NULL,
    dia_semana smallint NOT NULL CHECK (dia_semana BETWEEN 1 AND 7),  -- 1 lunes … 7 domingo
    desde time NOT NULL,
    hasta time NOT NULL,
    CHECK (desde < hasta)
);
CREATE INDEX IF NOT EXISTS ix_franja_organica ON fila.franja_organica (sede, dia_semana);

CREATE TABLE IF NOT EXISTS fila.sesion_organica (
    id bigserial PRIMARY KEY,
    sede text NOT NULL,
    abierta_en timestamptz NOT NULL DEFAULT now(),
    abierta_por text NOT NULL,
    abierta_desde text NOT NULL CHECK (abierta_desde IN ('guardia', 'bascula')),
    cerrada_en timestamptz,
    cerrada_por text,
    cerrada_desde text CHECK (cerrada_desde IN ('guardia', 'bascula', 'parametro')),
    CHECK ((cerrada_en IS NULL) = (cerrada_por IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sesion_organica_abierta
    ON fila.sesion_organica (sede) WHERE cerrada_en IS NULL;

ALTER TABLE fila.viaje ADD COLUMN IF NOT EXISTS recibida_como text
    CHECK (recibida_como IS NULL OR recibida_como IN ('organica', 'convencional'));

CREATE TABLE IF NOT EXISTS fila.foto_patente (
    viaje_id bigint PRIMARY KEY REFERENCES fila.viaje(id),
    contenido bytea NOT NULL CHECK (octet_length(contenido) BETWEEN 1000 AND 3000000),
    tipo text NOT NULL CHECK (tipo IN ('image/jpeg', 'image/png', 'image/webp')),
    tomada_por text NOT NULL,
    tomada_en timestamptz NOT NULL DEFAULT now()
);

-- Estado de la sesión en un momento dado. Lo usan la consola del guardia y Gestión.
CREATE OR REPLACE FUNCTION fila.estado_organica(p_sede text, p_momento timestamptz DEFAULT now())
RETURNS TABLE(recibe boolean, abierta boolean, origen text, desde timestamptz, hasta timestamptz,
              abierta_por text, abierta_desde text, prioridad boolean, quien_abre text,
              modo_franjas text, inicio_cosecha date, dias_prioridad integer)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v_par fila.parametro_organica;
    v_local timestamp := p_momento AT TIME ZONE 'America/Argentina/San_Juan';
    v_ses fila.sesion_organica;
    v_franja fila.franja_organica;
BEGIN
    SELECT * INTO v_par FROM fila.parametro_organica WHERE sede = p_sede;
    IF NOT FOUND OR NOT v_par.recibe_organica THEN
        RETURN QUERY SELECT false, false, NULL::text, NULL::timestamptz, NULL::timestamptz,
            NULL::text, NULL::text, false, COALESCE(v_par.quien_abre, 'ambos'),
            COALESCE(v_par.modo_franjas, 'manual'), v_par.inicio_cosecha,
            COALESCE(v_par.dias_prioridad, 15);
        RETURN;
    END IF;
    prioridad := v_par.inicio_cosecha IS NOT NULL
        AND v_local::date >= v_par.inicio_cosecha
        AND v_local::date < v_par.inicio_cosecha + v_par.dias_prioridad;
    IF v_par.modo_franjas = 'fijas' THEN
        SELECT * INTO v_franja FROM fila.franja_organica f
         WHERE f.sede = p_sede AND f.dia_semana = extract(isodow FROM v_local)
           AND v_local::time >= f.desde AND v_local::time < f.hasta
         ORDER BY f.desde LIMIT 1;
        RETURN QUERY SELECT true, FOUND, CASE WHEN FOUND THEN 'franja' END,
            CASE WHEN FOUND THEN (v_local::date + v_franja.desde) AT TIME ZONE 'America/Argentina/San_Juan' END,
            CASE WHEN FOUND THEN (v_local::date + v_franja.hasta) AT TIME ZONE 'America/Argentina/San_Juan' END,
            NULL::text, NULL::text, prioridad, v_par.quien_abre, v_par.modo_franjas,
            v_par.inicio_cosecha, v_par.dias_prioridad;
        RETURN;
    END IF;
    SELECT * INTO v_ses FROM fila.sesion_organica s
     WHERE s.sede = p_sede AND s.cerrada_en IS NULL;
    RETURN QUERY SELECT true, FOUND, CASE WHEN FOUND THEN 'manual' END,
        v_ses.abierta_en, NULL::timestamptz, v_ses.abierta_por, v_ses.abierta_desde,
        prioridad, v_par.quien_abre, v_par.modo_franjas, v_par.inicio_cosecha, v_par.dias_prioridad;
END $$;

CREATE OR REPLACE FUNCTION fila._puede_operar_sesion(p_sede text, p_desde text)
RETURNS fila.parametro_organica LANGUAGE plpgsql SET search_path = fila, pg_temp AS $$
DECLARE v_par fila.parametro_organica;
BEGIN
    SELECT * INTO v_par FROM fila.parametro_organica WHERE sede = p_sede FOR UPDATE;
    IF NOT FOUND OR NOT v_par.recibe_organica THEN
        RAISE EXCEPTION 'esta bodega no recibe uva orgánica' USING ERRCODE = 'P0001';
    END IF;
    IF v_par.modo_franjas <> 'manual' THEN
        RAISE EXCEPTION 'la sesión orgánica sigue las franjas horarias fijas' USING ERRCODE = 'P0001';
    END IF;
    IF v_par.quien_abre <> 'ambos' AND v_par.quien_abre <> p_desde THEN
        RAISE EXCEPTION 'la sesión orgánica la abre y la cierra %',
            CASE v_par.quien_abre WHEN 'guardia' THEN 'la guardia' ELSE 'la báscula' END
            USING ERRCODE = 'P0001';
    END IF;
    RETURN v_par;
END $$;

CREATE OR REPLACE FUNCTION fila.abrir_sesion_organica(p_sede text, p_actor text, p_desde text)
RETURNS fila.sesion_organica
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_ses fila.sesion_organica;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' OR p_desde NOT IN ('guardia', 'bascula') THEN
        RAISE EXCEPTION 'falta quién abre la sesión' USING ERRCODE = 'P0001';
    END IF;
    PERFORM fila._puede_operar_sesion(p_sede, p_desde);
    IF EXISTS (SELECT 1 FROM fila.sesion_organica WHERE sede = p_sede AND cerrada_en IS NULL) THEN
        RAISE EXCEPTION 'la sesión orgánica ya está abierta' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.sesion_organica (sede, abierta_por, abierta_desde)
    VALUES (p_sede, left(p_actor, 100), p_desde) RETURNING * INTO v_ses;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('sesion_organica_abierta', left(p_actor, 100),
            jsonb_build_object('sede', p_sede, 'desde', p_desde, 'sesion', v_ses.id));
    RETURN v_ses;
END $$;

CREATE OR REPLACE FUNCTION fila.cerrar_sesion_organica(p_sede text, p_actor text, p_desde text)
RETURNS fila.sesion_organica
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_ses fila.sesion_organica;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' OR p_desde NOT IN ('guardia', 'bascula') THEN
        RAISE EXCEPTION 'falta quién cierra la sesión' USING ERRCODE = 'P0001';
    END IF;
    PERFORM fila._puede_operar_sesion(p_sede, p_desde);
    UPDATE fila.sesion_organica
       SET cerrada_en = now(), cerrada_por = left(p_actor, 100), cerrada_desde = p_desde
     WHERE sede = p_sede AND cerrada_en IS NULL
    RETURNING * INTO v_ses;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no hay una sesión orgánica abierta' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('sesion_organica_cerrada', left(p_actor, 100),
            jsonb_build_object('sede', p_sede, 'desde', p_desde, 'sesion', v_ses.id));
    RETURN v_ses;
END $$;

-- Gestión: parámetros y franjas de una bodega. Pasar a franjas fijas o dejar de recibir
-- orgánica cierra la sesión manual que hubiera abierta.
CREATE OR REPLACE FUNCTION fila.fijar_parametro_organica(
    p_sede text, p_recibe boolean, p_quien_abre text, p_modo text,
    p_inicio date, p_dias integer, p_actor text
) RETURNS fila.parametro_organica
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_par fila.parametro_organica;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién hace el cambio' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.parametro_organica AS p
        (sede, recibe_organica, quien_abre, modo_franjas, inicio_cosecha, dias_prioridad,
         actualizado_por, actualizado_en)
    VALUES (p_sede, p_recibe, p_quien_abre, p_modo, p_inicio, p_dias, left(p_actor, 100), now())
    ON CONFLICT (sede) DO UPDATE SET
        recibe_organica = EXCLUDED.recibe_organica, quien_abre = EXCLUDED.quien_abre,
        modo_franjas = EXCLUDED.modo_franjas, inicio_cosecha = EXCLUDED.inicio_cosecha,
        dias_prioridad = EXCLUDED.dias_prioridad, actualizado_por = EXCLUDED.actualizado_por,
        actualizado_en = now()
    RETURNING * INTO v_par;
    IF NOT p_recibe OR p_modo <> 'manual' THEN
        UPDATE fila.sesion_organica
           SET cerrada_en = now(), cerrada_por = left(p_actor, 100), cerrada_desde = 'parametro'
         WHERE sede = p_sede AND cerrada_en IS NULL;
    END IF;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('parametro_organica', left(p_actor, 100), to_jsonb(v_par));
    RETURN v_par;
END $$;

CREATE OR REPLACE FUNCTION fila.fijar_franjas_organica(
    p_sede text, p_dias smallint[], p_desde time[], p_hasta time[], p_actor text
) RETURNS SETOF fila.franja_organica
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE i integer;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién hace el cambio' USING ERRCODE = 'P0001';
    END IF;
    IF p_sede IS NULL OR p_sede !~ '^[a-z0-9_-]{2,30}$' THEN
        RAISE EXCEPTION 'sede inválida' USING ERRCODE = 'P0001';
    END IF;
    IF COALESCE(cardinality(p_dias), 0) <> COALESCE(cardinality(p_desde), 0)
       OR COALESCE(cardinality(p_dias), 0) <> COALESCE(cardinality(p_hasta), 0)
       OR COALESCE(cardinality(p_dias), 0) > 50 THEN
        RAISE EXCEPTION 'franjas inválidas' USING ERRCODE = 'P0001';
    END IF;
    DELETE FROM fila.franja_organica WHERE sede = p_sede;
    FOR i IN 1 .. COALESCE(cardinality(p_dias), 0) LOOP
        IF p_desde[i] IS NULL OR p_hasta[i] IS NULL OR p_desde[i] >= p_hasta[i] THEN
            RAISE EXCEPTION 'cada franja tiene que empezar antes de terminar' USING ERRCODE = 'P0001';
        END IF;
        IF EXISTS (SELECT 1 FROM fila.franja_organica f
                    WHERE f.sede = p_sede AND f.dia_semana = p_dias[i]
                      AND f.desde < p_hasta[i] AND p_desde[i] < f.hasta) THEN
            RAISE EXCEPTION 'hay franjas que se superponen el mismo día' USING ERRCODE = 'P0001';
        END IF;
        INSERT INTO fila.franja_organica (sede, dia_semana, desde, hasta)
        VALUES (p_sede, p_dias[i], p_desde[i], p_hasta[i]);
    END LOOP;
    INSERT INTO fila.evento (tipo, actor, detalle)
    VALUES ('franjas_organica', left(p_actor, 100),
            jsonb_build_object('sede', p_sede, 'cantidad', COALESCE(cardinality(p_dias), 0)));
    RETURN QUERY SELECT * FROM fila.franja_organica WHERE sede = p_sede ORDER BY dia_semana, desde;
END $$;

-- Lugar en la fila que ve el chofer en su ticket: misma regla que la consola del guardia
-- (la orgánica sólo pasa adelante con la sesión abierta o en los días de prioridad).
CREATE OR REPLACE FUNCTION fila.leer_ticket(p_ticket text)
RETURNS TABLE(id bigint, sede text, patente text, estado text, numero_dia integer,
              confirmado_en timestamptz, posicion integer, adelante integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    WITH v AS (SELECT * FROM fila.viaje WHERE ticket = p_ticket),
    prioriza AS (
        SELECT e.recibe AND (e.abierta OR e.prioridad) AS si
          FROM v, fila.estado_organica(v.sede) e
    ),
    cola AS (
        SELECT o.id, o.confirmado_en,
               CASE WHEN (SELECT si FROM prioriza) AND o.declara_organica AND EXISTS (
                         SELECT 1 FROM fila.productor_organico p
                          WHERE p.clientecuit = o.clientecuit
                            AND (p.vence IS NULL OR p.vence >= current_date)) THEN 1
                    WHEN o.turno_id IS NOT NULL THEN 2 ELSE 3 END AS grupo
          FROM fila.viaje o, v
         WHERE o.sede = v.sede AND o.estado = 'en_espera'
    )
    SELECT v.id, v.sede, v.patente, v.estado, v.numero_dia, v.confirmado_en,
           CASE WHEN v.estado = 'en_espera' THEN (
               SELECT count(*)::integer FROM cola c, cola m
                WHERE m.id = v.id AND (c.grupo, c.confirmado_en, c.id) <= (m.grupo, m.confirmado_en, m.id))
           END,
           CASE WHEN v.estado = 'en_espera' THEN (
               SELECT count(*)::integer FROM cola c, cola m
                WHERE m.id = v.id AND (c.grupo, c.confirmado_en, c.id) < (m.grupo, m.confirmado_en, m.id))
           END
      FROM v
$$;

REVOKE ALL ON FUNCTION fila.estado_organica(text, timestamptz),
    fila._puede_operar_sesion(text, text),
    fila.abrir_sesion_organica(text, text, text),
    fila.cerrar_sesion_organica(text, text, text),
    fila.fijar_parametro_organica(text, boolean, text, text, date, integer, text),
    fila.fijar_franjas_organica(text, smallint[], time[], time[], text)
    FROM PUBLIC;

-- Consola del guardia (rol fila_guardia, que ya escribe viajes y eventos).
GRANT SELECT ON fila.parametro_organica, fila.franja_organica, fila.sesion_organica TO fila_guardia;
GRANT SELECT, INSERT, UPDATE ON fila.foto_patente TO fila_guardia;
GRANT EXECUTE ON FUNCTION fila.estado_organica(text, timestamptz),
    fila.abrir_sesion_organica(text, text, text),
    fila.cerrar_sesion_organica(text, text, text)
    TO fila_guardia;

-- Gestión (rol gestion_tablero): ve todo, cambia sólo con las funciones.
GRANT SELECT ON fila.parametro_organica, fila.franja_organica, fila.sesion_organica TO gestion_tablero;
GRANT SELECT ON fila.foto_patente TO gestion_tablero;
GRANT SELECT (id, recibida_como) ON fila.viaje TO gestion_tablero;
GRANT EXECUTE ON FUNCTION fila.estado_organica(text, timestamptz),
    fila.abrir_sesion_organica(text, text, text),
    fila.cerrar_sesion_organica(text, text, text),
    fila.fijar_parametro_organica(text, boolean, text, text, date, integer, text),
    fila.fijar_franjas_organica(text, smallint[], time[], time[], text)
    TO gestion_tablero;
