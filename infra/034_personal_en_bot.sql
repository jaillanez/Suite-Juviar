-- DMZ: celulares del personal de Juviar-ENAV que el bot reconoce.
--
-- Se cargan a mano desde Gestión (sección «Personal en el bot»): legajo, nombre, empresa
-- y si es «Personal» o «Mando medio». Gestión no escribe la tabla directamente: usa las
-- funciones de abajo, que dejan quién hizo cada cambio. Nunca se borra: la baja es lógica.
--
-- Un celular es de productor o de empleado, nunca de los dos: lo controla la base en las
-- dos tablas (consulta.telefono_productor y consulta.telefono_personal).
-- Se aplica antes de instalar el código. Idempotente.

CREATE TABLE IF NOT EXISTS consulta.telefono_personal (
    telefono text PRIMARY KEY CHECK (telefono ~ '^[0-9]{8,20}$'),
    legajo text NOT NULL CHECK (legajo ~ '^[0-9A-Za-z-]{1,20}$'),
    nombre text NOT NULL CHECK (length(btrim(nombre)) BETWEEN 2 AND 120),
    empresa text NOT NULL CHECK (empresa IN ('ENAV', 'JUBIAR')),
    tipo text NOT NULL CHECK (tipo IN ('personal', 'mando_medio')),
    activo boolean NOT NULL DEFAULT true,
    alta_por text NOT NULL,
    alta_en timestamptz NOT NULL DEFAULT now(),
    actualizado_por text NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_personal_legajo ON consulta.telefono_personal (legajo);

CREATE TABLE IF NOT EXISTS consulta.personal_evento (
    id bigserial PRIMARY KEY,
    telefono text NOT NULL,
    tipo text NOT NULL CHECK (tipo IN ('alta', 'cambio', 'baja')),
    actor text NOT NULL,
    antes jsonb,
    despues jsonb,
    momento timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_personal_evento_telefono ON consulta.personal_evento (telefono, momento DESC);

-- Un celular de productor activo no se puede cargar como personal, y al revés.
CREATE OR REPLACE FUNCTION consulta.exigir_celular_de_un_solo_tipo() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = consulta, pg_temp AS $$
BEGIN
    IF NOT NEW.activo THEN
        RETURN NEW;
    END IF;
    -- Las dos tablas se escriben por caminos distintos (Gestión y el publicador): se
    -- serializa por número para que dos altas simultáneas no pasen ambas el control.
    PERFORM pg_advisory_xact_lock(hashtext('celular:' || NEW.telefono));
    IF TG_TABLE_NAME = 'telefono_personal' AND EXISTS (
        SELECT 1 FROM consulta.telefono_productor WHERE telefono = NEW.telefono AND activo
    ) THEN
        RAISE EXCEPTION 'ese celular ya está cargado como contacto de un productor' USING ERRCODE = 'P0001';
    END IF;
    IF TG_TABLE_NAME = 'telefono_productor' AND EXISTS (
        SELECT 1 FROM consulta.telefono_personal WHERE telefono = NEW.telefono AND activo
    ) THEN
        RAISE EXCEPTION 'ese celular ya está cargado como personal de la empresa' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS tg_personal_un_solo_tipo ON consulta.telefono_personal;
CREATE TRIGGER tg_personal_un_solo_tipo BEFORE INSERT OR UPDATE ON consulta.telefono_personal
    FOR EACH ROW EXECUTE FUNCTION consulta.exigir_celular_de_un_solo_tipo();
DROP TRIGGER IF EXISTS tg_productor_un_solo_tipo ON consulta.telefono_productor;
CREATE TRIGGER tg_productor_un_solo_tipo BEFORE INSERT OR UPDATE ON consulta.telefono_productor
    FOR EACH ROW EXECUTE FUNCTION consulta.exigir_celular_de_un_solo_tipo();

CREATE OR REPLACE FUNCTION consulta.guardar_personal(
    p_telefono text, p_legajo text, p_nombre text, p_empresa text, p_tipo text, p_actor text
) RETURNS consulta.telefono_personal
LANGUAGE plpgsql SECURITY DEFINER SET search_path = consulta, pg_temp AS $$
DECLARE
    v_antes consulta.telefono_personal;
    v consulta.telefono_personal;
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién hace el cambio' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_antes FROM consulta.telefono_personal WHERE telefono = p_telefono FOR UPDATE;
    IF v_antes.activo AND v_antes.legajo <> p_legajo THEN
        RAISE EXCEPTION 'ese celular ya está cargado para %', v_antes.nombre USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO consulta.telefono_personal
        (telefono, legajo, nombre, empresa, tipo, activo, alta_por, actualizado_por)
    VALUES (p_telefono, p_legajo, btrim(p_nombre), p_empresa, p_tipo, true,
            left(p_actor, 100), left(p_actor, 100))
    ON CONFLICT (telefono) DO UPDATE SET
        legajo = EXCLUDED.legajo, nombre = EXCLUDED.nombre, empresa = EXCLUDED.empresa,
        tipo = EXCLUDED.tipo, activo = true,
        actualizado_por = EXCLUDED.actualizado_por, actualizado_en = now()
    RETURNING * INTO v;
    INSERT INTO consulta.personal_evento (telefono, tipo, actor, antes, despues)
    VALUES (p_telefono, CASE WHEN v_antes.activo THEN 'cambio' ELSE 'alta' END, left(p_actor, 100),
            CASE WHEN v_antes.telefono IS NULL THEN NULL ELSE to_jsonb(v_antes) END, to_jsonb(v));
    RETURN v;
END $$;

CREATE OR REPLACE FUNCTION consulta.baja_personal(p_telefono text, p_actor text)
RETURNS consulta.telefono_personal
LANGUAGE plpgsql SECURITY DEFINER SET search_path = consulta, pg_temp AS $$
DECLARE
    v_antes consulta.telefono_personal;
    v consulta.telefono_personal;
BEGIN
    SELECT * INTO v_antes FROM consulta.telefono_personal
     WHERE telefono = p_telefono AND activo FOR UPDATE;
    IF v_antes.telefono IS NULL THEN
        RAISE EXCEPTION 'ese celular no está activo' USING ERRCODE = 'P0001';
    END IF;
    UPDATE consulta.telefono_personal
       SET activo = false, actualizado_por = left(p_actor, 100), actualizado_en = now()
     WHERE telefono = p_telefono
    RETURNING * INTO v;
    INSERT INTO consulta.personal_evento (telefono, tipo, actor, antes, despues)
    VALUES (p_telefono, 'baja', left(p_actor, 100), to_jsonb(v_antes), to_jsonb(v));
    RETURN v;
END $$;

REVOKE ALL ON FUNCTION consulta.guardar_personal(text, text, text, text, text, text),
    consulta.baja_personal(text, text), consulta.exigir_celular_de_un_solo_tipo() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consulta.guardar_personal(text, text, text, text, text, text),
    consulta.baja_personal(text, text) TO gestion_tablero;
GRANT SELECT ON consulta.telefono_personal, consulta.personal_evento TO gestion_tablero;
GRANT SELECT (telefono, nombre, empresa, tipo, activo) ON consulta.telefono_personal TO consulta_bot;
