-- Sólo para el entorno local. En producción las contraseñas van por
-- variable de entorno o gestor de secretos, nunca en un archivo del repo.
ALTER ROLE web_sitio  WITH PASSWORD 'sitio_local';
ALTER ROLE web_worker WITH PASSWORD 'worker_local';

-- Cierra el acceso por defecto al esquema public, que PostgreSQL concede
-- a todo rol nuevo. Sin esto, web_sitio puede crear tablas propias.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM web_sitio;
REVOKE ALL ON SCHEMA public FROM web_worker;

-- En un único servidor local los roles son globales al clúster. Estos
-- permisos reproducen el aislamiento que en producción dan los dos motores.
REVOKE CONNECT ON DATABASE juviar_web_local FROM PUBLIC;
GRANT CONNECT ON DATABASE juviar_web_local TO web_sitio, web_worker;
REVOKE CONNECT ON DATABASE juviar_suite_local FROM PUBLIC;
