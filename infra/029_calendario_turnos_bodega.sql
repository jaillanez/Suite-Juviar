-- DMZ: calendario de turnos cargado por el personal de la bodega desde Gestión.
--
-- Gestión no escribe las tablas directamente: usa estas tres funciones, que aplican las
-- mismas reglas que la fila (modulos/fila/cupo.py y fila_app.repositorio.reservar_turno):
-- nada de días pasados ni a más de 60 días, 1 a 50 camiones, 1.000 a 40.000 kg por camión,
-- sin pasarse de la capacidad del día y orgánico sólo con certificado vigente.
-- Cada operación deja quién la hizo. Se aplica antes de instalar el código. Idempotente.

CREATE OR REPLACE FUNCTION fila.fijar_capacidad(
    p_sede text, p_fecha date, p_kg_dia bigint, p_actor text
) RETURNS fila.capacidad
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.capacidad;
BEGIN
    IF p_kg_dia IS NULL OR p_kg_dia < 0 OR p_kg_dia > 10000000 THEN
        RAISE EXCEPTION 'capacidad fuera de rango' USING ERRCODE = 'P0001';
    END IF;
    IF p_sede !~ '^[a-z0-9_-]{2,30}$' THEN
        RAISE EXCEPTION 'sede inválida' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.capacidad (sede, fecha, kg_dia, actualizado_por)
    VALUES (p_sede, p_fecha, p_kg_dia, left(p_actor, 100))
    ON CONFLICT (sede, fecha) DO UPDATE
        SET kg_dia = EXCLUDED.kg_dia, actualizado_por = EXCLUDED.actualizado_por,
            actualizado_en = now()
    RETURNING * INTO v;
    RETURN v;
END $$;

CREATE OR REPLACE FUNCTION fila.reservar_turno_bodega(
    p_sede text, p_fecha date, p_cuit text, p_codigo text, p_camiones integer,
    p_kg_por_camion integer, p_organica boolean, p_actor text
) RETURNS fila.turno
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v_hoy date := (now() AT TIME ZONE 'America/Argentina/San_Juan')::date;
    v_capacidad bigint;
    v_reservado bigint;
    v fila.turno;
BEGIN
    IF p_fecha < v_hoy THEN
        RAISE EXCEPTION 'no se reservan turnos para días pasados' USING ERRCODE = 'P0001';
    END IF;
    IF p_fecha > v_hoy + 60 THEN
        RAISE EXCEPTION 'los turnos se piden con hasta 60 días de anticipación' USING ERRCODE = 'P0001';
    END IF;
    IF p_camiones NOT BETWEEN 1 AND 50 THEN
        RAISE EXCEPTION 'cantidad de camiones fuera de rango' USING ERRCODE = 'P0001';
    END IF;
    IF p_kg_por_camion NOT BETWEEN 1000 AND 40000 THEN
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
            p_organica, left(p_actor, 100), 'bodega')
    RETURNING * INTO v;
    INSERT INTO fila.evento (turno_id, tipo, actor) VALUES (v.id, 'turno_bodega', left(p_actor, 100));
    RETURN v;
END $$;

CREATE OR REPLACE FUNCTION fila.cancelar_turno(p_id bigint, p_actor text)
RETURNS fila.turno
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.turno;
BEGIN
    UPDATE fila.turno SET estado = 'cancelado'
     WHERE id = p_id AND estado = 'activo' AND camiones_usados = 0
    RETURNING * INTO v;
    IF v.id IS NULL THEN
        RAISE EXCEPTION 'el turno no existe, ya está cancelado o ya llegaron camiones'
            USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.evento (turno_id, tipo, actor)
    VALUES (p_id, 'turno_cancelado', left(p_actor, 100));
    RETURN v;
END $$;

REVOKE ALL ON FUNCTION fila.fijar_capacidad(text, date, bigint, text),
    fila.reservar_turno_bodega(text, date, text, text, integer, integer, boolean, text),
    fila.cancelar_turno(bigint, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.fijar_capacidad(text, date, bigint, text),
    fila.reservar_turno_bodega(text, date, text, text, integer, integer, boolean, text),
    fila.cancelar_turno(bigint, text) TO gestion_tablero;
GRANT USAGE ON SCHEMA fila TO gestion_tablero;
GRANT SELECT ON fila.productor_organico TO gestion_tablero;
