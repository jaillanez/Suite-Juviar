-- DMZ: Gestión administra las tablets de guardia (usuarios de la consola del portón).
--
-- Gestión no escribe fila.guardia directamente: usa estas funciones, que validan los datos,
-- cierran las sesiones abiertas cuando corresponde y dejan quién hizo cada cambio en
-- fila.guardia_evento. Nunca se borra un usuario: se deshabilita.
-- La clave llega ya convertida en hash (pbkdf2, la misma que verifica la fila); Gestión
-- nunca puede leer los hashes. Se aplica antes de instalar el código. Idempotente.

CREATE TABLE IF NOT EXISTS fila.guardia_evento (
    id bigserial PRIMARY KEY,
    usuario text NOT NULL,
    tipo text NOT NULL CHECK (tipo IN ('alta', 'cambio', 'nueva_clave', 'baja', 'reactivada')),
    actor text NOT NULL,
    detalle jsonb,
    momento timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_guardia_evento_usuario ON fila.guardia_evento (usuario, momento DESC);

CREATE OR REPLACE FUNCTION fila._validar_guardia(p_nombre text, p_sede text, p_actor text)
RETURNS void LANGUAGE plpgsql SET search_path = fila, pg_temp AS $$
BEGIN
    IF p_actor IS NULL OR btrim(p_actor) = '' THEN
        RAISE EXCEPTION 'falta quién hace el cambio' USING ERRCODE = 'P0001';
    END IF;
    IF p_nombre IS NULL OR length(btrim(p_nombre)) NOT BETWEEN 3 AND 120 THEN
        RAISE EXCEPTION 'el nombre tiene que tener entre 3 y 120 letras' USING ERRCODE = 'P0001';
    END IF;
    IF p_sede IS NULL OR p_sede !~ '^[a-z0-9_-]{2,30}$' THEN
        RAISE EXCEPTION 'sede inválida' USING ERRCODE = 'P0001';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION fila._cerrar_sesiones_guardia(p_usuario text)
RETURNS void LANGUAGE sql SET search_path = fila, pg_temp AS $$
    UPDATE fila.sesion_guardia SET cerrada_en = now() WHERE usuario = p_usuario AND cerrada_en IS NULL;
$$;

CREATE OR REPLACE FUNCTION fila.crear_guardia(
    p_usuario text, p_nombre text, p_sede text, p_clave_hash text, p_actor text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
BEGIN
    PERFORM fila._validar_guardia(p_nombre, p_sede, p_actor);
    IF p_usuario IS NULL OR p_usuario !~ '^[a-z0-9._-]{3,30}$' THEN
        RAISE EXCEPTION 'usuario inválido: minúsculas, números, punto o guion (3 a 30)' USING ERRCODE = 'P0001';
    END IF;
    IF p_clave_hash IS NULL OR p_clave_hash !~ '^pbkdf2_sha256\$' THEN
        RAISE EXCEPTION 'clave inválida' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM fila.guardia WHERE usuario = p_usuario) THEN
        RAISE EXCEPTION 'ese usuario ya existe' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO fila.guardia (usuario, nombre, sede, clave_hash, creado_por, debe_cambiar_clave)
    VALUES (p_usuario, btrim(p_nombre), p_sede, p_clave_hash, left(p_actor, 100), true);
    INSERT INTO fila.guardia_evento (usuario, tipo, actor, detalle)
    VALUES (p_usuario, 'alta', left(p_actor, 100), jsonb_build_object('nombre', btrim(p_nombre), 'sede', p_sede));
END $$;

CREATE OR REPLACE FUNCTION fila.modificar_guardia(
    p_usuario text, p_nombre text, p_sede text, p_actor text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_antes fila.guardia;
BEGIN
    PERFORM fila._validar_guardia(p_nombre, p_sede, p_actor);
    SELECT * INTO v_antes FROM fila.guardia WHERE usuario = p_usuario FOR UPDATE;
    IF v_antes.usuario IS NULL THEN
        RAISE EXCEPTION 'ese usuario no existe' USING ERRCODE = 'P0001';
    END IF;
    UPDATE fila.guardia SET nombre = btrim(p_nombre), sede = p_sede WHERE usuario = p_usuario;
    -- Una tablet que cambia de sede vuelve a ingresar: la sesión abierta era de la otra sede.
    IF v_antes.sede <> p_sede THEN
        PERFORM fila._cerrar_sesiones_guardia(p_usuario);
    END IF;
    INSERT INTO fila.guardia_evento (usuario, tipo, actor, detalle)
    VALUES (p_usuario, 'cambio', left(p_actor, 100), jsonb_build_object(
        'antes', jsonb_build_object('nombre', v_antes.nombre, 'sede', v_antes.sede),
        'despues', jsonb_build_object('nombre', btrim(p_nombre), 'sede', p_sede)));
END $$;

CREATE OR REPLACE FUNCTION fila.nueva_clave_guardia(p_usuario text, p_clave_hash text, p_actor text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_activo boolean;
BEGIN
    IF p_clave_hash IS NULL OR p_clave_hash !~ '^pbkdf2_sha256\$' THEN
        RAISE EXCEPTION 'clave inválida' USING ERRCODE = 'P0001';
    END IF;
    SELECT activo INTO v_activo FROM fila.guardia WHERE usuario = p_usuario FOR UPDATE;
    IF v_activo IS NULL THEN
        RAISE EXCEPTION 'ese usuario no existe' USING ERRCODE = 'P0001';
    END IF;
    UPDATE fila.guardia SET clave_hash = p_clave_hash, debe_cambiar_clave = true, activo = true
     WHERE usuario = p_usuario;
    PERFORM fila._cerrar_sesiones_guardia(p_usuario);
    INSERT INTO fila.guardia_evento (usuario, tipo, actor)
    VALUES (p_usuario, CASE WHEN v_activo THEN 'nueva_clave' ELSE 'reactivada' END, left(p_actor, 100));
END $$;

CREATE OR REPLACE FUNCTION fila.baja_guardia(p_usuario text, p_actor text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
BEGIN
    UPDATE fila.guardia SET activo = false WHERE usuario = p_usuario AND activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'esa tablet no está activa' USING ERRCODE = 'P0001';
    END IF;
    PERFORM fila._cerrar_sesiones_guardia(p_usuario);
    INSERT INTO fila.guardia_evento (usuario, tipo, actor) VALUES (p_usuario, 'baja', left(p_actor, 100));
END $$;

REVOKE ALL ON FUNCTION fila._validar_guardia(text, text, text), fila._cerrar_sesiones_guardia(text),
    fila.crear_guardia(text, text, text, text, text), fila.modificar_guardia(text, text, text, text),
    fila.nueva_clave_guardia(text, text, text), fila.baja_guardia(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.crear_guardia(text, text, text, text, text),
    fila.modificar_guardia(text, text, text, text), fila.nueva_clave_guardia(text, text, text),
    fila.baja_guardia(text, text) TO gestion_tablero;
GRANT SELECT (usuario, nombre, sede, activo, debe_cambiar_clave, creado_por, creado_en, ultimo_ingreso)
    ON fila.guardia TO gestion_tablero;
GRANT SELECT ON fila.guardia_evento TO gestion_tablero;
