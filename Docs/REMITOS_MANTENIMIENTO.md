# Remitos de salida de Mantenimiento

Reunión del 15-11, punto 5: ningún equipo ni herramienta sale de la planta sin un remito
autorizado por el Encargado de Mantenimiento; se controla que todo vuelva.

## Recorrido

1. **Mantenimiento** carga el remito en Gestión → Equipos y activos → Remitos de salida:
   bodega de la que sale, taller o lugar, motivo y lo que lleva. Un equipo etiquetado se carga
   por su código; una herramienta sin etiqueta, describiéndola a mano.
2. **El Encargado de Mantenimiento** (perfil nuevo `ENCARGADO_MANTENIMIENTO`) lo firma:
   - en la pantalla (celular o computadora): queda la firma dibujada en el PDF, o
   - en papel: autoriza en Gestión y firma a mano el remito impreso.
3. Al firmar, el remito se publica en la base de la fila (`infra/041`). **La guardia** de esa
   bodega lo ve en su consola («Remitos de salida»), revisa lo que lleva y toca «Dejar salir».
   Con firma en papel, la consola le recuerda que revise la firma en el remito impreso.
4. Gestión lee la salida (cada minuto y al abrir la lista): cada equipo con código pasa a
   «En taller externo» con su reparación abierta.
5. **Regreso**: la herramienta sin código vuelve con un clic; el equipo, con su costo, la
   empresa a la que va la factura y el sector al que vuelve (también se puede cargar desde la
   ficha del equipo). Cuando vuelve todo, el remito queda cerrado.

Un remito se puede anular mientras no salió; anulado, la guardia ya no lo deja salir.

## WhatsApp

El personal cargado en «Personal en el bot» manda una foto con un texto (por ejemplo
«BOM-0003 sale a Taller Pérez»). Si el mensaje habla de salida, taller, mantenimiento o remito,
el bot lo registra y responde con un número. Una foto sin ninguna palabra ya no entra sola: el bot
pide que diga si es para Mantenimiento, un certificado médico o un pedido de EPP
(ver `RRHH_WHATSAPP.md`). En Gestión aparece en
«Mensajes de WhatsApp». Según Parámetros:

- **Para revisar**: el Encargado arma el remito desde el mensaje o lo descarta.
- **Directo**: el remito se arma solo como borrador (códigos y bodega que aparezcan en el
  texto, más la foto) y el Encargado lo completa y firma.

En los dos casos nada sale sin la firma. La foto se baja por Chattigo con el mismo esquema que
Meta (`GET /{version}/{media_id}` y luego el archivo): hay que confirmarlo cuando estén las
credenciales.

## Parámetros

Gestión → Parámetros → «Remitos de salida de Mantenimiento»:

- Días que algo puede estar afuera antes de marcarlo **demorado** (sin cargar, no se marca).
- Cómo entra lo que llega por WhatsApp (para revisar o directo).

## Instalación

Aplicar `infra/041_remitos_mantenimiento.sql` en la base de la fila antes de instalar el código.
