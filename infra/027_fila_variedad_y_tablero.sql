-- DMZ: variedad de uva declarada al llegar y rol de sólo lectura para el tablero de Gestión.
--
-- * fila.viaje.variedad_declarada guarda lo que dice el chofer (QR) o el guardia al
--   confirmar / dar de alta directa. Es un dato declarado, sin validar: la variedad real
--   sigue siendo la de consulta.descarga_publica.variedad (vía fila.viaje.descarga_id).
-- * fila.registrar_llegada(...) suma una sobrecarga de 8 parámetros (p_variedad). La de
--   7 parámetros queda intacta para que el código anterior siga funcionando mientras se
--   despliega; se puede retirar en una migración posterior.
-- * fila_guardia y fila_worker ya tienen SELECT/INSERT/UPDATE sobre toda fila.viaje
--   (020), así que la columna nueva no necesita permisos extra.
-- * gestion_tablero: rol LOGIN de sólo lectura para el tablero de Gestión. La clave NO
--   va en este archivo; se fija al aplicar:  ALTER ROLE gestion_tablero PASSWORD '...';
--
-- Idempotente. APLICAR ANTES de desplegar el código de fila que envía la variedad: ese
-- código llama a la función de 8 parámetros y lee la columna nueva.

ALTER TABLE fila.viaje ADD COLUMN IF NOT EXISTS variedad_declarada text
    CHECK (variedad_declarada IS NULL OR char_length(variedad_declarada) BETWEEN 1 AND 60);

CREATE OR REPLACE FUNCTION fila.registrar_llegada(
    p_id_cliente uuid, p_ticket text, p_productor text, p_sede text,
    p_patente text, p_telefono text, p_ip text, p_variedad text
) RETURNS TABLE(id bigint, ticket text, estado text, patente text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_id bigint;
BEGIN
    IF (SELECT count(*) FROM fila.evento WHERE tipo='registro_publico'
        AND detalle->>'ip'=p_ip AND momento > now()-interval '1 hour') >= 5 THEN
        RAISE EXCEPTION 'limite_registros' USING ERRCODE='P0001';
    END IF;
    INSERT INTO fila.viaje
        (id_cliente,ticket,productor_texto,sede,patente,chofer_tel,origen,estado,
         variedad_declarada)
    VALUES (p_id_cliente,p_ticket,p_productor,p_sede,p_patente,p_telefono,'qr','pendiente',
            NULLIF(left(btrim(p_variedad),60),''))
    ON CONFLICT (id_cliente) DO UPDATE SET id_cliente=EXCLUDED.id_cliente
    RETURNING fila.viaje.id INTO v_id;
    INSERT INTO fila.evento(id_cliente,viaje_id,tipo,actor,detalle)
    VALUES (p_id_cliente,v_id,'registro_publico',
            'chofer:'||COALESCE(p_telefono,'sin-telefono'),jsonb_build_object('ip',p_ip))
    ON CONFLICT (id_cliente) DO NOTHING;
    RETURN QUERY SELECT v.id,v.ticket,v.estado,v.patente FROM fila.viaje v WHERE v.id=v_id;
END $$;

REVOKE ALL ON FUNCTION fila.registrar_llegada(uuid,text,text,text,text,text,text,text)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.registrar_llegada(uuid,text,text,text,text,text,text,text)
    TO fila_publico;

DO $$ BEGIN CREATE ROLE gestion_tablero LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT USAGE ON SCHEMA fila, consulta TO gestion_tablero;
GRANT SELECT ON fila.viaje TO gestion_tablero;
GRANT SELECT (sede, id_suite, variedad, neto, azucar, fecha, estado)
    ON consulta.descarga_publica TO gestion_tablero;
