-- DMZ: la cancelación de turnos aplica en la base las mismas reglas que la pantalla.
-- No se cancelan turnos de días pasados y la sede tiene que coincidir con la del turno.
-- Reemplaza fila.cancelar_turno(bigint, text) de 029. Idempotente.

DROP FUNCTION IF EXISTS fila.cancelar_turno(bigint, text);

CREATE OR REPLACE FUNCTION fila.cancelar_turno(p_id bigint, p_sede text, p_actor text)
RETURNS fila.turno
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v fila.turno;
BEGIN
    UPDATE fila.turno SET estado = 'cancelado'
     WHERE id = p_id AND sede = p_sede AND estado = 'activo' AND camiones_usados = 0
       AND fecha >= (now() AT TIME ZONE 'America/Argentina/San_Juan')::date
    RETURNING * INTO v;
    IF v.id IS NULL THEN
        RAISE EXCEPTION 'el turno no existe, es de un día pasado, ya está cancelado o ya llegaron camiones'
            USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.evento (turno_id, tipo, actor)
    VALUES (p_id, 'turno_cancelado', left(p_actor, 100));
    RETURN v;
END $$;

REVOKE ALL ON FUNCTION fila.cancelar_turno(bigint, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.cancelar_turno(bigint, text, text) TO gestion_tablero;
