-- Avisos de WhatsApp al personal de la planta (por ahora, mosto virgen sin descargar).
--
-- Se reusa la cola del bot de infra/038: el worker ya los toma y los manda por Chattigo.
-- Gestión no escribe la tabla directamente: sólo encola un texto a un teléfono válido.

CREATE OR REPLACE FUNCTION fila.encolar_aviso_interno(p_telefono text, p_texto text)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_id bigint;
BEGIN
    IF p_telefono IS NULL OR p_telefono !~ '^[0-9]{8,20}$' THEN
        RAISE EXCEPTION 'teléfono inválido' USING ERRCODE = 'P0001';
    END IF;
    IF p_texto IS NULL OR btrim(p_texto) = '' THEN
        RAISE EXCEPTION 'el aviso no tiene texto' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.aviso_productor (oferta_id, telefono, texto)
    VALUES (NULL, p_telefono, left(p_texto, 3000))
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

REVOKE ALL ON FUNCTION fila.encolar_aviso_interno(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.encolar_aviso_interno(text, text) TO gestion_tablero;
