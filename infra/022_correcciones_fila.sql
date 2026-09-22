-- Permisos que necesita el worker para conciliar con la proyección Oracle.
GRANT USAGE ON SCHEMA consulta TO fila_worker;
GRANT SELECT ON consulta.descarga_publica TO fila_worker;
