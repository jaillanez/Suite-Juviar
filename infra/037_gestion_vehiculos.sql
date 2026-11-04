-- DMZ: Recepción elige la patente del camión de los que ya pasaron por la fila.
--
-- Al elegirla, Gestión completa el acoplado, el DNI del último chofer y el productor.
-- No lee el teléfono del chofer. Se aplica antes de instalar el código. Es idempotente.

GRANT SELECT (patente, patente_acoplado, ultimo_chofer_dni, ultimo_chofer_nombre, ultimo_clientecuit,
              actualizado_en)
    ON fila.vehiculo TO gestion_tablero;
