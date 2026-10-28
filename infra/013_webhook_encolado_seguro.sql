-- El webhook ejecuta una operación cerrada; no accede directamente a la tabla.
CREATE OR REPLACE FUNCTION consulta.encolar_bot(
    p_wamid text,
    p_telefono text,
    p_tipo text,
    p_texto text,
    p_enviado_en timestamptz
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, consulta
AS $$
BEGIN
    INSERT INTO consulta.bot_entrada (wamid, telefono, tipo, texto, enviado_en)
    VALUES (p_wamid, p_telefono, p_tipo, p_texto, p_enviado_en)
    ON CONFLICT (wamid) DO NOTHING;
    RETURN FOUND;
END;
$$;

REVOKE ALL ON FUNCTION consulta.encolar_bot(text, text, text, text, timestamptz)
    FROM PUBLIC;
REVOKE INSERT ON consulta.bot_entrada FROM consulta_webhook;
REVOKE USAGE ON SEQUENCE consulta.bot_entrada_id_seq FROM consulta_webhook;
GRANT EXECUTE ON FUNCTION consulta.encolar_bot(text, text, text, text, timestamptz)
    TO consulta_webhook;
