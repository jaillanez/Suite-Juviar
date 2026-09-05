# ADR 0002 — Inmutabilidad en el motor, no en el código

**Estado:** aceptado

**Contexto.** La evidencia que pediría una inspección de la SRT o del INV vale
por su integridad. Una bitácora que el código "no modifica" es una bitácora que
alguien puede modificar con un `UPDATE` en una consola.

**Decisión.** Dos roles de base: `sj_owner` migra, `sj_app` corre la aplicación
sin DDL. Al rol de aplicación se le revocan `UPDATE` y `DELETE` sobre el schema
`bitacora` y sobre `plataforma.documento_firmado`.

**Consecuencias.** Corregir un asiento es imposible; solo se agrega otro. Las
correcciones del negocio se modelan como contra-asientos (contra-romaneo,
documento que anula a otro), que además es lo que una auditoría espera ver.
