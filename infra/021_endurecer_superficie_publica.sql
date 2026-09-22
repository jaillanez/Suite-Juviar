-- DMZ: la consulta pública de patentes no expone al chofer y limita enumeración por IP.
DROP FUNCTION IF EXISTS fila.autocompletar_patente(text);

CREATE OR REPLACE FUNCTION fila.autocompletar_patente(p_patente text, p_ip text)
RETURNS TABLE(productor text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_ip, 0));
    IF (SELECT count(*) FROM fila.evento
        WHERE tipo = 'consulta_patente'
          AND detalle->>'ip' = p_ip
          AND momento > now() - interval '1 hour') >= 20 THEN
        RAISE EXCEPTION 'limite_consultas_patente' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO fila.evento(tipo, actor, detalle)
    VALUES ('consulta_patente', 'publico',
            jsonb_build_object('ip', p_ip, 'patente', p_patente));

    RETURN QUERY
    SELECT 'Patente reconocida'::text
    WHERE EXISTS (SELECT 1 FROM fila.vehiculo v WHERE v.patente = p_patente);
END $$;

REVOKE ALL ON FUNCTION fila.autocompletar_patente(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.autocompletar_patente(text,text) TO fila_publico;
