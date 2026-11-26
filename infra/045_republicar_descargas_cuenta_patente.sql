-- Base de Suite: vuelve a publicar a la DMZ las descargas de los últimos tres años.
--
-- Desde infra/044 la proyección de la DMZ (consulta.descarga_publica) lleva además la cuenta
-- (CLIENTECODIGO), la patente (CODIGOTRANSPORTE) y el CUIT del inscripto, que el publicador
-- nuevo completa. Las descargas que ya estaban publicadas no los tienen: se marcan para que el
-- worker de Recepción las vuelva a mandar (de a 5000 por vuelta, sin tocar Oracle).
--
-- Se aplica en la base de Suite después de infra/044 (DMZ) y de instalar el publicador nuevo.
-- Se puede volver a correr: desde acá no se sabe cuáles ya tienen los datos nuevos en la DMZ,
-- así que marca todas las de la ventana; publicarlas otra vez no cambia nada.

UPDATE recepcion.descarga SET pendiente_publicar = true
 WHERE NOT pendiente_publicar
   AND (fecha IS NULL OR fecha > now() - interval '3 years')
   AND (clientecodigo IS NOT NULL OR codigotransporte IS NOT NULL OR cuit IS NOT NULL);
