-- DMZ: el bot de WhatsApp pide turnos con las mismas reglas que Gestión y la fila.
--
-- APLICAR ANTES DE DESPLEGAR el código del bot que trae "Pedir turno" / "Mis turnos":
-- el worker guarda el borrador del pedido en consulta.bot_sesion.turno y reserva con
-- fila.reservar_turno_whatsapp(...). Idempotente.
--
-- Las reglas (días, rango de camiones y kilos, capacidad del día y certificado orgánico)
-- quedan en una sola función, parametrizada por canal. fila.reservar_turno_bodega(...)
-- conserva su firma y pasa a ser un envoltorio, así Gestión sigue funcionando sin cambios.

ALTER TABLE consulta.bot_sesion ADD COLUMN IF NOT EXISTS turno jsonb;

CREATE OR REPLACE FUNCTION fila.reservar_turno_canal(
    p_sede text, p_fecha date, p_cuit text, p_codigo text, p_camiones integer,
    p_kg_por_camion integer, p_organica boolean, p_actor text, p_canal text
) RETURNS fila.turno
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v_hoy date := (now() AT TIME ZONE 'America/Argentina/San_Juan')::date;
    v_capacidad bigint;
    v_reservado bigint;
    v fila.turno;
BEGIN
    IF p_canal IS NULL OR p_canal NOT IN ('bodega', 'whatsapp', 'web') THEN
        RAISE EXCEPTION 'canal inválido' USING ERRCODE = 'P0001';
    END IF;
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién pide el turno' USING ERRCODE = 'P0001';
    END IF;
    IF p_fecha IS NULL OR p_fecha < v_hoy THEN
        RAISE EXCEPTION 'no se reservan turnos para días pasados' USING ERRCODE = 'P0001';
    END IF;
    IF p_fecha > v_hoy + 60 THEN
        RAISE EXCEPTION 'los turnos se piden con hasta 60 días de anticipación' USING ERRCODE = 'P0001';
    END IF;
    IF p_camiones IS NULL OR p_camiones NOT BETWEEN 1 AND 50 THEN
        RAISE EXCEPTION 'cantidad de camiones fuera de rango' USING ERRCODE = 'P0001';
    END IF;
    IF p_kg_por_camion IS NULL OR p_kg_por_camion NOT BETWEEN 1000 AND 40000 THEN
        RAISE EXCEPTION 'kilos por camión fuera de rango' USING ERRCODE = 'P0001';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM fila.productor WHERE clientecuit = p_cuit) THEN
        RAISE EXCEPTION 'el productor no está en la lista' USING ERRCODE = 'P0001';
    END IF;
    SELECT kg_dia INTO v_capacidad FROM fila.capacidad
     WHERE sede = p_sede AND fecha = p_fecha FOR UPDATE;
    IF v_capacidad IS NULL THEN
        SELECT kg_dia INTO v_capacidad FROM fila.capacidad
         WHERE sede = p_sede AND fecha IS NULL FOR UPDATE;
    END IF;
    IF v_capacidad IS NULL THEN
        RAISE EXCEPTION 'la bodega todavía no definió capacidad para esa sede' USING ERRCODE = 'P0001';
    END IF;
    SELECT COALESCE(sum(camiones * kg_por_camion), 0) INTO v_reservado FROM fila.turno
     WHERE sede = p_sede AND fecha = p_fecha AND estado = 'activo';
    IF p_camiones::bigint * p_kg_por_camion > v_capacidad - v_reservado THEN
        RAISE EXCEPTION 'sin cupo: quedan % kg para ese día', GREATEST(v_capacidad - v_reservado, 0)
            USING ERRCODE = 'P0001';
    END IF;
    IF p_organica AND NOT EXISTS (
        SELECT 1 FROM fila.productor_organico
         WHERE clientecuit = p_cuit AND (vence IS NULL OR vence >= p_fecha)
    ) THEN
        RAISE EXCEPTION 'el productor no tiene certificado orgánico vigente' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.turno (sede, fecha, clientecuit, clientecodigo, camiones, kg_por_camion,
                            declara_organica, pedido_por, canal)
    VALUES (p_sede, p_fecha, p_cuit, NULLIF(btrim(p_codigo), ''), p_camiones, p_kg_por_camion,
            COALESCE(p_organica, false), left(p_actor, 100), p_canal)
    RETURNING * INTO v;
    INSERT INTO fila.evento (turno_id, tipo, actor)
    VALUES (v.id, 'turno_' || p_canal, left(p_actor, 100));
    RETURN v;
END $$;

-- El bot no elige canal ni actor: siempre 'whatsapp' y el teléfono que escribió.
CREATE OR REPLACE FUNCTION fila.reservar_turno_whatsapp(
    p_sede text, p_fecha date, p_cuit text, p_codigo text, p_camiones integer,
    p_kg_por_camion integer, p_organica boolean, p_telefono text
) RETURNS fila.turno
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
BEGIN
    IF p_telefono IS NULL OR p_telefono !~ '^[0-9]{8,20}$' THEN
        RAISE EXCEPTION 'teléfono inválido' USING ERRCODE = 'P0001';
    END IF;
    RETURN fila.reservar_turno_canal(p_sede, p_fecha, p_cuit, p_codigo, p_camiones,
                                     p_kg_por_camion, p_organica, 'whatsapp:' || p_telefono,
                                     'whatsapp');
END $$;

-- Misma firma que en 029: Gestión no se entera del cambio.
CREATE OR REPLACE FUNCTION fila.reservar_turno_bodega(
    p_sede text, p_fecha date, p_cuit text, p_codigo text, p_camiones integer,
    p_kg_por_camion integer, p_organica boolean, p_actor text
) RETURNS fila.turno
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT fila.reservar_turno_canal(p_sede, p_fecha, p_cuit, p_codigo, p_camiones,
                                     p_kg_por_camion, p_organica, p_actor, 'bodega');
$$;

REVOKE ALL ON FUNCTION
    fila.reservar_turno_canal(text, date, text, text, integer, integer, boolean, text, text)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION
    fila.reservar_turno_bodega(text, date, text, text, integer, integer, boolean, text)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION
    fila.reservar_turno_whatsapp(text, date, text, text, integer, integer, boolean, text)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
    fila.reservar_turno_bodega(text, date, text, text, integer, integer, boolean, text)
    TO gestion_tablero;
-- fila.reservar_turno_canal no se otorga a nadie: sólo la usan los envoltorios.
GRANT EXECUTE ON FUNCTION
    fila.reservar_turno_whatsapp(text, date, text, text, integer, integer, boolean, text)
    TO consulta_bot;

-- Lo que el bot lee para armar la lista de días, el certificado orgánico y "Mis turnos".
-- Sólo columnas: no ve quién pidió los turnos de otros (pedido_por) ni datos del certificado.
GRANT USAGE ON SCHEMA fila TO consulta_bot;
GRANT SELECT (sede, fecha, kg_dia) ON fila.capacidad TO consulta_bot;
GRANT SELECT (id, sede, fecha, clientecuit, clientecodigo, camiones, camiones_usados,
              kg_por_camion, declara_organica, estado)
    ON fila.turno TO consulta_bot;
GRANT SELECT (clientecuit, vence) ON fila.productor_organico TO consulta_bot;
