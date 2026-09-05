# ADR 0003 — HMAC para indexar, cifrado para guardar

**Estado:** aceptado

**Contexto.** El sistema maneja DNI y CUIT de empleados, temporarios de
cosecha, productores y choferes, y tiene que poder buscar por ellos.

**Decisión.** Cada dato personal se guarda en dos columnas: `<campo>_hmac`
(HMAC-SHA256 determinístico, indexado y único) y `<campo>_cif` (AES-256-GCM).
La clave del HMAC vive fuera de la base, inyectada por el orquestador.

**Consecuencias.** Un dump de la base no alcanza para reconstruir los DNI. El
modelo de lectura del bot solo guarda el HMAC del CUIT del productor: le
alcanza para filtrar "lo mío" sin tener nunca el CUIT en claro.
