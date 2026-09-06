-- Roles de mínimo privilegio para los módulos internos de la suite.
-- Son NOLOGIN: el secreto y el LOGIN de cada desplegable se crean fuera del repo.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'suite_rrhh_epp') THEN
        CREATE ROLE suite_rrhh_epp NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'suite_seleccion_rrhh') THEN
        CREATE ROLE suite_seleccion_rrhh NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'suite_capacitacion_rrhh') THEN
        CREATE ROLE suite_capacitacion_rrhh NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'suite_sin_acceso') THEN
        CREATE ROLE suite_sin_acceso NOLOGIN;
    END IF;
END
$$;

REVOKE ALL ON SCHEMA rrhh_epp, seleccion, capacitacion FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA rrhh_epp, seleccion, capacitacion FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA rrhh_epp, seleccion, capacitacion FROM PUBLIC;

GRANT USAGE ON SCHEMA rrhh_epp TO suite_rrhh_epp;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA rrhh_epp TO suite_rrhh_epp;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rrhh_epp TO suite_rrhh_epp;

GRANT USAGE ON SCHEMA seleccion TO suite_seleccion_rrhh;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA seleccion TO suite_seleccion_rrhh;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA seleccion TO suite_seleccion_rrhh;

GRANT USAGE ON SCHEMA capacitacion TO suite_capacitacion_rrhh;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA capacitacion TO suite_capacitacion_rrhh;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA capacitacion TO suite_capacitacion_rrhh;

ALTER DEFAULT PRIVILEGES IN SCHEMA rrhh_epp REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA rrhh_epp GRANT SELECT, INSERT, UPDATE ON TABLES TO suite_rrhh_epp;
ALTER DEFAULT PRIVILEGES IN SCHEMA seleccion REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA seleccion GRANT SELECT, INSERT, UPDATE ON TABLES TO suite_seleccion_rrhh;
ALTER DEFAULT PRIVILEGES IN SCHEMA capacitacion REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA capacitacion GRANT SELECT, INSERT ON TABLES TO suite_capacitacion_rrhh;

-- Habilita SET ROLE al dueño que ejecuta esta migración para la verificación
-- local. En producción la membresía se otorga sólo al LOGIN del desplegable.
GRANT suite_rrhh_epp, suite_seleccion_rrhh, suite_capacitacion_rrhh, suite_sin_acceso
    TO CURRENT_USER;

DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO suite_rrhh_epp, suite_seleccion_rrhh, suite_capacitacion_rrhh',
        current_database()
    );
END
$$;
