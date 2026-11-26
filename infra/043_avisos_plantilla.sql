-- DMZ: avisos de WhatsApp con plantilla aprobada de Meta.
--
-- Meta sólo entrega los mensajes que inicia la empresa fuera de la ventana de 24 h si son
-- plantillas aprobadas. Los avisos de la cola del bot (infra/038 y 040) pasan a viajar con el
-- nombre de la plantilla y sus parámetros, además del texto de siempre: el worker manda la
-- plantilla por Meta y, si Meta todavía no la aprobó, cae al texto (sirve dentro de las 24 h).
-- Las plantillas están en apps/consulta/src/consulta_publica/bot/plantillas.py.
--
-- Las mismas funciones que hoy encolan completan la plantilla; Gestión no cambia. El aviso del
-- micro (infra/042) no necesita columnas: el worker arma la plantilla con el recorrido.
--
-- Se aplica antes de instalar el worker nuevo (el anterior sigue andando con esto aplicado).
-- Idempotente.

ALTER TABLE fila.aviso_productor ADD COLUMN IF NOT EXISTS plantilla text
    CHECK (plantilla IS NULL OR plantilla ~ '^[a-z0-9_]{1,60}$');
ALTER TABLE fila.aviso_productor ADD COLUMN IF NOT EXISTS parametros jsonb
    CHECK (parametros IS NULL OR jsonb_typeof(parametros) = 'array');


-- Día como lo escribe Gestión en los avisos: «lunes 02/12».
CREATE OR REPLACE FUNCTION fila._dia_largo(p_dia date) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = fila, pg_temp AS $$
    SELECT (ARRAY['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'])
           [extract(isodow FROM p_dia)::integer] || ' ' || to_char(p_dia, 'DD/MM');
$$;


-- Igual que en 038 (los mismos destinatarios y el mismo texto), y además la plantilla:
--   * oferta asignada: turnos_asignados (productor, bodega, variedad, desde, hasta, camiones);
--   * oferta detenida: oferta_postergada (productor, bodega, variedad, desde cuándo).
-- Los días son los turnos creados en esta misma transacción (now() es la hora de la
-- transacción): al reasignar una oferta detenida no se cuentan los días viejos.
CREATE OR REPLACE FUNCTION fila._encolar_aviso(p_oferta fila.oferta, p_texto text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE
    v_n integer;
    v_productor text;
    v_bodega text := initcap(replace(p_oferta.sede, '-', ' '));
    v_plantilla text;
    v_parametros jsonb;
    v_desde date;
    v_hasta date;
    v_camiones bigint;
BEGIN
    IF p_texto IS NULL OR btrim(p_texto) = '' THEN
        RETURN 0;
    END IF;
    SELECT btrim(razonsocial) INTO v_productor FROM fila.productor WHERE clientecuit = p_oferta.clientecuit;
    IF p_oferta.estado = 'asignada' THEN
        SELECT min(fecha), max(fecha), sum(camiones) INTO v_desde, v_hasta, v_camiones
          FROM fila.turno
         WHERE oferta_id = p_oferta.id AND estado = 'activo' AND creado_en = now();
        IF v_desde IS NOT NULL THEN
            v_plantilla := 'turnos_asignados';
            v_parametros := jsonb_build_array(
                v_productor, v_bodega, p_oferta.variedad, fila._dia_largo(v_desde), fila._dia_largo(v_hasta),
                v_camiones || CASE WHEN v_camiones = 1 THEN ' camión' ELSE ' camiones' END);
        END IF;
    ELSIF p_oferta.estado = 'detenida' AND p_oferta.detenida_hasta IS NOT NULL THEN
        v_plantilla := 'oferta_postergada';
        v_parametros := jsonb_build_array(
            v_productor, v_bodega, p_oferta.variedad, fila._dia_largo(p_oferta.detenida_hasta));
    END IF;
    IF v_productor IS NULL THEN
        v_plantilla := NULL;
        v_parametros := NULL;
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
    INSERT INTO fila.aviso_productor (oferta_id, telefono, texto, plantilla, parametros)
    SELECT p_oferta.id, telefono, left(p_texto, 3000), v_plantilla, v_parametros FROM destino;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $$;


-- Igual que en 040, y además la plantilla mosto_virgen_demorado con los mismos datos del texto.
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
    INSERT INTO fila.aviso_productor (oferta_id, telefono, texto, plantilla, parametros)
    VALUES (NULL, p_telefono, format(
        'URGENTE mosto virgen: el camión %s (%s, compra N.º %s) lleva %s h en %s sin descargarse. '
        'Hay que descargarlo o pasarlo al concentrador.',
        p_patente, btrim(p_proveedor), p_compra, round(p_horas, 1), p_bodega),
        'mosto_virgen_demorado',
        jsonb_build_array(p_patente, btrim(p_proveedor), p_compra::text, round(p_horas, 1)::text, p_bodega))
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;


-- El worker ahora también lee la plantilla. Cambia lo que devuelve: hay que borrarla y crearla.
DROP FUNCTION IF EXISTS fila.tomar_avisos(integer);
CREATE FUNCTION fila.tomar_avisos(p_lote integer)
RETURNS TABLE (id bigint, telefono text, texto text, plantilla text, parametros jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.aviso_productor a
       SET tomado_en = now(), intentos = a.intentos + 1
     WHERE a.id IN (
        SELECT x.id FROM fila.aviso_productor x
         WHERE x.enviado_en IS NULL AND x.intentos < 5
           AND (x.tomado_en IS NULL OR x.tomado_en < now() - interval '10 minutes')
         ORDER BY x.creado_en LIMIT LEAST(GREATEST(p_lote, 1), 50)
         FOR UPDATE SKIP LOCKED)
    RETURNING a.id, a.telefono, a.texto, a.plantilla, a.parametros;
$$;


-- Salió, pero con una nota: Meta rechazó la plantilla (no existe o no está aprobada) y se mandó
-- el texto. Queda enviado y la nota en ultimo_error, para verlo sin reenviarlo.
CREATE OR REPLACE FUNCTION fila.marcar_aviso(p_id bigint, p_wamid text, p_error text, p_nota text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.aviso_productor
       SET enviado_en = CASE WHEN p_error IS NULL THEN now() END,
           wamid = left(p_wamid, 200), ultimo_error = left(COALESCE(p_error, p_nota), 300)
     WHERE id = p_id AND enviado_en IS NULL;
$$;

CREATE OR REPLACE FUNCTION fila.marcar_aviso_personal(p_id bigint, p_wamid text, p_error text, p_nota text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    UPDATE fila.aviso_personal
       SET enviado_en = CASE WHEN p_error IS NULL THEN now() END,
           wamid = left(p_wamid, 200), ultimo_error = left(COALESCE(p_error, p_nota), 300)
     WHERE id = p_id AND enviado_en IS NULL;
$$;


REVOKE ALL ON FUNCTION fila._dia_largo(date), fila.tomar_avisos(integer),
    fila.marcar_aviso(bigint, text, text, text), fila.marcar_aviso_personal(bigint, text, text, text)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.tomar_avisos(integer),
    fila.marcar_aviso(bigint, text, text, text), fila.marcar_aviso_personal(bigint, text, text, text)
    TO consulta_bot;
