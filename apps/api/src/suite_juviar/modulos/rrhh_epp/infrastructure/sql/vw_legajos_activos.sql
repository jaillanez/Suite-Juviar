/* ===========================================================================
   Vista de solo lectura sobre el maestro de legajos de Nexus.

   Es lo único que el módulo de RRHH/EPP necesita de Nexus. Mientras no exista,
   el sistema lee data/nexus_simulado.yaml, que devuelve estas mismas once
   columnas con estos mismos nombres.

   Qué hay que pedirle al responsable de Nexus:
     1. Crear esta Vista en el servidor de Santa Fe.
     2. Un usuario de base con SELECT sobre la Vista y NADA sobre las tablas.
     3. Confirmar los nombres reales de las tablas y columnas de origen
        (abajo están puestos como hipótesis y seguro no se llaman así).

   Reglas 1 y 2 de la base común: el módulo lee de Nexus y no escribe nunca.
   =========================================================================== */

CREATE OR ALTER VIEW dbo.vw_legajos_activos AS
SELECT
    CAST(e.nro_legajo      AS VARCHAR(20))  AS legajo,
    CAST(e.nombres         AS NVARCHAR(80)) AS nombre,
    CAST(e.apellidos       AS NVARCHAR(80)) AS apellido,
    CAST(e.documento       AS VARCHAR(15))  AS dni,
    CAST(p.codigo          AS VARCHAR(20))  AS puesto_codigo,
    CAST(p.descripcion     AS NVARCHAR(80)) AS puesto,
    CAST(s.codigo          AS VARCHAR(20))  AS sector_codigo,
    CAST(s.descripcion     AS NVARCHAR(80)) AS sector,
    CAST(emp.sigla         AS VARCHAR(20))  AS empresa,        -- ENAV | JUBIAR
    CAST(e.tipo_vinculo    AS VARCHAR(20))  AS tipo_vinculo,   -- PERMANENTE | TEMPORARIO
    CAST(CASE WHEN e.fecha_egreso IS NULL THEN 1 ELSE 0 END AS BIT) AS activo
FROM dbo.empleados       e
JOIN dbo.puestos         p   ON p.id   = e.id_puesto
JOIN dbo.sectores        s   ON s.id   = e.id_sector
JOIN dbo.empresas        emp ON emp.id = e.id_empresa;
GO

/* Permisos: sólo lectura, y sólo sobre la Vista.
   Verificar el permiso conectándose con este usuario e intentando un UPDATE
   sobre dbo.empleados: tiene que fallar. Un GRANT escrito no es un GRANT
   verificado (§6.5 de la base común). */
-- CREATE LOGIN suite_lectura WITH PASSWORD = '...';
-- CREATE USER  suite_lectura FOR LOGIN suite_lectura;
-- GRANT SELECT ON dbo.vw_legajos_activos TO suite_lectura;
-- DENY  SELECT ON dbo.empleados TO suite_lectura;
