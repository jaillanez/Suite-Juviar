-- DMZ: lo que Gestión necesita leer para Recepción y para el calendario de turnos.
--
-- * Recepción elige el productor de la lista real (fila.productor) y puede tomar un camión
--   de la fila con su CUIT, acoplado y chofer: el operador de báscula los necesita para abrir
--   el romaneo. Sigue sin leer el ticket ni el teléfono del chofer.
-- * Calendario: lectura de turnos y capacidad por sede.
-- Se aplica antes de instalar el código. Es idempotente.

GRANT SELECT ON fila.productor TO gestion_tablero;
GRANT SELECT (id, clientecuit, patente_acoplado, chofer_dni, chofer_nombre)
    ON fila.viaje TO gestion_tablero;
GRANT SELECT ON fila.turno, fila.capacidad TO gestion_tablero;
