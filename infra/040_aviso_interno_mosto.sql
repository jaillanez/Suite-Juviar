-- Aviso de WhatsApp al personal: mosto virgen que pasó las horas límite sin descargarse.
--
-- Se reusa la cola del bot de infra/038: el worker ya los toma y los manda por Chattigo.
-- Gestión no escribe la tabla ni elige el texto: pasa los datos del camión y la base arma
-- el mensaje. Sólo se avisa a celulares activos en «Personal en el bot» (infra/034) y hay un
-- tope por hora para que nadie pueda usar la cola para mandar mensajes en masa.

DROP FUNCTION IF EXISTS fila.encolar_aviso_interno(text, text);

CREATE OR REPLACE FUNCTION fila.encolar_aviso_mosto(
    p_telefono text, p_patente text, p_proveedor text, p_compra integer, p_horas numeric, p_bodega text
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_id bigint;
BEGIN
    IF p_telefono IS NULL OR NOT EXISTS (
        SELECT 1 FROM consulta.telefono_personal tp WHERE tp.telefono = p_telefono AND tp.activo
    ) THEN
        RAISE EXCEPTION 'ese celular no está activo en Personal en el bot' USING ERRCODE = 'P0001';
    END IF;
    IF p_patente IS NULL OR p_patente !~ '^[A-Z0-9]{5,10}$'
       OR p_bodega IS NULL OR p_bodega !~ '^[A-Za-zÁÉÍÓÚáéíóúñÑ ]{2,30}$'
       OR p_proveedor IS NULL OR length(btrim(p_proveedor)) NOT BETWEEN 1 AND 120
       OR p_compra IS NULL OR p_compra < 1 OR p_horas IS NULL OR p_horas < 0 OR p_horas > 10000 THEN
        RAISE EXCEPTION 'datos del aviso inválidos' USING ERRCODE = 'P0001';
    END IF;
    IF (SELECT count(*) FROM fila.aviso_productor
         WHERE oferta_id IS NULL AND creado_en > now() - interval '1 hour') >= 60 THEN
        RAISE EXCEPTION 'tope de avisos internos por hora' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.aviso_productor (oferta_id, telefono, texto)
    VALUES (NULL, p_telefono, format(
        'URGENTE mosto virgen: el camión %s (%s, compra N.º %s) lleva %s h en %s sin descargarse. '
        'Hay que descargarlo o pasarlo al concentrador.',
        p_patente, btrim(p_proveedor), p_compra, round(p_horas, 1), p_bodega))
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

REVOKE ALL ON FUNCTION fila.encolar_aviso_mosto(text, text, text, integer, numeric, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.encolar_aviso_mosto(text, text, text, integer, numeric, text)
    TO gestion_tablero;
