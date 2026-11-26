-- DMZ: comprobante DDJJ por WhatsApp y acceso al bot sin alta previa.
--
-- Recupera dos funciones del bot anterior (decisión del usuario):
--   * Comprobante DDJJ – Comprobante de Ingreso de Uva en PDF, por descarga (por número de CIU
--     o el de la última). La proyección suma la cuenta (CLIENTECODIGO) para imprimirla.
--   * Un número que no está dado de alta (ni productor ni personal) puede consultar escribiendo
--     el Número de CUENTA, el CUIT o la Patente del camión. El bot deja ese teléfono vinculado a
--     la cuenta hasta que escribe «Salir». Con ese vínculo sólo ve estadísticas, el informe y
--     los comprobantes: ofrecer uva, turnos y contactos siguen siendo para los números que da
--     de alta la bodega.
--
-- Para que no se use para barrer CUIT, cada intento queda en consulta.bot_identificacion y la
-- base corta después de N intentos sin resultado por hora y por teléfono. El vínculo sólo se
-- crea para una cuenta que ese mismo teléfono acaba de identificar.
--
-- La patente sale de CODIGOTRANSPORTE de Oracle (normalizada) y, además, de los camiones que se
-- registraron en la fila (fila.viaje) en el último año.
--
-- Las columnas nuevas de descarga_publica las completa el publicador de Recepción desde esta
-- versión; las descargas anteriores se vuelven a publicar con infra/045 (base de Suite).
--
-- Se aplica antes de instalar el código. Idempotente.

ALTER TABLE consulta.descarga_publica ADD COLUMN IF NOT EXISTS clientecodigo text;
ALTER TABLE consulta.descarga_publica ADD COLUMN IF NOT EXISTS patente text;
ALTER TABLE consulta.descarga_publica ADD COLUMN IF NOT EXISTS cuit_inscripto text;
CREATE INDEX IF NOT EXISTS ix_publica_patente
    ON consulta.descarga_publica (patente, fecha DESC) WHERE patente IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_publica_cuit_inscripto
    ON consulta.descarga_publica (cuit_inscripto) WHERE cuit_inscripto IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_publica_ciu
    ON consulta.descarga_publica (clientecuit, (ltrim(ciu, '0')));
CREATE INDEX IF NOT EXISTS ix_productor_codigos ON fila.productor USING gin (codigos);

-- Rastro de cada consulta hecha con un vínculo abierto: queda el teléfono.
ALTER TABLE consulta.bitacora_consulta ADD COLUMN IF NOT EXISTS telefono text;

-- Cuentas entre las que tiene que elegir quien escribió un CUIT o una patente con varias.
ALTER TABLE consulta.bot_sesion ADD COLUMN IF NOT EXISTS candidatas text[];

CREATE TABLE IF NOT EXISTS consulta.bot_identificacion (
    id bigserial PRIMARY KEY,
    telefono text NOT NULL CHECK (telefono ~ '^[0-9]{8,20}$'),
    por text NOT NULL CHECK (por IN ('cuenta', 'cuit', 'patente')),
    dato text NOT NULL,
    cuentas text[] NOT NULL DEFAULT '{}',
    momento timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bot_identificacion_telefono
    ON consulta.bot_identificacion (telefono, momento DESC);

CREATE TABLE IF NOT EXISTS consulta.bot_vinculo (
    telefono text PRIMARY KEY CHECK (telefono ~ '^[0-9]{8,20}$'),
    clientecuit text NOT NULL,
    codigo text,
    por text NOT NULL CHECK (por IN ('cuenta', 'cuit', 'patente')),
    dato text NOT NULL,
    vinculado_en timestamptz NOT NULL DEFAULT now()
);


-- Busca la cuenta por código («J80158»), CUIT (11 dígitos) o patente («VCT917», «AB123CD»).
-- El dato llega normalizado (mayúsculas, sin espacios ni guiones). Deja el intento anotado.
CREATE OR REPLACE FUNCTION consulta.bot_identificar(
    p_telefono text, p_por text, p_dato text, p_maximo integer DEFAULT 10
) RETURNS TABLE(clientecuit text, codigo text, titular text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = consulta, fila, pg_temp AS $$
DECLARE
    v_fallidos integer;
    v_cuentas text[];
BEGIN
    IF p_telefono IS NULL OR p_telefono !~ '^[0-9]{8,20}$' THEN
        RAISE EXCEPTION 'telefono_invalido' USING ERRCODE = 'P0001';
    END IF;
    IF p_por IS NULL OR p_dato IS NULL
       OR (p_por = 'cuenta' AND p_dato !~ '^[A-Z][0-9]{5}$')
       OR (p_por = 'cuit' AND p_dato !~ '^[0-9]{11}$')
       OR (p_por = 'patente' AND p_dato !~ '^[A-Z0-9]{5,10}$')
       OR p_por NOT IN ('cuenta', 'cuit', 'patente') THEN
        RAISE EXCEPTION 'dato_invalido' USING ERRCODE = 'P0001';
    END IF;
    -- Dos mensajes seguidos del mismo teléfono no se cuentan a la vez.
    PERFORM pg_advisory_xact_lock(hashtext('bot_identificar:' || p_telefono));
    SELECT count(*) INTO v_fallidos FROM consulta.bot_identificacion i
     WHERE i.telefono = p_telefono AND i.cuentas = '{}' AND i.momento > now() - interval '1 hour';
    IF v_fallidos >= greatest(1, least(coalesce(p_maximo, 10), 50)) THEN
        RAISE EXCEPTION 'demasiados_intentos' USING ERRCODE = 'P0001';
    END IF;

    IF p_por = 'cuenta' THEN
        SELECT array_agg(p.clientecuit) INTO v_cuentas FROM fila.productor p
         WHERE p.codigos @> ARRAY[p_dato];
    ELSIF p_por = 'cuit' THEN
        SELECT array_agg(p.clientecuit) INTO v_cuentas FROM fila.productor p
         WHERE regexp_replace(p.clientecuit, '\D', '', 'g') = p_dato
            OR p.clientecuit IN (SELECT d.clientecuit FROM consulta.descarga_publica d
                                  WHERE d.cuit_inscripto = p_dato AND d.clientecuit IS NOT NULL
                                    AND d.fecha > now() - interval '3 years');
    ELSE
        SELECT array_agg(p.clientecuit) INTO v_cuentas FROM fila.productor p
         WHERE p.clientecuit IN (
                SELECT d.clientecuit FROM consulta.descarga_publica d
                 WHERE d.patente = p_dato AND d.clientecuit IS NOT NULL
                   AND d.fecha > now() - interval '1 year'
                UNION
                SELECT v.clientecuit FROM fila.viaje v
                 WHERE upper(regexp_replace(v.patente, '[^A-Za-z0-9]', '', 'g')) = p_dato
                   AND v.clientecuit IS NOT NULL AND v.estado <> 'cancelado'
                   AND v.registrado_en > now() - interval '1 year');
    END IF;

    INSERT INTO consulta.bot_identificacion (telefono, por, dato, cuentas)
    VALUES (p_telefono, p_por, p_dato, coalesce(v_cuentas[1:50], '{}'));

    RETURN QUERY
        SELECT p.clientecuit,
               CASE WHEN p_por = 'cuenta' THEN p_dato
                    ELSE coalesce(p.codigos[1], p.clientecuit) END,
               p.razonsocial
          FROM fila.productor p
         WHERE p.clientecuit = ANY(coalesce(v_cuentas[1:50], '{}'))
         ORDER BY p.razonsocial, p.clientecuit;
END;
$$;

-- Deja el teléfono vinculado a una cuenta que ese mismo teléfono identificó en la última hora.
CREATE OR REPLACE FUNCTION consulta.bot_vincular(
    p_telefono text, p_clientecuit text, p_codigo text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = consulta, pg_temp AS $$
DECLARE v consulta.bot_identificacion;
BEGIN
    SELECT * INTO v FROM consulta.bot_identificacion i
     WHERE i.telefono = p_telefono AND p_clientecuit = ANY(i.cuentas)
       AND i.momento > now() - interval '1 hour'
     ORDER BY i.momento DESC LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'cuenta_no_identificada' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO consulta.bot_vinculo (telefono, clientecuit, codigo, por, dato)
    VALUES (p_telefono, p_clientecuit, left(p_codigo, 20), v.por, v.dato)
    ON CONFLICT (telefono) DO UPDATE SET clientecuit = EXCLUDED.clientecuit,
        codigo = EXCLUDED.codigo, por = EXCLUDED.por, dato = EXCLUDED.dato, vinculado_en = now();
END;
$$;

REVOKE ALL ON FUNCTION consulta.bot_identificar(text, text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION consulta.bot_vincular(text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consulta.bot_identificar(text, text, text, integer) TO consulta_bot;
GRANT EXECUTE ON FUNCTION consulta.bot_vincular(text, text, text) TO consulta_bot;
-- El bot lee y borra el vínculo («Salir»); crearlo sólo se puede con bot_vincular.
GRANT SELECT, DELETE ON consulta.bot_vinculo TO consulta_bot;
-- El publicador de Recepción completa las columnas nuevas (ya tiene INSERT y UPDATE en la tabla).
GRANT SELECT, INSERT, UPDATE ON consulta.descarga_publica TO consulta_publicador;
